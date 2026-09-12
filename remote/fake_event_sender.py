from __future__ import annotations

import argparse
import itertools
import random
import time

from bridge import send_event


AGENTS = [
    {
        "agent_type": "claude-code",
        "session_id": "sabr-01",
        "server": "compute01",
        "project": "sabr",
        "cwd": "/home/me/sabr",
        "tmux_session": "sabr-01",
    },
    {
        "agent_type": "claude-code",
        "session_id": "fpga-cache",
        "server": "compute01",
        "project": "fpga",
        "cwd": "/home/me/fpga",
        "tmux_session": "fpga-cache",
    },
    {
        "agent_type": "codex",
        "session_id": "backtest-02",
        "server": "research02",
        "project": "backtest",
        "cwd": "/srv/backtest",
        "tmux_session": "backtest-02",
    },
]

STATES = [
    ("idle", "Ready for next prompt"),
    ("working", "Editing files"),
    ("waiting", "Waiting for approval"),
    ("error", "Command failed"),
    ("done", "Task completed"),
]


def build_payload(index: int) -> dict:
    agent = AGENTS[index % len(AGENTS)].copy()
    event, message = STATES[index % len(STATES)]
    agent.update(
        {
            "event": event,
            "message": message,
            "timestamp": time.time(),
        }
    )
    return agent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:17321/api/events")
    parser.add_argument("--interval", type=float, default=1.2)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    sequence = range(len(AGENTS) * len(STATES)) if args.once else itertools.count()
    for index in sequence:
        payload = build_payload(index)
        try:
            result = send_event(args.url, payload)
            print(f"sent {result['server']}:{result['session_id']} -> {result['event']}")
        except Exception as exc:
            print(f"send failed: {exc}")
        if args.once:
            continue
        time.sleep(args.interval + random.uniform(0, 0.5))


if __name__ == "__main__":
    main()
