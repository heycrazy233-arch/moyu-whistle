# Real agent connections

## Local Mac, Windows or Linux

From the repository, start the dashboard and collector together:

```sh
python3 desktop/server.py --collect
```

On Windows use `py desktop/server.py --collect`. Open http://127.0.0.1:17321/.
No PySide6, FastAPI or extra Python packages are required for this mode.

The collector observes Codex logs under `CODEX_HOME` (default `~/.codex`)
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
