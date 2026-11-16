from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QScrollArea, QToolButton, QVBoxLayout, QWidget

from ..state import AppState
from ..widgets import label, card


class Page(QWidget):
    """A step of the guided flow: header + scrolling body."""
    changed = Signal()            # something the Next button depends on changed
    title = ""
    subtitle = ""
    key = ""

    def __init__(self, state: AppState):
        super().__init__()
        self.setObjectName("Page")
        self.state = state
        outer = QVBoxLayout(self)
        outer.setContentsMargins(44, 34, 44, 0)
        outer.setSpacing(6)
        self.title_lb = label(self.title, "title")
        self.sub_lb = label(self.subtitle, "sub", wrap=True)
        outer.addWidget(self.title_lb)
        outer.addWidget(self.sub_lb)
        outer.addSpacing(14)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("Page")
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(0, 0, 14, 28)
        self.body.setSpacing(16)
        self.scroll.setWidget(host)
        outer.addWidget(self.scroll, 1)

    # ---- hooks used by the window
    def on_enter(self) -> None: ...

    def validate(self) -> str | None:
        """Return a short reason the user can't continue yet, or None if the step is complete."""
        return None

    # ---- helpers
    def section(self, title: str = "", subtitle: str = ""):
        f, lay = card()
        if title:
            lay.addWidget(label(title, "h2"))
        if subtitle:
            lay.addWidget(label(subtitle, "muted", wrap=True))
        self.body.addWidget(f)
        return f, lay


class Collapsible(QWidget):
    """'Advanced options' disclosure."""

    def __init__(self, text="Advanced options"):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.btn = QToolButton()
        self.btn.setObjectName("Link")
        self.btn.setCheckable(True)
        self.btn.setCursor(Qt.PointingHandCursor)
        self._text = text
        self.btn.toggled.connect(self._toggle)
        lay.addWidget(self.btn, 0, Qt.AlignLeft)
        self.frame, self.inner = card()
        self.frame.setVisible(False)
        lay.addWidget(self.frame)
        self._toggle(False)

    def _toggle(self, on: bool):
        self.btn.setText(("▾  " if on else "▸  ") + self._text)
        self.frame.setVisible(on)
