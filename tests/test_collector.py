import json
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "remote"))
sys.path.insert(0, str(ROOT / "desktop"))
from collector import LogReader, Collector, publish
from server import create_store, handle_collector, ApiError, AgentDockRequestHandler
from ssh_tunnel import command


class CollectorTests(unittest.TestCase):
    def test_remote_http_snapshot_roundtrip(self):
        # Isolated store: test records never reach the user's dashboard.
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp) / "db")
            handler = type("TestHandler", (AgentDockRequestHandler,), {"store": store})
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{httpd.server_port}/api/collectors"
                row = {"session_id": "test-session", "event": "working", "agent_type": "codex", "status_known": True}
                self.assertEqual(publish(url, "remote-test", [row])["count"], 1)
                self.assertEqual(store.list_agents()[0]["server"], "remote-test")
                publish(url, "remote-test", [])
                self.assertEqual(store.list_agents(), [])
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join()

    def test_codex_metadata_transitions_and_privacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.jsonl"
            path.write_text(json.dumps({"type": "session_meta", "payload": {"id": "test", "cwd": "/project"}}) + "\n")
            reader = LogReader()
            self.assertFalse(reader.read(path)["status_known"])
            for event, state in [("task_started", "working"), ("task_complete", "done"), ("turn_aborted", "idle")]:
                with path.open("a") as stream:
                    stream.write(json.dumps({"type": "event_msg", "payload": {"type": event, "message": "SECRET PROMPT"}}) + "\n")
                result = reader.read(path)
                self.assertEqual(result["event"], state)
                self.assertNotIn("SECRET", json.dumps(result))

    def test_claude_only_live_processes_and_subagents_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sessions").mkdir()
            (root / "sessions" / "1.json").write_text(json.dumps({"pid": 1, "sessionId": "test", "status": "waiting", "cwd": "/code"}))
            (root / "sessions" / "sub.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {"id": "internal", "source": {"subagent": "guardian"}}}) + "\n")
            with patch("collector.open_codex_sessions", return_value={}), patch("collector.process_alive", return_value=True):
                rows = Collector(root, root, "machine").scan()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["event"], "waiting")
            with patch("collector.open_codex_sessions", return_value={}), patch("collector.process_alive", return_value=False):
                self.assertEqual(Collector(root, root, "machine").scan(), [])

    def test_partial_log_write_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.jsonl"
            path.write_text('{"type":"session_meta","payload":{"id":"t"}}\n' +
                            '{"type":"turn_context","payload":{"cwd":"/current"}}\n' +
                            '{"type":"event_msg","payload":{"type":"task_started"}}\n')
            reader = LogReader()
            self.assertEqual(reader.read(path)["event"], "working")
            with path.open("a") as stream:
                stream.write('{"type":"event_msg","payload":')
            self.assertEqual(reader.read(path)["event"], "working")
            with path.open("a") as stream:
                stream.write('{"type":"task_complete"}}\n')
            self.assertEqual(reader.read(path)["event"], "done")
            self.assertEqual(reader.read(path)["cwd"], "/current")

    def test_snapshot_replacement_host_isolation_and_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp) / "db")
            event = {"session_id": "same", "event": "working", "agent_type": "codex", "status_known": True}
            for host in ("local", "remote"):
                handle_collector(store, {"server": host, "agents": [event]})
            self.assertEqual(len(store.list_agents()), 2)
            handle_collector(store, {"server": "local", "agents": []})
            self.assertEqual(store.list_agents()[0]["server"], "remote")
            with patch("database.time.time", return_value=9999999999):
                self.assertFalse(store.list_agents()[0]["collector_online"])
            with self.assertRaises(ApiError):
                handle_collector(store, {"server": "local", "agents": [None]})

    def test_tunnel_binds_remote_loopback_and_rejects_options(self):
        self.assertIn("127.0.0.1:17322:127.0.0.1:17321", command("my-server", 17321, 17322))
        with self.assertRaises(ValueError):
            command("-oProxyCommand=anything", 17321, 17322)


if __name__ == "__main__":
    unittest.main()
