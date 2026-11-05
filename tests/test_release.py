import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'desktop'))
sys.path.insert(0, str(ROOT/'scripts'))
from state import AgentEvent
from server import ApiError, create_store, handle_event, handle_collector, local_request_allowed, run_server
from migrate_data import migrate


class ReleaseTests(unittest.TestCase):
    def test_platform_layout_keeps_shared_core_and_compatibility_launchers(self):
        for path in (
            ROOT/'web/index.html', ROOT/'desktop/server.py', ROOT/'remote/collector.py',
            ROOT/'platforms/common/README.md', ROOT/'platforms/macos/start.command',
            ROOT/'platforms/windows/start.cmd', ROOT/'platforms/windows/doctor.ps1',
        ):
            self.assertTrue(path.is_file(), path)
        self.assertIn('platforms\\windows\\start.cmd',
                      (ROOT/'Start Moyu Whistle.cmd').read_text())
        self.assertIn('platforms/macos/start.command',
                      (ROOT/'Start Moyu Whistle.command').read_text())

    def test_bad_event_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp)/'test.db')
            for value in ([], None, 'bad', {'event':'working', 'timestamp':float('nan')},
                          {'event':'working', 'timestamp':float('inf')},
                          {'event':'working', 'timestamp':{}}, {'event':'working', 'session_id':[]}):
                with self.subTest(value=value), self.assertRaises(ApiError):
                    handle_event(store, value)
            for value in (float('nan'), float('inf'), -1):
                with self.assertRaises(ApiError):
                    handle_collector(store, {'server':'s','agents':[{
                        'event':'working', 'session_id':'s', 'last_activity':value}]})

    def test_loopback_boundary(self):
        self.assertTrue(local_request_allowed('127.0.0.1:17321', None))
        self.assertTrue(local_request_allowed('localhost:17321', 'http://localhost:17321'))
        for host, origin in (('[', None), ('evil.example', None),
                             ('localhost:17321', 'https://evil.example')):
            self.assertFalse(local_request_allowed(host, origin))
        with self.assertRaises(ValueError):
            run_server(None, '0.0.0.0')

    def test_migration_preserves_source_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp)/'previous.sqlite3', Path(tmp)/'new.sqlite3'
            with sqlite3.connect(str(source)) as conn:
                conn.execute('CREATE TABLE test(value TEXT)')
                conn.execute("INSERT INTO test VALUES ('preserved')")
            source.with_suffix('.settings.json').write_text('{"interval":5}', encoding='utf-8')
            migrate(source, target)
            for path in (source, target):
                with sqlite3.connect(str(path)) as conn:
                    self.assertEqual(conn.execute('SELECT value FROM test').fetchone()[0], 'preserved')
            self.assertEqual(json.loads(target.with_suffix('.settings.json').read_text()), {'interval':5})
            with self.assertRaises(ValueError):
                migrate(source, target)
