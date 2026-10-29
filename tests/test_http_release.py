import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import threading
import json
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop'))
from server import create_store, create_fastapi_app, MoyuWhistleRequestHandler


class StandardHttpReleaseTests(unittest.TestCase):
    def test_malformed_inputs_and_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            handler = type('IsolatedHandler', (MoyuWhistleRequestHandler,),
                           {'store':create_store(Path(tmp)/'test.db')})
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = build_opener(ProxyHandler({}))
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                for path, expected in (('/api/events?limit=bad', 400), ('/assets/', 404)):
                    with self.assertRaises(HTTPError) as result:
                        opener.open(base+path, timeout=3)
                    self.assertEqual(result.exception.code, expected)
                for value in (None, [], {'event':'working', 'timestamp':{}}):
                    request = Request(base+'/api/events', data=json.dumps(value).encode(),
                                      headers={'Content-Type':'application/json'})
                    with self.assertRaises(HTTPError) as result:
                        opener.open(request, timeout=3)
                    self.assertEqual(result.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


@unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'),
                     'Optional FastAPI/httpx dependencies not installed')
class FastApiReleaseTests(unittest.TestCase):
    def test_json_limits_and_validation(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp:
            app = create_fastapi_app(create_store(Path(tmp)/'test.db'))
            with TestClient(app, base_url='http://127.0.0.1:17321') as client:
                self.assertEqual(client.get('/health').json()['service'], 'moyu-whistle')
                response = client.post('/api/events', json={'event':'working', 'session_id':'unit'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(client.post('/api/events', json={'event':'working','timestamp':{}}).status_code, 400)
                self.assertEqual(client.post('/api/events', content='bad').status_code, 400)
                self.assertEqual(client.post('/api/events', content='x'*1_000_001,
                    headers={'Content-Type':'application/json'}).status_code, 413)
                self.assertEqual(client.get('/api/events?limit=bad').status_code, 422)
                self.assertEqual(client.get('/health', headers={'Origin':'https://evil.example'}).status_code, 403)
                self.assertEqual(client.get('/health', headers={'Host':'['}).status_code, 403)
                self.assertEqual(client.get('/assets/whistle.html').status_code, 200)
