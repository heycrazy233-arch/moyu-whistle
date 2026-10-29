# Architecture and API

start.py selects the launcher. desktop/server.py exposes a loopback API through
FastAPI or the standard library. settings.py owns scheduling, SSH and backoff.
remote/collector.py extracts metadata and optional lifecycle log evidence.
database.py owns SQLite; frontends never access its tables directly.
floating/alerts.py deduplicates native reminders. Guada is presentation, not evidence.

- GET /health: ok, service=moyu-whistle, version.
- GET /api/agents: snapshots with agent_key, session_id, agent_type, server,
  project, event, timestamp, status_known, evidence, presence, last_activity,
  collector_online, collection_paused, client_type.
- GET/POST /api/settings: validated preferences and source health.
- POST /api/collectors: {server, agents}, replaces one source snapshot.
- GET/POST /api/events: legacy manual history, not collector history.

Four visible states: working, waiting, error, idle. Input done maps to idle.
Collection uncertainty is separate from state. Respect status_known,
collector_online and collection_paused; never infer progress from stale data.
Fields added to the API must be optional. Keep collector.py standalone for SSH.
Hooks must not return approval decisions. Classification does not use a model.

Tests do not prove real integration. Verify human approval, execution, rejection,
interrupt and reconnect for each OS/version. Async question-answer correlation
and immediate approval-to-execution transitions remain incomplete.
