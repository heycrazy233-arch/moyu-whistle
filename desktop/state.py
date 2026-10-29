from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from time import time
from typing import Any
import math


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    ERROR = "error"
    DONE = "done"


STATUS_LABELS = {
    AgentStatus.IDLE: "Idle",
    AgentStatus.WORKING: "Working",
    AgentStatus.WAITING: "Waiting",
    AgentStatus.ERROR: "Error",
    AgentStatus.DONE: "Done",
}


STATUS_COLORS = {
    AgentStatus.IDLE: "#60a5fa",
    AgentStatus.WORKING: "#1f9d55",
    AgentStatus.WAITING: "#c47f00",
    AgentStatus.ERROR: "#d83a3a",
    AgentStatus.DONE: "#2b6cb0",
}


@dataclass(frozen=True)
class AgentEvent:
    event: AgentStatus
    agent_type: str
    session_id: str
    server: str
    project: str
    cwd: str = ""
    tmux_session: str = ""
    message: str = ""
    timestamp: float = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AgentEvent":
        if not isinstance(payload, dict):
            raise ValueError("Event must be a JSON object")
        for key in ("agent_type", "session_id", "server", "project", "cwd", "tmux_session", "message"):
            value = payload.get(key)
            if value is not None and (not isinstance(value, str) or len(value) > 4096):
                raise ValueError(f"Invalid {key}")
        event = AgentStatus(str(payload.get("event", "")).lower())
        raw_timestamp = payload.get("timestamp")
        if raw_timestamp is not None and (isinstance(raw_timestamp, bool) or not isinstance(raw_timestamp, (str, int, float))):
            raise ValueError("Invalid timestamp")
        try:
            timestamp = time() if raw_timestamp is None else float(raw_timestamp)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid timestamp") from exc
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("Invalid timestamp")
        return cls(
            event=event,
            agent_type=str(payload.get("agent_type") or "unknown"),
            session_id=str(payload.get("session_id") or "unknown"),
            server=str(payload.get("server") or "local"),
            project=str(payload.get("project") or "unknown"),
            cwd=str(payload.get("cwd") or ""),
            tmux_session=str(payload.get("tmux_session") or ""),
            message=str(payload.get("message") or ""),
            timestamp=timestamp,
        )

    @property
    def agent_key(self) -> str:
        return f"{self.server}:{self.session_id}"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event"] = self.event.value
        result["status_label"] = STATUS_LABELS[self.event]
        result["status_color"] = STATUS_COLORS[self.event]
        result["agent_key"] = self.agent_key
        return result
