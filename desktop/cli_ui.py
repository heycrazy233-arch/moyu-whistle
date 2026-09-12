from __future__ import annotations

import os
import time

from database import AgentStore


def run_console_ui(store: AgentStore, refresh_seconds: float = 1.5) -> None:
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("Agent Dock V0.1")
        print("Local status center: http://127.0.0.1:17321")
        print()
        agents = store.list_agents()
        if not agents:
            print("No agents yet. Start remote/fake_event_sender.py to simulate events.")
        for agent in agents:
            print(
                f"{agent['event'].upper():8} "
                f"{agent['server']:<12} "
                f"{agent['project']:<12} "
                f"{agent['session_id']:<14} "
                f"{agent['message']}"
            )
        print()
        print("Press Ctrl+C to stop.")
        time.sleep(refresh_seconds)
