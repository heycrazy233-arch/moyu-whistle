"""Read local agent metadata; send only status snapshots to Agent Dock."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time
from datetime import datetime
from urllib.request import Request, build_opener, ProxyHandler


def json_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
        return {}
    try:
        result = subprocess.run(
            ["lsof", "-n", "-Fpn", "+D", str(home / "thread-writer-locks")],
            capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
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


class LogReader:
    def __init__(self):
        self.cache = {}

    def read(self, path):
        stat = path.stat()
        previous = self.cache.get(path)
        if previous and previous[0] == (stat.st_size, stat.st_mtime_ns):
            return dict(previous[1])
        continuing = previous is not None and stat.st_size >= previous[0][0]
        data = dict(previous[1]) if continuing else {
            "event": "idle", "status_known": False, "message": "Status unknown",
            "last_activity": stat.st_mtime}
        # Incremental read preserves task_started across arbitrarily long turns.
        # Store only extracted metadata, never transcript text.
        with path.open("rb") as stream:
            first = stream.readline()
            try:
                meta = json.loads(first).get("payload", {})
            except ValueError:
                meta = {}
            if not continuing:
                data.update(session_id=meta.get("id", ""), cwd=meta.get("cwd", ""),
                            subagent=isinstance(meta.get("source"), dict))
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
                payload = row.get("payload", {})
                if row.get("type") == "turn_context":
                    data["cwd"] = payload.get("cwd", data["cwd"])
                if row.get("type") != "event_msg":
                    continue
                state = {"task_started": "working", "task_complete": "done",
                         "turn_aborted": "idle"}.get(payload.get("type"))
                if state:
                    data.update(event=state, status_known=True,
                                message={"working": "Task started", "done": "Turn completed",
                                         "idle": "Turn interrupted"}[state],
                                last_activity=timestamp(row.get("timestamp")) or stat.st_mtime)
        self.cache[path] = ((stat.st_size, stat.st_mtime_ns), data, offset)
        return dict(data)


class Collector:
    def __init__(self, codex_home, claude_home, server, recent_seconds=3600, metadata_only=False):
        self.codex_home, self.claude_home = Path(codex_home), Path(claude_home)
        self.server, self.recent_seconds = server, recent_seconds
        self.reader = LogReader()
        self.metadata_only = metadata_only

    def minimal_scan(self):
        agents = []
        opened = open_codex_sessions(self.codex_home)
        sources = {}
        databases = sorted(self.codex_home.glob("state_*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
        if databases and opened:
            try:
                with sqlite3.connect(databases[0].resolve().as_uri() + "?mode=ro", uri=True) as conn:
                    marks = ",".join("?" for _ in opened)
                    sources = dict(conn.execute(f"SELECT id, source FROM threads WHERE id IN ({marks})", list(opened)))
            except sqlite3.Error:
                pass
        cli = {pid: is_cli(pid) for pid in set(opened.values())}
        for sid, pid in opened.items():
            if sources.get(sid) not in ("cli", "vscode", "app-server") and not cli.get(pid):
                continue
            agents.append(dict(session_id=sid, agent_type="codex", event="idle", status_known=False,
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
        return agents

    def scan(self):
        if self.metadata_only:
            return self.minimal_scan()
        agents = []
        opened = open_codex_sessions(self.codex_home)
        cli_sessions = {sid for sid, pid in opened.items() if is_cli(pid)}
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
            matched.add(sid)
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
        return list(deduped.values())


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
    parser.add_argument("--interval", type=float, default=3)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--snapshot", action="store_true", help="Print one JSON snapshot for SSH polling; do not POST")
    parser.add_argument("--metadata-only", action="store_true", help="Do not read conversation logs or send project paths")
    args = parser.parse_args()
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
