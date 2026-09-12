from __future__ import annotations

import argparse
import json
import time
import urllib.request


def send_event(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one Agent Dock event.")
    parser.add_argument("--url", default="http://127.0.0.1:17321/api/events")
    parser.add_argument("--event", required=True, choices=["idle", "working", "waiting", "error", "done"])
    parser.add_argument("--agent-type", default="claude-code")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--server", default="compute01")
    parser.add_argument("--project", required=True)
    parser.add_argument("--cwd", default="")
    parser.add_argument("--tmux-session", default="")
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    payload = {
        "event": args.event,
        "agent_type": args.agent_type,
        "session_id": args.session_id,
        "server": args.server,
        "project": args.project,
        "cwd": args.cwd,
        "tmux_session": args.tmux_session,
        "message": args.message,
        "timestamp": time.time(),
    }
    print(json.dumps(send_event(args.url, payload), indent=2))


if __name__ == "__main__":
    main()
