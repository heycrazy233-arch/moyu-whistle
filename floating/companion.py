"""Four-state Guada companion. Shares the native monitor; never sends alerts."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QEvent, QPoint
from PySide6.QtGui import QPixmap, QMovie, QImageReader
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from gestures import WindowGestures


PRIORITY = ('waiting', 'error', 'working', 'idle')


def aggregate(agents, online):
    if not online:
        return None, 0
    counts = dict.fromkeys(PRIORITY, 0)
    for agent in agents:
        state = 'idle' if agent.get('event') == 'done' else agent.get('event')
        if (agent.get('status_known') is False or agent.get('collector_online') is False or
                agent.get('collection_paused') or state not in counts):
            return None, 0
        counts[state] += 1
    state = next((state for state in PRIORITY if counts[state]), 'idle')
    return state, counts[state]


class Companion(QWidget):
    def __init__(self, owner, open_session):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName('guada-companion')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(156, 170)
        self.owner = owner
        self.open_session = open_session
        self.state = None
        self.stale = True
        self.reduced_motion = False
        self.movie = None
        self.asset_ok = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.bubble = QLabel()
        self.bubble.setFixedHeight(30)
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setTextFormat(Qt.TextFormat.PlainText)
        self.bubble.setStyleSheet('color:#fff3d3;background:#302a38;border-radius:12px;font-size:11px;')
        layout.addWidget(self.bubble)
        self.art = QLabel()
        self.art.setFixedSize(156, 134)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setStyleSheet('color:#d5cbe9;')
        layout.addWidget(self.art)
        for label in (self.bubble, self.art):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.root = Path(__file__).resolve().parents[1] / 'pet/assets/guada'
        try:
            self.assets = json.loads((self.root / 'manifest.json').read_text(encoding="utf-8"))['states']
        except (OSError, ValueError, KeyError):
            self.assets = {}
        self.set_visual('idle', 0)
        self.update_snapshot([], False)
        self.last_owner = owner.pos()
        self.anchor()
        owner.installEventFilter(self)
        QApplication.instance().screenRemoved.connect(lambda *_: self.constrain())
        self.gestures = WindowGestures(self)

    def anchor(self):
        area = self.owner.screen().availableGeometry()
        x = self.owner.x() + self.owner.width() + 12
        if x + self.width() > area.right():
            x = self.owner.x() - self.width() - 12
        self.move(x, self.owner.y() + self.owner.height() - self.height())
        self.constrain()

    def constrain(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or self.owner.screen()
        area = screen.availableGeometry()
        self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                  max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def eventFilter(self, target, event):
        if target is self.owner and event.type() == QEvent.Type.Move:
            delta = self.owner.pos() - self.last_owner
            self.last_owner = self.owner.pos()
            self.move(self.pos() + delta)
            self.constrain()
        return False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_session(self.state if not self.stale else 'all')
            event.accept()

    def set_visual(self, state, count):
        if state != self.state:
            if self.movie:
                self.movie.stop()
                self.movie.deleteLater()
                self.movie = None
            self.art.clear()
            self.asset_ok = False
            try:
                asset = (self.root / self.assets[state]).resolve()
                if asset.parent != self.root.resolve() or asset.stat().st_size > 10_000_000:
                    raise ValueError('Asset outside limits')
                reader = QImageReader(str(asset))
                size = reader.size()
                if not size.isValid() or size.width() * size.height() > 4_000_000:
                    raise ValueError('Invalid image dimensions')
                scaled = size.scaled(QSize(112, 128), Qt.AspectRatioMode.KeepAspectRatio)
                if reader.supportsAnimation():
                    movie = QMovie(str(asset), parent=self)
                    movie.setCacheMode(QMovie.CacheMode.CacheNone)
                    movie.setScaledSize(scaled)
                    if not movie.isValid():
                        movie.deleteLater()
                        raise ValueError('Invalid animation')
                    self.movie = movie
                    self.art.setMovie(movie)
                    movie.jumpToFrame(0)
                else:
                    image = reader.read()
                    if image.isNull():
                        raise ValueError('Invalid image')
                    self.art.setPixmap(QPixmap.fromImage(image).scaled(scaled, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.asset_ok = True
            except (OSError, ValueError, KeyError, TypeError):
                self.art.setText('呱搭素材暂不可用')
            self.state = state
        self.bubble.setText(f'有 {count} 个任务等你' if state == 'waiting' else f'有 {count} 个任务出错' if state == 'error' else '')
        self.bubble.setStyleSheet('color:#fff3d3;background:#302a38;border-radius:12px;font-size:11px;' if state in ('waiting', 'error') else 'background:transparent;')
        self.setToolTip(f'{state} · 单击查看会话，长按拖动呱搭')
        self.sync_animation()

    def update_snapshot(self, agents, online):
        state, count = aggregate(agents, online)
        self.stale = state is None
        if state is not None:
            self.set_visual(state, count)
        else:
            self.bubble.setText('采集暂停或状态待确认' if online else '服务断开 · 状态待确认')
            self.bubble.setStyleSheet('color:#ccc5d5;background:#302a38;border-radius:12px;font-size:10px;')
        self.sync_animation()

    def sync_animation(self):
        if not self.movie:
            return
        animate = self.isVisible() and not self.stale and not self.reduced_motion
        if animate and self.movie.state() == QMovie.MovieState.NotRunning:
            self.movie.start()
        elif self.movie.state() != QMovie.MovieState.NotRunning:
            self.movie.setPaused(not animate)

    def set_reduced_motion(self, value):
        self.reduced_motion = value
        self.sync_animation()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_animation()

    def hideEvent(self, event):
        if self.movie:
            self.movie.setPaused(True)
        super().hideEvent(event)
