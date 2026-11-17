"""The plugin library screen: browse the catalog, install, update or remove plugins (network work runs off the UI thread)."""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ... import library as L
from ... import plugins as P
from ..widgets import label


class _Worker(QObject):
    done = Signal(object, str)                      # result, error message ("" = fine)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(), "")
        except L.LibraryError as e:
            self.done.emit(None, str(e))
        except Exception as e:                      # noqa: BLE001 - shown to the user, never crashes the window
            self.done.emit(None, f"Something went wrong: {e}")


class PluginCard(QFrame):
    act = Signal(object, str)                       # entry, "install" | "update" | "remove"

    def __init__(self, entry: L.Entry, state: str):
        super().__init__()
        self.setObjectName("Card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(18)
        text = QVBoxLayout()
        text.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(label(entry.name, "h2"))
        head.addWidget(label(f"v{entry.version}" + (f"  ·  {entry.author}" if entry.author else ""), "faint"))
        head.addStretch(1)
        text.addLayout(head)
        text.addWidget(label(entry.description, "sub", wrap=True))
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for c in entry.chips:
            chips.addWidget(label(c, "chip"))
        chips.addStretch(1)
        text.addLayout(chips)
        lay.addLayout(text, 1)
        side = QVBoxLayout()
        side.setSpacing(6)
        self.btn = QPushButton({"install": "Install", "update": "Update", "installed": "Installed ✓",
                                "added": "Already added"}[state])
        if state in ("install", "update"):
            self.btn.setObjectName("Primary")
            self.btn.setCursor(Qt.PointingHandCursor)
            self.btn.clicked.connect(lambda: self.act.emit(entry, state))
        else:
            self.btn.setEnabled(False)
        side.addWidget(self.btn)
        if state in ("installed", "update"):
            rm = QPushButton("Remove")
            rm.setObjectName("Ghost")
            rm.clicked.connect(lambda: self.act.emit(entry, "remove"))
            side.addWidget(rm)
        side.addStretch(1)
        lay.addLayout(side)


class LibraryPage(QWidget):
    back = Signal()
    changed = Signal()                              # a plugin was installed or removed: the window refreshes
    confirm = Signal(object)                        # entry: ask before installing (the window shows the dialog)
    _finished = Signal(object, object, str)         # callback, result, error: queued onto the UI thread

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setObjectName("Page")
        self._threads: list[QThread] = []
        self._finished.connect(self._deliver)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(56, 40, 56, 28)
        outer.setSpacing(8)
        outer.addWidget(label("Plugin library", "display"))
        outer.addWidget(label("Plugins are ready-made flows for one purpose, such as a birthday film. Install one and "
                              "its card appears on the home screen.", "sub", wrap=True))
        outer.addSpacing(14)
        self.status = label("", "muted", wrap=True)
        outer.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("Page")
        self.list = QVBoxLayout(host)
        self.list.setContentsMargins(0, 0, 14, 0)
        self.list.setSpacing(14)
        self.list.addStretch(1)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)
        foot = QHBoxLayout()
        home = QPushButton("Home")
        home.clicked.connect(self.back)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("Ghost")
        self.refresh_btn.clicked.connect(self.load)
        foot.addWidget(home)
        foot.addStretch(1)
        foot.addWidget(self.refresh_btn)
        outer.addLayout(foot)
        self.entries: list[L.Entry] = []

    # ------------------------------------------------------------------ work off the UI thread
    @Slot(object, object, str)
    def _deliver(self, then, res, err) -> None:
        then(res, err)

    def _run(self, fn, then) -> None:
        th, w = QThread(self), _Worker(fn)
        w.moveToThread(th)
        th.started.connect(w.run)
        w.done.connect(lambda res, err: (self._finished.emit(then, res, err), th.quit()))   # runs on the worker thread
        th.finished.connect(lambda: self._threads.remove(th) if th in self._threads else None)
        th.finished.connect(th.deleteLater)
        th._w = w                                   # keep the worker alive as long as the thread
        self._threads.append(th)
        th.start()

    def _busy(self, text: str) -> None:
        self.status.setText(text)
        self.refresh_btn.setEnabled(not text)

    def load(self) -> None:
        self._busy("Loading the library…")
        self._run(L.fetch_catalog, self._loaded)

    def _loaded(self, entries, err: str) -> None:
        self._busy("")
        if err:
            self.status.setText(err)
            return
        self.entries = entries
        self.render()

    def render(self) -> None:
        while self.list.count() > 1:
            item = self.list.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        installed = self.state.plugins
        if not self.entries:
            self.status.setText("No plugins are in the library yet.")
        for i, e in enumerate(self.entries):
            c = PluginCard(e, L.status(e, installed))
            c.act.connect(self._act)
            self.list.insertWidget(i, c)
            c.show()                                # added after the page is visible: it would stay hidden otherwise

    # ------------------------------------------------------------------ actions
    def _act(self, entry: L.Entry, what: str) -> None:
        if what == "remove":
            L.remove(entry.id)
            self.changed.emit()
            self.render()
        else:
            self.confirm.emit(entry)                # the window asks, then calls install()

    def install(self, entry: L.Entry) -> None:
        self._busy(f"Installing {entry.name}…")
        self._run(lambda: L.install(entry), lambda res, err: self._installed(entry, err))

    def _installed(self, entry: L.Entry, err: str) -> None:
        self._busy("")
        if err:
            self.status.setText(err)
            return
        self.status.setText(f"{entry.name} is installed. Its card is on the home screen.")
        self.changed.emit()
        self.render()
