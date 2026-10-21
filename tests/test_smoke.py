from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
if str(DESKTOP) not in sys.path:
    sys.path.insert(0, str(DESKTOP))

from server import ApiError, WEB_DIR, create_store, handle_event


class AgentDockSmokeTest(unittest.TestCase):
    def test_records_events_and_keeps_latest_agent_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "agent-dock.sqlite3")

            first = handle_event(
                store,
                {
                    "event": "working",
                    "agent_type": "claude-code",
                    "session_id": "sabr-01",
                    "server": "compute01",
                    "project": "sabr",
                    "cwd": "/home/me/sabr",
                    "tmux_session": "sabr-01",
                    "message": "Editing files",
                    "timestamp": 10,
                },
            )
            second = handle_event(
                store,
                {
                    "event": "done",
                    "agent_type": "claude-code",
                    "session_id": "sabr-01",
                    "server": "compute01",
                    "project": "sabr",
                    "cwd": "/home/me/sabr",
                    "tmux_session": "sabr-01",
                    "message": "Task completed",
                    "timestamp": 20,
                },
            )

            agents = store.list_agents()
            events = store.list_events(limit=10)

            self.assertEqual(first["agent_key"], "compute01:sabr-01")
            self.assertEqual(second["event"], "done")
            self.assertEqual(len(agents), 1)
            self.assertEqual(agents[0]["event"], "done")
            self.assertEqual(agents[0]["message"], "Task completed")
            self.assertEqual([event["event"] for event in events], ["done", "working"])

    def test_rejects_unknown_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = create_store(Path(temp_dir) / "agent-dock.sqlite3")
            with self.assertRaises(ApiError):
                handle_event(store, {"event": "paused"})

    def test_web_dashboard_assets_exist(self) -> None:
        self.assertTrue((WEB_DIR / "index.html").is_file())
        self.assertTrue((WEB_DIR / "assets" / "app.js").is_file())
        self.assertTrue((WEB_DIR / "assets" / "styles.css").is_file())


if __name__ == "__main__":
    unittest.main()
