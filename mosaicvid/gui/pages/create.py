from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from ..coffee import Signature
from ..jobs import JobRunner
from ..state import ASPECTS, STYLES, save_prefs
from ..theme import C
from ..widgets import Banner, OptionRow, PathPicker, card, clear_layout, hline, label
from .base import Page

STAGE_TEXT = {"prepare": "Prepare photos", "solve": "Place every photo", "still": "Create the mosaic image",
              "render": "Render the video"}


def _open(path: str):
    if path and Path(path).exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class CreatePage(Page):
    key = "create"
    title = "Review and create"
    subtitle = "Check your choices, pick where to save, and press Create."
    phase_changed = Signal(str)           # ready | running | done | error
    make_another = Signal(str)            # scene.json path

    def __init__(self, state):
        super().__init__(state)
        self.phase = "ready"
        self.runner = JobRunner(self)
        self.runner.event.connect(self._event)
        self.runner.finished.connect(self._finished)
        self.outputs: dict = {}
        self._t0 = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        # ---------------------------------------------------------------- ready view
        self.ready = QWidget()
        rl = QVBoxLayout(self.ready)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(16)
        self.summary_card, self.summary = card()
        rl.addWidget(self.summary_card)
        fc, fl = card()
        self.folder = PathPicker("folder", "Choose where to save", "Everything is saved in this folder")
        self.folder.btn.setText("Change")
        self.folder.changed.connect(self._folder_changed)
        fl.addWidget(OptionRow("Save to", "output_folder", QWidget()))
        fl.addWidget(self.folder)
        self.warn = Banner("warn", "")
        self.warn.setVisible(False)
        fl.addWidget(self.warn)
        rl.addWidget(fc)
        self.body.addWidget(self.ready)

        # ---------------------------------------------------------------- running view
        self.running = QWidget()
        gl = QVBoxLayout(self.running)
        gl.setContentsMargins(0, 0, 0, 0)
        rc, rcl = card(margins=(26, 24, 26, 24), spacing=16)
        self.run_head = label("Working on it…", "title")
        self.run_sub = label("You can leave this window open and do something else. It will tell you when it is done.",
                             "sub", wrap=True)
        rcl.addWidget(self.run_head)
        rcl.addWidget(self.run_sub)
        self.stage_box = QVBoxLayout()
        self.stage_box.setSpacing(8)
        rcl.addLayout(self.stage_box)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(10)
        rcl.addWidget(self.bar)
        row = QHBoxLayout()
        self.elapsed = label("0:00", "muted")
        row.addWidget(self.elapsed)
        row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Danger")
        self.cancel_btn.clicked.connect(self._cancel)
        row.addWidget(self.cancel_btn)
        rcl.addLayout(row)
        gl.addWidget(rc)
        self.running.setVisible(False)
        self.body.addWidget(self.running)

        # ---------------------------------------------------------------- result view
        self.result = QWidget()
        sl = QVBoxLayout(self.result)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(16)
        self.res_banner = Banner("ok", "")
        sl.addWidget(self.res_banner)
        self.res_card, self.res_lay = card(QHBoxLayout, spacing=22)
        self.thumb = QLabel()
        self.thumb.setFixedSize(260, 260)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f"background: {C['surface']}; border-radius: 14px;")
        self.res_lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(10)
        self.res_title = label("", "title")
        self.res_text = label("", "sub", wrap=True)
        col.addWidget(self.res_title)
        col.addWidget(self.res_text)
        col.addSpacing(6)
        self.btn_image = QPushButton("Open image")
        self.btn_video = QPushButton("Play video")
        self.btn_folder = QPushButton("Show in folder")
        self.btn_more = QPushButton("Make another video from this mosaic")
        self.btn_video.setObjectName("Primary")
        self.btn_image.clicked.connect(lambda: _open(self.outputs.get("image", "")))
        self.btn_video.clicked.connect(lambda: _open(self.outputs.get("video", "")))
        self.btn_folder.clicked.connect(lambda: _open(self.state.out_dir))
        self.btn_more.clicked.connect(lambda: self.make_another.emit(self.outputs.get("scene", "")))
        for b in (self.btn_video, self.btn_image, self.btn_folder, self.btn_more):
            col.addWidget(b, 0, Qt.AlignLeft)
        col.addStretch(1)
        self.res_lay.addLayout(col, 1)
        sl.addWidget(self.res_card)
        self.thanks = Signature()
        sl.addWidget(self.thanks, 0, Qt.AlignRight)
        self.result.setVisible(False)
        self.body.addWidget(self.result)

        # ---------------------------------------------------------------- error view
        self.error = QWidget()
        el = QVBoxLayout(self.error)
        el.setContentsMargins(0, 0, 0, 0)
        self.err_banner = Banner("bad", "")
        el.addWidget(self.err_banner)
        self.err_toggle = QToolButton()
        self.err_toggle.setObjectName("Link")
        self.err_toggle.setText("Show technical details")
        self.err_toggle.setCheckable(True)
        self.err_detail = QPlainTextEdit()
        self.err_detail.setReadOnly(True)
        self.err_detail.setMinimumHeight(160)
        self.err_detail.setVisible(False)
        self.err_toggle.toggled.connect(self.err_detail.setVisible)
        el.addWidget(self.err_toggle, 0, Qt.AlignLeft)
        el.addWidget(self.err_detail)
        self.error.setVisible(False)
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self._stage_labels: dict[str, QLabel] = {}

    # ------------------------------------------------------------------ page hooks
    def on_enter(self):
        if self.phase in ("done", "error", "running"):
            return
        st = self.state
        if not st.out_dir:
            st.out_dir = st.default_out_dir()
        self.folder.set_path(st.out_dir, emit=False)
        self.folder.title_lb.setText(Path(st.out_dir).name)
        self.folder.sub_lb.setText(str(st.out_dir))
        self._fill_summary()
        self._check_overwrite()
        self.title_lb.setText("Review and create")

    def validate(self) -> str | None:
        return None if self.state.out_dir else "Choose where to save."

    def button_text(self) -> str:
        return {"image": "Create image", "video": "Create video", "both": "Create image + video"}[self.state.goal]

    # ------------------------------------------------------------------ summary
    def _fill_summary(self):
        clear_layout(self.summary)
        st, s = self.state, self.state.settings
        self.summary.addWidget(label("Your choices", "h2"))
        rows = [("Making", {"image": "A mosaic image", "video": "A mosaic video", "both": "A mosaic image and video"}[st.goal])]
        if st.use_existing:
            rows.append(("From", Path(st.scene).parent.name + " (saved mosaic)"))
        else:
            extra = f" + {len(s.extra_tile_dirs)} more folder(s)" if s.extra_tile_dirs else ""
            rows += [("Photos", f"{st.n_photos:,} in “{Path(st.tiles_dir).name}”{extra}"),
                     ("Main picture", Path(st.main_image).name),
                     ("Shape", ASPECTS.get(s.video_aspect, s.video_aspect)),
                     ("Detail", f"about {s.num_tiles:,} tiles"),
                     ("Preparation", "Skipped" if st.skip_prep else
                      ", ".join(n for n, on in (("trim borders", s.trim_borders), ("remove duplicates", s.dedupe),
                                                ("skip blurry/tiny", st.filter_bad), ("smart crop", s.smart_crop),
                                                ("fix sideways", s.auto_rotate)) if on) or "None")]
        if st.makes_video:
            q = {"draft": "Draft preview (fast, low resolution)", "standard": "Standard", "high": "High"}[st.quality]
            res = "" if st.quality == "draft" else f" · {s.video_res}p"
            rows += [("Video", f"{STYLES[s.style][0]} · {int(s.duration)} s · {q}{res} · {s.video_format.upper()}")]
        if s.grayscale:
            rows += [("Colour", "Black and white")]
        if st.makes_image and st.print_on:
            w, h = st.print_pixels()
            rows += [("Print size", f"{st.print_w:g} {st.print_unit} wide · {st.print_dpi} DPI · about {w:,} x {h:,} px")]
        if st.makes_image:
            rows += [("Image file", {"png": "PNG", "jpg": f"JPEG (quality {s.image_quality})",
                                     "webp": f"WebP (quality {s.image_quality})", "tiff": "TIFF"}[s.image_format])]
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        for i, (k, v) in enumerate(rows):
            grid.addWidget(label(k, "muted"), i, 0, Qt.AlignTop)
            grid.addWidget(label(v, "", wrap=True), i, 1)
        grid.setColumnStretch(1, 1)
        wrap = QWidget()
        wrap.setLayout(grid)
        self.summary.addWidget(wrap)

    def _folder_changed(self, p: str):
        self.state.out_dir = p
        self.folder.title_lb.setText(Path(p).name)
        self.folder.sub_lb.setText(p)
        self._check_overwrite()
        self.changed.emit()

    def _check_overwrite(self):
        d = Path(self.state.out_dir)
        hit = list(d.glob("mosaic.*")) + ([d / "scene.json"] if (d / "scene.json").exists() else [])
        if hit and not self.state.use_existing:
            self.warn.set_text("This folder already has a mosaic in it. Creating again will replace it. "
                               "Pick another folder to keep both.", "warn")
            self.warn.setVisible(True)
        else:
            self.warn.setVisible(False)

    # ------------------------------------------------------------------ running
    def start(self):
        st = self.state
        save_prefs(st)
        Path(st.out_dir).mkdir(parents=True, exist_ok=True)
        self.outputs = {}
        self.ready.setVisible(False)
        self.result.setVisible(False)
        self.error.setVisible(False)
        self.running.setVisible(True)
        self.title_lb.setText("Creating…")
        self.sub_lb.setText("")
        self._stage_labels.clear()
        clear_layout(self.stage_box)
        order = (["prepare", "render"] if st.use_existing else
                 ["prepare", "solve", "still"] + (["render"] if st.makes_video else []))
        for k in order:
            lb = QLabel()
            self._stage_labels[k] = lb
            self.stage_box.addWidget(lb)
            self._set_stage(k, "todo")
        self.bar.setRange(0, 0)
        self.cancel_btn.setEnabled(True)
        self._t0 = time.time()
        self.timer.start(500)
        self._set_phase("running")
        job = st.to_job("video" if st.use_existing else st.goal)
        self.runner.start(job)

    def _cancel(self):
        self.cancel_btn.setEnabled(False)
        self.run_head.setText("Cancelling…")
        self.runner.cancel()

    def _tick(self):
        s = int(time.time() - self._t0)
        self.elapsed.setText(f"{s // 60}:{s % 60:02d} elapsed")

    def _set_stage(self, key: str, state: str):
        lb = self._stage_labels.get(key)
        if not lb:
            return
        icon, col = {"todo": ("○", C["faint"]), "doing": ("●", C["accent"]), "done": ("✓", C["ok"])}[state]
        weight = 700 if state == "doing" else 500
        lb.setText(f"<span style='color:{col}; font-weight:700;'>{icon}</span>&nbsp;&nbsp;"
                   f"<span style='color:{C['text'] if state != 'todo' else C['faint']}; font-weight:{weight};'>"
                   f"{STAGE_TEXT[key]}</span>")

    def _event(self, ev: dict):
        k = ev.get("event")
        if k == "stage":
            keys = list(self._stage_labels)
            cur = ev["stage"]
            if cur in keys:
                for kk in keys[:keys.index(cur)]:
                    self._set_stage(kk, "done")
                self._set_stage(cur, "doing")
            self.run_head.setText(ev.get("label", "Working on it…"))
            self.bar.setRange(0, 0)
        elif k == "progress" and ev.get("total"):
            self.bar.setRange(0, ev["total"])
            self.bar.setValue(ev["done"])
        elif k == "result":
            self.outputs = ev.get("outputs", {})
            self._show_result(ev)
        elif k == "error":
            self._show_error(ev)

    def _finished(self, code: int, cancelled: bool):
        self.timer.stop()
        if cancelled:
            self.running.setVisible(False)
            self.ready.setVisible(True)
            self.title_lb.setText("Review and create")
            self.sub_lb.setText("Cancelled. Nothing was lost; you can change anything and try again.")
            self._set_phase("ready")

    def _show_result(self, ev: dict):
        self.timer.stop()
        self.running.setVisible(False)
        self.result.setVisible(True)
        o, st = self.outputs, self.state
        secs = int(ev.get("seconds", 0))
        self.title_lb.setText("All done")
        self.sub_lb.setText("")
        took = f"{secs // 60}:{secs % 60:02d}"
        self.res_banner.set_text(f"Finished in {took}. Your files are saved in {st.out_dir}", "ok")
        img = o.get("image")
        pm = QPixmap(img) if img else QPixmap()
        if pm.isNull() and o.get("scene"):
            for alt in sorted(Path(o["scene"]).parent.glob("mosaic.*")):
                pm = QPixmap(str(alt))
                if not pm.isNull():
                    break
        self.thumb.setPixmap(pm.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pm.isNull()
                             else QPixmap())
        self.res_title.setText({"image": "Your mosaic image", "video": "Your mosaic video",
                                "both": "Your mosaic image and video"}[st.goal])
        st_s = ev.get("stats") or {}
        note = ""
        if st_s.get("max_uses_raised"):
            note = "Some photos were used a few extra times because there were not enough photos for the detail you chose."
        self.res_text.setText(note or "Open it, or try a different animation style from the same mosaic in seconds.")
        self.btn_image.setVisible("image" in o)
        self.btn_video.setVisible("video" in o)
        self.btn_more.setVisible("scene" in o)
        self._set_phase("done")

    def _show_error(self, ev: dict):
        self.timer.stop()
        self.running.setVisible(False)
        self.error.setVisible(True)
        self.title_lb.setText("That did not work")
        self.err_banner.set_text(ev.get("message", "Unknown error"), "bad")
        self.err_detail.setPlainText(ev.get("detail", ""))
        self._set_phase("error")

    def reset(self):
        self.running.setVisible(False)
        self.result.setVisible(False)
        self.error.setVisible(False)
        self.ready.setVisible(True)
        self.title_lb.setText("Review and create")
        self.sub_lb.setText("Check your choices, pick where to save, and press Create.")
        self._set_phase("ready")

    def _set_phase(self, p: str):
        self.phase = p
        self.phase_changed.emit(p)
