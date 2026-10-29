"""Independent floating viewer. Connects to the existing backend; never starts it."""
import sys
import json


def main(on_ready=None):
    try:
        from PySide6.QtCore import QObject, Qt, QUrl, Slot, QTimer, QFile, QIODevice
        from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut, QIcon, QPixmap, QPainter
        from PySide6.QtWidgets import QApplication, QLabel, QWidget, QSystemTrayIcon, QMenu, QVBoxLayout, QPushButton
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        sys.exit('缺少桌面依赖。请在虚拟环境运行：pip install -r floating/requirements.txt')

    base = 'http://127.0.0.1:17321'
    app = QApplication(sys.argv)
    app.setApplicationName('摸鱼哨')

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            return url.toString() == base + '/assets/whistle.html'

    view = QWebEngineView()
    view.setWindowTitle('摸鱼哨')
    view.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    page = Page(view)
    page.setBackgroundColor(QColor('transparent'))
    view.setPage(page)

    from gestures import WindowGestures
    gestures = WindowGestures(view)

    def show_window():
        view.showNormal()
        view.raise_()

    tray = QSystemTrayIcon(app)
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QColor('#bcb3f2'))
    for x, height in ((8, 10), (15, 18), (22, 25)):
        painter.fillRect(x, 29 - height, 4, height, QColor('#bcb3f2'))
    painter.end()
    tray.setIcon(QIcon(pixmap))
    tray.setToolTip('摸鱼哨')
    menu = QMenu()
    menu.addAction('显示悬浮窗口', show_window)
    menu.addAction('打开控制台', lambda: QDesktopServices.openUrl(QUrl(base + '/')))
    menu.addSeparator()
    menu.addAction('退出 摸鱼哨', app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: show_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        tray.show()

    def open_waiting():
        show_window()
        view.page().runJavaScript("window.openWaiting && window.openWaiting()")
        notice.hide()

    from waiting_notice import WaitingNotice
    from alerts import WaitingMonitor
    notice = WaitingNotice(open_waiting)
    monitor = WaitingMonitor(base, app)
    monitor.changed.connect(notice.update_waiting)
    monitor.changed.connect(lambda agents, fresh, stale: tray.setToolTip(
        f'摸鱼哨 · {len(agents)} 个会话等待操作' if agents else '摸鱼哨'))
    quit_shortcut = QShortcut(QKeySequence.StandardKey.Quit, view)
    quit_shortcut.activated.connect(app.quit)
    unavailable = QLabel('本地服务未连接，正在重试…', view)
    unavailable.setGeometry(8, 8, 404, 60)
    unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
    unavailable.setStyleSheet('background: #19191f; color: #eeeef4; border-radius: 24px;')
    unavailable.hide()
    retry = QTimer(view)
    retry.setInterval(5000)
    retry.timeout.connect(lambda: view.load(QUrl(base + '/assets/whistle.html')))

    def loaded(ok):
        unavailable.setVisible(not ok)
        if ok:
            retry.stop()
        else:
            unavailable.raise_()
            retry.start()

    view.loadFinished.connect(loaded)

    class Bridge(QObject):
        @Slot(bool)
        def setExpanded(self, expanded):
            view.resize(420, 590 if expanded else 76)
            screen = view.screen().availableGeometry()
            view.move(max(screen.left(), min(view.x(), screen.right() - view.width() + 1)),
                      max(screen.top(), min(view.y(), screen.bottom() - view.height() + 1)))

        @Slot()
        def openDashboard(self):
            QDesktopServices.openUrl(QUrl(base + '/'))

        @Slot()
        def hideWindow(self):
            if tray.isVisible():
                view.hide()
            else:
                view.showMinimized()

        @Slot(str)
        def notifyWaiting(self, message):
            notice.present(message)

        @Slot()
        def clearWaiting(self):
            notice.hide()

    bridge = Bridge()
    channel = QWebChannel(page)
    channel.registerObject('whistle', bridge)
    page.setWebChannel(channel)
    script = QWebEngineScript()
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    bridge_source = QFile(':/qtwebchannel/qwebchannel.js')
    if not bridge_source.open(QIODevice.OpenModeFlag.ReadOnly):
        sys.exit('无法加载 Qt WebChannel 资源，请检查桌面依赖安装。')
    bridge_js = bytes(bridge_source.readAll()).decode('utf-8')
    bridge_source.close()
    script.setSourceCode(bridge_js + '\nnew QWebChannel(qt.webChannelTransport, channel => window.connectWhistle(channel.objects.whistle));')
    page.scripts().insert(script)
    view.resize(420, 76)
    area = app.primaryScreen().availableGeometry()
    view.move(area.center().x() - 210, area.top() + 12)
    view.load(QUrl(base + '/assets/whistle.html'))
    view.show()
    from companion import Companion

    def open_pet_state(state):
        show_window()
        selected = state if state in ('waiting', 'error', 'working', 'idle') else 'all'
        view.page().runJavaScript(f'window.openAgentState && window.openAgentState({json.dumps(selected)})')

    companion = Companion(view, open_pet_state)
    monitor.snapshot.connect(companion.update_snapshot)
    show_pet = menu.addAction('显示呱搭')
    show_pet.setCheckable(True)
    show_pet.setChecked(True)
    show_pet.toggled.connect(companion.setVisible)
    pause_pet = menu.addAction('暂停呱搭动画')
    pause_pet.setCheckable(True)
    pause_pet.toggled.connect(companion.set_reduced_motion)
    companion.show()
    monitor.start()
    if on_ready is not None:
        on_ready()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
