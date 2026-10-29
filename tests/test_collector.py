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
from collector import LogReader, Collector, publish, codex_client
from server import create_store, handle_collector, ApiError, MoyuWhistleRequestHandler, dashboard_agents
from ssh_tunnel import command


class CollectorTests(unittest.TestCase):
    def test_async_question_does_not_block_or_prevent_idle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            path.write_text('{"type":"session_meta","payload":{"id":"test"}}\n')
            reader = LogReader()
            def append(payload):
                with path.open('a') as stream:
                    stream.write(json.dumps({'type':'event_msg','payload':payload})+'\n')
                return reader.read(path)
            append({'type':'task_started','turn_id':'t'})
            result = append({'type':'item_completed','item':{'type':'AgentMessage','delivery':'async',
                                                             'questions':[{'title':'PRIVATE QUESTION','options':['PRIVATE']} ]}})
            self.assertEqual(result['event'],'working')
            self.assertNotIn('PRIVATE',json.dumps(result))
            self.assertEqual(reader.read(path)['event'],'working')
            self.assertEqual(append({'type':'task_complete','turn_id':'t'})['event'],'done')
            self.assertEqual(LogReader().read(path)['event'],'done')
            self.assertEqual(append({'type':'item_completed','item':{'type':'UserMessage','content':[]}})['event'],'done')
            self.assertEqual(append({'type':'task_started','turn_id':'t'})['event'],'working')
            self.assertEqual(append({'type':'task_complete','turn_id':'t'})['event'],'done')

    def test_plain_question_text_does_not_imply_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            rows = [{'type':'session_meta','payload':{'id':'t'}},
                    {'type':'event_msg','payload':{'type':'task_started'}},
                    {'type':'event_msg','payload':{'type':'item_completed','item':{
                        'type':'AgentMessage','content':'Would you like to run?', 'questions':[]}}}]
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(LogReader().read(path)['event'],'working')

    def test_local_identity_survives_network_hostname_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'db'
            store = create_store(path)
            original = store.local_source('host.local')
            self.assertEqual(create_store(path).local_source('host.router'), original)
            for host in (original, 'ssh:remote'):
                handle_collector(store, {'server':host,'agents':[{
                    'session_id':'same','event':'working','agent_type':'codex'}]})
            self.assertEqual(len(store.list_agents()),2)

    def test_codex_client_identity(self):
        self.assertEqual(codex_client('codex_work_desktop'), 'desktop')
        self.assertEqual(codex_client('codex-tui'), 'terminal')
        self.assertEqual(codex_client('codex_work_desktop', cli_process=True), 'terminal')
        for originator in (None, 'vscode', 'app-server', {}, 'unrecognized'):
            self.assertEqual(codex_client(originator), 'unknown')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            path.write_text(json.dumps({'type':'session_meta','payload':{
                'id':'test','source':'vscode','originator':'codex_work_desktop'}})+'\n')
            self.assertEqual(LogReader().read(path)['client_type'],'desktop')

    def test_client_identity_api_whitelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp)/'db')
            for client, expected in [('desktop','desktop'),('terminal','terminal'),('bad-value','unknown'), (None,'unknown'), ([], 'unknown')]:
                handle_collector(store, {'server':'local','agents':[{
                    'session_id':'test','agent_type':'codex','event':'working','client_type':client}]})
                row = dashboard_agents(store)[0]
                self.assertEqual(row['client_type'],expected)
                self.assertEqual(row['agent_type'],'codex')

    def test_live_view_maps_done_without_rewriting_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp)/'db')
            handle_collector(store, {'server':'local','agents':[
                {'session_id':'open','event':'done','status_known':True,'presence':'open'},
                {'session_id':'unknown','event':'idle','status_known':False}]})
            rows = dashboard_agents(store)
            self.assertEqual(rows[0]['event'], 'idle')
            self.assertEqual(rows[0]['status_label'], 'Idle')
            self.assertEqual(store.list_agents()[0]['event'], 'done')
            self.assertFalse(rows[1]['status_known'])

    def test_closed_session_removed_only_after_successful_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'sessions').mkdir()
            path = root/'sessions'/'test.jsonl'
            path.write_text('{"type":"session_meta","payload":{"id":"test","cwd":"/project"}}\n'
                            '{"type":"event_msg","payload":{"type":"task_complete"}}\n')
            collector = Collector(root,root,'local')
            for discovered, expected in [({'test':123},1), ({},0), (None,1)]:
                with patch('collector.open_codex_sessions',return_value=discovered), patch('collector.is_cli',return_value=True):
                    self.assertEqual(len(collector.scan()),expected)

    def test_old_completion_cannot_end_new_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            path.write_text('{"type":"session_meta","payload":{"id":"test"}}\n')
            reader = LogReader()
            for kind, turn, expected in [('task_started','old','working'),
                                         ('task_started','new','working'),
                                         ('task_complete','old','working'),
                                         ('turn_aborted','old','working'),
                                         ('task_complete','new','done')]:
                with path.open('a') as stream:
                    stream.write(json.dumps({'type':'event_msg','payload':{'type':kind,'turn_id':turn}})+'\n')
                self.assertEqual(reader.read(path)['event'], expected)

    def test_tool_errors_and_text_do_not_classify_task_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            path.write_text('{"type":"session_meta","payload":{"id":"test"}}\n'
                            '{"type":"event_msg","payload":{"type":"task_started"}}\n')
            reader = LogReader()
            self.assertEqual(reader.read(path)['event'], 'working')
            rows = [None, [], {'type':'event_msg','payload':None},
                    {'type':'event_msg','payload':{'type':[]}},
                    {'type':'event_msg','payload':{'type':'agent_message','message':'waiting error done SECRET'}},
                    {'type':'response_item','payload':{'type':'function_call_output','output':'ERROR SECRET'}},
                    {'type':'event_msg','payload':{'type':'error','message':'retriable SECRET'}}]
            with path.open('a') as stream:
                stream.writelines(json.dumps(row)+'\n' for row in rows)
            result = reader.read(path)
            self.assertEqual(result['event'], 'working')
            self.assertNotIn('SECRET', json.dumps(result))

    def test_replaced_log_does_not_keep_old_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            meta = '{"type":"session_meta","payload":{"id":"test"}}\n'
            path.write_text(meta+'{"type":"event_msg","payload":{"type":"task_started"}}\n')
            reader = LogReader()
            self.assertEqual(reader.read(path)['event'], 'working')
            replacement = path.with_suffix('.tmp')
            replacement.write_text(meta+'{"type":"event_msg","payload":{"type":"task_complete"}}\n')
            replacement.replace(path)
            self.assertEqual(reader.read(path)['event'], 'done')
            path.write_text(meta)
            result = reader.read(path)
            self.assertFalse(result['status_known'])
            self.assertEqual(result['last_activity'], 0)

    def test_claude_explicit_states_in_both_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'sessions').mkdir()
            path = root/'sessions'/'status.json'
            for minimal in (True, False):
                collector = Collector(root,root,'test',metadata_only=minimal)
                for status in ('working','waiting','error','done','idle','new-unsupported-status'):
                    path.write_text(json.dumps({'pid':123,'sessionId':'test','status':status}))
                    with patch('collector.open_codex_sessions',return_value={}), patch('collector.process_alive',return_value=True):
                        row = collector.scan()[0]
                    self.assertEqual(row['status_known'], status != 'new-unsupported-status')
                    if row['status_known']:
                        self.assertEqual(row['event'],status)

    def test_remote_http_snapshot_roundtrip(self):
        # Isolated store: test records never reach the user's dashboard.
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp) / "db")
            handler = type("TestHandler", (MoyuWhistleRequestHandler,), {"store": store})
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
