from __future__ import annotations

from datetime import datetime

from database import AgentStore
from state import STATUS_COLORS, AgentStatus


def pyside_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def run_desktop_ui(store: AgentStore) -> int:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )

    class AgentDockWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Agent Dock")
            self.setMinimumSize(760, 480)
            root = QWidget()
            self.setCentralWidget(root)
            self.layout = QVBoxLayout(root)
            self.layout.setContentsMargins(24, 20, 24, 20)
            self.layout.setSpacing(12)

            title = QLabel("Agent Dock")
            title.setFont(QFont("Arial", 22, QFont.Weight.Bold))
            self.layout.addWidget(title)

            subtitle = QLabel("Offline-first status center for remote coding agents")
            subtitle.setStyleSheet("color: #59616d;")
            self.layout.addWidget(subtitle)

            self.rows = QVBoxLayout()
            self.rows.setSpacing(8)
            self.layout.addLayout(self.rows)
            self.layout.addStretch(1)

            self.footer = QLabel()
            self.footer.setStyleSheet("color: #6b7280;")
            self.layout.addWidget(self.footer)

            self.timer = QTimer()
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1000)
            self.refresh()

        def clear_rows(self) -> None:
            while self.rows.count():
                child = self.rows.takeAt(0)
                widget = child.widget()
                if widget:
                    widget.deleteLater()

        def refresh(self) -> None:
            self.clear_rows()
            agents = store.list_agents()
            if not agents:
                empty = QLabel("No agents yet. Run fake_event_sender.py to simulate remote activity.")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setMinimumHeight(180)
                empty.setStyleSheet("color: #6b7280; border: 1px solid #d7dce2;")
                self.rows.addWidget(empty)
            for agent in agents:
                self.rows.addWidget(self.render_agent(agent))
            ts = datetime.now().strftime("%H:%M:%S")
            self.footer.setText(f"{len(agents)} agents · localhost:17321 · refreshed {ts}")

        def render_agent(self, agent: dict) -> QFrame:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame.setStyleSheet("QFrame { border: 1px solid #d7dce2; background: #fbfcfe; }")
            layout = QHBoxLayout(frame)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(12)

            dot = QLabel("●")
            dot.setFont(QFont("Arial", 18))
            dot.setStyleSheet(f"color: {STATUS_COLORS[AgentStatus(agent['event'])]}; border: none;")
            layout.addWidget(dot)

            name = QLabel(f"{agent['project']} / {agent['session_id']}")
            name.setFont(QFont("Arial", 13, QFont.Weight.Bold))
            name.setStyleSheet("border: none;")
            name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            layout.addWidget(name)

            meta = QLabel(f"{agent['server']} · {agent['agent_type']} · {agent['tmux_session'] or 'no tmux'}")
            meta.setStyleSheet("color: #59616d; border: none;")
            meta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            layout.addWidget(meta)

            message = QLabel(agent["message"])
            message.setStyleSheet("color: #303846; border: none;")
            message.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            layout.addWidget(message)

            state = QLabel(agent["event"].upper())
            state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            state.setMinimumWidth(88)
            state.setStyleSheet(
                f"color: white; background: {STATUS_COLORS[AgentStatus(agent['event'])]}; "
                "border: none; padding: 5px 8px;"
            )
            layout.addWidget(state)
            return frame

    app = QApplication([])
    window = AgentDockWindow()
    window.show()
    return app.exec()
