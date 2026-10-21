# Real agent connections

## Browser settings

Open **设置 · 采集与 SSH** on the dashboard. Save applies to the running
`desktop/server.py --collect` service. Preferences are local, beside the database
as `work/agent-dock.settings.json` (ignored by Git).

- Automatic collection toggle; interval 5–3600 seconds, default 5.
- Optional daily time window using the dashboard computer's system timezone;
  start inclusive, end exclusive, overnight windows supported. Uncheck for all day.
- Up to eight independently enabled SSH profiles: unique name, host/SSH alias,
  login port (e.g. 2222), and installed remote Python script path.
- Metadata-only is the default. Codex writer locks and read-only session ID/source
  metadata identify open sessions; no transcript files or project paths are read.
  Task states remain Unknown for Codex in this mode. Claude session status is read.
  Windows lacks writer-lock discovery, so metadata-only Codex discovery is not yet supported.
The explicit compatibility checkbox re-enables the older log adapter described below.

Managed SSH profiles **pull snapshots through authenticated SSH**, so they require
no reverse forwarding or remote HTTP listener. Run once from your terminal to
establish normal host trust and key authentication, then copy the current script:

```sh
ssh -p 2222 user@your-server
scp -P 2222 remote/collector.py user@your-server:agent-dock-collector.py
```

Set the profile host to `user@your-server`, port to `2222`, script to
`agent-dock-collector.py`, enable it and save. Use the account that owns the agents.
The remote host currently must have a POSIX shell and Python 3.9+.
BatchMode forbids password prompts; StrictHostKeyChecking stays enabled.
Each poll launches one SSH call and a one-shot collector, bounded by a 12-second
timeout. Each source has a separate worker and cannot overlap its own polls.
The next poll occurs one interval after the prior one completes. On slow links
choose 30–60 seconds to reduce SSH setup overhead. No automatic uploads occur.
Failed polls back off exponentially (10, 20, 40 seconds at the default interval),
up to 300 seconds or the configured interval if longer. Success or changed
settings reset backoff. SSH output is capped at 1 MB while reading, stderr is
discarded, and timed-out/oversized processes are killed and reaped. Local status
JSON files are capped at 64 KiB. SQLite connections are explicitly closed after
each operation; metadata queries have a 0.5-second lock timeout.

Paused schedules stop new polls; an already running poll may finish within its
timeout, but its result is discarded after settings or schedule changes. Disabled
or removed profiles are not polled; their retained snapshots display Paused.
The browser refreshes stored snapshots every two seconds, independently of polling.
The settings pane shows source errors and latest wall-clock collection duration.
It never displays SSH stderr, which may contain private system information.

Settings API rejects foreign origins and Host headers. Keep the server bound to
loopback. Remote profiles execute only the installed collector path with validated
arguments; no password/key contents are stored in the settings.

The manual reverse-tunnel workflow below remains available but is separately
managed: the web schedule does not control collectors you launch yourself.
Do not use manual and managed collection for the same server simultaneously.

## Local Mac, Windows or Linux

From the repository, start the dashboard and collector together:

```sh
python3 desktop/server.py --collect
```

On Windows use `py desktop/server.py --collect`. Open http://127.0.0.1:17321/.
No PySide6, FastAPI or extra Python packages are required for this mode.

Only with explicit `--allow-logs`, the collector observes Codex logs under `CODEX_HOME` (default `~/.codex`)
and Claude session status files under `CLAUDE_CONFIG_DIR` (default `~/.claude`).
It reports existing sessions without restarting the agents or changing their settings.
Only identifiers, directories, timestamps and status metadata go to the dashboard.
Prompts, answers, tool arguments and code are not sent or stored by the collector.

Codex logs are an internal, version-dependent format, not a stable public API.
The reader recognizes task_started, task_complete and turn_aborted. Other states,
including approval waits, are not reliably available from this adapter yet.
Working means the last observed task event was task_started, not a claim of current CPU activity.
Subagent logs are excluded. Recent sessions (one hour) are included even after a terminal closes;
the presence label and activity time distinguish them from confirmed open sessions.
On macOS/Linux with lsof and ps, open Codex writer locks also discover CLI sessions
before their first task. On Windows, Codex discovery requires a written session log.
Multiple rollouts for the same session are deduplicated by latest file modification time.

Claude Code must provide `sessions/*.json` with pid, sessionId and status fields.
This Mac's installed version does. Versions without those files need a future hook adapter;
they are not silently inferred from transcript activity. Process checks are read-only.

Unknown is used when a session is found without a recognized task state.
Offline means the collector has not reported for 30 seconds. The last activity
timestamp remains visible. A connected collector does not prove every remote agent is working.

## Remote agents over SSH

Keep the local dashboard running. In another local terminal:

```sh
python3 remote/ssh_tunnel.py user@your-server
```

This uses your SSH client/config/keys and forwards the remote loopback port 17322
to local port 17321. It does not change SSH settings or disable host verification.
Forwarding failure exits; connection loss is detected with SSH keepalives.
Reconnect by running the command again. If a remote port is occupied, select another
with `--remote-port` and use the matching URL below.

Copy the standalone collector to that server (replace the destination):

```sh
scp remote/collector.py user@your-server:agent-dock-collector.py
```

In your SSH session, run as the same remote user who runs the agents:

```sh
python3 agent-dock-collector.py --server compute-a --url http://127.0.0.1:17322/api/collectors
```

Use a unique `--server` label for each machine/user. One collector per label;
each heartbeat replaces that label's snapshot and preserves other machines.
Failed sends are retried on the next scan. Current state is recovered on reconnect;
intermediate transitions during a disconnection are not replayed.
You can override --codex-home and --claude-home for custom installations.

The API is intended for a trusted single-user machine. It is unauthenticated and
must remain bound to loopback. Do not expose it to a LAN or public address.
Remote loopback is also accessible to other users on a shared server; token
authentication is needed before use on an untrusted shared server.

This is a current-status integration, not an event-history recorder. Collector
heartbeats update SQLite snapshots, not the old manual `/api/events` history.
The SSH command and collector HTTP protocol are locally tested; a real remote
server and a Windows machine have not yet been tested.

## Resource verification

Local macOS measurement on 2026-10-21, metadata-only, six scans spaced five
seconds apart: 7 sessions, 76-117 ms wall time per scan, 0.594 CPU seconds
including child processes over 30 seconds (about 2% of one CPU core).
This is a short collector sample, not a full-service memory/leak soak test or
a Windows/SSH benchmark. SSH still opens a new connection per successful poll.
The CI matrix covers Python 3.11/3.13 on macOS, Windows and Linux; unit tests
cannot establish compatibility with every installed agent version.
Standalone collectors now also default to metadata-only; update remote scripts
before enabling the optional legacy log mode with `--allow-logs`.
