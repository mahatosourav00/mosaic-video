from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from ..jobs import JobRunner
from ..widgets import label


class PreviewDialog(QDialog):
    """Builds a small, fast draft of the mosaic so the user can check it before the real build.

    The draft uses the same settings and random seed, so the final mosaic has the same arrangement, only sharper.
    It shares the cache folder with the real run: the photo preparation done here is not repeated later."""

    def __init__(self, parent, state):
        super().__init__(parent)
        self.setWindowTitle("Preview your mosaic")
        self.resize(760, 780)
        self.setModal(True)
        out = Path(state.out_dir or state.default_out_dir())
        settings = state.final_settings()
        settings.update(cell_px=24, print_width_px=0, print_dpi=0, image_format="png")   # small and fast
        job = {"mode": "image", "tiles_dir": state.tiles_dir, "main_image": state.main_image,
               "out_dir": str(out / "preview"), "cache_dir": str(out / "cache"), "settings": settings}
        self.runner = JobRunner(self)
        self.runner.event.connect(self._event)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(26, 22, 26, 22)
        self.lay.setSpacing(12)
        self.head = label("Building a quick draft…", "title")
        self.sub = label("The first preview also prepares your photos, which takes about a minute for a few hundred "
                         "photos. Later previews are quick.", "sub", wrap=True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setFixedHeight(10)
        self.img = QLabel()
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setVisible(False)
        self.stage = label("", "muted")
        for w in (self.head, self.sub, self.bar, self.stage, self.img):
            self.lay.addWidget(w)
        self.lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.close_btn = QPushButton("Cancel")
        self.close_btn.clicked.connect(self.reject)
        row.addWidget(self.close_btn)
        self.lay.addLayout(row)
        self.runner.start(job)

    def done(self, r):
        self.runner.cancel()
        super().done(r)

    def _event(self, ev: dict):
        k = ev.get("event")
        if k == "stage":
            self.stage.setText(ev.get("label", ""))
            self.bar.setRange(0, 0)
        elif k == "progress" and ev.get("total"):
            self.bar.setRange(0, ev["total"])
            self.bar.setValue(ev["done"])
        elif k == "result":
            self.bar.setVisible(False)
            self.stage.setVisible(False)
            pm = QPixmap(ev["outputs"]["image"])
            self.img.setPixmap(pm.scaled(700, 560, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.img.setVisible(True)
            self.head.setText("Here is your mosaic, in draft")
            self.sub.setText("The final mosaic has exactly this arrangement, just much sharper. If you want "
                             "something different, close this, change a setting and preview again.")
            self.close_btn.setText("Looks good")
            self.close_btn.setObjectName("Primary")
            self.close_btn.setStyle(self.close_btn.style())
        elif k == "error":
            self.bar.setVisible(False)
            self.head.setText("The preview did not work")
            self.sub.setText(ev.get("message", ""))
            self.close_btn.setText("Close")
