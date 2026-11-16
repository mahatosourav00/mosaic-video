from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDoubleSpinBox, QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ..state import MOSAIC_SHAPES, PRESETS, TILE_SHAPES
from ..widgets import Banner, OptionRow, Segmented, SliderField, Toggle, card, hline, label
from .base import Collapsible, Page

PRESET_TEXT = {
    "draft": "Quick draft: a coarse mosaic in under a minute. Great for trying ideas.",
    "balanced": "Balanced: detailed and still quick. The right choice for most pictures.",
    "best": "Best quality: finer detail and a sharper image. Takes noticeably longer.",
}
PCT = lambda v: f"{int(round(v * 100))}%"                      # noqa: E731


class LookPage(Page):
    key = "look"
    title = "Design your mosaic"
    subtitle = "Choose how detailed and how colourful it should be. A preset is a great place to start."

    def __init__(self, state):
        super().__init__(state)
        s = state.settings
        # ---------------------------------------------------------------- preview
        pv, play = card(QHBoxLayout, flat=True)
        txt = QVBoxLayout()
        txt.addWidget(label("See it before you build it", "h2"))
        txt.addWidget(label("A quick draft shows the arrangement and colours. The final mosaic matches it exactly.",
                            "muted", wrap=True))
        play.addLayout(txt, 1)
        from ..widgets import HelpButton
        play.addWidget(HelpButton("preview"))
        self.preview_btn = QPushButton("Preview mosaic")
        self.preview_btn.setObjectName("Primary")
        self.preview_btn.clicked.connect(self._preview)
        play.addWidget(self.preview_btn)
        self.body.addWidget(pv)

        # ---------------------------------------------------------------- preset + shape
        f, lay = self.section()
        self.preset = Segmented([("draft", "Quick draft"), ("balanced", "Balanced"), ("best", "Best quality")],
                                state.preset)
        self.preset.changed.connect(self._preset)
        lay.addWidget(OptionRow("Quality preset", "preset", self.preset))
        self.preset_lb = label(PRESET_TEXT[state.preset], "muted", wrap=True)
        lay.addWidget(self.preset_lb)
        lay.addWidget(hline())
        self.shape = Segmented([(k, v) for k, v in MOSAIC_SHAPES.items()], s.mosaic_aspect)
        self.shape.changed.connect(self._shape)
        self.shape_row = OptionRow("Mosaic shape", "shape", self.shape, "Match where you will show it.")
        lay.addWidget(self.shape_row)
        lay.addWidget(hline())
        self.tile_shape = Segmented([(k, v) for k, v in TILE_SHAPES.items()], s.tile_aspect)
        self.tile_shape.changed.connect(lambda k: setattr(s, "tile_aspect", k))
        lay.addWidget(OptionRow("Tile shape", "tile_shape", self.tile_shape,
                                "The shape of each photo in the mosaic."))

        # ---------------------------------------------------------------- main controls
        f2, lay2 = self.section("Look and feel")
        self.detail = SliderField(500, 6000, s.num_tiles, 100, lambda v: f"{int(v):,} tiles", recommended=1500)
        self.detail.changed.connect(self._detail)
        lay2.addWidget(OptionRow("Detail", "detail", self.detail, "More tiles = finer picture, slower build."))
        self.advice = Banner("tip", "")
        lay2.addWidget(self.advice)
        lay2.addWidget(hline())
        self.repeats = SliderField(0, 30, s.max_uses, 1, lambda v: "Auto" if v == 0 else f"{int(v)} times",
                                   recommended=0)
        self.repeats.changed.connect(lambda v: setattr(s, "max_uses", int(v)))
        lay2.addWidget(OptionRow("Most times one photo can appear", "repeats", self.repeats))
        lay2.addWidget(hline())
        self.colour = SliderField(0, 1, s.tint, 0.05, PCT, recommended=0.6)
        self.colour.changed.connect(lambda v: setattr(s, "tint", float(v)))
        lay2.addWidget(OptionRow("Colour match", "colour", self.colour, "How strongly tiles take the picture's colours."))
        lay2.addWidget(hline())
        self.faces = SliderField(0, 1, s.subject_weight, 0.05, PCT, recommended=0.6)
        self.faces.changed.connect(lambda v: setattr(s, "subject_weight", float(v)))
        lay2.addWidget(OptionRow("Focus on faces and subject", "faces", self.faces,
                                 "Extra care where it matters most."))

        lay2.addWidget(hline())
        self.gray = Toggle(s.grayscale)
        self.gray.toggled.connect(lambda on: setattr(s, "grayscale", on))
        lay2.addWidget(OptionRow("Black and white", "grayscale", self.gray, "A classic monochrome mosaic."))

        # ---------------------------------------------------------------- image-only
        self.img_card, lay3 = self.section("Mosaic image")
        self.out_mode = Segmented([("screen", "Screen"), ("print", "Print size")], "print" if state.print_on else "screen")
        self.out_mode.changed.connect(self._out_mode)
        lay3.addWidget(OptionRow("Output size", "print_size", self.out_mode))
        self.print_box = QWidget()
        pb = QVBoxLayout(self.print_box)
        pb.setContentsMargins(0, 0, 0, 0)
        pb.setSpacing(10)
        roww = QHBoxLayout()
        self.pw = QDoubleSpinBox()
        self.pw.setRange(2, 600)
        self.pw.setDecimals(1)
        self.pw.setValue(state.print_w)
        self.pw.setFixedWidth(100)
        self.pw.valueChanged.connect(self._print_changed)
        self.punit = Segmented([("in", "inches"), ("cm", "cm")], state.print_unit)
        self.punit.changed.connect(self._print_changed)
        self.pdpi = Segmented([("150", "150 DPI"), ("300", "300 DPI"), ("600", "600 DPI")], str(state.print_dpi))
        self.pdpi.changed.connect(self._print_changed)
        roww.addWidget(label("Width", "muted"))
        roww.addWidget(self.pw)
        roww.addWidget(self.punit)
        roww.addSpacing(10)
        roww.addWidget(self.pdpi)
        roww.addStretch(1)
        pb.addLayout(roww)
        self.print_info = Banner("tip", "")
        pb.addWidget(self.print_info)
        lay3.addWidget(self.print_box)
        lay3.addWidget(hline())
        self.size = Segmented([("32", "Draft"), ("64", "Standard"), ("96", "Large"), ("128", "Max")], str(s.cell_px))
        self.size.changed.connect(lambda k: setattr(s, "cell_px", int(k)))
        self.size_row = OptionRow("Image sharpness", "size", self.size)
        lay3.addWidget(self.size_row)
        self.print_box.setVisible(state.print_on)
        self.size_row.setVisible(not state.print_on)
        lay3.addWidget(hline())
        self.img_fmt = Segmented([("png", "PNG"), ("jpg", "JPEG"), ("webp", "WebP"), ("tiff", "TIFF")], s.image_format)
        self.img_fmt.changed.connect(self._img_format)
        lay3.addWidget(OptionRow("File type", "image_format", self.img_fmt))
        self.quality = SliderField(60, 100, s.image_quality, 1, lambda v: f"{int(v)}", recommended=95)
        self.quality.changed.connect(lambda v: setattr(s, "image_quality", int(v)))
        self.quality_row = OptionRow("Quality", "image_quality", self.quality)
        lay3.addWidget(self.quality_row)
        self.quality_row.setVisible(s.image_format in ("jpg", "webp"))
        lay3.addWidget(hline())
        self.blend = SliderField(0, 0.4, s.main_blend, 0.01, PCT, recommended=0.10)
        self.blend.changed.connect(lambda v: setattr(s, "main_blend", float(v)))
        lay3.addWidget(OptionRow("Main picture showing through", "blend", self.blend))

        # ---------------------------------------------------------------- advanced
        adv = Collapsible("Advanced options")
        self.spread = SliderField(0, 12, s.min_distance, 1, lambda v: f"{int(v)} tiles", recommended=6)
        self.spread.changed.connect(lambda v: setattr(s, "min_distance", float(v)))
        adv.inner.addWidget(OptionRow("Keep repeats apart", "spread", self.spread))
        self.sub_t = Toggle(s.use_subtiles)
        self.sub_t.toggled.connect(self._subtiles)
        adv.inner.addWidget(hline())
        adv.inner.addWidget(OptionRow("Extra fine detail (small tiles)", "subtiles", self.sub_t,
                                      "Splits busy areas such as eyes and hair into smaller tiles."))
        self.sub_pct = SliderField(5, 60, s.subtile_percent, 5, lambda v: f"{int(v)}%", recommended=20)
        self.sub_pct.changed.connect(lambda v: setattr(s, "subtile_percent", float(v)))
        self.sub_row = OptionRow("How much to split", "subtile_percent", self.sub_pct)
        adv.inner.addWidget(self.sub_row)
        adv.inner.addWidget(hline())
        self.even = SliderField(0, 1, s.even_usage, 0.05, PCT, recommended=0.5)
        self.even.changed.connect(lambda v: setattr(s, "even_usage", float(v)))
        adv.inner.addWidget(OptionRow("Use all photos evenly", "even_usage", self.even))
        adv.inner.addWidget(hline())
        self.flip = Toggle(s.allow_flip)
        self.flip.toggled.connect(lambda on: setattr(s, "allow_flip", on))
        adv.inner.addWidget(OptionRow("Allow mirrored photos", "flip", self.flip))
        adv.inner.addWidget(hline())
        self.gap = SliderField(0, 8, s.gap_px, 1, lambda v: "None" if v == 0 else f"{int(v)} px", recommended=0)
        self.gap.changed.connect(lambda v: setattr(s, "gap_px", int(v)))
        adv.inner.addWidget(OptionRow("Gap between tiles", "gap", self.gap))
        self.gap_btn = QPushButton("Choose colour")
        self.gap_btn.setFixedWidth(150)
        self.gap_btn.clicked.connect(self._pick_gap_colour)
        adv.inner.addWidget(hline())
        adv.inner.addWidget(OptionRow("Gap colour", "gap_color", self.gap_btn))
        self._gap_swatch()
        adv.inner.addWidget(hline())
        self.seed = QSpinBox()
        self.seed.setRange(0, 99999)
        self.seed.setValue(s.seed)
        self.seed.setFixedWidth(110)
        self.seed.valueChanged.connect(lambda v: setattr(s, "seed", int(v)))
        adv.inner.addWidget(OptionRow("Variation number", "seed", self.seed,
                                      "Change it to get a different arrangement."))
        self.body.addWidget(adv)
        self.body.addStretch(1)
        self._subtiles(s.use_subtiles)

    # ------------------------------------------------------------------
    def on_enter(self):
        st = self.state
        s = st.settings
        self.img_card.setVisible(st.makes_image)
        self.shape.set_value(s.mosaic_aspect)
        self.tile_shape.set_value(s.tile_aspect)
        self.shape_row.set_desc("Shape of your " + ("mosaic image." if st.goal == "image" else
                                                    "mosaic. It is fixed once the mosaic is built."))
        self._advice()
        self._print_changed()

    def _preset(self, key: str):
        s = self.state.settings
        self.state.preset = key
        p = PRESETS[key]
        s.num_tiles, s.cell_px = p["num_tiles"], p["cell_px"]
        self.detail.set_value(s.num_tiles, emit=False)
        self.size.set_value(str(s.cell_px))
        self.preset_lb.setText(PRESET_TEXT[key])
        self._advice()

    def sync(self):
        st, s = self.state, self.state.settings
        self.preset.set_value(st.preset)
        self.preset_lb.setText(PRESET_TEXT.get(st.preset, ""))
        self.shape.set_value(s.mosaic_aspect)
        self.tile_shape.set_value(s.tile_aspect)
        self.detail.set_value(s.num_tiles, emit=False)
        self.repeats.set_value(s.max_uses, emit=False)
        self.colour.set_value(s.tint, emit=False)
        self.faces.set_value(s.subject_weight, emit=False)
        self.size.set_value(str(s.cell_px))
        self.img_fmt.set_value(s.image_format)
        self.quality.set_value(s.image_quality, emit=False)
        self.quality_row.setVisible(s.image_format in ("jpg", "webp"))
        self.blend.set_value(s.main_blend, emit=False)
        self.spread.set_value(s.min_distance, emit=False)
        self.sub_pct.set_value(s.subtile_percent, emit=False)
        self.even.set_value(s.even_usage, emit=False)
        self.gap.set_value(s.gap_px, emit=False)
        self.seed.blockSignals(True)
        self.seed.setValue(s.seed)
        self.seed.blockSignals(False)
        for t, v in ((self.sub_t, s.use_subtiles), (self.flip, s.allow_flip), (self.gray, s.grayscale)):
            t.blockSignals(True)
            t.setChecked(v)
            t.blockSignals(False)
            t.update()
        self.sub_row.setEnabled(s.use_subtiles)
        self.out_mode.set_value("print" if st.print_on else "screen")
        self.print_box.setVisible(st.print_on)
        self.size_row.setVisible(not st.print_on)
        for w, v in ((self.pw, st.print_w),):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.punit.set_value(st.print_unit)
        self.pdpi.set_value(str(st.print_dpi))
        self._gap_swatch()
        self._print_changed()
        self._advice()

    def _out_mode(self, key: str):
        st = self.state
        st.print_on = key == "print"
        self.print_box.setVisible(st.print_on)
        self.size_row.setVisible(not st.print_on)
        self._print_changed()

    def _print_changed(self, *_):
        st = self.state
        st.print_w = float(self.pw.value())
        st.print_unit = self.punit.value()
        st.print_dpi = int(self.pdpi.value())
        w, h = st.print_pixels()
        mp = w * h / 1e6
        unit = "in" if st.print_unit == "in" else "cm"
        txt = f"About {st.print_w:g} x {st.print_w * h / max(w, 1):.1f} {unit}  ·  {w:,} x {h:,} pixels  ·  {mp:.0f} megapixels"
        if mp > 400:
            self.print_info.set_text(txt + ". That is more than the 400 MP limit, so it will be made a little smaller.",
                                     "warn")
        elif mp > 120:
            self.print_info.set_text(txt + ". Large: expect a long build and a big file.", "warn")
        else:
            self.print_info.set_text(txt, "tip")

    def _pick_gap_colour(self):
        s = self.state.settings
        c = QColorDialog.getColor(QColor(*s.gap_color), self.window(), "Gap colour")
        if c.isValid():
            s.gap_color = (c.red(), c.green(), c.blue())
            self._gap_swatch()

    def _gap_swatch(self):
        r, g, b = self.state.settings.gap_color
        self.gap_btn.setStyleSheet(f"QPushButton {{ border-left: 22px solid rgb({r},{g},{b}); text-align: center; }}")

    def _preview(self):
        from .preview import PreviewDialog
        st = self.state
        if not st.out_dir:
            st.out_dir = st.default_out_dir()
        PreviewDialog(self.window(), st).exec()

    def _img_format(self, key: str):
        self.state.settings.image_format = key
        self.quality_row.setVisible(key in ("jpg", "webp"))

    def _shape(self, key: str):
        self.state.settings.mosaic_aspect = key
        self._print_changed()

    def _detail(self, v: float):
        self.state.settings.num_tiles = int(v)
        self._advice()

    def _subtiles(self, on: bool):
        self.state.settings.use_subtiles = on
        self.sub_row.setEnabled(on)
        self._advice()

    def _advice(self):
        st, s = self.state, self.state.settings
        n = max(st.n_photos, 1)
        cells = s.num_tiles * (1 + (0.75 * s.subtile_percent / 100 * 4 if s.use_subtiles else 0))
        per = cells / n
        if st.n_photos == 0:
            self.advice.setVisible(False)
            return
        self.advice.setVisible(True)
        if per <= 4:
            self.advice.set_text(f"With {n:,} photos, each one appears about {per:.1f} times. Good variety.", "ok")
        elif per <= 10:
            self.advice.set_text(f"With {n:,} photos, each one appears about {per:.0f} times. That is fine, and the "
                                 "builder keeps copies of the same photo apart.", "tip")
        else:
            self.advice.set_text(f"With {n:,} photos, each one would appear about {per:.0f} times, which can look "
                                 "repetitive. Lower the detail or add more photos.", "warn")
