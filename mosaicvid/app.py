"""Single entry point for the desktop app (also what the packaged .exe runs).

    MosaicStudio.exe                      open the window
    MosaicStudio.exe --engine <args>      run the engine (the window starts this itself for every job)
    MosaicStudio.exe --selftest out.png   render the window offscreen to a PNG and exit (packaging check)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _attach_stdout() -> None:
    """A windowed (no-console) Windows build starts with sys.stdout = None even when a parent process gave it a
    pipe. Re-attach to that pipe so the engine can report progress to the window."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes
        import msvcrt
        h = ctypes.windll.kernel32.GetStdHandle(-11)                       # STD_OUTPUT_HANDLE
        if h and h != -1:
            fd = msvcrt.open_osfhandle(h, os.O_WRONLY)
            sys.stdout = os.fdopen(fd, "w", encoding="utf-8", buffering=1, closefd=False)
            sys.stderr = sys.stdout
            return
    except Exception:
        pass
    sys.stdout = sys.stderr = open(os.devnull, "w")


def run_gui() -> int:
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication

    from .gui.theme import qss
    from .gui.window import MainWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Mosaic Studio")
    app.setStyleSheet(qss())
    f = QFont("Segoe UI")
    f.setPointSize(10)
    app.setFont(f)
    icon = Path(__file__).parent / "gui" / "assets" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    w = MainWindow()
    w.show()
    return app.exec()


def selftest(out_png: str) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from .gui.theme import qss
    from .gui.window import MainWindow
    app = QApplication(sys.argv[:1])
    app.setStyleSheet(qss())
    f = QFont("Segoe UI")
    f.setPointSize(10)
    app.setFont(f)
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    w.start_flow("both")
    app.processEvents()
    ok = w.grab().save(out_png)
    qr = "no-upi-set"
    from .gui import branding
    if branding.has_upi():                       # the coffee dialog's QR must scan to the payment link
        import cv2
        import numpy as np
        from PySide6.QtGui import QImage
        from .gui.coffee import CoffeeDialog
        d = CoffeeDialog()
        d.show()
        app.processEvents()
        img = d.grab().toImage().convertToFormat(QImage.Format_RGB888)
        a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, : img.width() * 3]
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(a.reshape(img.height(), img.width(), 3).copy())
        qr = "ok" if text == branding.upi_uri() else f"FAIL({text!r})"
        ok = ok and qr == "ok"
    Path(out_png + ".txt").write_text(f"ok={ok} qr={qr} steps={w.keys}", encoding="utf-8")
    return 0 if ok else 1


def selftest_run(job_path: str, result_path: str) -> int:
    """Start a job exactly the way the window does (JobRunner -> this exe in --engine mode) and record the events."""
    import json
    import time
    from PySide6.QtCore import QCoreApplication

    from .gui.jobs import JobRunner
    app = QCoreApplication(sys.argv[:1])
    events: list[dict] = []
    runner = JobRunner()
    runner.event.connect(events.append)
    runner.finished.connect(lambda *_: app.quit())
    runner.start(json.loads(Path(job_path).read_text(encoding="utf-8")))
    t0 = time.time()
    from PySide6.QtCore import QTimer
    guard = QTimer()
    guard.timeout.connect(lambda: (runner.cancel(), app.quit()) if time.time() - t0 > 300 else None)
    guard.start(1000)
    app.exec()
    kinds = [e.get("event") for e in events]
    last = events[-1] if events else {}
    Path(result_path).write_text(json.dumps({"events": len(events), "kinds": kinds[:4] + ["..."] + kinds[-1:],
                                             "last": last}), encoding="utf-8")
    return 0 if last.get("event") == "result" else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--engine"]:
        _attach_stdout()
        from .cli import main as engine_main
        return engine_main(argv[1:])
    if argv[:1] == ["--selftest"] and len(argv) > 1:
        return selftest(argv[1])
    if argv[:1] == ["--selftest-run"] and len(argv) > 2:
        return selftest_run(argv[1], argv[2])
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
