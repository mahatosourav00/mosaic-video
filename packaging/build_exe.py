"""Build the double-clickable app:   .\.venv\Scripts\python.exe packaging\build_exe.py

Result: dist\MosaicStudio\MosaicStudio.exe  (a folder; zip it or point an installer at it to share).
Everything the app needs (Python, Qt, OpenCV, FFmpeg) is inside, so the target PC needs nothing installed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "mosaicvid" / "gui" / "assets"

# Qt modules we never import. Leaving them out keeps the app a few hundred MB smaller.
EXCLUDE = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebView",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtBluetooth", "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6",
]


def main() -> int:
    subprocess.check_call([sys.executable, str(ROOT / "packaging" / "make_icon.py")])
    import PyInstaller.__main__ as pyi
    args = [
        str(ROOT / "packaging" / "entry.py"),
        "--name", "MosaicStudio",
        "--windowed", "--noconfirm", "--clean",
        "--icon", str(ASSETS / "icon.ico"),
        "--paths", str(ROOT),
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
        "--add-data", f"{ASSETS};mosaicvid/gui/assets",
        "--collect-all", "imageio_ffmpeg",        # bundles the ffmpeg.exe used to write videos
        "--collect-data", "cv2",                  # face-detection model files
        "--hidden-import", "glcontext",           # OpenGL context for the video renderer
        "--hidden-import", "moderngl",
    ]
    for m in EXCLUDE:
        args += ["--exclude-module", m]
    pyi.run(args)
    exe = ROOT / "dist" / "MosaicStudio" / "MosaicStudio.exe"
    print("\nBuilt:", exe, "(exists)" if exe.exists() else "(MISSING)")
    return 0 if exe.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
