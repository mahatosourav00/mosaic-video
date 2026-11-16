"""Job runner shared by the CLI (`mosaicvid run`) and the GUI.

A *job* is a plain dict (JSON-serialisable), so the GUI can write it to a file and start the engine as a
separate process (responsive window, cancel = kill). The runner reports through `emit(event_dict)`; the
`run` command prints each event as one JSON line.

Job keys
    mode        "image" | "video" | "both" | "inspect"
    tiles_dir   folder of tile photos           (image / both / inspect)
    main_image  the picture to recreate         (image / both)
    out_dir     output folder
    scene       existing scene.json             (video only: skips preparing photos and solving)
    settings    dict of Settings fields (anything missing keeps its default)
    preview     bool, render a fast low-res draft video
    video_name  optional output file name (without extension)
    cache_dir   optional shared cache folder (a preview run reuses the real run's cache)

Events
    {"event": "start", "mode": ...}
    {"event": "stage", "stage": "prepare|solve|still|render|report", "label": "..."}
    {"event": "progress", "stage": ..., "done": i, "total": n}
    {"event": "info", "message": "..."}
    {"event": "result", "outputs": {"image":..., "scene":..., "video":..., "report":...}, "stats": {...}}
    {"event": "error", "message": "...", "detail": "..."}
"""
from __future__ import annotations

import math
import time
import traceback
from pathlib import Path
from typing import Callable

from PIL import Image

from .settings import Settings

Emit = Callable[[dict], None]

# Settings an existing mosaic (scene.json) can still change when only a video is made from it.
# Grid shape (num_tiles, aspect, sub-tiles, ...) is fixed once the mosaic is built.
VIDEO_ONLY_KEYS = (
    "video_aspect", "video_res", "fps", "duration", "video_format", "crf", "style", "bg_color", "anim_seed", "hero_tiles",
    "hero_size", "flight_scale", "pulses", "pulse_depth", "dof", "frame_margin", "backdrop", "glow", "particles",
)


def _settings(job: dict) -> Settings:
    s = Settings.from_json_dict(job.get("settings") or {})
    if s.cell_px > s.cache_px:            # keep stored tiles at least as sharp as the output
        s.cache_px = min(s.cell_px, 512)
    if s.print_width_px:                  # print size is decided after the grid is known; keep tiles sharp
        s.cache_px = 512
    return s


MAX_STILL_PIXELS = 400_000_000           # safety cap for print-size stills


def _cache(job: dict, out_dir: Path) -> Path:
    return Path(job.get("cache_dir") or out_dir / "cache")


def _need(job: dict, *keys: str) -> None:
    for k in keys:
        if not job.get(k):
            raise ValueError(f"Missing '{k}' in the job")


def _progress(emit: Emit, stage: str, every: int = 1):
    last = [-1]

    def cb(i, n):
        if i == n or i - last[0] >= every:
            last[0] = i
            emit({"event": "progress", "stage": stage, "done": int(i), "total": int(n)})
    return cb


def save_image(img, out_dir: Path, s: Settings) -> Path:
    """Write the still mosaic in the chosen format (mosaic.png / .jpg / .webp / .tif)."""
    from .settings import IMAGE_FORMATS
    fmt = s.image_format if s.image_format in IMAGE_FORMATS else "png"
    path = out_dir / f"mosaic.{IMAGE_FORMATS[fmt]}"
    im = Image.fromarray(img)
    q = int(min(max(s.image_quality, 1), 100))
    dpi = {"dpi": (s.print_dpi, s.print_dpi)} if s.print_dpi > 0 else {}
    if fmt == "jpg":
        im.save(path, "JPEG", quality=q, subsampling=0, optimize=True, **dpi)
    elif fmt == "webp":
        im.save(path, "WEBP", quality=q, method=4)          # WebP has no DPI field
    elif fmt == "tiff":
        im.save(path, "TIFF", compression="tiff_lzw", **dpi)
    else:
        im.save(path, "PNG", optimize=False, **dpi)
    return path


def _video_path(out_dir: Path, s: Settings, job: dict) -> Path:
    ext = {"mp4": "mp4", "mp4-h265": "mp4", "webm": "webm", "gif": "gif"}[s.video_format]
    name = job.get("video_name") or f"mosaic_{s.style}{'_preview' if job.get('preview') else ''}"
    return out_dir / f"{name}.{ext}"


def _render(emit: Emit, m, tiles, s: Settings, out_dir: Path, job: dict, cache_dir: Path | None = None) -> Path:
    from .render_gl import render_video
    out = _video_path(out_dir, s, job)
    W, H = s.video_dims()
    emit({"event": "stage", "stage": "render", "label": f"Rendering the {s.style} video ({W}x{H}, {s.duration:g}s)"})
    render_video(m, tiles, s, out, preview=bool(job.get("preview")), cache_dir=cache_dir or out_dir / "cache",
                 progress=_progress(emit, "render", every=5))
    return out


def run_job(job: dict, emit: Emit) -> int:
    """Run a job; returns 0 on success, 1 on error (an 'error' event is emitted first)."""
    t0 = time.time()
    try:
        mode = job.get("mode")
        if mode not in ("image", "video", "both", "inspect"):
            raise ValueError(f"Unknown mode '{mode}'")
        emit({"event": "start", "mode": mode})
        outputs: dict = {}
        stats: dict = {}

        # ---------------------------------------------------------------- inspect (preprocess report only)
        if mode == "inspect":
            from .preprocess import prepare_tiles_report
            from .report import write_report
            _need(job, "tiles_dir", "out_dir")
            s = _settings(job)
            out = Path(job["out_dir"])
            emit({"event": "stage", "stage": "prepare", "label": "Checking your photos"})
            tiles, recs = prepare_tiles_report(job["tiles_dir"], s, cache_dir=_cache(job, out),
                                               progress=_progress(emit, "prepare", every=10))
            emit({"event": "stage", "stage": "report", "label": "Building the review sheets"})
            info = write_report(recs, tiles, out / "report")
            outputs["report"] = str(out / "report")
            stats = info["counts"]
            emit({"event": "result", "outputs": outputs, "stats": stats, "seconds": round(time.time() - t0, 1)})
            return 0

        # ---------------------------------------------------------------- video from an existing mosaic
        if mode == "video" and job.get("scene"):
            from .solver import load_scene
            scene = Path(job["scene"])
            out_dir = Path(job.get("out_dir") or scene.parent)
            emit({"event": "stage", "stage": "prepare", "label": "Opening your mosaic"})
            m, tiles, s = load_scene(scene)
            wanted = _settings(job)
            for k in VIDEO_ONLY_KEYS:                       # grid-shaping options stay as built
                if k in (job.get("settings") or {}):
                    setattr(s, k, getattr(wanted, k))
            out_dir.mkdir(parents=True, exist_ok=True)
            outputs["video"] = str(_render(emit, m, tiles, s, out_dir, job, cache_dir=scene.parent / "cache"))
            outputs["scene"] = str(scene)
            emit({"event": "result", "outputs": outputs, "stats": stats, "seconds": round(time.time() - t0, 1)})
            return 0

        # ---------------------------------------------------------------- build the mosaic (image / both)
        from .preprocess import prepare_tiles
        from .solver import render_still, save_scene, solve
        _need(job, "tiles_dir", "main_image", "out_dir")
        s = _settings(job)
        s.validate()
        out_dir = Path(job["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        emit({"event": "stage", "stage": "prepare", "label": "Preparing your photos"})
        tiles = prepare_tiles(job["tiles_dir"], s, cache_dir=_cache(job, out_dir),
                              progress=_progress(emit, "prepare", every=10))
        emit({"event": "info", "message": f"{len(tiles)} photos are usable"})
        if len(tiles) < 2:
            raise ValueError("Fewer than 2 usable photos were found in that folder.")

        emit({"event": "stage", "stage": "solve", "label": "Placing every photo"})
        m = solve(tiles, job["main_image"], s)
        stats = dict(m.stats)

        if s.print_width_px:
            cell = int(min(512, max(16, math.ceil(s.print_width_px / m.world_w))))     # tile height
            while (m.world_w * cell) * (m.rows * cell) > MAX_STILL_PIXELS and cell > 16:
                cell -= 1
            if cell != s.cell_px:
                emit({"event": "info", "message": f"Sizing the image for print: {cell}px per tile"})
            s.cell_px = cell
        emit({"event": "stage", "stage": "still", "label": "Creating the mosaic image"})
        img = render_still(m, tiles, s)
        stats["image_px"] = [int(img.shape[1]), int(img.shape[0])]
        image_path = save_image(img, out_dir, s)                # still always saved: it is the result thumbnail
        if mode != "video":
            outputs["image"] = str(image_path)
        save_scene(m, s, out_dir / "scene.json")
        s.to_json(out_dir / "settings.json")
        outputs["scene"] = str(out_dir / "scene.json")

        if mode in ("both", "video"):                           # "video" here = new photos, no saved mosaic yet
            outputs["video"] = str(_render(emit, m, tiles, s, out_dir, job, cache_dir=_cache(job, out_dir)))

        emit({"event": "result", "outputs": outputs, "stats": stats, "seconds": round(time.time() - t0, 1)})
        return 0
    except Exception as e:                                    # noqa: BLE001 - reported to the user
        emit({"event": "error", "message": str(e) or type(e).__name__,
              "detail": traceback.format_exc()[-1500:]})
        return 1
