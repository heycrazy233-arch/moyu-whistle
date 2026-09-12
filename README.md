# Vibe Island Win V0.1

Windows-first, offline-first status island for coding agents running across local and remote servers.

Agent Dock is the internal prototype name for the status center inside this project.

This prototype focuses on the local desktop surface and a fake remote event sender. SSH tunnels,
Claude Code hooks, Codex hooks, and tmux jump are intentionally left as the next integration layer.

## What Works Now

- Local status API on `127.0.0.1:17321`
- SQLite event history
- Five-state agent model: `idle`, `working`, `waiting`, `error`, `done`
- Fake remote event sender
- PySide6 desktop UI when PySide6 is installed
- Console UI fallback when desktop dependencies are not installed

## Structure

```text
Vibe_Island_Win/
├── desktop/
│   ├── app.py
│   ├── cli_ui.py
│   ├── database.py
│   ├── launcher.py
│   ├── server.py
│   ├── state.py
│   └── ui.py
├── remote/
│   ├── bridge.py
│   ├── config.example.json
│   └── fake_event_sender.py
├── requirements.txt
└── README.md
```

## Run

With only Python available:

```bash
python3 desktop/launcher.py --console
```

In another terminal:

```bash
python3 remote/fake_event_sender.py --once
curl http://127.0.0.1:17321/api/agents
```

With target desktop dependencies installed:

```bash
pip install -r requirements.txt
python3 desktop/launcher.py
```

## API

Health:

```text
GET /health
```

Current agent snapshots:

```text
GET /api/agents
```

Recent event history:

```text
GET /api/events?limit=50
```

Receive a remote event:

```text
POST /api/events
Content-Type: application/json
```

Example:

```json
{
  "event": "working",
  "agent_type": "claude-code",
  "session_id": "sabr-01",
  "server": "compute01",
  "project": "sabr",
  "cwd": "/home/me/sabr",
  "tmux_session": "sabr-01",
  "message": "Optimizing cache path"
}
```

## Next

- SSH tunnel profile manager
- Claude Code hook scripts
- Codex hook adapter
- tmux jump actions from the UI
- Windows packaging

## Publish

If GitHub CLI is unavailable, this repo includes a token-based publisher:

```bash
GITHUB_TOKEN=... python3 scripts/publish_github.py --name Vibe_Island_Win
```

Add `--public` if the GitHub repo should be public. By default it creates a private repo.
