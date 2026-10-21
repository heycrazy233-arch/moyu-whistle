from __future__ import annotations

import sqlite3
import json
import time
from pathlib import Path
from threading import Lock
from typing import Any

from state import AgentEvent


class AgentStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS collectors (server TEXT PRIMARY KEY, received REAL NOT NULL, payload TEXT NOT NULL)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_key TEXT NOT NULL,
                    event TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    server TEXT NOT NULL,
                    project TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    tmux_session TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_snapshots (
                    agent_key TEXT PRIMARY KEY,
                    event TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    server TEXT NOT NULL,
                    project TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    tmux_session TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
                """
            )

    def record_event(self, event: AgentEvent) -> dict[str, Any]:
        row = event.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (
                    agent_key, event, agent_type, session_id, server, project,
                    cwd, tmux_session, message, timestamp
                ) VALUES (
                    :agent_key, :event, :agent_type, :session_id, :server, :project,
                    :cwd, :tmux_session, :message, :timestamp
                )
                """,
                row,
            )
            conn.execute(
                """
                INSERT INTO agent_snapshots (
                    agent_key, event, agent_type, session_id, server, project,
                    cwd, tmux_session, message, timestamp
                ) VALUES (
                    :agent_key, :event, :agent_type, :session_id, :server, :project,
                    :cwd, :tmux_session, :message, :timestamp
                )
                ON CONFLICT(agent_key) DO UPDATE SET
                    event = excluded.event,
                    agent_type = excluded.agent_type,
                    session_id = excluded.session_id,
                    server = excluded.server,
                    project = excluded.project,
                    cwd = excluded.cwd,
                    tmux_session = excluded.tmux_session,
                    message = excluded.message,
                    timestamp = excluded.timestamp
                """,
                row,
            )
        return row

    def list_agents(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_snapshots ORDER BY server, project, session_id"
            ).fetchall()
            collectors = conn.execute("SELECT * FROM collectors").fetchall()
        result = [dict(row) for row in rows]
        for collector in collectors:
            for agent in json.loads(collector["payload"]):
                agent["collector_online"] = time.time() - collector["received"] < 30
                agent["received_at"] = collector["received"]
                result.append(agent)
        return result

    def record_collector(self, server: str, agents: list) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO collectors VALUES (?, ?, ?) ON CONFLICT(server) DO UPDATE SET received=excluded.received, payload=excluded.payload",
                         (server, time.time(), json.dumps(agents)))

    def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY timestamp DESC, id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]
