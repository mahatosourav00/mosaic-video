"""User-facing settings. One serialisable object drives CLI and (later) the GUI."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path


IMAGE_FORMATS = {"png": "png", "jpg": "jpg", "webp": "webp", "tiff": "tif"}     # name -> file extension


@dataclass
class Settings:
    # ---- layout -------------------------------------------------------
    num_tiles: int = 1500            # approx. number of base cells
    tile_aspect: str = "1:1"         # tile shape W:H (1:1 square, 4:3 landscape, 3:4 portrait, ...)
    mosaic_aspect: str = "image"     # mosaic shape: "image" (same as the main picture) or W:H
    mosaic_ratio: float = 0.0        # set by the solver: final mosaic width/height
    cell_px: int = 48                # pixels per base cell in the still mosaic
    gap_px: int = 0                  # border/gap around each tile
    gap_color: tuple = (0, 0, 0)

    # ---- repetition rules ---------------------------------------------
    max_uses: int = 0                # max times one photo may appear (0 = auto)
    min_distance: float = 6.0        # min distance (in base cells) between same photo
    allow_flip: bool = True          # allow mirrored variants of tiles
    even_usage: float = 0.5          # 0..1+ : push the solver to use all photos evenly

    # ---- sub-tiles ----------------------------------------------------
    use_subtiles: bool = False
    subtile_percent: float = 20.0    # % of base cells that get subdivided
    subtile_grid: int = 2            # subtiles per cell side (2 -> 4 subtiles)
    subtile_select: str = "detail"   # "detail" (busiest areas first) or "random"

    # ---- look ---------------------------------------------------------
    tint: float = 0.5                # 0..1 tile colour adjustment toward target
    main_blend: float = 0.10         # 0..1 main-image overlay on the still mosaic
    subject_weight: float = 0.6      # 0..1 extra fidelity on faces/subject vs background
    detect_faces: bool = True

    # ---- preprocessing ------------------------------------------------
    trim_borders: bool = True
    auto_rotate: bool = False        # EXPERIMENTAL: Haar-based, ~2/3 right on the test set; needs a real orientation model
    smart_crop: bool = True          # crop to square around faces/detail (off = plain centre crop)
    dedupe: bool = True
    min_side: int = 96               # reject photos smaller than this
    min_sharpness: float = 8.0       # reject very blurry photos (Laplacian var)
    cache_px: int = 256              # stored tile resolution

    seed: int = 42

    # ---- photo collection ---------------------------------------------
    include_subfolders: bool = True  # also use photos inside sub-folders
    extra_tile_dirs: list = field(default_factory=list)   # more folders of tile photos
    exclude_dirs: list = field(default_factory=list)      # folders (anywhere inside) to leave out
    grayscale: bool = False          # black & white mosaic (tiles and main picture)

    # ---- still image output -------------------------------------------
    print_width_px: int = 0          # >0: size the still to about this width (print); 0 = use cell_px
    print_dpi: int = 0               # >0: write this DPI into png / jpg / tiff files
    image_format: str = "png"        # png | jpg | webp | tiff
    image_quality: int = 95          # jpg / webp quality 1..100

    # ---- video --------------------------------------------------------
    video_aspect: str = "same"       # "same" (as the mosaic) or "W:H", e.g. 9:16, 16:9, 1:1, 4:5
    video_res: int = 1080            # short side in pixels (1080 -> "1080p")
    fps: int = 30
    duration: float = 20.0           # seconds
    video_format: str = "mp4"        # mp4 | mp4-h265 | webm | gif
    crf: int = 23                  # quality (lower = better, bigger)
    style: str = "swarm"             # animation style
    bg_color: tuple = (10, 10, 14)
    anim_seed: int = 7
    hero_tiles: int = 18             # "showcase" photos that fly large through the foreground
    hero_size: float = 0.38         # showcase tile width as a fraction of the frame width
    flight_scale: float = 1.7        # how much bigger ordinary tiles are while flying
    pulses: int = 4                  # arrival comes in this many waves (calm beats between)
    pulse_depth: float = 0.55        # 0 = constant stream, ~1 = strong waves
    dof: float = 0.7                 # defocus of tiles away from the focal plane (0 = off)
    frame_margin: float = 0.80       # final mosaic fills this fraction of the frame

    # ---- finale (calm & elegant) ---------------------------------------
    backdrop: bool = True            # blurred, darkened main image + vignette behind the mosaic
    glow: float = 0.6                # soft shadow / glow / rim around the mosaic (0 = off)
    particles: int = 220            # drifting dust/bokeh (0 = off)

    def tile_ratio(self) -> float:
        a, b = (float(v) for v in self.tile_aspect.split(":"))
        return a / b

    def video_dims(self) -> tuple[int, int]:
        if self.video_aspect == "same":
            r = self.mosaic_ratio or 9 / 16
            a, b = r, 1.0
        else:
            a, b = (float(v) for v in self.video_aspect.split(":"))
        if a <= b:
            w, h = self.video_res, self.video_res * b / a
        else:
            w, h = self.video_res * a / b, self.video_res
        return int(round(w / 2) * 2), int(round(h / 2) * 2)

    # ---- io -----------------------------------------------------------
    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> "Settings":
        return cls.from_json_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_json_dict(cls, data: dict) -> "Settings":
        names = {f.name for f in fields(cls)}
        data = {k: v for k, v in data.items() if k in names}
        for k in ("gap_color", "bg_color"):
            if k in data:
                data[k] = tuple(data[k])
        return cls(**data)

    def validate(self) -> None:
        try:
            if not 0.25 <= self.tile_ratio() <= 4:
                raise ValueError
            if self.mosaic_aspect != "image":
                float(self.mosaic_aspect.split(":")[0]); float(self.mosaic_aspect.split(":")[1])
        except Exception:
            raise ValueError("tile_aspect / mosaic_aspect must look like 4:3 (tiles between 1:4 and 4:1)")
        if self.num_tiles < 4:
            raise ValueError("num_tiles must be >= 4")
        if self.image_format not in IMAGE_FORMATS:
            raise ValueError(f"image_format must be one of {', '.join(IMAGE_FORMATS)}")
        if self.subtile_grid < 2:
            raise ValueError("subtile_grid must be >= 2")
        for name in ("tint", "main_blend", "subject_weight"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be within 0..1")
