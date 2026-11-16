from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ..state import STYLES, VIDEO_SHAPES
from ..theme import C
from ..widgets import Banner, OptionRow, Segmented, SliderField, Toggle, hline, label
from .base import Collapsible, Page

PCT = lambda v: f"{int(round(v * 100))}%"                      # noqa: E731


class StyleArt(QWidget):
    """A tiny diagram of the style's motion."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.setFixedHeight(96)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#10131A"))
        p.drawRoundedRect(0, 0, w, h, 12, 12)
        rnd = random.Random(7)
        cx, cy = w / 2, h / 2

        def tile(x, y, s, a, col):
            p.save()
            p.translate(x, y)
            p.rotate(a)
            p.setBrush(col)
            p.drawRoundedRect(-s / 2, -s / 2, s, s, 1.5, 1.5)
            p.restore()

        if self.kind == "vortex":
            for i in range(70):
                t = i / 70
                ang = t * 9.5
                r = 6 + t * min(w, h) * 0.55
                col = QColor(139, 124, 255, int(255 * (1 - t * .6)))
                tile(cx + math.cos(ang) * r * 1.3, cy + math.sin(ang) * r * .85, 3 + 5 * (1 - t), math.degrees(ang), col)
        elif self.kind == "wave":
            for i in range(48):
                x = 12 + i * (w - 24) / 47
                for j in range(3):
                    y = cy + math.sin(i * .35 + j * .8) * 18 + (j - 1) * 17
                    a = int(255 * (0.25 + 0.75 * i / 47))
                    tile(x, y, 6, 0, QColor(79, 195, 247, a))
        elif self.kind == "zoom":
            for k in range(7):
                s = 12 + k * 22
                a = int(255 * (1 - k / 8))
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(139, 124, 255, a), 2))
                p.drawRoundedRect(cx - s / 2 * 1.2, cy - s / 2 * .8, s * 1.2, s * .8, 3, 3)
            p.setPen(Qt.NoPen)
            for i in range(24):
                ang = i / 24 * 2 * math.pi
                r = 36 + rnd.random() * 30
                tile(cx + math.cos(ang) * r * 1.2, cy + math.sin(ang) * r * .75, 5, math.degrees(ang),
                     QColor(79, 195, 247, 200))
        else:  # swarm
            for i in range(64):
                x, y = rnd.random() * (w - 20) + 10, rnd.random() * (h - 20) + 10
                col = QColor(139, 124, 255, rnd.randint(90, 255)) if rnd.random() > .35 else QColor(79, 195, 247, 200)
                tile(x, y, rnd.randint(4, 9), rnd.randint(0, 90), col)


class StyleCard(QFrame):
    picked = Signal(str)

    def __init__(self, key: str, name: str, text: str):
        super().__init__()
        self.key = key
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)
        lay.addWidget(StyleArt(key))
        self.name_lb = label(name, "h2")
        lay.addWidget(self.name_lb)
        lay.addWidget(label(text, "muted", wrap=True))
        lay.addStretch(1)
        self.set_selected(False)

    def set_selected(self, on: bool):
        self.setStyleSheet(
            f"StyleCard {{ background: {C['accent_dim'] if on else C['card']};"
            f" border: {2 if on else 1}px solid {C['accent'] if on else C['border']}; border-radius: 16px; }}")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.picked.emit(self.key)


class VideoPage(Page):
    key = "video"
    title = "Design your video"
    subtitle = "Pick an animation style, then choose length and quality."

    def __init__(self, state):
        super().__init__(state)
        s = state.settings
        # ---------------------------------------------------------------- style cards
        f, lay = self.section()
        head = QHBoxLayout()
        head.addWidget(label("Animation style", "h2"))
        from ..widgets import HelpButton
        head.addWidget(HelpButton("video_style"))
        head.addStretch(1)
        lay.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.cards: dict[str, StyleCard] = {}
        for k, (name, text) in STYLES.items():
            c = StyleCard(k, name, text)
            c.picked.connect(self._style)
            self.cards[k] = c
            row.addWidget(c)
        lay.addLayout(row)
        self.tip = Banner("tip", "Tip: choose Draft quality below to preview a style in seconds, then switch to "
                          "Standard for the final video.")
        lay.addWidget(self.tip)

        # ---------------------------------------------------------------- basics
        f2, lay2 = self.section("Basics")
        self.length = SliderField(8, 40, s.duration, 1, lambda v: f"{int(v)} seconds", recommended=20)
        self.length.changed.connect(lambda v: setattr(s, "duration", float(v)))
        lay2.addWidget(OptionRow("Length", "length", self.length))
        lay2.addWidget(hline())
        self.quality = Segmented([("draft", "Draft preview"), ("standard", "Standard"), ("high", "High")],
                                 state.quality)
        self.quality.changed.connect(self._quality)
        self.q_row = OptionRow("Quality", "quality", self.quality)
        lay2.addWidget(self.q_row)
        lay2.addWidget(hline())
        self.res = Segmented([("720", "720p"), ("1080", "1080p"), ("1440", "1440p"), ("2160", "4K")],
                             str(s.video_res))
        self.res.changed.connect(lambda k: setattr(s, "video_res", int(k)))
        lay2.addWidget(OptionRow("Resolution", "resolution", self.res, "Short side of the video, in pixels."))
        lay2.addWidget(hline())
        self.fmt = Segmented([("mp4", "MP4"), ("mp4-h265", "MP4 (H.265)"), ("webm", "WebM"), ("gif", "GIF")],
                             s.video_format)
        self.fmt.changed.connect(lambda k: setattr(s, "video_format", k))
        lay2.addWidget(OptionRow("File type", "format", self.fmt))
        lay2.addWidget(hline())
        self.vshape = Segmented([(k, v) for k, v in VIDEO_SHAPES.items()], s.video_aspect)
        self.vshape.changed.connect(lambda k: setattr(s, "video_aspect", k))
        lay2.addWidget(OptionRow("Video shape", "video_shape", self.vshape,
                                 "By default the video has the same shape as your mosaic."))

        # ---------------------------------------------------------------- advanced
        adv = Collapsible("Advanced options")
        self.adv_sliders: dict[str, SliderField] = {}
        self.fps = Segmented([("30", "30 fps"), ("60", "60 fps")], str(s.fps))
        self.fps.changed.connect(lambda k: setattr(s, "fps", int(k)))
        adv.inner.addWidget(OptionRow("Smoothness", "fps", self.fps))
        for title, key, field, lo, hi, step, fmt, rec in (
                ("Showcase photos", "showcase", "hero_tiles", 0, 30, 1, lambda v: "Off" if v == 0 else f"{int(v)}", 18),
                ("Depth blur", "dof", "dof", 0, 1, 0.05, PCT, 0.7),
                ("Glow and shadow", "glow", "glow", 0, 1, 0.05, PCT, 0.6),
                ("Floating dust", "particles", "particles", 0, 500, 20, lambda v: "Off" if v == 0 else f"{int(v)}", 220),
                ("Arrival waves", "pulses", "pulses", 0, 8, 1, lambda v: "Off" if v == 0 else f"{int(v)}", 4)):
            adv.inner.addWidget(hline())
            sl = SliderField(lo, hi, getattr(s, field), step, fmt, recommended=rec)
            sl.changed.connect(lambda v, f=field, integer=isinstance(getattr(s, field), int):
                               setattr(s, f, int(v) if integer else float(v)))
            self.adv_sliders[field] = sl
            adv.inner.addWidget(OptionRow(title, key, sl))
        adv.inner.addWidget(hline())
        self.backdrop = Toggle(s.backdrop)
        self.backdrop.toggled.connect(lambda on: setattr(s, "backdrop", on))
        adv.inner.addWidget(OptionRow("Blurred backdrop", "backdrop", self.backdrop))
        self.body.addWidget(adv)
        self.body.addStretch(1)
        self._style(s.style)

    def sync(self):
        st, s = self.state, self.state.settings
        self._style(s.style)
        self.length.set_value(s.duration, emit=False)
        self.quality.set_value(st.quality)
        self.res.set_value(str(s.video_res))
        self.fmt.set_value(s.video_format)
        self.vshape.set_value(s.video_aspect)
        self.fps.set_value(str(s.fps))
        for f, sl in self.adv_sliders.items():
            sl.set_value(getattr(s, f), emit=False)
        self.backdrop.blockSignals(True)
        self.backdrop.setChecked(s.backdrop)
        self.backdrop.blockSignals(False)
        self.backdrop.update()

    def on_enter(self):
        st = self.state
        self.fmt.setEnabled(True)
        pass

    def _style(self, key: str):
        self.state.settings.style = key
        for k, c in self.cards.items():
            c.set_selected(k == key)

    def _quality(self, key: str):
        self.state.quality = key
