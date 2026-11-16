"""Command line: python -m mosaicvid build --tiles DIR --main IMG --out DIR [options]"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

from .preprocess import prepare_tiles
from .settings import Settings
from .solver import render_still, save_scene, solve


def _video(a) -> int:
    from .render_gl import render_video
    from .solver import load_scene
    t0 = time.time()
    m, tiles, s = load_scene(a.scene)
    # look/animation settings come from the current defaults, not from whenever the scene was built
    fresh = Settings()
    for k in ("hero_tiles", "hero_size", "flight_scale", "pulses", "pulse_depth", "dof", "frame_margin",
              "backdrop", "glow", "particles", "anim_seed", "bg_color", "crf", "style"):
        setattr(s, k, getattr(fresh, k))
    for k, v in vars(a).items():
        if k in Settings.__dataclass_fields__ and v is not None:
            setattr(s, k, v)
    ext = {"mp4": "mp4", "mp4-h265": "mp4", "webm": "webm", "gif": "gif"}[s.video_format]
    out = Path(a.out) if a.out else Path(a.scene).parent / f"mosaic_{s.style}{'_preview' if a.preview else ''}.{ext}"
    W, H = s.video_dims()
    print(f"rendering {s.style}: {W}x{H} @ {s.fps}fps, {s.duration}s -> {out}")
    render_video(m, tiles, s, out, preview=a.preview, max_seconds=a.max_seconds,
                 cache_dir=Path(a.scene).parent / "cache",
                 progress=lambda i, n: print(f"\r  frame {i}/{n}", end="", flush=True))
    print(f"\ndone in {time.time() - t0:.1f}s: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


def _inspect(a) -> int:
    from .preprocess import prepare_tiles_report
    from .report import write_report
    s = Settings()
    if a.cache_px:
        s.cache_px = a.cache_px
    out = Path(a.out)
    t0 = time.time()
    def _prog(i, n):
        if i == n or i % 25 == 0:
            print(f"  preprocessing {i}/{n}  ({time.time() - t0:.0f}s)", flush=True)
    tiles, recs = prepare_tiles_report(a.tiles, s, cache_dir=out / "cache", progress=_prog)
    info = write_report(recs, tiles, out / "report")
    print(f"{len(recs)} photos in {time.time() - t0:.1f}s -> {info['counts']}")
    print("wrote", ", ".join(info["files"]), "+ report.csv in", out / "report")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mosaicvid")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="preprocess tiles and build a still mosaic + scene.json")
    b.add_argument("--tiles", required=True, help="folder of tile photos")
    b.add_argument("--main", required=True, help="main image")
    b.add_argument("--out", required=True, help="output folder")
    b.add_argument("--settings", help="settings JSON (CLI flags override)")
    b.add_argument("--num-tiles", type=int)
    b.add_argument("--cell-px", type=int)
    b.add_argument("--gap", type=int, dest="gap_px")
    b.add_argument("--max-uses", type=int)
    b.add_argument("--min-distance", type=float)
    b.add_argument("--subtiles", action="store_true", dest="use_subtiles")
    b.add_argument("--subtile-percent", type=float)
    b.add_argument("--subtile-grid", type=int)
    b.add_argument("--tint", type=float)
    b.add_argument("--blend", type=float, dest="main_blend")
    b.add_argument("--subject-weight", type=float, dest="subject_weight")
    b.add_argument("--seed", type=int)
    b.add_argument("--aspect", dest="video_aspect", help="video aspect the grid should follow, e.g. 9:16")
    b.add_argument("--res", type=int, dest="video_res")
    i = sub.add_parser("inspect", help="preprocess only: write contact sheets + report.csv, no mosaic")
    i.add_argument("--tiles", required=True)
    i.add_argument("--out", required=True)
    i.add_argument("--cache-px", type=int)
    r = sub.add_parser("run", help="run a job file (used by the GUI); prints one JSON event per line")
    r.add_argument("--job", required=True, help="job JSON file (see mosaicvid/runner.py)")
    v = sub.add_parser("video", help="render the animation video from a built scene.json")
    v.add_argument("--scene", required=True, help="scene.json from 'build'")
    v.add_argument("--out", help="output file (default: next to scene.json)")
    v.add_argument("--aspect", dest="video_aspect", help="e.g. 9:16, 16:9, 1:1")
    v.add_argument("--res", type=int, dest="video_res", help="short side in px (1080 = 1080p)")
    v.add_argument("--fps", type=int)
    v.add_argument("--duration", type=float)
    v.add_argument("--format", dest="video_format", choices=["mp4", "mp4-h265", "webm", "gif"])
    v.add_argument("--style")
    v.add_argument("--crf", type=int)
    v.add_argument("--no-backdrop", action="store_false", dest="backdrop", default=None)
    v.add_argument("--particles", type=int, help="dust/bokeh count (0 = off)")
    v.add_argument("--glow", type=float, help="shadow/glow/rim strength (0 = off)")
    v.add_argument("--dof", type=float, help="defocus strength 0..1 (0 = off)")
    v.add_argument("--hero-tiles", type=int, help="number of big showcase photos")
    v.add_argument("--flight-scale", type=float)
    v.add_argument("--margin", type=float, dest="frame_margin", help="final mosaic fill of the frame (0.86)")
    v.add_argument("--pulses", type=int)
    v.add_argument("--preview", action="store_true", help="fast low-res draft")
    v.add_argument("--max-seconds", type=float, help="render only the first N seconds")
    a = p.parse_args(argv)

    if a.cmd == "video":
        return _video(a)
    if a.cmd == "inspect":
        return _inspect(a)
    if a.cmd == "run":
        import json
        from .runner import run_job
        job = json.loads(Path(a.job).read_text(encoding="utf-8"))
        return run_job(job, lambda ev: print(json.dumps(ev), flush=True))

    s = Settings.from_json(a.settings) if a.settings else Settings()
    for k, v in vars(a).items():
        if k in Settings.__dataclass_fields__ and v is not None and v is not False:
            setattr(s, k, v)
    if s.cell_px > s.cache_px:           # keep stored tiles at least as sharp as the output
        s.cache_px = min(s.cell_px, 512)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    tiles = prepare_tiles(a.tiles, s, cache_dir=out / "cache")
    print(f"[1/3] {len(tiles)} usable tiles ({time.time() - t0:.1f}s)")
    m = solve(tiles, a.main, s)
    print(f"[2/3] solved: {m.stats} ({time.time() - t0:.1f}s)")
    img = render_still(m, tiles, s)
    Image.fromarray(img).save(out / "mosaic.png")
    if m.subject is not None:   # debug view of what the solver treats as "subject"
        import cv2, numpy as np
        sm = cv2.resize(m.subject, (img.shape[1] // 4, img.shape[0] // 4))
        main = cv2.resize(m.main, (sm.shape[1], sm.shape[0])).astype(np.float32)
        dbg = (main * (0.25 + 0.75 * sm[..., None])).astype(np.uint8)
        Image.fromarray(dbg).save(out / "subject_map.png")
    save_scene(m, s, out / "scene.json")
    s.to_json(out / "settings.json")
    print(f"[3/3] wrote {out / 'mosaic.png'} {img.shape[1]}x{img.shape[0]} ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
