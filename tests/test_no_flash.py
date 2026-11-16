"""Building the window must not pop up stand-alone windows (the 'flashing windows at start-up' bug).

A widget made visible before it is placed in a layout is shown by Windows as its own top-level window for a moment.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_only_the_main_window_is_ever_shown():
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QApplication, QWidget

    from mosaicvid.gui.theme import qss
    from mosaicvid.gui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(qss())
    shown: list[str] = []

    class Watch(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
                shown.append(f"{type(obj).__name__}:{getattr(obj, 'text', lambda: '')()[:40]}")
            return False

    watch = Watch()
    app.installEventFilter(watch)
    try:
        w = MainWindow()
        w.show()
        app.processEvents()
        w.start_flow("both")
        for i in range(len(w.keys)):
            w._go(i)
            app.processEvents()
    finally:
        app.removeEventFilter(watch)
    assert shown == ["MainWindow:"], shown
