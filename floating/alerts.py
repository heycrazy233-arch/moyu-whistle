"""Native Waiting monitor: unaffected by a hidden WebEngine page."""
import json

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class WaitingPolicy:
    def __init__(self):
        self.pending = {}
        self.notified = set()

    def update(self, agents):
        present, fresh, stale = set(), [], False
        for agent in agents:
            key = agent.get('agent_key')
            if not isinstance(key, str) or not key:
                continue
            present.add(key)
            reliable = (agent.get('status_known') is not False and
                        agent.get('collector_online') is not False and
                        not agent.get('collection_paused'))
            event = agent.get('event')
            if not reliable or event not in ('working', 'waiting', 'error', 'idle', 'done'):
                stale |= key in self.pending
                continue
            if event == 'waiting':
                self.pending[key] = agent
                if key not in self.notified:
                    fresh.append(key)
                    self.notified.add(key)
            else:
                self.pending.pop(key, None)
                self.notified.discard(key)
        for key in set(self.pending) - present:
            self.pending.pop(key, None)
            self.notified.discard(key)
        return list(self.pending.values()), bool(fresh), stale


class WaitingMonitor(QObject):
    changed = Signal(object, bool, bool)  # pending, new arrival, stale evidence
    snapshot = Signal(object, bool)  # shared with companion; no extra polling

    def __init__(self, base, parent=None):
        super().__init__(parent)
        self.base = base
        self.policy = WaitingPolicy()
        self.network = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.poll)
        self.reply = None

    def start(self):
        self.timer.start()
        self.poll()

    def poll(self):
        if self.reply is not None:
            return
        request = QNetworkRequest(QUrl(self.base + '/api/agents'))
        request.setTransferTimeout(8000)
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute, QNetworkRequest.CacheLoadControl.AlwaysNetwork)
        reply = self.network.get(request)
        self.reply = reply
        reply.downloadProgress.connect(lambda received, total: reply.abort() if max(received, total) > 2_000_000 else None)
        reply.finished.connect(lambda: self.finished(reply))

    def finished(self, reply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError('Service unavailable')
            data = bytes(reply.readAll())
            if len(data) > 2_000_000:
                raise ValueError('Snapshot too large')
            agents = json.loads(data)
            if not isinstance(agents, list) or any(not isinstance(a, dict) for a in agents):
                raise ValueError('Invalid snapshot')
            self.changed.emit(*self.policy.update(agents))
            self.snapshot.emit(agents, True)
        except (ValueError, TypeError):
            # A failed refresh is not evidence that the user has handled Waiting.
            self.changed.emit(list(self.policy.pending.values()), False, True)
            self.snapshot.emit([], False)
        finally:
            self.reply = None
            reply.deleteLater()
