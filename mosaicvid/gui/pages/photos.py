from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImageReader

from ...preprocess import collection_paths
from ..state import nearest_aspect
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton

from ..widgets import Banner, ChipList, OptionRow, PathPicker, Toggle, label
from .base import Page

IMG_FILTER = "Pictures (*.jpg *.jpeg *.png *.webp *.bmp)"


class PhotosPage(Page):
    key = "photos"
    title = "Choose your pictures"
    subtitle = "Pick the folder of photos for the tiles and the main picture to recreate."

    def __init__(self, state):
        super().__init__(state)
        # --- reuse an existing mosaic (video goals only)
        self.exist_card, lay = self.section()
        self.exist_toggle = Toggle(state.use_existing)
        lay.addWidget(OptionRow("I already built a mosaic", "existing", self.exist_toggle,
                                "Skip building and make a new video from a mosaic you saved earlier."))
        self.exist_toggle.toggled.connect(self._existing_toggled)

        # --- photos + main picture
        self.new_box, nlay = self.section()
        self.tiles = PathPicker("folder", "Choose your photos folder", "Drop a folder here, or click to browse")
        self.main = PathPicker("file", "Choose your main picture", "The picture your mosaic will recreate",
                               IMG_FILTER)
        nlay.addWidget(OptionRow("Photos for the tiles", "tiles_folder", _spacer()))
        nlay.addWidget(self.tiles)
        # --- more folders / sub-folders / exclusions
        s = state.settings
        btns = QHBoxLayout()
        self.add_btn = QPushButton("+  Add another folder")
        self.excl_btn = QPushButton("Leave out a folder…")
        self.add_btn.clicked.connect(self._add_folder)
        self.excl_btn.clicked.connect(self._exclude_folder)
        btns.addWidget(self.add_btn)
        btns.addWidget(self.excl_btn)
        btns.addStretch(1)
        nlay.addLayout(btns)
        self.extra_list = ChipList("Also using these folders")
        self.excl_list = ChipList("Leaving out these folders")
        self.extra_list.changed.connect(lambda items: self._set_dirs("extra_tile_dirs", items))
        self.excl_list.changed.connect(lambda items: self._set_dirs("exclude_dirs", items))
        nlay.addWidget(self.extra_list)
        nlay.addWidget(self.excl_list)
        self.sub_toggle = Toggle(s.include_subfolders)
        self.sub_toggle.toggled.connect(self._subfolders)
        nlay.addWidget(OptionRow("Include photos in sub-folders", "subfolders", self.sub_toggle))
        nlay.addWidget(OptionRow("Main picture", "main_image", _spacer()))
        nlay.addWidget(self.main)
        self.tiles.changed.connect(self._tiles_changed)
        self.main.changed.connect(self._main_changed)
        self.info = Banner("tip", "")
        self.info.setVisible(False)
        nlay.addWidget(self.info)

        # --- existing scene picker
        self.scene_box, slay = self.section()
        self.scene = PathPicker("file", "Choose your saved mosaic", "Pick the scene.json from an earlier run",
                                "Mosaic scene (scene.json);;JSON (*.json)")
        slay.addWidget(OptionRow("Saved mosaic", "existing", _spacer()))
        slay.addWidget(self.scene)
        self.scene.changed.connect(self._scene_changed)
        self.body.addStretch(1)

    # ------------------------------------------------------------------
    def on_enter(self):
        st = self.state
        ph = (st.plugin.manifest.get("photos") or {}) if st.plugin_id else {}
        self.title_lb.setText(ph.get("title", self.title))
        self.sub_lb.setText(ph.get("subtitle", self.subtitle))
        self.exist_card.setVisible(False)              # the home screen decides: saved mosaic or new photos
        st.use_existing = st.goal == "video"
        self.exist_toggle.setChecked(st.use_existing)
        self._existing_toggled(st.use_existing)
        if st.tiles_dir and not self.tiles.path:
            self.tiles.set_path(st.tiles_dir, emit=False)
            self._count()
        if st.main_image and not self.main.path:
            self.main.set_path(st.main_image, emit=False)
        if st.scene and not self.scene.path:
            self.scene.set_path(st.scene, emit=False)
        self.changed.emit()

    def validate(self) -> str | None:
        st = self.state
        if st.use_existing:
            return None if st.scene and Path(st.scene).exists() else "Choose your saved mosaic to continue."
        if not st.tiles_dir or not Path(st.tiles_dir).is_dir():
            return "Choose the folder with your photos."
        if st.n_photos < 2:
            return "That folder needs at least a few pictures."
        if not st.main_image or not Path(st.main_image).exists():
            return "Choose the main picture to recreate."
        return None

    # ------------------------------------------------------------------
    def _existing_toggled(self, on: bool):
        self.state.use_existing = on
        self.new_box.setVisible(not on)
        self.scene_box.setVisible(on)
        self.changed.emit()

    def _tiles_changed(self, p: str):
        self.state.tiles_dir = p
        self._count()
        self.changed.emit()

    def _add_folder(self):
        p = QFileDialog.getExistingDirectory(self.window(), "Add another folder of photos", self.state.tiles_dir or "")
        if p and p != self.state.tiles_dir:
            self.extra_list.add(p)

    def _exclude_folder(self):
        p = QFileDialog.getExistingDirectory(self.window(), "Leave out this folder", self.state.tiles_dir or "")
        if p:
            self.excl_list.add(p)

    def _set_dirs(self, field: str, items: list):
        setattr(self.state.settings, field, list(items))
        self._count()
        self.changed.emit()

    def _subfolders(self, on: bool):
        self.state.settings.include_subfolders = on
        self._count()
        self.changed.emit()

    def sync(self):
        s = self.state.settings
        self.sub_toggle.setChecked(s.include_subfolders)
        self.extra_list.set_items(s.extra_tile_dirs)
        self.excl_list.set_items(s.exclude_dirs)
        if self.state.tiles_dir:
            self._count()

    def _count(self):
        try:
            n = len(collection_paths(self.state.tiles_dir, self.state.settings)) if self.state.tiles_dir else 0
        except OSError:
            n = 0
        self.state.n_photos = n
        if n == 0:
            self.tiles.set_status("No pictures found in this folder. Pick another one.")
            self.info.set_text("There are no .jpg, .png or .webp pictures in that folder.", "warn")
            self.info.setVisible(True)
        else:
            self.tiles.set_status(f"{n:,} pictures found")
            if n < 100:
                self.info.set_text(f"{n} pictures is on the low side. The mosaic will reuse photos a lot. For the "
                                   "best result use 300 or more, or keep the detail low in a later step.", "warn")
            elif n < 300:
                self.info.set_text(f"{n} pictures works well. More variety (300+) gives an even richer mosaic.", "tip")
            else:
                self.info.set_text(f"{n:,} pictures: plenty of variety for a rich, detailed mosaic.", "ok")
            self.info.setVisible(True)

    def _main_changed(self, p: str):
        self.state.main_image = p
        r = QImageReader(p)
        sz = r.size()
        if sz.isValid() and sz.height() > 0:
            self.state.image_ratio = sz.width() / sz.height()
        self.changed.emit()

    def _scene_changed(self, p: str):
        self.state.scene = p
        self.changed.emit()


def _spacer():
    from PySide6.QtWidgets import QWidget
    w = QWidget()
    w.setFixedSize(1, 1)
    return w
