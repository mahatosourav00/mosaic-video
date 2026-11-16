from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QBrush
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..theme import C
from ..coffee import Signature
from ..widgets import label


class GoalArt(QWidget):
    """Little illustration for each goal card."""

    def __init__(self, kind: str, height: int = 120):
        super().__init__()
        self.kind = kind
        self.setFixedHeight(height)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor("#2A2760"))
        g.setColorAt(1, QColor("#16314A"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(0, 0, w, h, 14, 14)

        sz = min(88, h - 24)                      # the little mosaic scales with the card art's height

        def mosaic(x0, y0, size, n):
            cell = size / n
            import random
            rnd = random.Random(5)
            for i in range(n):
                for j in range(n):
                    d = ((i - n / 2 + .5) ** 2 + (j - n / 2 + .5) ** 2) ** .5 / (n / 2)
                    a = int(235 - 150 * min(d, 1) + rnd.randint(-25, 25))
                    c = QColor(150 + rnd.randint(-40, 40), 140 + rnd.randint(-30, 50), 255, max(40, min(255, a)))
                    p.setBrush(c)
                    p.drawRoundedRect(x0 + i * cell + 1, y0 + j * cell + 1, cell - 2, cell - 2, 2, 2)

        if self.kind == "image":
            mosaic(w / 2 - sz / 2, (h - sz) / 2, sz, 8)
        elif self.kind == "video":
            mosaic(w / 2 - sz / 2, (h - sz) / 2, sz, 8)
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawEllipse(w / 2 - sz / 4, h / 2 - sz / 4, sz / 2, sz / 2)
            p.setBrush(QColor("white"))
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            cx, cy = w / 2, h / 2
            p.drawPolygon(QPolygonF([QPointF(cx - 6, cy - 10), QPointF(cx - 6, cy + 10), QPointF(cx + 10, cy)]))
        else:                                   # "both": the mosaic with a small play badge in the corner
            mosaic(w / 2 - sz / 2, (h - sz) / 2, sz, 8)
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QPolygonF
            cx, cy = w / 2 + sz / 2 - 4, (h + sz) / 2 - 6
            p.setBrush(QColor(0, 0, 0, 170))
            p.drawEllipse(QPointF(cx, cy), 15, 15)
            p.setBrush(QColor("white"))
            p.drawPolygon(QPolygonF([QPointF(cx - 4, cy - 7), QPointF(cx - 4, cy + 7), QPointF(cx + 7, cy)]))


class GoalCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, text: str, chips: list[str], compact: bool = False):
        super().__init__()
        self.key = key
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self._hover(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        lay.addWidget(GoalArt(key, 84 if compact else 120))
        lay.addWidget(label(title, "title"))
        lay.addWidget(label(text, "sub", wrap=True))
        lay.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(6)
        for c in chips:
            row.addWidget(label(c, "chip"))
        row.addStretch(1)
        lay.addLayout(row)
        self.setMinimumWidth(250)

    def _hover(self, on: bool):
        self.setStyleSheet(f"QFrame#Card {{ background: {C['card2'] if on else C['card']};"
                           f" border: 1px solid {C['accent'] if on else C['border']}; border-radius: 18px; }}")

    def enterEvent(self, e):
        self._hover(True)

    def leaveEvent(self, e):
        self._hover(False)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.key)


class HomePage(QWidget):
    chosen = Signal(str)
    add_plugin = Signal()

    def __init__(self, plugins: dict | None = None):
        super().__init__()
        self.setObjectName("Page")
        outer = QVBoxLayout(self)                    # scrolls, so the cards keep their size however many plugins there are
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("Page")
        scroll.setWidget(host)
        outer.addWidget(scroll)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(56, 52, 56, 40)
        lay.setSpacing(8)
        lay.addWidget(label("What would you like to do?", "display"))
        lay.addWidget(label("Turn a folder of photos into one big picture made of tiny photos, and, if you like, a "
                            "cinematic animation of it coming together. Everything runs on your computer.",
                            "sub", wrap=True))
        lay.addSpacing(26)
        row = QHBoxLayout()
        row.setSpacing(22)
        cards = [
            GoalCard("both", "Create a mosaic", "Pick your photos and a main picture. You get the finished "
                     "high-resolution image, and can add an animation of it assembling itself.",
                     ["Image", "Optional video"]),
            GoalCard("video", "New video from a saved mosaic", "Already built a mosaic with Mosaic Studio? Try a "
                     "different animation style or format in seconds, without rebuilding it.",
                     ["MP4 · GIF · WebM"]),
        ]
        for c in cards:
            c.clicked.connect(self.chosen)
            row.addWidget(c)
        lay.addLayout(row)
        if plugins:                                   # one card per installed plugin, three to a row
            lay.addSpacing(22)
            lay.addWidget(label("Made for a purpose", "h2"))
            grid = QGridLayout()
            grid.setHorizontalSpacing(22)
            grid.setVerticalSpacing(22)
            for i, pl in enumerate(plugins.values()):
                c = GoalCard(f"plugin:{pl.id}", pl.name, pl.manifest.get("description", ""),
                             list(pl.manifest.get("chips") or []), compact=True)
                c.clicked.connect(self.chosen)
                grid.addWidget(c, i // 2, i % 2)
            for col in range(2):                       # same two columns as the cards above
                grid.setColumnStretch(col, 1)
            lay.addLayout(grid)
        lay.addStretch(1)
        foot = QHBoxLayout()
        foot.addWidget(label("Tip: you can drag a folder of photos onto the next screen.", "faint"))
        foot.addStretch(1)
        add = QPushButton("Add a plugin\u2026")
        add.setObjectName("Ghost")
        add.setToolTip("Pick a plugin folder (it has a plugin.json in it) to add its card to this screen.")
        add.clicked.connect(self.add_plugin)
        foot.addWidget(add)
        foot.addWidget(Signature())
        lay.addLayout(foot)
