import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'remote'))
from collector import record_codex_hook, apply_codex_hooks, codex_hook_key, LogReader
from install_codex_hooks import install


class HookTests(unittest.TestCase):
    def test_auto_review_is_not_human_waiting(self):
        for reviewer, policy, expected in (('auto_review', 'on-request', 'working'),
                                            ('user', 'on-request', 'waiting'),
                                            ('user', 'never', 'working')):
            with self.subTest(reviewer=reviewer, policy=policy), tempfile.TemporaryDirectory() as tmp:
                record_codex_hook(tmp, dict(session_id='s', turn_id='t', hook_event_name='PermissionRequest',
                                           tool_name='Bash', tool_input={'command':'SECRET'}))
                path = Path(tmp)/'rollout.jsonl'
                rows = [{'type':'session_meta', 'payload':{'id':'s'}},
                        {'type':'event_msg', 'timestamp':'2000-01-01T00:00:00Z',
                         'payload':{'type':'task_started', 'turn_id':'t'}},
                        {'type':'turn_context', 'payload':{'turn_id':'t', 'approvals_reviewer':reviewer,
                                                          'approval_policy':policy}}]
                path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                reader = LogReader()
                for _ in range(2):
                    agent = dict(reader.read(path), agent_type='codex', presence='open')
                    result = apply_codex_hooks(tmp, [agent])[0]
                    self.assertEqual(result['event'], expected)
                    self.assertNotIn('_approval_context', result)
                # Reading does not delete evidence or change the user's policy.
                with sqlite3.connect(str(Path(tmp)/'moyu-whistle-hooks.sqlite3')) as conn:
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 1)

    def test_approval_context_tracks_turns_and_reviewer_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'rollout.jsonl'
            path.write_text('{"type":"session_meta","payload":{"id":"s"}}\n')
            reader = LogReader()
            def append(kind, payload):
                with path.open('a') as stream:
                    stream.write(json.dumps({'type':kind, 'payload':payload})+'\n')
                return reader.read(path)
            append('event_msg', {'type':'task_started', 'turn_id':'old'})
            append('turn_context', {'turn_id':'old', 'approvals_reviewer':'auto_review'})
            result = append('event_msg', {'type':'task_started', 'turn_id':'new'})
            self.assertNotIn('_approval_context', result)
            append('turn_context', {'turn_id':'new', 'approvals_reviewer':'user'})
            result = append('turn_context', {'turn_id':'old', 'approvals_reviewer':'auto_review'})
            self.assertEqual(result['_approval_context']['reviewer'], 'user')
            record_codex_hook(tmp, dict(session_id='s', turn_id='old', hook_event_name='PermissionRequest'))
            result.update(agent_type='codex', presence='open')
            self.assertEqual(apply_codex_hooks(tmp, [result])[0]['event'], 'working')

    def test_internal_context_is_not_exposed_without_hook_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = apply_codex_hooks(tmp, [dict(event='working', _approval_context={'turn_id':'t'})])
            self.assertNotIn('_approval_context', result[0])

    def test_approval_description_does_not_prevent_resolution(self):
        for tool in ('Bash', 'apply_patch'):
            for reason in (None, 'PRIVATE REASON'):
                with self.subTest(tool=tool, reason=reason), tempfile.TemporaryDirectory() as tmp:
                    value = dict(session_id='s', turn_id='t', tool_name=tool)
                    record_codex_hook(tmp, dict(value, hook_event_name='PermissionRequest',
                                               tool_input={'command':'PRIVATE COMMAND', 'description':reason}))
                    record_codex_hook(tmp, dict(value, hook_event_name='PostToolUse',
                                               tool_input={'command':'PRIVATE COMMAND'},
                                               tool_response={'stdout':'PRIVATE OUTPUT'}))
                    with sqlite3.connect(str(Path(tmp)/'moyu-whistle-hooks.sqlite3')) as conn:
                        self.assertEqual(conn.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 0)
                        self.assertEqual(conn.execute("SELECT matched FROM hook_receipts WHERE event='PostToolUse'").fetchone()[0], 1)
                    self.assertNotIn(b'PRIVATE', (Path(tmp)/'moyu-whistle-hooks.sqlite3').read_bytes())

    def test_mcp_description_remains_part_of_identity(self):
        a = dict(tool_name='mcp__server__tool', tool_input={'description':'first'})
        b = dict(tool_name='mcp__server__tool', tool_input={'description':'second'})
        self.assertNotEqual(codex_hook_key(a), codex_hook_key(b))

    def test_identical_parallel_commands_are_consumed_one_at_a_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(session_id='s', turn_id='t', tool_name='Bash', tool_input={'command':'same'})
            for _ in range(2):
                record_codex_hook(tmp, dict(value, hook_event_name='PermissionRequest'))
            record_codex_hook(tmp, dict(value, hook_event_name='PostToolUse'))
            with sqlite3.connect(str(Path(tmp)/'moyu-whistle-hooks.sqlite3')) as conn:
                self.assertEqual(conn.execute('SELECT occurrences FROM pending').fetchone()[0], 1)
            self.assertEqual(apply_codex_hooks(tmp, [dict(session_id='s', agent_type='codex',
                             presence='open', event='working', last_activity=0)])[0]['event'], 'waiting')
            record_codex_hook(tmp, dict(value, hook_event_name='PostToolUse'))
            with sqlite3.connect(str(Path(tmp)/'moyu-whistle-hooks.sqlite3')) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 0)

    def test_unrelated_completion_cannot_clear_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(session_id='s', turn_id='t', tool_name='Bash', tool_input={'command':'first'})
            record_codex_hook(tmp, dict(value, hook_event_name='PermissionRequest'))
            for changes in ({'session_id':'other'}, {'turn_id':'other'},
                            {'tool_input':{'command':'second'}}, {'tool_name':'apply_patch'}):
                record_codex_hook(tmp, dict(value, hook_event_name='PostToolUse', **changes))
            with sqlite3.connect(str(Path(tmp)/'moyu-whistle-hooks.sqlite3')) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT matched FROM hook_receipts WHERE session='s' AND event='PostToolUse'").fetchone()[0], 0)

    def test_old_database_is_migrated_without_discarding_pending(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(session_id='s', turn_id='t', tool_name='Bash', tool_input={'command':'old'})
            key = hashlib.sha256(json.dumps(['Bash',value['tool_input']], sort_keys=True).encode()).hexdigest()
            path = Path(tmp)/'moyu-whistle-hooks.sqlite3'
            with sqlite3.connect(str(path)) as conn:
                conn.execute('CREATE TABLE pending (session TEXT, turn TEXT, request TEXT, created REAL, PRIMARY KEY(session,turn,request))')
                conn.execute('INSERT INTO pending VALUES (?,?,?,?)', ('s','t',key,10))
            record_codex_hook(tmp, dict(value, hook_event_name='PostToolUse', turn_id='other'))
            with sqlite3.connect(str(path)) as conn:
                self.assertEqual(conn.execute('SELECT request,occurrences FROM pending').fetchone(), (key,1))
            record_codex_hook(tmp, dict(value, hook_event_name='PostToolUse'))
            with sqlite3.connect(str(path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 0)

    def test_hook_to_dashboard_lifecycle_in_isolated_store(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop'))
        from server import create_store, handle_collector, dashboard_agents
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp)/'dashboard.db')
            value = dict(session_id='s', turn_id='t', tool_name='Bash')
            def visible(event='working'):
                agents = apply_codex_hooks(tmp, [dict(session_id='s', agent_type='codex',
                    presence='open', event=event, status_known=True, last_activity=0)])
                handle_collector(store, {'server':'test', 'agents':agents})
                return dashboard_agents(store)[0]['event']
            self.assertEqual(visible(), 'working')
            record_codex_hook(tmp, dict(value, hook_event_name='PermissionRequest',
                                       tool_input={'command':'test', 'description':'approval only'}))
            self.assertEqual(visible(), 'waiting')
            # Polling/elapsed time must not invent an approval decision.
            with patch('collector.time.time', return_value=9999999999):
                self.assertEqual(visible(), 'waiting')
            record_codex_hook(tmp, dict(value, hook_event_name='PostToolUse', tool_input={'command':'test'}))
            self.assertEqual(visible(), 'working')
            record_codex_hook(tmp, dict(value, hook_event_name='Stop'))
            self.assertEqual(visible('done'), 'idle')

    def test_receipts_are_bounded_metadata_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(260):
                record_codex_hook(tmp, dict(session_id=str(index), hook_event_name='Stop',
                                           prompt='PRIVATE PROMPT', tool_response='PRIVATE RESULT'))
            path = Path(tmp)/'moyu-whistle-hooks.sqlite3'
            with sqlite3.connect(str(path)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM hook_receipts').fetchone()[0], 256)
            self.assertNotIn(b'PRIVATE', path.read_bytes())

    def test_wait_resolution_and_parallel_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(session_id='s',turn_id='t',tool_name='Bash',tool_input={'command':'SECRET'})
            def send(event, command='SECRET'):
                record_codex_hook(tmp,dict(value,hook_event_name=event,tool_input={'command':command}))
            def state():
                return apply_codex_hooks(tmp,[dict(session_id='s',agent_type='codex',presence='open',
                                                  event='working',last_activity=0)])[0]['event']
            send('PermissionRequest')
            send('PermissionRequest','SECOND')
            self.assertEqual(state(),'waiting')
            send('PostToolUse')
            self.assertEqual(state(),'waiting')
            send('PostToolUse','SECOND')
            self.assertEqual(state(),'working')
            send('PermissionRequest')
            send('Interrupt')
            self.assertEqual(state(),'working')
            self.assertNotIn(b'SECRET', (Path(tmp)/'moyu-whistle-hooks.sqlite3').read_bytes())

    def test_older_pending_cannot_override_new_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('collector.time.time',return_value=10):
                record_codex_hook(tmp,dict(session_id='s',turn_id='t',hook_event_name='PermissionRequest'))
            agent = dict(session_id='s',agent_type='codex',presence='open',event='done',last_activity=20)
            self.assertEqual(apply_codex_hooks(tmp,[agent])[0]['event'],'done')

    def test_hook_emits_no_approval_or_model_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'remote/collector.py'),
                                     '--hook','--codex-home',tmp],input=json.dumps({
                                         'session_id':'s','turn_id':'t','hook_event_name':'PermissionRequest'}),
                                    text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout,'')
            self.assertEqual(result.stderr,'')

    def test_install_preserves_existing_hooks_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'hooks.json'
            original={'hooks':{'Stop':[{'hooks':[{'type':'command','command':'existing'}]}]}}
            path.write_text(json.dumps(original))
            install(tmp)
            first=json.loads(path.read_text())
            install(tmp)
            self.assertEqual(json.loads(path.read_text()),first)
            self.assertEqual(first['hooks']['Stop'][0],original['hooks']['Stop'][0])
