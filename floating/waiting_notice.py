"""One visible, persistent prompt for all waiting agents."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QMovie, QCursor, QImageReader
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QApplication


class WaitingNotice(QWidget):
    def __init__(self, open_waiting):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName('waiting-notice')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(460)
        self.setStyleSheet('''
            QWidget#waiting-notice { background:#24212e; border:3px solid #f4bd58; border-radius:18px; }
            QLabel { color:#fff5e3; background:transparent; border:0; }
            QPushButton { padding:12px; border-radius:10px; background:#f4bd58; color:#211c14; font-size:15px; font-weight:bold; }
            QPushButton#dismiss { background:#393342; color:#ded8e8; font-size:12px; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        row = QHBoxLayout()
        art = QLabel('!')
        art.setFixedSize(112, 112)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(art)
        title = QLabel('需要你操作\nAgent 正在等待')
        title.setStyleSheet('font-size:24px;font-weight:bold;color:#ffd58a;')
        row.addWidget(title, 1)
        layout.addLayout(row)
        self.text = QLabel()
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setWordWrap(True)
        self.text.setStyleSheet('font-size:14px;line-height:1.5;')
        layout.addWidget(self.text)
        self.status = QLabel('等待确认、审批或必需输入。请在原会话中处理。')
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color:#c6bfce;font-size:12px;')
        layout.addWidget(self.status)
        button = QPushButton('查看等待会话 →')
        button.setObjectName('view-waiting')
        button.clicked.connect(open_waiting)
        layout.addWidget(button)
        dismiss = QPushButton('我知道了，暂时收起')
        dismiss.setObjectName('dismiss')
        dismiss.clicked.connect(self.hide)
        layout.addWidget(dismiss)
        self.movie = None
        try:
            root = Path(__file__).resolve().parents[1] / 'pet/assets/guada'
            manifest = json.loads((root / 'manifest.json').read_text(encoding="utf-8"))
            asset = (root / manifest['states']['waiting']).resolve()
            if asset.parent != root.resolve() or asset.stat().st_size > 10_000_000:
                raise ValueError('Invalid waiting asset')
            size = QImageReader(str(asset)).size()
            if not size.isValid() or size.width() * size.height() > 4_000_000:
                raise ValueError('Invalid waiting image dimensions')
            movie = QMovie(str(asset))
            movie.setScaledSize(QSize(112, 110))
            if movie.isValid():
                art.setMovie(movie)
                self.movie = movie
        except (OSError, ValueError, KeyError, TypeError):
            pass  # The prompt must still work when artwork is unavailable.

    def present(self, message):
        self.text.setText(message[:800])
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 22, area.bottom() - self.height() - 22)
        self.show()
        self.raise_()

    def update_waiting(self, agents, fresh, stale):
        if not agents:
            self.hide()
            return
        message = f'{len(agents)} 个会话等待你的操作\n\n' + '\n'.join(
            f"• {str(a.get('project') or '未命名项目')[:80]} · {str(a.get('agent_type') or 'Agent')[:30]}"
            for a in agents[:4])
        if len(agents) > 4:
            message += f'\n以及其他 {len(agents) - 4} 个会话'
        self.text.setText(message)
        self.status.setText('连接或采集暂不可用：保留上次等待，请核实原会话。' if stale else '等待确认、审批或必需输入。请在原会话中处理。')
        if fresh:
            self.present(message)
        if self.movie and self.isVisible():
            self.movie.setPaused(stale)

    def showEvent(self, event):
        super().showEvent(event)
        if self.movie:
            self.movie.start()

    def hideEvent(self, event):
        if self.movie:
            self.movie.setPaused(True)
        super().hideEvent(event)
