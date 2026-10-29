"""Visible design preview only; never connects to the backend."""
import sys
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import QTimer
from waiting_notice import WaitingNotice

app = QApplication(sys.argv)
app.setApplicationName('Moyu Whistle · 效果预览')
notice = WaitingNotice(app.quit)
notice.status.setText('效果预览 · 不是实际审批请求，不会修改任何会话状态。')
notice.findChild(QPushButton, 'view-waiting').setText('看完了，关闭预览')
notice.findChild(QPushButton, 'dismiss').clicked.connect(app.quit)
notice.present('【效果预览】1 个会话等待你的操作\n\n• moyu-whistle · Codex')
QTimer.singleShot(500, lambda: print(f'Preview visible={notice.isVisible()}, animation={notice.movie is not None}', flush=True))
sys.exit(app.exec())
