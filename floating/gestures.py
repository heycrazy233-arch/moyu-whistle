"""Recognize gestures before Qt WebEngine forwards mouse events to Chromium."""
from PySide6.QtCore import QObject, QEvent, QPoint, QTimer, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid


class WindowGestures(QObject):
    HOLD_MS = 350

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.target = None
        self.dragging = False
        self.replaying = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.begin_drag)
        view.installEventFilter(self)
        if hasattr(view, 'loadFinished'):
            view.loadFinished.connect(self.install_input_filter)
        self.install_input_filter()
        QApplication.instance().applicationStateChanged.connect(
            lambda state: self.cancel() if state != Qt.ApplicationState.ApplicationActive else None)

    def install_input_filter(self, *_):
        receiver = self.view.focusProxy()
        if receiver is not None:
            receiver.installEventFilter(self)

    def belongs(self, target):
        return isinstance(target, QWidget) and (target is self.view or self.view.isAncestorOf(target))

    def begin_drag(self):
        if self.target is not None:
            self.dragging = True
            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
            self.view.move(self.origin + self.latest - self.start)

    def cancel(self):
        self.timer.stop()
        if self.target is not None:
            self.view.releaseMouse()
        if self.dragging:
            QApplication.restoreOverrideCursor()
        self.target = None
        self.dragging = False

    def eventFilter(self, target, event):
        if self.replaying:
            return False
        kind = event.type()
        if self.target is not None and (kind == QEvent.Type.ApplicationDeactivate or
                                       (target is self.view and kind == QEvent.Type.Hide)):
            self.cancel()
            return False
        if kind == QEvent.Type.MouseButtonPress and self.belongs(target) and event.button() == Qt.MouseButton.LeftButton:
            self.cancel()
            self.target = target
            self.press = QMouseEvent(event)
            self.start = event.globalPosition().toPoint()
            self.latest = QPoint(self.start)
            self.origin = self.view.pos()
            self.moved = False
            self.view.grabMouse()
            self.timer.start(self.HOLD_MS)
            return True
        if self.target is None:
            return False
        if kind == QEvent.Type.MouseMove:
            self.latest = event.globalPosition().toPoint()
            self.moved |= (self.latest - self.start).manhattanLength() > QApplication.startDragDistance()
            if self.dragging:
                self.view.move(self.origin + self.latest - self.start)
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            receiver, press = self.target, self.press
            short_click = not self.dragging and not self.moved
            self.cancel()
            if short_click and isValid(receiver):
                # Only a genuine short click reaches the webpage. A long press
                # never sends a press/release pair, so it cannot activate links.
                release = QMouseEvent(QEvent.Type.MouseButtonRelease, press.position(),
                                      event.globalPosition(), event.button(), event.buttons(), event.modifiers())
                release.setTimestamp(event.timestamp())
                self.replaying = True
                try:
                    QApplication.sendEvent(receiver, press)
                    QApplication.sendEvent(receiver, release)
                finally:
                    self.replaying = False
            return True
        return False
