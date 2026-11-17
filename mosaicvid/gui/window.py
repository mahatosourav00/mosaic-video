from __future__ import annotations

from PySide6.QtCore import Qt
import json
from pathlib import Path

from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .coffee import Signature
from .pages.create import CreatePage
from .pages.home import HomePage
from .pages.library import LibraryPage
from .pages.look import LookPage
from .pages.photos import PhotosPage
from .pages.prepare import PreparePage
from .pages.video import VideoPage
from .plugin_form import PluginStepPage
from .. import plugins as plugin_api
from .state import AppState, apply_preset, load_prefs, to_preset
from .widgets import StepRail, label

RAIL_NAMES = {"photos": "Pictures", "prepare": "Prepare photos", "look": "Design mosaic", "video": "Design video",
              "create": "Create"}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mosaic Studio")
        self.resize(1200, 800)
        self.setMinimumSize(1020, 700)
        self.rail_names = dict(RAIL_NAMES)
        self.state = AppState()
        self.state.plugins = plugin_api.discover()           # manifests only; plugin code runs in the engine process
        load_prefs(self.state)
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        self.top = QStackedWidget()
        outer.addWidget(self.top)

        self.home = None
        self._make_home()

        flow = QWidget()
        fl = QHBoxLayout(flow)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)
        self.rail = StepRail()
        self.rail.signature_slot.addWidget(Signature(compact=True))
        self.rail.save_btn.clicked.connect(self._save_settings)
        self.rail.load_btn.clicked.connect(self._load_settings)
        fl.addWidget(self.rail)
        right = QVBoxLayout()
        right.setSpacing(0)
        self.pages: dict[str, object] = {}
        self.stack = QStackedWidget()
        for cls in (PhotosPage, PreparePage, LookPage, VideoPage, CreatePage):
            pg = cls(self.state)
            pg.changed.connect(self._refresh)
            self.pages[pg.key] = pg
            self.stack.addWidget(pg)
        self._make_plugin_pages()
        self.create: CreatePage = self.pages["create"]
        self.create.phase_changed.connect(lambda _p: self._refresh())
        self.create.make_another.connect(self._make_another)
        right.addWidget(self.stack, 1)

        foot = QFrame()
        foot.setObjectName("Footer")
        foot.setFixedHeight(72)
        hl = QHBoxLayout(foot)
        hl.setContentsMargins(36, 0, 36, 0)
        hl.setSpacing(14)
        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self._back)
        self.hint = label("", "muted")
        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("Primary")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.clicked.connect(self._next)
        hl.addWidget(self.back_btn)
        hl.addWidget(self.hint, 1)
        hl.addWidget(self.next_btn)
        right.addWidget(foot)
        fl.addLayout(right, 1)
        self.top.addWidget(flow)
        self.library = LibraryPage(self.state)
        self.library.back.connect(lambda: self.top.setCurrentIndex(0))
        self.library.changed.connect(self._library_changed)
        self.library.confirm.connect(self._confirm_install)
        self.top.addWidget(self.library)
        self.step = 0

    # ------------------------------------------------------------------ plugins
    def _make_home(self):
        """(Re)build the home screen: it lists the installed plugins."""
        old = self.home
        self.home = HomePage(self.state.plugins)
        self.home.chosen.connect(self.start_flow)
        self.home.add_plugin.connect(self._add_plugin)
        self.home.open_library.connect(self._open_library)
        self.top.insertWidget(0, self.home)
        if old is not None:
            self.top.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        self.top.setCurrentIndex(0)

    def _make_plugin_pages(self):
        for pl in self.state.plugins.values():               # the form steps of every plugin (new ones only)
            for i in range(len(pl.steps)):
                key = f"plugin.{pl.id}.{i}"
                if key in self.pages:
                    continue
                pg = PluginStepPage(self.state, pl, i)
                pg.changed.connect(self._refresh)
                self.pages[pg.key] = pg
                self.stack.addWidget(pg)
                self.rail_names[pg.key] = pg.title

    def _open_library(self):
        self.library.load()
        self.top.setCurrentWidget(self.library)

    def _library_changed(self):
        """A plugin was installed, updated or removed from the library: show it (or its absence) everywhere."""
        self.state.plugins = plugin_api.discover()
        self._make_plugin_pages()
        self._make_home()
        self.top.setCurrentWidget(self.library)              # _make_home returns to Home; stay in the library
        self.library.render()

    def _confirm_install(self, entry):
        ans = QMessageBox.question(
            self, "Install this plugin?",
            f"Install “{entry.name}” v{entry.version}?\n\nA plugin is a program that runs on your computer. "
            "Only install plugins from sources you trust.")
        if ans == QMessageBox.Yes:
            self.library.install(entry)

    def _add_plugin(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose the plugin's folder (it contains plugin.json)",
                                                  str(Path.home() / "Downloads"))
        if not folder:
            return
        try:
            pid = plugin_api.link(folder)
        except plugin_api.PluginError as e:
            QMessageBox.warning(self, "Could not add the plugin", str(e))
            return
        self.state.plugins = plugin_api.discover()
        self._make_plugin_pages()
        self._make_home()
        QMessageBox.information(self, "Plugin added",
                                f"\u201c{self.state.plugins[pid].name}\u201d is now on the home screen.")

    # ------------------------------------------------------------------ navigation
    @property
    def keys(self) -> list[str]:
        return self.state.steps()

    def start_flow(self, goal: str):
        st = self.state
        st.goal = goal
        st.use_existing = goal == "video"          # "video" = a new video from a mosaic saved earlier
        st.scene = ""
        st.plugin_preview = {}
        st.out_dir = st.out_dir if not st.plugin_id else ""      # a plugin's folder name depends on what is made
        self.create.reset()
        self.top.setCurrentIndex(1)
        self._go(0)

    def _go(self, i: int):
        keys = self.keys
        self.step = max(0, min(i, len(keys) - 1))
        pg = self.pages[keys[self.step]]
        self.stack.setCurrentWidget(pg)
        pg.on_enter()
        self._refresh()
        pg.scroll.verticalScrollBar().setValue(0)

    def _refresh(self):
        keys = self.keys
        if self.step >= len(keys):
            self.step = len(keys) - 1
        pg = self.pages[keys[self.step]]
        self.rail.set_steps([self.rail_names[k] for k in keys], self.step)
        self.rail.foot.setText(
            self.state.plugin.name if self.state.plugin_id else
            {"image": "Making a mosaic image", "video": "Making a video from a saved mosaic",
             "both": "Making a mosaic"}[self.state.goal])
        last = keys[self.step] == "create"
        phase = self.create.phase if last else "ready"
        self.back_btn.setVisible(phase in ("ready", "error", "done") or not last)
        self.back_btn.setText("Home" if self.step == 0 else "Back")
        if last:
            self.back_btn.setEnabled(phase != "running")
            if phase == "ready":
                self.next_btn.setText(self.create.button_text())
            elif phase == "running":
                self.next_btn.setText("Working…")
            elif phase == "done":
                self.next_btn.setText("Start over")
            else:
                self.next_btn.setText("Try again")
        else:
            self.back_btn.setEnabled(True)
            self.next_btn.setText("Next")
        why = pg.validate() if phase == "ready" else None
        self.hint.setText(why or "")
        self.next_btn.setEnabled(phase != "running" and why is None)

    def _next(self):
        keys = self.keys
        key = keys[self.step]
        if key == "create":
            phase = self.create.phase
            if phase == "ready":
                self.create.start()
            elif phase == "done":
                self.create.reset()
                self.top.setCurrentIndex(0)
            elif phase == "error":
                self.create.reset()
                self._refresh()
            return
        if self.pages[key].validate() is None:
            self._go(self.step + 1)

    def _back(self):
        if self.keys[self.step] == "create" and self.create.phase in ("done", "error"):
            self.create.reset()
        if self.step == 0:
            self.top.setCurrentIndex(0)
        else:
            self._go(self.step - 1)

    # ------------------------------------------------------------------ settings files
    PRESET_FILTER = "Mosaic Studio settings (*.mosaicpreset);;JSON (*.json)"

    def _preset_dir(self) -> str:
        d = Path.home() / "Documents" / "Mosaic Studio"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _save_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save your settings", str(Path(self._preset_dir()) / "my-settings.mosaicpreset"),
                                              self.PRESET_FILTER)
        if path:
            if not Path(path).suffix:
                path += ".mosaicpreset"
            Path(path).write_text(json.dumps(to_preset(self.state), indent=2), encoding="utf-8")
            self.hint.setText(f"Settings saved to {Path(path).name}")

    def _load_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load settings", self._preset_dir(), self.PRESET_FILTER)
        if not path:
            return
        try:
            apply_preset(self.state, json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception as e:                                   # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, "Could not load settings", f"{Path(path).name} could not be used.\n\n{e}")
            return
        for pg in self.pages.values():
            if hasattr(pg, "sync"):
                pg.sync()
        self._refresh()
        self.hint.setText(f"Loaded settings from {Path(path).name}")

    def _make_another(self, scene: str):
        st = self.state
        st.goal, st.use_existing, st.scene = "video", True, scene
        st.quality = "standard"
        if hasattr(self.pages.get("video"), "sync"):
            self.pages["video"].sync()
        self.create.reset()
        self.pages["photos"].scene.set_path(scene, emit=False)
        self._go(1)

    def closeEvent(self, e):
        if self.create.runner.running:
            ans = QMessageBox.question(self, "Quit while working?",
                                       "A mosaic is still being created. Quit and cancel it?")
            if ans != QMessageBox.Yes:
                e.ignore()
                return
            self.create.runner.cancel()
        e.accept()
