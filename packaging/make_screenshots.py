r"""Regenerate the README screenshots (docs/images/*.png) from the current UI, headless:

    .\.venv\Scripts\python.exe packaging\make_screenshots.py

Uses made-up choices only (no personal folders are shown). Plugin shots need a plugin linked
(`python -m mosaicvid plugins link <folder>`); they are skipped when none is installed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "images"


def main() -> int:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from mosaicvid.gui.theme import qss
    from mosaicvid.gui.window import MainWindow

    app = QApplication([])
    app.setStyleSheet(qss())
    f = QFont("Segoe UI")
    f.setPointSize(10)
    app.setFont(f)
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    OUT.mkdir(parents=True, exist_ok=True)

    def snap(name: str) -> None:
        for _ in range(3):                                   # let wrapped labels re-flow before the picture is taken
            app.processEvents()
        w.grab().save(str(OUT / name))
        print("saved", name)

    snap("home.png")
    st = w.state
    st.tiles_dir = st.main_image = st.out_dir = ""          # nothing personal on screen
    st.n_photos, st.image_ratio = 780, 0.75
    w.start_flow("both")
    st.tiles_dir, st.main_image, st.n_photos = "photos", "portrait.jpg", 780
    for key, name in (("prepare", "prepare.png"), ("look", "design-mosaic.png"), ("video", "design-video.png")):
        w._go(w.keys.index(key))
        snap(name)
    pl = next(iter(st.plugins.values()), None)
    if pl is not None:
        st.plugin_preview = {}
        w.start_flow(f"plugin:{pl.id}")
        w._go(1 if pl.needs_mosaic else 0)
        snap("plugin-form.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
