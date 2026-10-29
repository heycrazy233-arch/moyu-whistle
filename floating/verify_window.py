"""Render our own window and check its bridge against the live read-only API."""
import json
import tempfile
from pathlib import Path
import faulthandler
faulthandler.enable()
from main import main

from PySide6.QtCore import QTimer, QPoint, QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon
from PySide6.QtWebEngineWidgets import QWebEngineView


def wait_height(view, expected):
    # Native resize follows asynchronously after Chromium and WebChannel.
    for _ in range(50):
        if view.height() == expected:
            return
        QTest.qWait(100)


def inspect():
    app = QApplication.instance()
    view = next(w for w in app.topLevelWidgets() if isinstance(w, QWebEngineView))
    # Deliver to Chromium's actual input widget, rather than an artificial overlay.
    target = view.focusProxy()
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(150, 35))
    wait_height(view, 590)
    if view.height() != 590:
        def diagnostic(value):
            print(f'FAIL: short click did not reach webpage: height={view.height()}, page={value}', flush=True)
            app.exit(1)
        view.page().runJavaScript("JSON.stringify({ready:document.readyState,bridge:!!window.whistleBridge,expanded:document.getElementById('toggle')?.getAttribute('aria-expanded')})", diagnostic)
        return
    for point in (QPoint(35, 35), QPoint(150, 35), QPoint(200, 280), QPoint(390, 35)):
        before = view.pos()
        start = target.mapToGlobal(point)
        press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(point), QPointF(start), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target, press)
        QTest.qWait(420)
        for kind, button, buttons in (
            (QEvent.Type.MouseMove, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
        ):
            event = QMouseEvent(kind, QPointF(point), QPointF(start + QPoint(45, 30)), button, buttons, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(target, event)
        QTest.qWait(150)
        if view.pos() != before + QPoint(45, 30) or view.height() != 590 or not view.isVisible():
            print(f'FAIL: long press drag or click suppression at {point}', flush=True)
            app.exit(1)
            return
        view.move(before)
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(150, 35))
    wait_height(view, 76)
    if view.height() != 76:
        print(f'FAIL: short click collapse, actual height={view.height()}', flush=True)
        app.exit(1)
        return
    print('PASS: actual WebEngine input short clicks; long press on icon/header/body/close button moves without activating', flush=True)
    pet = next(w for w in app.topLevelWidgets() if w.objectName() == 'guada-companion')
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(75, 90))
    wait_height(view, 590)
    if view.height() != 590:
        print('FAIL: pet click did not expand existing WebEngine window', flush=True)
        app.exit(1)
        return
    view.page().runJavaScript("document.getElementById('toggle').click()")
    wait_height(view, 76)
    print('PASS: companion click expands existing window', flush=True)

    def opened(result):
        if not result:
            print('FAIL: page or native bridge unavailable', flush=True)
            app.exit(1)
            return

        def capture(attempt=0):
            if view.height() != 590 and attempt < 40:
                QTimer.singleShot(100, lambda: capture(attempt + 1))
                return
            path = str(Path(tempfile.gettempdir()) / 'moyu-whistle-preview.png')
            saved = view.grab().save(path)
            if view.height() != 590:
                print(f'FAIL: native expansion, actual={view.width()}x{view.height()}', flush=True)
                app.exit(1)
                return
            print(json.dumps({'expanded_height': view.height(), 'screenshot': path, 'saved': saved}), flush=True)
            view.page().runJavaScript("document.getElementById('toggle').click()")

            def finish(attempt=0):
                if view.height() != 76 and attempt < 40:
                    QTimer.singleShot(100, lambda: finish(attempt + 1))
                    return
                ok = view.height() == 76
                if ok:
                    view.grab().save(str(Path(tempfile.gettempdir()) / 'moyu-whistle-collapsed.png'))
                print('PASS: native collapse' if ok else 'FAIL: native collapse', flush=True)
                if not ok or not saved:
                    app.exit(1)
                    return
                tray = app.findChild(QSystemTrayIcon)
                view.page().runJavaScript("document.getElementById('quit').click()")

                def restore():
                    hidden = not view.isVisible() if tray.isVisible() else view.isMinimized()
                    tray.contextMenu().actions()[0].trigger()
                    restored = view.isVisible() and not view.isMinimized()
                    print(f'Hide/restore: hidden={hidden}, restored={restored}', flush=True)
                    if not (hidden and restored):
                        app.exit(1)
                        return
                    # Exercise the registered native slot synchronously. The live
                    # snapshot correctly clears a synthetic notice on its next
                    # refresh; waiting for that poll made this test race itself.
                    bridge = view.page().webChannel().registeredObjects()['whistle']
                    bridge.notifyWaiting('隔离界面测试：Waiting 提醒，不写入后端')
                    notice = next(w for w in app.topLevelWidgets() if w.objectName() == 'waiting-notice')
                    ok = notice.isVisible() and notice.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
                    notice.grab().save(str(Path(tempfile.gettempdir()) / 'moyu-whistle-waiting-notice.png'))
                    print(f'Waiting popup visible, no-focus flag: {ok}', flush=True)
                    notice.hide()
                    app.exit(0 if ok else 1)

                QTimer.singleShot(700, restore)

            QTimer.singleShot(600, finish)

        QTimer.singleShot(1200, capture)

    view.page().runJavaScript("Boolean(window.whistleBridge && (document.getElementById('toggle').click(), true))", opened)


def ready():
    QTimer.singleShot(6000, inspect)
    QTimer.singleShot(35000, lambda: QApplication.instance().exit(1))


main(ready)
