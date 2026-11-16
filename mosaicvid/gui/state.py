"""What the user has chosen so far, and how that turns into an engine job."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from PySide6.QtCore import QSettings

from ..settings import Settings

ASPECTS = {"9:16": "Story  9:16", "4:5": "Portrait  4:5", "1:1": "Square  1:1", "16:9": "Wide  16:9"}
STYLES = {
    "swarm": ("Swarm", "Tiles swoop in from all sides while the camera sweeps across the picture."),
    "vortex": ("Vortex", "The camera circles the subject as tiles spiral in from a swirl."),
    "wave": ("Wave", "A wave of tiles sweeps across the picture while the camera tracks along it."),
    "zoom": ("Zoom", "Starts macro-close and pulls straight back to reveal the whole portrait."),
}
PRESETS = {  # detail, image sharpness (px per tile)
    "draft": dict(num_tiles=800, cell_px=32),
    "balanced": dict(num_tiles=1500, cell_px=64),
    "best": dict(num_tiles=3000, cell_px=96),
}
CELL_PX = {"standard": 64, "large": 96, "max": 128}


def nearest_aspect(w: int, h: int) -> str:
    r = w / max(h, 1)
    return "9:16" if r < 0.7 else "4:5" if r < 0.9 else "1:1" if r < 1.2 else "16:9"


@dataclass
class AppState:
    goal: str = "image"                   # image | video | both
    tiles_dir: str = ""
    main_image: str = ""
    out_dir: str = ""
    use_existing: bool = False            # video from an existing mosaic (scene.json)
    scene: str = ""
    n_photos: int = 0
    skip_prep: bool = False
    filter_bad: bool = True               # leave out blurry / tiny photos
    quality: str = "standard"             # draft | standard | high   (video)
    preset: str = "balanced"
    aspect_touched: bool = False
    print_on: bool = False                # image only: size for print instead of screen
    print_w: float = 24.0                 # width in `print_unit`
    print_unit: str = "in"                # in | cm
    print_dpi: int = 300
    settings: Settings = field(default_factory=Settings)

    def __post_init__(self):
        s = self.settings
        s.num_tiles, s.cell_px = PRESETS["balanced"]["num_tiles"], PRESETS["balanced"]["cell_px"]
        s.tint, s.subject_weight, s.max_uses, s.min_distance = 0.6, 0.6, 0, 6.0
        s.style, s.hero_tiles = "swarm", 18

    # ---- which pages are shown
    def steps(self) -> list[str]:
        if self.goal == "image":
            return ["photos", "prepare", "look", "create"]
        if self.use_existing:
            return ["photos", "video", "create"]
        return ["photos", "prepare", "look", "video", "create"]

    @property
    def makes_video(self) -> bool:
        return self.goal in ("video", "both")

    @property
    def makes_image(self) -> bool:
        return self.goal in ("image", "both")

    # ---- engine job
    def final_settings(self) -> dict:
        s = Settings.from_json_dict(asdict(self.settings))
        if self.skip_prep:
            s.trim_borders = s.dedupe = s.smart_crop = s.auto_rotate = False
            s.min_sharpness, s.min_side = 0.0, 0
        elif not self.filter_bad:
            s.min_sharpness, s.min_side = 0.0, 0
        if self.makes_video:
            s.crf = 18 if self.quality == "high" else 23
        if self.print_on and self.makes_image:
            s.print_width_px = self.print_pixels()[0]
            s.print_dpi = int(self.print_dpi)
        else:
            s.print_width_px, s.print_dpi = 0, 0
        d = asdict(s)
        d["gap_color"], d["bg_color"] = list(s.gap_color), list(s.bg_color)
        return d

    def to_job(self, mode: str | None = None) -> dict:
        mode = mode or self.goal
        job = {"mode": mode, "out_dir": self.out_dir, "settings": self.final_settings(),
               "preview": self.quality == "draft" and mode in ("video", "both")}
        if mode == "video" and self.use_existing:
            job["scene"] = self.scene
            job["settings"] = {k: v for k, v in job["settings"].items()}
        else:
            job["tiles_dir"], job["main_image"] = self.tiles_dir, self.main_image
        return job

    def print_pixels(self) -> tuple[int, int]:
        """Requested image size in pixels (width, height) from the physical size, unit, DPI and shape."""
        a, b = (float(v) for v in self.settings.video_aspect.split(":"))
        w_in = self.print_w / (2.54 if self.print_unit == "cm" else 1.0)
        return int(round(w_in * self.print_dpi)), int(round(w_in * self.print_dpi * b / a))

    def default_out_dir(self) -> str:
        base = Path.home() / "Documents" / "Mosaic Studio"
        name = Path(self.main_image).stem if self.main_image else "mosaic"
        return str(base / name)


PRESET_KEYS = ("skip_prep", "filter_bad", "quality", "preset", "aspect_touched", "print_on", "print_w", "print_unit",
               "print_dpi")
PRIVATE = ("extra_tile_dirs", "exclude_dirs")           # tied to this person's folders, never saved in a preset


def to_preset(state: AppState) -> dict:
    s = asdict(state.settings)
    for k in PRIVATE:
        s.pop(k, None)
    s["gap_color"], s["bg_color"] = list(s["gap_color"]), list(s["bg_color"])
    return {"app": "MosaicStudio", "version": 1, "settings": s, "choices": {k: getattr(state, k) for k in PRESET_KEYS}}


def apply_preset(state: AppState, data: dict) -> None:
    if data.get("app") != "MosaicStudio":
        raise ValueError("This file is not a Mosaic Studio settings file.")
    keep = {k: getattr(state.settings, k) for k in PRIVATE}
    new = Settings.from_json_dict({**asdict(state.settings), **(data.get("settings") or {})})
    for k, v in keep.items():
        setattr(new, k, v)
    new.validate()
    for f in fields(Settings):                      # in place: the pages' controls hold this object
        setattr(state.settings, f.name, getattr(new, f.name))
    for k, v in (data.get("choices") or {}).items():
        if k in PRESET_KEYS:
            setattr(state, k, v)


# ---- remembered between sessions
def load_prefs(state: AppState) -> None:
    q = QSettings("MosaicStudio", "MosaicStudio")
    for k in ("tiles_dir", "main_image", "out_dir"):
        v = q.value(k, "")
        if v and Path(v).exists():
            setattr(state, k, v)


def save_prefs(state: AppState) -> None:
    q = QSettings("MosaicStudio", "MosaicStudio")
    for k in ("tiles_dir", "main_image", "out_dir"):
        q.setValue(k, getattr(state, k))
    q.sync()          # the packaged app exits without Qt's normal shutdown, so write now
