"""Read local agent metadata; send only status snapshots to Moyu Whistle."""
from __future__ import annotations

import argparse
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
from datetime import datetime
from urllib.request import Request, build_opener, ProxyHandler


def codex_hook_key(value):
    tool, inputs = value.get("tool_name"), value.get("tool_input")
    # Approval-only descriptions are not part of Bash/apply_patch identity.
    # MCP arguments, including fields named description, remain significant.
    if tool in ("Bash", "apply_patch") and isinstance(inputs, dict):
        command = inputs.get("command")
        if isinstance(command, str):
            inputs = {"command": command}
    return "v2:" + hashlib.sha256(json.dumps([tool, inputs], sort_keys=True).encode()).hexdigest()


def record_codex_hook(home, value):
    """Observe only: callers must never print an approval decision."""
    kind = value.get("hook_event_name")
    if kind not in ("PermissionRequest", "PostToolUse", "UserPromptSubmit", "Stop", "Interrupt", "SessionEnd"):
        return
    sid, turn = value.get("session_id"), value.get("turn_id", "")
    if not isinstance(sid, str) or not sid or len(sid) > 128 or not isinstance(turn, str):
        return
    # Digests correlate callbacks without persisting commands or approval reasons.
    key = codex_hook_key(value)
    legacy_key = hashlib.sha256(json.dumps([value.get("tool_name"), value.get("tool_input")],
                                          sort_keys=True).encode()).hexdigest()
    path = Path(home)/"moyu-whistle-hooks.sqlite3"
    with closing(sqlite3.connect(path, timeout=0.5)) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS pending (session TEXT, turn TEXT, request TEXT, created REAL, PRIMARY KEY(session,turn,request))")
        if "occurrences" not in {row[1] for row in conn.execute("PRAGMA table_info(pending)")}:
            # Serialize first-use migration across concurrent command hooks.
            conn.execute("BEGIN IMMEDIATE")
            if "occurrences" not in {row[1] for row in conn.execute("PRAGMA table_info(pending)")}:
                conn.execute("ALTER TABLE pending ADD COLUMN occurrences INTEGER NOT NULL DEFAULT 1")
        conn.execute("CREATE TABLE IF NOT EXISTS hook_receipts (session TEXT, event TEXT, received REAL, matched INTEGER, PRIMARY KEY(session,event))")
        matched = None
        if kind == "PermissionRequest":
            conn.execute("INSERT INTO pending (session,turn,request,created,occurrences) VALUES (?,?,?,?,1) "
                         "ON CONFLICT(session,turn,request) DO UPDATE SET "
                         "created=excluded.created, occurrences=pending.occurrences+1", (sid,turn,key,time.time()))
        elif kind == "PostToolUse":
            # Consume one request, not every parallel invocation of the same command.
            for candidate in (key, legacy_key):
                cursor = conn.execute("UPDATE pending SET occurrences=occurrences-1 "
                                      "WHERE session=? AND turn=? AND request=?", (sid,turn,candidate))
                if cursor.rowcount:
                    conn.execute("DELETE FROM pending WHERE session=? AND turn=? AND request=? AND occurrences<=0",
                                 (sid,turn,candidate))
                    matched = 1
                    break
            else:
                matched = 0
        else:
            if kind in ("UserPromptSubmit", "SessionEnd"):
                conn.execute("DELETE FROM pending WHERE session=?", (sid,))
            else:
                conn.execute("DELETE FROM pending WHERE session=? AND turn=?", (sid,turn))
        conn.execute("INSERT OR REPLACE INTO hook_receipts VALUES (?,?,?,?)", (sid,kind,time.time(),matched))
        conn.execute("DELETE FROM hook_receipts WHERE rowid NOT IN "
                     "(SELECT rowid FROM hook_receipts ORDER BY received DESC, rowid DESC LIMIT 256)")


def apply_codex_hooks(home, agents):
    # Context is collector-internal; do not extend the public snapshot payload.
    contexts = [agent.pop("_approval_context", {}) for agent in agents]
    path = Path(home)/"moyu-whistle-hooks.sqlite3"
    if not path.exists():
        return agents
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True, timeout=0.2)) as conn:
            for agent, context in zip(agents, contexts):
                if agent.get("agent_type") != "codex" or agent.get("presence") != "open":
                    continue
                rows = conn.execute("SELECT turn,created FROM pending WHERE session=?",
                                    (agent["session_id"],)).fetchall()
                pending = []
                for turn, created in rows:
                    if context.get("turn_id"):
                        if turn != context["turn_id"]:
                            continue
                        # PermissionRequest precedes the reviewer decision. It is
                        # not evidence of a human prompt when review is automatic.
                        if context.get("reviewer") == "auto_review" or context.get("policy") == "never":
                            continue
                    if created and created >= agent.get("last_activity", 0):
                        pending.append(created)
                if pending:
                    agent.update(event="waiting", status_known=True, evidence="approval hook",
                                 message="Approval requested; resolution not yet observed",
                                 last_activity=max(pending))
    except sqlite3.Error:
        pass
    return agents


def json_file(path):
    try:
        with path.open("rb") as stream:
            content = stream.read(65537)
        if len(content) > 65536:
            return {}
        value = json.loads(content)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def open_codex_sessions(home):
    """lsof proves a writer holds the file; a leftover lock file does not."""
    if os.name == "nt":
        return None
    try:
        result = subprocess.run(
            ["lsof", "-n", "-Fpn", "+D", str(home / "thread-writer-locks")],
            capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode not in (0, 1) or result.stderr.strip():
        return None
    sessions = {}
    pid = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and line.endswith(".lock"):
            session = Path(line[1:]).stem
            if not session.startswith("."):
                sessions[session] = pid
    return sessions


def process_cwd(pid):
    try:
        if Path("/proc").exists():
            return str(Path(f"/proc/{pid}/cwd").resolve(strict=True))
        result = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                                capture_output=True, text=True, timeout=3)
        return next((line[1:] for line in result.stdout.splitlines() if line.startswith("n")), "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def is_cli(pid):
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "args="],
                                capture_output=True, text=True, timeout=3)
        args = result.stdout.strip().split()
        return bool(args) and Path(args[0]).name == "codex" and "app-server" not in args
    except (OSError, subprocess.TimeoutExpired):
        return False


def codex_client(originator=None, cli_process=False):
    """Only classify observed identifiers; source=vscode also occurs in desktop."""
    if cli_process:
        return "terminal"
    if originator == "codex_work_desktop":
        return "desktop"
    if originator == "codex-tui":
        return "terminal"
    return "unknown"


class LogReader:
    def __init__(self):
        self.cache = {}

    def read(self, path):
        stat = path.stat()
        previous = self.cache.get(path)
        fingerprint = (stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino)
        if previous and previous[0] == fingerprint:
            return dict(previous[1])
        continuing = (previous is not None and stat.st_size > previous[0][0]
                      and fingerprint[2:] == previous[0][2:])
        data = dict(previous[1]) if continuing else {
            "event": "idle", "status_known": False, "message": "Status unknown",
            "last_activity": 0}
        active_turn = previous[3] if continuing else None
        # Incremental read preserves task_started across arbitrarily long turns.
        # Store only extracted metadata, never transcript text.
        with path.open("rb") as stream:
            first = stream.readline()
            try:
                first_row = json.loads(first)
                meta = first_row.get("payload", {}) if isinstance(first_row, dict) else {}
                if not isinstance(meta, dict):
                    meta = {}
            except ValueError:
                meta = {}
            if not continuing:
                data.update(session_id=meta.get("id", ""), cwd=meta.get("cwd", ""),
                            subagent=isinstance(meta.get("source"), dict),
                            client_type=codex_client(meta.get("originator")))
            if continuing:
                stream.seek(previous[2])
            offset = stream.tell()
            while True:
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    break
                offset = stream.tell()
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                payload = row.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                if row.get("type") == "turn_context":
                    if isinstance(payload.get("cwd"), str):
                        data["cwd"] = payload["cwd"]
                    turn = payload.get("turn_id")
                    if isinstance(turn, str) and turn and (not active_turn or turn == active_turn):
                        reviewer = payload.get("approvals_reviewer")
                        policy = payload.get("approval_policy")
                        data["_approval_context"] = {
                            "turn_id": turn,
                            "reviewer": reviewer if reviewer in ("auto_review", "user") else None,
                            "policy": policy if policy in ("never", "on-request", "untrusted", "on-failure") else None,
                        }
                if row.get("type") != "event_msg":
                    continue
                kind = payload.get("type")
                if not isinstance(kind, str):
                    continue
                # Optional async questions do not block execution or override turn completion.
                state = {"task_started": "working", "task_complete": "done",
                         "turn_aborted": "idle"}.get(kind)
                if state:
                    turn = payload.get("turn_id")
                    turn = turn if isinstance(turn, str) and turn else None
                    # A delayed terminal event must not end a newer known turn.
                    if kind != "task_started" and active_turn and turn and turn != active_turn:
                        continue
                    if kind == "task_started":
                        active_turn = turn
                        if data.get("_approval_context", {}).get("turn_id") != turn:
                            data.pop("_approval_context", None)
                    data.update(event=state, status_known=True,
                                message={"working": "Task started", "done": "Turn completed",
                                         "idle": "Turn interrupted"}[state],
                                last_activity=timestamp(row.get("timestamp")) or stat.st_mtime)
        self.cache[path] = (fingerprint, data, offset, active_turn)
        return dict(data)


class Collector:
    def __init__(self, codex_home, claude_home, server, recent_seconds=3600, metadata_only=False):
        self.codex_home, self.claude_home = Path(codex_home), Path(claude_home)
        self.server, self.recent_seconds = server, recent_seconds
        self.reader = LogReader()
        self.metadata_only = metadata_only

    def minimal_scan(self):
        agents = []
        opened = open_codex_sessions(self.codex_home) or {}
        sources = {}
        databases = sorted(self.codex_home.glob("state_*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
        if databases and opened:
            try:
                with closing(sqlite3.connect(databases[0].resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)) as conn:
                    marks = ",".join("?" for _ in opened)
                    sources = dict(conn.execute(f"SELECT id, source FROM threads WHERE id IN ({marks})", list(opened)))
            except sqlite3.Error:
                pass
        cli = {pid: is_cli(pid) for pid in set(opened.values())}
        for sid, pid in opened.items():
            if sources.get(sid) not in ("cli", "vscode", "app-server") and not cli.get(pid):
                continue
            agents.append(dict(session_id=sid, agent_type="codex", event="idle", status_known=False,
                               client_type=codex_client(cli_process=cli.get(pid, False)),
                               message="Open; task status unavailable in metadata-only mode",
                               last_activity=0, evidence="session metadata", presence="open"))
        for path in (self.claude_home / "sessions").glob("*.json"):
            data = json_file(path)
            if not process_alive(data.get("pid")) or not data.get("sessionId"):
                continue
            state = {"working": "working", "running": "working", "busy": "working", "waiting": "waiting",
                     "idle": "idle", "error": "error", "done": "done"}.get(data.get("status"))
            agents.append(dict(session_id=data["sessionId"], agent_type="claude-code", event=state or "idle",
                               status_known=state is not None, message=state or "Status unknown",
                               last_activity=float(data.get("statusUpdatedAt", 0)) / 1000,
                               evidence="session status", presence="open"))
        for row in agents:
            row.update(server=self.server, project=row["agent_type"], cwd="",
                       agent_key=f"{self.server}:{row['agent_type']}:{row['session_id']}")
        return apply_codex_hooks(self.codex_home, agents)

    def scan(self):
        if self.metadata_only:
            return self.minimal_scan()
        agents = []
        observed = open_codex_sessions(self.codex_home)
        opened = observed or {}
        cli_pids = {pid for pid in set(opened.values()) if is_cli(pid)}
        cli_sessions = {sid for sid, pid in opened.items() if pid in cli_pids}
        matched = set()
        now = time.time()
        paths = list((self.codex_home / "sessions").rglob("*.jsonl"))
        for path in sorted(paths, key=lambda p: p.stat().st_mtime):
            try:
                if now - path.stat().st_mtime > self.recent_seconds:
                    # An open CLI can be idle for a long time.
                    if not any(sid in path.name for sid in cli_sessions):
                        continue
                data = self.reader.read(path)
            except OSError:
                continue
            sid = data.get("session_id")
            if not sid or data.pop("subagent", False):
                continue
            if observed is not None and sid not in opened:
                continue
            matched.add(sid)
            if sid in cli_sessions:
                data["client_type"] = "terminal"
            data.update(agent_type="codex", evidence="session log",
                        presence="open" if sid in opened else "recent session")
            agents.append(data)
        for sid, pid in opened.items():
            if sid in matched or sid not in cli_sessions:
                continue
            # Locks belonging to known internal subagents must not become fallback rows.
            if any(sid in p.name for p in self.reader.cache):
                continue
            agents.append(dict(session_id=sid, cwd=process_cwd(pid), agent_type="codex",
                               client_type="terminal",
                               event="idle", status_known=False, message="Open; no task event yet",
                               last_activity=0, evidence="writer lock", presence="open"))
        for path in (self.claude_home / "sessions").glob("*.json"):
            data = json_file(path)
            if not process_alive(data.get("pid")) or not data.get("sessionId"):
                continue
            raw = data.get("status")
            state = {"working": "working", "running": "working", "busy": "working",
                     "waiting": "waiting", "idle": "idle", "error": "error",
                     "done": "done"}.get(raw)
            agents.append(dict(session_id=data["sessionId"], cwd=data.get("cwd", ""),
                               agent_type="claude-code", event=state or "idle",
                               status_known=state is not None,
                               message="Waiting for input" if state == "waiting" else (state or "Status unknown"),
                               last_activity=float(data.get("statusUpdatedAt", 0)) / 1000,
                               evidence="session status", presence="open"))
        deduped = {(data["agent_type"], data["session_id"]): data for data in agents}
        for data in deduped.values():
            data.update(server=self.server, project=Path(data["cwd"]).name or "unknown",
                        agent_key=f"{self.server}:{data['agent_type']}:{data['session_id']}")
        return apply_codex_hooks(self.codex_home, list(deduped.values()))


def publish(url, server, agents):
    body = json.dumps({"server": server, "agents": agents}).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    # Loopback SSH forwarding must not go through an HTTP proxy.
    with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:17321/api/collectors")
    parser.add_argument("--server", default=socket.gethostname())
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--claude-home", default=os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--snapshot", action="store_true", help="Print one JSON snapshot for SSH polling; do not POST")
    parser.add_argument("--hook", action="store_true", help="Read a Codex hook from stdin; never emit a decision")
    privacy = parser.add_mutually_exclusive_group()
    privacy.add_argument("--metadata-only", dest="metadata_only", action="store_true", default=True, help="Do not read conversation logs or send project paths (default)")
    privacy.add_argument("--allow-logs", dest="metadata_only", action="store_false", help="Explicitly allow the legacy transcript-reading adapter")
    args = parser.parse_args()
    if args.hook:
        import sys
        try:
            raw = sys.stdin.buffer.read(1_000_001)
            if len(raw) <= 1_000_000:
                value = json.loads(raw)
                if isinstance(value, dict):
                    record_codex_hook(args.codex_home, value)
        except (OSError, ValueError, sqlite3.Error):
            pass
        return
    collector = Collector(args.codex_home, args.claude_home, args.server, metadata_only=args.metadata_only)
    if args.snapshot:
        print(json.dumps(collector.scan()))
        return
    while True:
        try:
            agents = collector.scan()
            publish(args.url, args.server, agents)
            print(f"{args.server}: {len(agents)} real sessions", flush=True)
        except (OSError, ValueError) as exc:
            print(f"Collector unavailable: {type(exc).__name__}", flush=True)
            if args.once:
                raise SystemExit(1)
        if args.once:
            break
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
