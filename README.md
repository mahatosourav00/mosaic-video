# Mosaic Studio

Turn a folder of photos into **one big picture made of tiny photos**, or into a **cinematic animation** of that
mosaic assembling itself. Everything runs offline on your own Windows PC, with a clean guided app (or a command line
if you prefer).

<p align="center">
  <img src="docs/images/home.png" alt="Mosaic Studio home screen, with a plugin installed under 'Made for a purpose'" width="80%">
</p>

## See it in action

**Portrait.** A mosaic of Vermeer's *Girl with a Pearl Earring* made from about 1,200 NASA photos (4,500 tiles), and
the animation of it assembling itself (the *vortex* style):

<p align="center">
  <img src="docs/images/sample-portrait.gif" alt="Animation: thousands of tiny photos swirl in and assemble into a portrait" width="40%">
  <img src="docs/images/sample-portrait.jpg" alt="Finished mosaic of Girl with a Pearl Earring built from NASA photos" width="48%">
</p>

**Planet.** A 64 x 64 mosaic of **Earth** from ~780 NASA photos, and its animation (the *swarm* style):

<p align="center">
  <img src="docs/images/sample-animation.gif" alt="Animation: thousands of tiny photos fly in and assemble into a picture of Earth" width="48%">
  <img src="docs/images/sample-mosaic.jpg" alt="Finished mosaic of Earth built from NASA photos" width="48%">
</p>

<sub>Made with Mosaic Studio. Tiles: the [NASA Image and Video Library](https://images.nasa.gov/) (NASA media is
generally not copyrighted). Main pictures: NASA's Blue Marble, and *Girl with a Pearl Earring* (Johannes Vermeer,
c. 1665, public domain, via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Meisje_met_de_parel.jpg)).
The GIFs are small, low-colour previews; the real MP4s are 1080p and far smoother.</sub>

## Download (Windows)

1. Get **MosaicStudio-vX.Y.Z-windows.zip** from the [latest release](https://github.com/mahatosourav00/mosaic-video/releases/latest) and unzip it anywhere (keep the folder together).
2. Double-click **MosaicStudio.exe**.

Nothing else needs to be installed: Python, Qt, OpenCV and FFmpeg are inside.

> Windows may say **"Windows protected your PC"** (SmartScreen). That is because the app is new and not yet code-signed,
> not because anything is wrong: the full source code is in this repository. Click **More info**, then **Run anyway**.
>
> To check that your download is genuine, compare its checksum with `SHA256SUMS.txt` on the release page:
> `Get-FileHash .\MosaicStudio-vX.Y.Z-windows.zip` in PowerShell.

Requirements: Windows 10 / 11 (64-bit). Videos are rendered with OpenGL, so you need a graphics driver that supports
OpenGL 3.3 (an integrated GPU is fine).

## What you can make

| Choice | You get |
|---|---|
| **Create a mosaic** | The finished high-resolution picture built from your photos (PNG, JPEG, WebP or TIFF, for screens or for print). A switch on the *Design mosaic* page adds an **animation** of it assembling itself, in four styles, as MP4 (H.264 / H.265), WebM or GIF, 720p to 4K. |
| **New video from a saved mosaic** | Reuse a mosaic you built earlier to try a different animation style or format in seconds, without rebuilding it. |
| **A plugin** | A ready-made flow for one purpose, such as a birthday film with names, a message and music. Plugins live in their own folders and appear on the home screen under *Made for a purpose*; see [Plugins](#plugins). |

## The app

A short guided flow with a progress rail: **Pictures → Prepare photos → Design mosaic → Design video → Create**.
Steps that do not apply to your goal are left out.

<p align="center">
  <img src="docs/images/design-mosaic.png" alt="Design your mosaic" width="48%">
  <img src="docs/images/design-video.png" alt="Design your video" width="48%">
</p>

- **Made for beginners:** a **?** next to every option explains it in plain language and says what is recommended.
  Presets (Quick draft, Balanced, Best quality) and live advice, such as how often each photo will repeat.
- **Skip what you do not need:** every photo-preparation step has its own switch, plus a master "Skip all preparation".
  **Preview what will change** shows which photos would be kept, trimmed, left out or treated as duplicates.
- **Preview before you build:** a fast draft that has exactly the arrangement of the final mosaic.
- **Your photos, your way:** several photo folders, folders to leave out, a sub-folder switch, black and white, gap colour.
- **Shapes:** the mosaic can follow your picture or be Story 9:16, Portrait 4:5, Square or Wide; tiles can be square, wide or
  tall; the video can have yet another shape.
- **Print-ready:** choose a physical size (inches or cm) and 150 / 300 / 600 DPI; the DPI is saved inside the file.
- **Settings files:** save your settings and load them again later (your folders are never stored in them).
- **Stays responsive:** the work runs in a separate process, so the window never freezes and **Cancel** really cancels.

<p align="center">
  <img src="docs/images/prepare.png" alt="Prepare your photos" width="80%">
</p>

### Animation styles

Each style has its own camera, so you can tell them apart at a glance.

| Style | Camera and motion |
|---|---|
| **Swarm** | Tiles swoop in from all sides while the camera orbits and sweeps across the picture; big "showcase" photos fly past. |
| **Vortex** | The camera circles the subject as the tiles spiral in from a swirl. |
| **Wave** | A level sideways tracking shot follows a wave of tiles sweeping across the picture. |
| **Zoom** | Starts macro-close and pulls straight back along the lens axis to reveal the whole portrait. |

Vortex, Wave and Zoom open with tiles already in flight and keep the showcase photos away from the face; Swarm is
the original style. Every style ends on a calm, straight full frame with a soft glow, drifting dust and a light sweep.

### Photo preparation

EXIF rotation, border and frame trimming, blur / size filtering, near-duplicate removal, face- and detail-aware square
cropping, and an on-disk cache so later runs are fast. An experimental "fix sideways photos" option is available (off by
default).

## Plugins

A plugin turns Mosaic Studio into a tool for **one specific purpose**, with its own guided steps, without changing the
app. It is a small folder of its own (usually its own project and repository) that the app links to:

```
my-plugin/
    plugin.json    what the window shows: home card, steps, form fields, review summary (the window reads only this)
    plugin.py      def run(ctx): ...  does the work in the engine process and returns {"video": "path"}
```

<p align="center">
  <img src="docs/images/plugin-form.png" alt="A plugin's form, built from its plugin.json" width="80%">
</p>

- **Add one:** click **Add a plugin…** on the home screen and pick its folder (or, from source,
  `python -m mosaicvid plugins link "path\to\my-plugin"`; `plugins list` and `plugins unlink` also exist). Plugins are also
  found in `%APPDATA%\MosaicStudio\plugins`. A broken plugin is skipped, never fatal.
- **Forms without Qt code:** `plugin.json` lists typed fields (text, multi-line text, number, toggle, choice, colour, file,
  folder, list). The app builds the pages, validates required fields, shows a review screen and saves the values in the
  settings files.
- **The mosaic is handled for you:** a plugin that sets `"needs": "mosaic"` gets the photo and main-picture steps, and the
  engine prepares the photos and solves the mosaic first (and reuses it when only the plugin's own options changed). `run(ctx)`
  receives the finished scene, the tile cache, the form values, a progress reporter and the FFmpeg path.
- **Any animation style:** the four styles expose their camera (`Plan.state`), so a plugin can continue a style's camera move.
- **Short previews:** a plugin can offer "render only a short slice" on its review screen.

The first plugin is **Birthday video** (a personal film: a name drawn in the night sky, the photos gathering into a mosaic
portrait in any of the four styles, your message, music, a finale). It lives in its own repository.
The format is documented at the top of [`mosaicvid/plugins.py`](mosaicvid/plugins.py).

## Command line

The same engine can be used without the app (from a source checkout, see below).

```bash
# 1. Build the mosaic (writes mosaic.png, scene.json and a cache into --out)
python -m mosaicvid build --tiles "path\to\photos" --main "path\to\main.jpg" --out output\run1 ^
  --num-tiles 3000 --cell-px 128 --max-uses 12 --min-distance 6 --subtiles --subtile-percent 25 ^
  --tint 0.7 --blend 0.15 --subject-weight 0.7 --aspect 9:16

# 2. Render a video from it (--preview = fast low-res draft)
python -m mosaicvid video --scene output\run1\scene.json --style vortex [--preview --duration 20 --res 1080 --format mp4]

# Check what photo preparation would do, without building anything (contact sheets + report.csv)
python -m mosaicvid inspect --tiles "path\to\photos" --out output\run1

# Run a job file (this is what the app uses; progress is printed as one JSON event per line)
python -m mosaicvid run --job job.json

# Plugins: link a plugin folder, list the installed ones, unlink
python -m mosaicvid plugins link "path\to\my-plugin"
python -m mosaicvid plugins list
```

`python -m mosaicvid <command> --help` lists every option. A job file is plain JSON (`mode`: `image`, `video`, `both` or
`inspect` or `plugin`, plus paths and a `settings` object); see the top of [`mosaicvid/runner.py`](mosaicvid/runner.py).

## Run from source

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m mosaicvid.gui          # open the app
.venv\Scripts\python.exe -m pytest -q              # run the tests (31)
```

Python 3.12 on Windows is what it is tested with. FFmpeg comes from the `imageio-ffmpeg` package.

## Build the .exe yourself

```bash
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe packaging\build_exe.py
```

This produces `dist\MosaicStudio\MosaicStudio.exe` (a self-contained folder; zip it to share).

## Project layout

| Path | Role |
|---|---|
| `mosaicvid/preprocess.py` | photo ingestion and cleanup, cache |
| `mosaicvid/subject.py` | subject (face / saliency) map |
| `mosaicvid/solver.py` | grid, matching, assignment, still render, scene files |
| `mosaicvid/animation.py` | per-tile flights, cameras and the four animation styles |
| `mosaicvid/render_gl.py` | headless OpenGL renderer and FFmpeg export |
| `mosaicvid/settings.py` | every user option in one serialisable object |
| `mosaicvid/runner.py` | one job entry point (image / video / both / inspect / plugin) with JSON progress events |
| `mosaicvid/plugins.py` | plugin manifest, discovery, linking and the context a plugin's `run()` receives |
| `mosaicvid/report.py` | contact sheets and CSV report of what preparation did |
| `mosaicvid/cli.py` | `build`, `inspect`, `video`, `run` and `plugins` commands |
| `mosaicvid/app.py` | entry point for the window and the packaged exe |
| `mosaicvid/gui/` | the PySide6 app: pages, widgets, theme, help text, plugin forms (`plugin_form.py`) |
| `packaging/` | icon generator, the PyInstaller build script and `make_screenshots.py` (regenerates `docs/images`) |
| `tests/` | automated tests |

Generated media (videos, stills, caches) and build output stay out of git on purpose; see `.gitignore`.

## Roadmap

- Mixed tile shapes, irregular mosaic shapes from a mask, and using frames from your own videos as tiles
- Reliable automatic rotation of sideways photos (needs an orientation model)
- Music and title overlays for videos (plugins can already do this; a built-in option is still open)
- Plugins that add their own animation styles or renderer passes; a plugin gallery
- In-app video playback, a Windows installer and code signing
- Scale tests (thousands of photos) and renderer tests

## Credits and support

Developed by **Sourav**. If this helped you make something you love, you can support its development with the
**Buy me a coffee** button inside the app (it shows a UPI QR code).

## License

Mosaic Studio is free and open source under the [MIT License](LICENSE): you may use, change and share it, including
commercially, as long as the licence text stays with it. The downloadable app bundles other open-source software;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
