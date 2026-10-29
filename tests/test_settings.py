import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop'))
sys.path.insert(0, str(ROOT / 'remote'))
from settings import DEFAULT, Settings, validate, in_window, ssh_command, Monitor, read_snapshot, retry_delay
from collector import Collector, json_file
from server import create_store, dashboard_agents, handle_collector


class SettingsTests(unittest.TestCase):
    def test_default_and_backoff(self):
        self.assertEqual(DEFAULT['interval'], 5)
        self.assertEqual([retry_delay(5, n) for n in range(8)], [5,10,20,40,80,160,300,300])
        self.assertEqual(retry_delay(3600, 5), 3600)

    def test_bounded_subprocess(self):
        self.assertEqual(read_snapshot([sys.executable, '-c', 'print("[]")']), [])
        with self.assertRaises(ValueError):
            read_snapshot([sys.executable, '-c', 'print("x" * 2000)'], limit=1000)
        with self.assertRaises(ValueError):
            read_snapshot([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=0.1)
        with self.assertRaises(ValueError):
            read_snapshot([sys.executable, '-c', 'raise SystemExit(1)'])

    def test_metadata_file_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'status.json'
            for content in ['[]', 'invalid', ' ' * 65537]:
                path.write_text(content)
                self.assertEqual(json_file(path), {})
            path.write_text('{"status":"idle"}')
            self.assertEqual(json_file(path), {'status':'idle'})

    def test_database_connections_close(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp)/'state.db')
            with store._connect() as conn:
                conn.execute('SELECT 1')
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute('SELECT 1')

    def test_windows_and_midnight(self):
        value = dict(DEFAULT, scheduled=True)
        for hour, minute, active in [(8,59,False),(9,0,True),(17,59,True),(18,0,False)]:
            self.assertEqual(in_window(value, datetime(2026,1,1,hour,minute)), active)
        value.update(start='22:00', end='06:00')
        self.assertTrue(in_window(value, datetime(2026,1,1,1)))
        self.assertFalse(in_window(value, datetime(2026,1,1,12)))
        value['enabled'] = False
        self.assertFalse(in_window(value, datetime(2026,1,1,23)))

    def test_validation_persistence_and_injection(self):
        value = copy.deepcopy(DEFAULT)
        value['servers'] = [dict(name='research', host='user@host', port=2222, script='moyu-whistle-collector.py', enabled=False)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'settings.json'
            Settings(path).save(value)
            self.assertEqual(Settings(path).get(), value)
        command = ssh_command(value['servers'][0], False)
        self.assertIn('2222', command)
        self.assertIn('--metadata-only', command[-1])
        for host in ['-oProxyCommand=evil', 'host;whoami', '$(whoami)', 'host\nwhoami']:
            value['servers'][0]['host'] = host
            with self.assertRaises(ValueError):
                validate(value)
        for interval in [0, 4, 3601, True, 1.5]:
            with self.assertRaises(ValueError):
                validate(dict(DEFAULT, interval=interval))

    def test_metadata_mode_never_reads_transcripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'sessions').mkdir()
            (root/'sessions'/'test.jsonl').write_text('SECRET TRANSCRIPT')
            collector = Collector(root, root, 'local', metadata_only=True)
            with patch('collector.open_codex_sessions', return_value={}), patch.object(collector.reader, 'read', side_effect=AssertionError('Must not read logs')):
                self.assertEqual(collector.scan(), [])

    def test_long_intervals_and_scheduled_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = create_store(Path(tmp)/'state.db')
            store.settings.save(dict(DEFAULT, interval=120))
            handle_collector(store, {'server':'local', 'agents':[{'session_id':'test', 'event':'working'}]})
            import time
            with patch('server.time.time', return_value=time.time()+60):
                self.assertTrue(dashboard_agents(store)[0]['collector_online'])
            store.settings.save(dict(DEFAULT, enabled=False))
            self.assertTrue(dashboard_agents(store)[0]['collection_paused'])

    def test_paused_worker_does_not_scan_or_connect(self):
        with tempfile.TemporaryDirectory() as tmp:
            from unittest.mock import Mock
            settings = Settings(Path(tmp)/'settings.json')
            settings.save(dict(DEFAULT, enabled=False))
            collector = Mock(server='local')
            monitor = Monitor(settings, collector, Mock(), Mock())
            monitor.stop = Mock()
            monitor.stop.wait.side_effect = [False, True]
            with patch('settings.subprocess.run') as run:
                monitor.worker(-1)
                collector.scan.assert_not_called()
                run.assert_not_called()

    def test_remote_worker_uses_configured_port_and_ingests_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            from unittest.mock import Mock
            settings = Settings(Path(tmp)/'settings.json')
            settings.save(dict(DEFAULT, servers=[dict(name='remote',host='test-host',port=2222,script='collector.py',enabled=True)]))
            ingest, store = Mock(), Mock()
            monitor = Monitor(settings, Mock(server='local'), store, ingest)
            monitor.stop = Mock()
            monitor.stop.wait.side_effect = [False, True]
            with patch('settings.read_snapshot', return_value=[]) as run:
                monitor.worker(0)
                self.assertIn('2222', run.call_args.args[0])
                self.assertIn('--metadata-only', run.call_args.args[0][-1])
                ingest.assert_called_once_with(store, {'server':'ssh:remote','agents':[]})


if __name__ == '__main__':
    unittest.main()
