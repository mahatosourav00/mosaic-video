"""Reusable, styled building blocks."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .help_text import HELP
from .theme import C


def label(text: str = "", role: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


def clear_layout(layout, keep: int = 0) -> None:
    """Remove widgets from a layout right away (deleteLater alone leaves them painted until the event loop runs)."""
    while layout.count() > keep:
        item = layout.takeAt(keep)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    f.setFixedHeight(1)
    return f


def card(layout_cls=QVBoxLayout, margins=(22, 20, 22, 20), spacing=14, flat=False) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("CardFlat" if flat else "Card")
    lay = layout_cls(f)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return f, lay


# ------------------------------------------------------------------------------------------ help
class HelpPopup(QFrame):
    def __init__(self, key: str, parent=None):
        super().__init__(parent, Qt.Popup)
        title, body, rec = HELP.get(key, (key, "", ""))
        self.setStyleSheet(f"QFrame#HelpPop {{ background: {C['card2']}; border: 1px solid {C['border_hi']};"
                           f" border-radius: 12px; }}")
        self.setObjectName("HelpPop")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(label(title, "h2"))
        b = label(body, "sub", wrap=True)
        b.setStyleSheet("font-size: 13px;")
        lay.addWidget(b)
        if rec:
            r = QLabel(f"Recommended:  {rec}")
            r.setWordWrap(True)
            r.setStyleSheet(f"color: {C['accent2']}; font-weight: 600; font-size: 12px;")
            lay.addWidget(r)
        self.setFixedWidth(330)


class HelpButton(QToolButton):
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Help")
        self.setText("?")
        self.setCursor(Qt.PointingHandCursor)
        self.key = key
        title, body, rec = HELP.get(key, (key, "", ""))
        self.setToolTip(f"{title}: click for help")
        self.clicked.connect(self._show)

    def _show(self):
        pop = HelpPopup(self.key, self.window())
        pop.adjustSize()
        pos = self.mapToGlobal(QPoint(self.width() + 8, -8))
        screen = self.screen().availableGeometry()
        pos.setX(min(pos.x(), screen.right() - pop.width() - 10))
        pos.setY(min(pos.y(), screen.bottom() - pop.sizeHint().height() - 10))
        pop.move(pos)
        pop.show()


# ------------------------------------------------------------------------------------------ controls
class Toggle(QAbstractButton):
    """iOS-style switch."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 26)

    def sizeHint(self):
        return QSize(44, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        en = self.isEnabled()
        track = QColor(C["accent"] if on else "#2D3340")
        if not en:
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 1, 44, 24), 12, 12)
        p.setBrush(QColor("white" if en else "#9aa"))
        x = 22 if on else 3
        p.drawEllipse(QRectF(x, 4, 18, 18))


class SliderField(QWidget):
    """Slider + live value text. `fmt` turns the number into display text."""
    changed = Signal(float)

    def __init__(self, lo: float, hi: float, value: float, step: float = 1.0,
                 fmt: Callable[[float], str] = lambda v: f"{v:g}", recommended: float | None = None, parent=None):
        super().__init__(parent)
        self.lo, self.step, self.fmt, self.recommended = lo, step, fmt, recommended
        n = int(round((hi - lo) / step))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, n)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.setMinimumWidth(190)
        self.value_lb = label("", "value")
        self.value_lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.chip = label("recommended", "chip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.value_lb)
        lay.addWidget(self.chip)
        self.setMinimumWidth(320)
        self.slider.valueChanged.connect(self._on)
        self.set_value(value, emit=False)

    def value(self) -> float:
        return round(self.lo + self.slider.value() * self.step, 6)

    def set_value(self, v: float, emit=True):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        self.slider.blockSignals(False)
        self._refresh()
        if emit:
            self.changed.emit(self.value())

    def _refresh(self):
        v = self.value()
        self.value_lb.setText(self.fmt(v))
        self.chip.setVisible(self.recommended is not None and abs(v - self.recommended) < 1e-9)

    def _on(self, _):
        self._refresh()
        self.changed.emit(self.value())


class Segmented(QFrame):
    """Exclusive pill buttons. options: [(key, text)]"""
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], value: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("SegBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        if value in self.buttons:
            self.buttons[value].setChecked(True)
        elif self.buttons:
            next(iter(self.buttons.values())).setChecked(True)

    def value(self) -> str:
        for k, b in self.buttons.items():
            if b.isChecked():
                return k
        return ""

    def set_value(self, key: str, emit=False):
        if key in self.buttons:
            self.buttons[key].setChecked(True)
            if emit:
                self.changed.emit(key)


class OptionRow(QWidget):
    """label (+ help) and optional one-line description on the left, the control on the right."""

    def __init__(self, title: str, help_key: str | None, control: QWidget, desc: str = "", parent=None):
        super().__init__(parent)
        self.control = control
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(20)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title_lb = label(title, "h2")
        self.title_lb.setStyleSheet("font-size: 14px;")
        head.addWidget(self.title_lb)
        if help_key:
            head.addWidget(HelpButton(help_key))
        head.addStretch(1)
        left.addLayout(head)
        self.desc_lb = label(desc, "muted", wrap=True)
        self.desc_lb.setVisible(bool(desc))
        left.addWidget(self.desc_lb)
        wl = QWidget()
        wl.setLayout(left)
        wl.setMinimumWidth(240)
        wl.setMaximumWidth(330)
        outer.addWidget(wl, 3)
        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred) if isinstance(control, SliderField) else None
        outer.addWidget(control, 7, Qt.AlignVCenter | (Qt.AlignRight if isinstance(control, (Toggle, Segmented))
                                                       else Qt.AlignLeft))

    def set_desc(self, text: str):
        self.desc_lb.setText(text)
        self.desc_lb.setVisible(bool(text))


class Banner(QFrame):
    """Tip / warning / success strip with an optional action button."""

    def __init__(self, kind="tip", text="", action_text="", on_action: Callable | None = None, parent=None):
        super().__init__(parent)
        self.kind = kind
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 14, 12)
        lay.setSpacing(12)
        self.icon = QLabel()
        self.icon.setFixedWidth(20)
        self.text_lb = QLabel(text)
        self.text_lb.setWordWrap(True)
        self.btn = QPushButton(action_text)
        self.btn.setObjectName("Ghost")
        self.btn.setStyleSheet(f"color: {C['accent2']};")
        self.btn.setVisible(bool(action_text))
        if on_action:
            self.btn.clicked.connect(on_action)
        lay.addWidget(self.icon, 0, Qt.AlignTop)
        lay.addWidget(self.text_lb, 1)
        lay.addWidget(self.btn)
        self.set_kind(kind)

    def set_kind(self, kind: str):
        col = {"tip": C["accent2"], "warn": C["warn"], "ok": C["ok"], "bad": C["bad"]}[kind]
        glyph = {"tip": "i", "warn": "!", "ok": "✓", "bad": "×"}[kind]
        bg = {"tip": "#142029", "warn": "#2A2213", "ok": "#12261A", "bad": "#2B1618"}[kind]
        self.setStyleSheet(f"Banner {{ background: {bg}; border: 1px solid {col}44; border-radius: 12px; }}")
        self.icon.setText(glyph)
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet(f"color: {col}; font-weight: 800; font-size: 15px;")
        self.text_lb.setStyleSheet("color: #D5D9E4; font-size: 13px;")

    def set_text(self, text: str, kind: str | None = None):
        if kind and kind != self.kind:
            self.kind = kind
            self.set_kind(kind)
        self.text_lb.setText(text)


class PathPicker(QFrame):
    """Drop-zone / browse box for a folder or a file. Emits `changed(path)`."""
    changed = Signal(str)

    def __init__(self, kind: str, prompt: str, hint: str = "", file_filter: str = "", parent=None):
        super().__init__(parent)
        self.kind, self.file_filter, self.prompt = kind, file_filter, prompt
        self.path = ""
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("CardFlat")
        self.setMinimumHeight(96)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(16)
        self.thumb = QLabel()
        self.thumb.setFixedSize(68, 68)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f"background: {C['card2']}; border-radius: 12px; color: {C['faint']}; font-size: 26px;")
        self.thumb.setText("🗂" if kind == "folder" else "🖼")
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title_lb = label(prompt, "h2")
        self.sub_lb = label(hint, "muted", wrap=True)
        col.addStretch(1)
        col.addWidget(self.title_lb)
        col.addWidget(self.sub_lb)
        col.addStretch(1)
        self.btn = QPushButton("Choose…")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self.browse)
        lay.addWidget(self.thumb)
        lay.addLayout(col, 1)
        lay.addWidget(self.btn)
        self._hint = hint
        self._set_idle_style()

    def _set_idle_style(self, hover=False):
        bc = C["accent"] if hover else C["border_hi"]
        self.setStyleSheet(f"QFrame#CardFlat {{ background: {C['surface']}; border: 1.5px dashed {bc};"
                           f" border-radius: 14px; }}")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.browse()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_idle_style(True)

    def dragLeaveEvent(self, _):
        self._set_idle_style()

    def dropEvent(self, e):
        self._set_idle_style()
        urls = e.mimeData().urls()
        if urls:
            p = urls[0].toLocalFile()
            if self.kind == "folder" and os.path.isfile(p):
                p = os.path.dirname(p)
            self.set_path(p)

    def browse(self):
        start = self.path or str(Path.home() / "Pictures")
        if self.kind == "folder":
            p = QFileDialog.getExistingDirectory(self.window(), self.prompt, start)
        else:
            p, _ = QFileDialog.getOpenFileName(self.window(), self.prompt, start, self.file_filter)
        if p:
            self.set_path(p)

    def set_path(self, p: str, emit=True):
        self.path = p
        if not p:
            self.title_lb.setText(self.prompt)
            self.sub_lb.setText(self._hint)
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("🗂" if self.kind == "folder" else "🖼")
            return
        self.title_lb.setText(Path(p).name or p)
        self.sub_lb.setText(str(Path(p).parent if self.kind == "file" else p))
        self.btn.setText("Change")
        if self.kind == "file" and Path(p).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
            pm = QPixmap(p)
            if not pm.isNull():
                self.thumb.setText("")
                self.thumb.setPixmap(pm.scaled(68, 68, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                                     .copy(0, 0, 68, 68))
        if emit:
            self.changed.emit(p)

    def set_status(self, text: str):
        self.sub_lb.setText(text)


class StepRail(QFrame):
    """Left progress rail: numbered steps with the current one highlighted."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Rail")
        self.setFixedWidth(232)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 26, 18, 22)
        self._lay.setSpacing(4)
        brand = QHBoxLayout()
        dot = QLabel("◆")
        dot.setStyleSheet(f"color: {C['accent']}; font-size: 18px;")
        name = label("Mosaic Studio", "h2")
        name.setStyleSheet("font-size: 16px; font-weight: 700;")
        brand.addWidget(dot)
        brand.addWidget(name)
        brand.addStretch(1)
        self._lay.addLayout(brand)
        self._lay.addSpacing(26)
        self._items: list[QLabel] = []
        self._holder = QVBoxLayout()
        self._holder.setSpacing(2)
        self._lay.addLayout(self._holder)
        self._lay.addStretch(1)
        self.save_btn = QPushButton("Save settings…")
        self.load_btn = QPushButton("Load settings…")
        for b in (self.save_btn, self.load_btn):
            b.setObjectName("Ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("text-align: left; padding: 7px 8px;")
            self._lay.addWidget(b)
        self._lay.addSpacing(8)
        self.signature_slot = QVBoxLayout()
        self._lay.addLayout(self.signature_slot)
        self._lay.addSpacing(6)
        self.foot = label("", "faint", wrap=True)
        self._lay.addWidget(self.foot)

    def set_steps(self, names: list[str], current: int):
        clear_layout(self._holder)
        for i, n in enumerate(names):
            done, cur = i < current, i == current
            row = QLabel()
            row.setTextFormat(Qt.RichText)
            num = "✓" if done else str(i + 1)
            col = C["text"] if cur else (C["muted"] if done else C["faint"])
            badge = (f"background:{C['accent']};color:white;" if cur else
                     (f"background:{C['accent_soft']};color:#CFC9FF;" if done else
                      f"background:{C['card2']};color:{C['faint']};"))
            row.setText(f"<span style='{badge} border-radius:11px; padding:2px 8px; font-weight:700;'>&nbsp;{num}&nbsp;"
                        f"</span>&nbsp;&nbsp;<span style='color:{col}; font-weight:{600 if cur else 500};'>{n}</span>")
            row.setStyleSheet(f"padding: 9px 8px; border-radius: 10px;"
                              f"{'background:' + C['card'] + ';' if cur else ''}")
            self._holder.addWidget(row)


class ChipList(QWidget):
    """A titled list of removable paths (extra folders, excluded folders). Emits `changed(list)`."""
    changed = Signal(list)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.items: list[str] = []
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self.title_lb = label(title, "muted")
        self._lay.addWidget(self.title_lb)
        self.setVisible(False)

    def set_items(self, items: list[str], emit=False):
        self.items = list(items)
        clear_layout(self._lay, keep=1)
        for i, p in enumerate(self.items):
            row = QFrame()
            row.setObjectName("CardFlat")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 6, 6, 6)
            name = QLabel(f"{Path(p).name}   <span style='color:{C['faint']}'>{p}</span>")
            name.setTextFormat(Qt.RichText)
            name.setToolTip(p)
            x = QToolButton()
            x.setText("✕")
            x.setObjectName("Help")
            x.setCursor(Qt.PointingHandCursor)
            x.clicked.connect(lambda _=False, idx=i: self._remove(idx))
            h.addWidget(name, 1)
            h.addWidget(x)
            self._lay.addWidget(row)
        self.setVisible(bool(self.items))
        if emit:
            self.changed.emit(self.items)

    def add(self, p: str):
        if p and p not in self.items:
            self.set_items(self.items + [p], emit=True)

    def _remove(self, idx: int):
        self.set_items(self.items[:idx] + self.items[idx + 1:], emit=True)
