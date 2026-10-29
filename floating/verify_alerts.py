"""Isolated HTTP -> native watcher -> visible Waiting prompt integration test."""
import json
import threading
import time
import tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest
from alerts import WaitingMonitor
from waiting_notice import WaitingNotice


snapshot = []
offline = False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(snapshot).encode()
        self.send_response(503 if offline else 200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
opened = []
notice = WaitingNotice(lambda: opened.append(True))
monitor = WaitingMonitor(f'http://127.0.0.1:{server.server_port}', app)
monitor.changed.connect(notice.update_waiting)
results = []
monitor.changed.connect(lambda *args: results.append(args))


def poll():
    count = len(results)
    start = time.monotonic()
    monitor.poll()
    while len(results) == count and time.monotonic() - start < 3:
        QTest.qWait(20)
    assert len(results) > count, 'Native HTTP poll timed out'
    return time.monotonic() - start


try:
    poll()
    assert not notice.isVisible()
    snapshot = [dict(agent_key='isolated-test', event='waiting', project='隔离测试 · 请确认操作', agent_type='Codex', status_known=True, collector_online=True)]
    delay = poll()
    assert notice.isVisible(), 'Waiting did not show prompt'
    if notice.movie is not None:
        assert notice.movie.isValid()
        frame = notice.movie.currentFrameNumber()
        QTest.qWait(140)
        assert notice.movie.currentFrameNumber() != frame, 'GIF is not advancing'
    notice.grab().save(str(Path(tempfile.gettempdir()) / 'moyu-whistle-waiting-guada.png'))
    notice.findChild(QPushButton, 'view-waiting').click()
    assert opened, 'View action not connected'
    notice.hide()
    poll()
    assert not notice.isVisible(), 'Acknowledged waiting repeated'
    snapshot.append(dict(agent_key='new-wait', event='waiting', project='第二个等待会话'))
    poll()
    assert notice.isVisible(), 'New waiting was suppressed'
    offline = True
    poll()
    assert notice.isVisible() and '暂不可用' in notice.status.text(), 'Disconnect cleared pending prompt'
    offline = False
    snapshot = [dict(agent_key='isolated-test', event='working'), dict(agent_key='new-wait', event='idle')]
    poll()
    assert not notice.isVisible(), 'Resolved Waiting left prompt open'
    print(f'PASS: isolated HTTP -> popup in {delay:.3f}s; optional Guada; click action; dedup; hidden/no browser; new waits; disconnect retention; resolution', flush=True)
finally:
    notice.hide()
    server.shutdown()
    server.server_close()
