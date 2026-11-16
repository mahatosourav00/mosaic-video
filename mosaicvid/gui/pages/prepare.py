from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QTabWidget,
                               QVBoxLayout, QWidget)

from ..jobs import JobRunner
from ..theme import C
from ..widgets import Banner, OptionRow, SliderField, Toggle, card, hline, label
from .base import Collapsible, Page

TAB_INFO = {
    "accepted": ("Kept", "These photos are used as they are."),
    "rotated": ("Turned upright", "These sideways photos were turned upright (experimental)."),
    "trimmed": ("Borders trimmed", "A frame or border was removed from these photos."),
    "rejected": ("Left out", "Too blurry, too small, or unreadable. Not used."),
    "duplicates": ("Duplicates", "Near-copies of a photo that is already used. Only one is kept."),
}


class ReportDialog(QDialog):
    """Runs the 'inspect' job and shows what preparation would do, as contact sheets."""

    def __init__(self, parent, job: dict):
        super().__init__(parent)
        self.setWindowTitle("Preview: what will happen to your photos")
        self.resize(980, 720)
        self.setModal(True)
        self.runner = JobRunner(self)
        self.runner.event.connect(self._event)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(26, 22, 26, 22)
        self.lay.setSpacing(12)
        self.head = label("Checking your photos…", "title")
        self.sub = label("The first check takes about a minute for a few hundred photos. Later ones are instant.",
                         "sub", wrap=True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setFixedHeight(10)
        self.lay.addWidget(self.head)
        self.lay.addWidget(self.sub)
        self.lay.addWidget(self.bar)
        self.lay.addStretch(1)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.job = job
        self.runner.start(job)

    def done(self, r):
        self.runner.cancel()
        super().done(r)

    def _event(self, ev: dict):
        k = ev.get("event")
        if k == "progress" and ev.get("total"):
            self.bar.setRange(0, ev["total"])
            self.bar.setValue(ev["done"])
        elif k == "result":
            self._show(Path(ev["outputs"]["report"]), ev.get("stats", {}))
        elif k == "error":
            self.head.setText("Something went wrong")
            self.sub.setText(ev.get("message", ""))
            self.bar.setVisible(False)
            self.lay.addWidget(self.close_btn, 0, Qt.AlignRight)

    def _show(self, folder: Path, counts: dict):
        self.bar.setVisible(False)
        total = sum(counts.values())
        kept = counts.get("accepted", 0) + counts.get("trimmed", 0) + counts.get("rotated", 0)
        self.head.setText(f"{kept:,} of {total:,} photos will be used")
        self.sub.setText("Browse each group. If something looks wrong, go back and switch that option off.")
        self.lay.takeAt(self.lay.count() - 1)          # the stretch
        tabs = QTabWidget()
        for name in ("accepted", "rotated", "trimmed", "rejected", "duplicates"):
            n = counts.get(name, 0)
            files = sorted(folder.glob(f"contact_{name}*.jpg"))
            if not n or not files:
                continue
            title, desc = TAB_INFO[name]
            page = QWidget()
            pl = QVBoxLayout(page)
            pl.setContentsMargins(0, 12, 0, 0)
            pl.addWidget(label(desc, "muted"))
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            holder = QWidget()
            hl = QVBoxLayout(holder)
            for f in files:
                lb = QLabel()
                pm = QPixmap(str(f))
                lb.setPixmap(pm.scaledToWidth(min(pm.width(), 900), Qt.SmoothTransformation))
                hl.addWidget(lb, 0, Qt.AlignHCenter)
            sc.setWidget(holder)
            pl.addWidget(sc, 1)
            tabs.addTab(page, f"{title}  ({n})")
        self.lay.addWidget(tabs, 1)
        self.lay.addWidget(self.close_btn, 0, Qt.AlignRight)


class PreparePage(Page):
    key = "prepare"
    title = "Prepare your photos"
    subtitle = ("Real-life photos are messy. These steps clean them up so they look good as tiles. "
                "Not sure? Keep the defaults, they suit most people.")

    def __init__(self, state):
        super().__init__(state)
        s = state.settings
        f, lay = self.section()
        self.skip = Toggle(state.skip_prep)
        lay.addWidget(OptionRow("Skip all preparation", "prep_skip", self.skip,
                                "Use my photos exactly as they are (they are still cropped to squares)."))
        self.skip.toggled.connect(self._skip_toggled)

        self.steps_card, slay = self.section("What should happen to your photos?")
        self.rows: list[OptionRow] = []

        def add(title, key, field, desc, toggle=None):
            t = toggle or Toggle(getattr(s, field))
            if toggle is None:
                t.toggled.connect(lambda on, fld=field: (setattr(s, fld, on), self.changed.emit()))
            row = OptionRow(title, key, t, desc)
            self.rows.append(row)
            if slay.count() > 1:
                slay.addWidget(hline())
            slay.addWidget(row)
            return t

        self.t_trim = add("Trim borders and frames", "prep_trim", "trim_borders",
                          "Removes white or black frames around photos.")
        self.t_dupe = add("Remove duplicates", "prep_dedupe", "dedupe", "Keeps one of each near-identical photo.")
        self.t_filter = Toggle(state.filter_bad)
        self.t_filter.toggled.connect(self._filter_toggled)
        add("Skip blurry and tiny photos", "prep_filter", "", "Leaves out photos that would look like smudges.",
            toggle=self.t_filter)
        self.t_crop = add("Smart square crop", "prep_crop", "smart_crop",
                          "Keeps faces and detail when cutting squares.")
        self.t_rot = add("Fix sideways photos  ·  experimental", "prep_rotate", "auto_rotate",
                         "Uses faces to turn photos upright; not always right, so check the preview.")

        adv = Collapsible("Fine-tune blur and size limits")
        self.sharp = SliderField(2, 40, s.min_sharpness, 1, lambda v: f"{v:g}", recommended=8)
        self.sharp.changed.connect(lambda v: setattr(s, "min_sharpness", float(v)))
        self.side = SliderField(32, 512, s.min_side, 16, lambda v: f"{int(v)} px", recommended=96)
        self.side.changed.connect(lambda v: setattr(s, "min_side", int(v)))
        adv.inner.addWidget(OptionRow("Blur strictness", "min_sharpness", self.sharp,
                                      "Higher drops more soft photos."))
        adv.inner.addWidget(OptionRow("Smallest photo size", "min_side", self.side))
        self.adv = adv
        self.body.addWidget(adv)

        pv, play = card(QHBoxLayout, flat=True)
        txt = QVBoxLayout()
        txt.addWidget(label("Not sure what these will do?", "h2"))
        txt.addWidget(label("See exactly which photos will be kept, trimmed, left out or treated as duplicates "
                            "before you build anything.", "muted", wrap=True))
        play.addLayout(txt, 1)
        self.preview_btn = QPushButton("Preview what will change")
        self.preview_btn.clicked.connect(self._preview)
        play.addWidget(self.preview_btn)
        self.body.addWidget(pv)
        self.body.addStretch(1)
        self._skip_toggled(state.skip_prep)

    def sync(self):
        st, s = self.state, self.state.settings
        for t, v in ((self.skip, st.skip_prep), (self.t_trim, s.trim_borders), (self.t_dupe, s.dedupe),
                     (self.t_filter, st.filter_bad), (self.t_crop, s.smart_crop), (self.t_rot, s.auto_rotate)):
            t.blockSignals(True)
            t.setChecked(v)
            t.blockSignals(False)
            t.update()
        self.sharp.set_value(s.min_sharpness or 8, emit=False)
        self.side.set_value(s.min_side or 96, emit=False)
        self._skip_toggled(st.skip_prep)
        self._filter_toggled(st.filter_bad)

    def on_enter(self):
        st = self.state
        if not st.out_dir:
            st.out_dir = st.default_out_dir()

    def _skip_toggled(self, on: bool):
        self.state.skip_prep = on
        self.steps_card.setEnabled(not on)
        self.adv.setEnabled(not on)
        self.preview_btn.setEnabled(True)
        self.changed.emit()

    def _filter_toggled(self, on: bool):
        self.state.filter_bad = on
        self.sharp.setEnabled(on)
        self.side.setEnabled(on)

    def _preview(self):
        st = self.state
        job = {"mode": "inspect", "tiles_dir": st.tiles_dir, "out_dir": st.out_dir or st.default_out_dir(),
               "settings": st.final_settings()}
        ReportDialog(self.window(), job).exec()
