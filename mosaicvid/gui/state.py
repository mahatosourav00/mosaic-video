"""What the user has chosen so far, and how that turns into an engine job."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from PySide6.QtCore import QSettings

from .. import plugins as plugin_api
from ..settings import Settings

ASPECTS = {"9:16": "Story  9:16", "4:5": "Portrait  4:5", "1:1": "Square  1:1", "16:9": "Wide  16:9"}
MOSAIC_SHAPES = {"image": "Same as picture", **ASPECTS}
VIDEO_SHAPES = {"same": "Same as mosaic", **ASPECTS}
TILE_SHAPES = {"1:1": "Square", "4:3": "Wide 4:3", "3:2": "Wide 3:2", "3:4": "Tall 3:4", "2:3": "Tall 2:3"}
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
    image_ratio: float = 0.0              # width/height of the main picture (0 = unknown)
    print_on: bool = False                # image only: size for print instead of screen
    print_w: float = 24.0                 # width in `print_unit`
    print_unit: str = "in"                # in | cm
    print_dpi: int = 300
    px_on: bool = False                   # image only: exact pixel size (instead of screen / print)
    px_val: int = 4096                    # that size, in pixels
    px_by: str = "w"                      # w = px_val is the width, h = it is the height
    settings: Settings = field(default_factory=Settings)
    plugins: dict = field(default_factory=dict)              # id -> plugins.Plugin (manifests only, no plugin code)
    plugin_values: dict = field(default_factory=dict)        # id -> {field key: value}
    plugin_preview: dict = field(default_factory=dict)       # {"on": bool, "start": s, "seconds": s} (review screen)

    def __post_init__(self):
        s = self.settings
        s.num_tiles, s.cell_px = PRESETS["balanced"]["num_tiles"], PRESETS["balanced"]["cell_px"]
        s.tint, s.subject_weight, s.max_uses, s.min_distance = 0.6, 0.6, 0, 6.0
        s.style, s.hero_tiles = "swarm", 18

    # ---- which pages are shown
    @property
    def plugin_id(self) -> str:
        """The plugin being used ('' for the built-in mosaic flows). The goal of a plugin flow is 'plugin:<id>'."""
        return self.goal[7:] if self.goal.startswith("plugin:") else ""

    @property
    def plugin(self):
        return self.plugins.get(self.plugin_id)

    def values_of(self, pid: str) -> dict:
        """Current form values of a plugin, created from the manifest's defaults on first use."""
        if pid not in self.plugin_values and pid in self.plugins:
            self.plugin_values[pid] = self.plugins[pid].defaults()
        return self.plugin_values.setdefault(pid, {})

    def steps(self) -> list[str]:
        if self.plugin_id:
            p = self.plugin
            return (["photos"] if p and p.needs_mosaic else []) + plugin_api.step_keys(self.plugin_id, self.plugins) + ["create"]
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
        if self.px_on and self.makes_image:
            s.print_width_px, s.print_dpi = self.pixel_size()[0], 0
        elif self.print_on and self.makes_image:
            s.print_width_px = self.print_pixels()[0]
            s.print_dpi = int(self.print_dpi)
        else:
            s.print_width_px, s.print_dpi = 0, 0
        d = asdict(s)
        d["gap_color"], d["bg_color"] = list(s.gap_color), list(s.bg_color)
        return d

    def plugin_job(self) -> dict:
        p = self.plugin
        job = {"mode": "plugin", "out_dir": self.out_dir, "settings": self.final_settings(), "preview": False,
               "plugin": {"id": p.id, "values": dict(self.values_of(p.id))}}
        if p.needs_mosaic:
            job["tiles_dir"], job["main_image"] = self.tiles_dir, self.main_image
        pv = self.plugin_preview
        if pv.get("on") and p.manifest.get("preview"):
            job["preview"] = True
            job["plugin"]["preview"] = {"start": pv.get("start", 0), "seconds": pv.get("seconds", 20)}
        return job

    def to_job(self, mode: str | None = None) -> dict:
        if self.plugin_id and mode is None:
            return self.plugin_job()
        mode = mode or self.goal
        job = {"mode": mode, "out_dir": self.out_dir, "settings": self.final_settings(),
               "preview": self.quality == "draft" and mode in ("video", "both")}
        if mode == "video" and self.use_existing:
            job["scene"] = self.scene
            job["settings"] = {k: v for k, v in job["settings"].items()}
        else:
            job["tiles_dir"], job["main_image"] = self.tiles_dir, self.main_image
        return job

    def ratio(self) -> float:
        """Width / height of the mosaic image."""
        s = self.settings
        if s.mosaic_aspect == "image":
            return self.image_ratio or 1.0
        a, b = (float(v) for v in s.mosaic_aspect.split(":"))
        return a / b

    def pixel_size(self) -> tuple[int, int]:
        """Exact-pixel mode: (width, height) when px_val is the width (px_by 'w') or the height ('h')."""
        r = self.ratio()
        if self.px_by == "h":
            return int(round(self.px_val * r)), int(self.px_val)
        return int(self.px_val), int(round(self.px_val / r))

    def print_pixels(self) -> tuple[int, int]:
        """Requested image size in pixels (width, height) from the physical size, unit, DPI and shape."""
        r = self.ratio()
        w_in = self.print_w / (2.54 if self.print_unit == "cm" else 1.0)
        return int(round(w_in * self.print_dpi)), int(round(w_in * self.print_dpi / r))

    def default_out_dir(self) -> str:
        base = Path.home() / "Documents" / "Mosaic Studio"
        name = Path(self.main_image).stem if self.main_image else "mosaic"
        if self.plugin_id:
            name = f"{self.plugin_id}_{name}"
        return str(base / name)


PRESET_KEYS = ("skip_prep", "filter_bad", "quality", "preset", "aspect_touched", "print_on", "print_w", "print_unit",
               "print_dpi", "px_on", "px_val", "px_by")
PRIVATE = ("extra_tile_dirs", "exclude_dirs")           # tied to this person's folders, never saved in a preset


def to_preset(state: AppState) -> dict:
    s = asdict(state.settings)
    for k in PRIVATE:
        s.pop(k, None)
    s["gap_color"], s["bg_color"] = list(s["gap_color"]), list(s["bg_color"])
    return {"app": "MosaicStudio", "version": 1, "settings": s, "choices": {k: getattr(state, k) for k in PRESET_KEYS},
            "plugins": {pid: dict(vals) for pid, vals in state.plugin_values.items()}}


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
    for pid, vals in (data.get("plugins") or {}).items():       # plugin forms: only keys the installed plugin knows
        if pid in state.plugins and isinstance(vals, dict):
            cur = state.values_of(pid)                          # in place: the form controls hold this dict
            for k, v in vals.items():
                if k in cur:
                    cur[k] = v


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
