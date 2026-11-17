"""A step of a plugin's flow, built from the field list in its plugin.json (no plugin code runs in the window)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QLineEdit, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from .widgets import OptionRow, PathPicker, Segmented, SliderField, Toggle, card, label
from .pages.base import Collapsible, Page


def _spacer() -> QWidget:
    w = QWidget()
    w.setFixedSize(1, 1)
    return w


def _show(v) -> str:
    return "on" if v is True else "off" if v is False else str(v)


def field_guide(f: dict) -> tuple[str, str, str]:
    """What the "?" next to a plugin option explains: (title, explanation, recommendation).

    A plugin can write its own with `tip` (a longer explanation than the short `help` line) and `recommended`.
    Without them the guide is built from `help` plus what the control does, so every option has a "?"."""
    typ, title = f.get("type"), f.get("label", f.get("key", ""))
    lines = [t for t in (f.get("tip"), None if f.get("tip") else f.get("help")) if t]
    how = {
        "text": "Type your own text.",
        "multiline": "Type or paste your text. Line breaks are kept.",
        "list": "Type one item per line.",
        "toggle": "Turn the switch on or off.",
        "color": "Click the colour to choose another one.",
        "file": "Click the box to browse for a file, or drop it there.",
        "folder": "Click the box to browse for a folder, or drop it there.",
    }.get(typ, "")
    if typ == "number":
        unit = f" {f['unit']}" if f.get("unit") else ""
        how = f"Drag the slider to choose a value from {f['min']:g}{unit} to {f['max']:g}{unit}."
    elif typ == "choice":
        shown = ", ".join(str(o[1]) for o in f.get("options", []))
        how = f"Pick one of: {shown}."
    if typ in ("file", "folder") and f.get("filter"):
        how += f" ({f['filter']})"
    lines.append(how)
    if f.get("required"):
        lines.append("This one is required: the Next button waits until it is filled in.")
    elif f.get("advanced"):
        lines.append("Most people can leave this alone.")
    rec = f.get("recommended", "")
    if not rec and "default" in f and typ in ("number", "toggle", "choice", "color"):
        d = f["default"]
        if typ == "choice":
            d = next((str(o[1]) for o in f.get("options", []) if str(o[0]) == str(d)), d)
        rec = f"{_show(d)} (the default)"
    return (title.replace("*", "").strip() or "Option", "  ".join(l for l in lines if l), rec)


class ColorButton(QPushButton):
    def __init__(self, value: str, on_change):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(120)
        self._on = on_change
        self.value = value
        self.clicked.connect(self._pick)
        self.set_value(value)

    def set_value(self, v: str):
        self.value = v
        c = QColor(v)
        dark = c.lightness() < 128
        self.setText(v.upper())
        self.setStyleSheet(f"background: {v}; color: {'#fff' if dark else '#000'}; border-radius: 8px; padding: 6px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.value), self.window(), "Choose a colour")
        if c.isValid():
            self.set_value(c.name())
            self._on(self.value)


class PluginStepPage(Page):
    """One step of a plugin: its sections and fields. Values live in `state.values_of(plugin_id)` (flat dotted keys)."""

    def __init__(self, state, plugin, index: int):
        self.plugin = plugin
        step = plugin.steps[index]
        self.key = f"plugin.{plugin.id}.{index}"
        self.title, self.subtitle = step.get("title", plugin.name), step.get("subtitle", "")
        super().__init__(state)
        self.step = step
        self.fields: dict[str, dict] = {}
        self.setters: dict = {}                       # key -> function(value) that updates the control
        adv: Collapsible | None = None
        for sec in step.get("sections", []):
            _, lay = self.section(sec.get("title", ""), sec.get("subtitle", ""))
            for f in sec.get("fields", []):
                target = lay
                if f.get("advanced"):
                    if adv is None:
                        adv = Collapsible()
                    target = adv.inner
                self._add_field(target, f)
        if adv is not None:
            self.body.addWidget(adv)
        self.body.addStretch(1)

    @property
    def values(self) -> dict:
        return self.state.values_of(self.plugin.id)

    # ------------------------------------------------------------------ building
    def _set(self, key: str, value) -> None:
        self.values[key] = value
        self.changed.emit()

    def _add_field(self, lay: QVBoxLayout, f: dict) -> None:
        key, typ = f["key"], f["type"]
        self.fields[key] = f
        cur = self.values.get(key, f.get("default"))
        title, desc = f.get("label", key), f.get("help", "")
        wide = False
        if typ == "text":
            w = QLineEdit(str(cur or ""))
            w.setMinimumWidth(280)
            w.textChanged.connect(lambda t, k=key: self._set(k, t))
            self.setters[key] = lambda v, w=w: w.setText(str(v or ""))
        elif typ in ("multiline", "list"):
            wide = True
            w = QPlainTextEdit()
            w.setMinimumHeight(150 if typ == "multiline" else 76)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            as_text = (lambda v: "\n".join(v)) if typ == "list" else (lambda v: str(v or ""))
            from_text = (lambda t: [ln for ln in t.splitlines()]) if typ == "list" else (lambda t: t)
            w.setPlainText(as_text(cur))
            w.textChanged.connect(lambda w=w, k=key, ft=from_text: self._set(k, ft(w.toPlainText())))
            self.setters[key] = lambda v, w=w, at=as_text: w.setPlainText(at(v))
        elif typ == "number":
            unit = f.get("unit", "")
            step = float(f.get("step", 1))
            w = SliderField(float(f["min"]), float(f["max"]), float(cur if cur is not None else f["min"]), step,
                            fmt=lambda v, u=unit, s=step: (f"{int(v)}" if s >= 1 else f"{v:g}") + (f" {u}" if u else ""))
            w.changed.connect(lambda v, k=key, s=step: self._set(k, int(v) if s >= 1 and float(s).is_integer() else float(v)))
            self.setters[key] = lambda v, w=w: w.set_value(float(v), emit=False)
        elif typ == "toggle":
            w = Toggle(bool(cur))
            w.toggled.connect(lambda on, k=key: self._set(k, bool(on)))
            self.setters[key] = lambda v, w=w: w.setChecked(bool(v))
        elif typ == "choice":
            opts = [(str(o[0]), str(o[1])) for o in f["options"]]
            if len(opts) <= 4:
                w = Segmented(opts, str(cur))
                w.changed.connect(lambda v, k=key: self._set(k, v))
                self.setters[key] = lambda v, w=w: w.set_value(str(v))
            else:
                w = QComboBox()
                for val, text in opts:
                    w.addItem(text, val)
                w.setCurrentIndex(max(0, w.findData(str(cur))))
                w.currentIndexChanged.connect(lambda _i, w=w, k=key: self._set(k, w.currentData()))
                self.setters[key] = lambda v, w=w: w.setCurrentIndex(max(0, w.findData(str(v))))
        elif typ == "color":
            w = ColorButton(str(cur or "#FFFFFF"), lambda v, k=key: self._set(k, v))
            self.setters[key] = lambda v, w=w: w.set_value(str(v))
        else:                                         # file | folder
            wide = True
            prompt = f.get("prompt", title)
            w = PathPicker("folder" if typ == "folder" else "file", prompt,
                           "Drop it here, or click to browse", f.get("filter", ""))
            if cur and Path(str(cur)).exists():
                w.set_path(str(cur), emit=False)
            w.changed.connect(lambda p, k=key: self._set(k, p))
            self.setters[key] = lambda v, w=w: w.set_path(str(v), emit=False) if v else None
        if f.get("required") and "*" not in title:
            title += "  *"
        lay.addWidget(OptionRow(title, field_guide(f), _spacer() if wide else w, desc))
        if wide:
            lay.addWidget(w)

    # ------------------------------------------------------------------ hooks
    def sync(self) -> None:
        """Show the current values again (after a settings file was loaded)."""
        for key, setter in self.setters.items():
            if key in self.values:
                setter(self.values[key])

    def validate(self) -> str | None:
        for key, f in self.fields.items():
            if not f.get("required"):
                continue
            v = self.values.get(key)
            if f["type"] in ("file", "folder"):
                if not v or not Path(str(v)).exists():
                    return f"Choose: {f.get('label', key)}."
            elif f["type"] == "list":
                if not any(str(x).strip() for x in (v or [])):
                    return f"Fill in: {f.get('label', key)}."
            elif not str(v or "").strip():
                return f"Fill in: {f.get('label', key)}."
        return None
