# Mosaic Video

Turn a folder of photos into an **animated photo-mosaic video**. The photos ("tiles") fly in from every
direction, settle into place to form a main picture, and the camera pulls back to reveal the finished
mosaic with a calm, elegant finale. Built in Python, GPU-rendered with OpenGL, encoded with FFmpeg.

The long-term goal is an installable **offline desktop app**.

## Features
- **Mosaic solver:** square tiles matched in Lab colour space; limits on how often one photo repeats and how
  close repeats may sit; optional sub-tiles; colour tinting; main-image blend; subject (face) aware, so the
  face gets finer tiles and the best matches.
- **Photo preprocessing:** EXIF rotation, border trimming, blur/size filtering, near-duplicate removal,
  face/saliency-aware square crops, on-disk cache.
- **Animation ("Swarm" style):** tiles arc in with spin and tilt, large "showcase" photos sweep past the camera,
  pulsed arrival waves, depth of field and fog, a multi-phase camera orbit, then a still finale with
  backdrop, glow, drifting dust, and a light sweep.
- **Configurable:** tile count and size, repeat rules, borders, aspect ratio, resolution, FPS, duration,
  format (MP4 H.264 / H.265, WebM, GIF) and more, all in one `Settings` object.

## Requirements
- Windows (tested), Python 3.12, a GPU/driver with OpenGL 3.3 (an integrated GPU is fine).
- FFmpeg is provided by the `imageio-ffmpeg` package; nothing to install separately.

## Install
```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Usage
1. Build the mosaic (the grid follows the video aspect ratio):
   ```bash
   .venv\Scripts\python.exe -m mosaicvid build --tiles "path\to\tile photos" --main "path\to\main.jpg" ^
     --out output\run1 --num-tiles 3000 --cell-px 128 --max-uses 12 --min-distance 6 ^
     --subtiles --subtile-percent 25 --tint 0.7 --blend 0.15 --subject-weight 0.7 --aspect 9:16
   ```
   This writes a still `mosaic.png` and a `scene.json` into the output folder.
2. Render the video:
   ```bash
   .venv\Scripts\python.exe -m mosaicvid video --scene output\run1\scene.json
   ```
   Useful flags: `--preview` (fast draft), `--aspect`, `--res`, `--fps`, `--duration`, `--format`,
   `--crf`, `--hero-tiles`, `--particles`, `--glow`, `--dof`. Run `... video --help` for all of them.

Generated media (videos, stills, caches) stay out of git on purpose; see `.gitignore`.

## Tests
```bash
.venv\Scripts\python.exe -m pytest -q
```

## Project layout
| Module | Role |
|---|---|
| `mosaicvid/preprocess.py` | photo ingestion and cleanup |
| `mosaicvid/subject.py` | subject (face/saliency) map |
| `mosaicvid/solver.py` | grid, matching, assignment, still render, scene I/O |
| `mosaicvid/animation.py` | per-tile flights, camera path, animation styles |
| `mosaicvid/render_gl.py` | headless OpenGL renderer and FFmpeg export |
| `mosaicvid/settings.py` | all user options |
| `mosaicvid/cli.py` | `build` and `video` commands |

## Roadmap
1. Auto-rotation, collage splitting and better border handling for messy real-world photos
2. More animation styles (vortex, wave reveal, zoom-in reveal)
3. Music and title overlays
4. Scale testing and renderer tests
5. PySide6 desktop GUI and offline installer
