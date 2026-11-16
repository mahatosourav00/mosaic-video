"""Plugin system: extend Mosaic Studio for one specific purpose (a birthday film, a wedding montage, ...).

A plugin is a folder with a `plugin.json` manifest and, usually, a Python entry file. It is normally its OWN
project (own folder, own development) that Mosaic Studio links to, not code inside this repository::

    <anywhere>/Birthday mosaic video/
        plugin.json      what the GUI shows (home card, steps, form fields) and how the engine runs it
        plugin.py        def run(ctx) -> {"video": "...path..."}      (engine side only)
        ...              its own helper files, assets, notes

Where Mosaic Studio looks (`plugin_dirs`): <app>/plugins/*, %APPDATA%/MosaicStudio/plugins/*, every folder linked with
`python -m mosaicvid plugins link <folder>` (saved in %APPDATA%/MosaicStudio/plugins.json), and MOSAICVID_PLUGINS.

Two halves, kept apart on purpose (the GUI never imports engine code, see CLAUDE.md):
  * the GUI reads ONLY plugin.json (this module's `discover`, no plugin code is executed in the window);
  * the engine process (`python -m mosaicvid run --job ...`, job mode "plugin") imports the entry file and calls run(ctx).

plugin.json (api 1)
    api            1
    id             short unique name, letters/digits/-/_       "birthday"
    name           shown on the home screen                      "Birthday video"
    version        "1.0.0"
    description    one or two sentences for the home card
    chips          small tags on the home card                   ["Names + message", "Music"]
    entry          python file with run(ctx)                     "plugin.py"   (default)
    needs          "mosaic" = the engine first prepares the photos and solves the mosaic (GUI asks for the photo
                   folder + main picture) and hands run() the finished scene; "none" = no photos needed
    photos         optional {"title", "subtitle"} for the picture step
    mosaic         optional {"settings": {Settings fields}}  forced onto the mosaic build (e.g. aspect 9:16, 3000 tiles)
    stages         [["render", "Make the film"]]   progress rows after the mosaic stages (id, label)
    button         label of the final button                     "Create birthday video"
    result         {"title": "Your birthday video"}
    summary        field keys listed on the review screen
    preview        optional {"start": 40, "seconds": 20}: adds a "render only a short slice" switch to the review screen
    steps          [{"id","title","subtitle","sections":[{"title","subtitle","fields":[FIELD]}]}]

FIELD
    key       unique within the plugin; dotted keys ("people.her_name") become nested dicts in `ctx.nested()`
    type      text | multiline | number | toggle | choice | color | file | folder | list
    label, help, default
    number:   min, max, step, unit
    choice:   options [[value, "Text"], ...]
    file:     filter ("Music (*.mp3 *.wav)")      file/folder: prompt
    list:     one item per line (value is a list of strings)
    required  true = the Next button waits until it is filled in (file/folder must also exist)
    advanced  true = tucked under "Advanced options"

run(ctx) receives a `PluginContext` (below) and returns a dict of output files (keys "video" / "image" show up as
buttons on the result screen). Anything it raises is shown to the user as the error.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

API_VERSION = 1
FIELD_TYPES = ("text", "multiline", "number", "toggle", "choice", "color", "file", "folder", "list")
APP_DIR = "MosaicStudio"


class PluginError(Exception):
    """A plugin is malformed or failed to load."""


# ------------------------------------------------------------------------------------------ discovery
def plugin_dirs() -> list[Path]:
    """Where plugins are looked for, in order: bundled with the app, the user's folder, MOSAICVID_PLUGINS."""
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        dirs += [base / "plugins", Path(sys.executable).parent / "plugins"]
    else:
        dirs.append(Path(__file__).resolve().parents[1] / "plugins")
    dirs.append(user_plugin_dir())
    dirs += [Path(p) for p in linked_paths()]
    for p in os.environ.get("MOSAICVID_PLUGINS", "").split(os.pathsep):
        if p.strip():
            dirs.append(Path(p.strip()))
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def user_plugin_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / APP_DIR / "plugins"


def _links_file() -> Path:
    return user_plugin_dir().parent / "plugins.json"


def linked_paths() -> list[str]:
    """Folders the user linked with `mosaicvid plugins link <folder>`: a plugin kept in its own project (its own
    repo, its own development) that Mosaic Studio loads in place. Each is a plugin folder (has plugin.json) or a
    folder that holds several."""
    try:
        data = json.loads(_links_file().read_text(encoding="utf-8"))
        return [str(p) for p in data.get("paths", [])]
    except (OSError, ValueError, AttributeError):
        return []


def _save_links(paths: list[str]) -> None:
    f = _links_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"paths": paths}, indent=2), encoding="utf-8")


def link(folder: str | Path) -> str:
    """Remember a plugin project folder. Returns the plugin id (raises PluginError if it is not a valid plugin)."""
    folder = Path(folder).resolve()
    mf = folder / "plugin.json"
    if not mf.is_file():
        raise PluginError(f"{folder} has no plugin.json")
    try:
        d = json.loads(mf.read_text(encoding="utf-8"))
    except ValueError as e:
        raise PluginError(f"plugin.json is not valid JSON: {e}") from None
    bad = validate_manifest(d, str(mf))
    if bad:
        raise PluginError("plugin.json: " + "; ".join(bad))
    paths = [p for p in linked_paths() if Path(p) != folder] + [str(folder)]
    _save_links(paths)
    return d["id"]


def unlink(folder: str | Path) -> bool:
    folder = Path(folder).resolve()
    paths = linked_paths()
    keep = [p for p in paths if Path(p) != folder]
    if len(keep) == len(paths):
        return False
    _save_links(keep)
    return True


@dataclass
class Plugin:
    id: str
    name: str
    path: Path
    manifest: dict
    problems: list[str] = field(default_factory=list)

    @property
    def needs_mosaic(self) -> bool:
        return self.manifest.get("needs", "mosaic") == "mosaic"

    @property
    def steps(self) -> list[dict]:
        return self.manifest.get("steps") or []

    def fields(self) -> list[dict]:
        return [f for st in self.steps for sec in st.get("sections", []) for f in sec.get("fields", [])]

    def defaults(self) -> dict[str, Any]:
        return {f["key"]: _copy(f.get("default", _EMPTY[f["type"]])) for f in self.fields()}

    def stages(self) -> list[tuple[str, str]]:
        st = [tuple(s) for s in self.manifest.get("stages") or [["render", "Make the video"]]]
        return ([("prepare", "Prepare photos"), ("solve", "Place every photo")] if self.needs_mosaic else []) + st


_EMPTY = {"text": "", "multiline": "", "number": 0, "toggle": False, "choice": "", "color": "#FFFFFF", "file": "",
          "folder": "", "list": []}


def _copy(v):
    return list(v) if isinstance(v, list) else v


def validate_manifest(d: dict, where: str = "plugin.json") -> list[str]:
    """Return a list of problems (empty = fine). Never raises."""
    bad: list[str] = []
    if not isinstance(d, dict):
        return [f"{where}: must be a JSON object"]
    if d.get("api") != API_VERSION:
        bad.append(f"api must be {API_VERSION} (this plugin says {d.get('api')!r})")
    pid = d.get("id", "")
    if not (isinstance(pid, str) and pid and all(c.isalnum() or c in "-_" for c in pid)):
        bad.append("id must be letters, digits, - or _")
    if not d.get("name"):
        bad.append("name is missing")
    if d.get("needs", "mosaic") not in ("mosaic", "none"):
        bad.append("needs must be 'mosaic' or 'none'")
    keys: set[str] = set()
    for si, st in enumerate(d.get("steps") or []):
        for sec in st.get("sections", []):
            for f in sec.get("fields", []):
                k = f.get("key")
                if not k or not isinstance(k, str):
                    bad.append(f"steps[{si}]: a field has no key")
                    continue
                if k in keys:
                    bad.append(f"duplicate field key '{k}'")
                keys.add(k)
                if f.get("type") not in FIELD_TYPES:
                    bad.append(f"field '{k}': type must be one of {', '.join(FIELD_TYPES)}")
                if f.get("type") == "choice" and not f.get("options"):
                    bad.append(f"field '{k}': a choice needs options")
                if f.get("type") == "number" and not all(x in f for x in ("min", "max")):
                    bad.append(f"field '{k}': a number needs min and max")
    for k in d.get("summary") or []:
        if k not in keys:
            bad.append(f"summary lists unknown field '{k}'")
    return bad


def discover(dirs: list[Path] | None = None) -> dict[str, Plugin]:
    """All valid plugins by id. A broken plugin is skipped (it never takes the app down); an id found twice keeps
    the first, so a bundled plugin cannot be shadowed by accident."""
    found: dict[str, Plugin] = {}
    for base in dirs if dirs is not None else plugin_dirs():
        if not base.is_dir():
            continue
        manifests = [base / "plugin.json"] if (base / "plugin.json").is_file() else sorted(base.glob("*/plugin.json"))
        for mf in manifests:
            try:
                d = json.loads(mf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if validate_manifest(d, str(mf)) or d["id"] in found:
                continue
            found[d["id"]] = Plugin(d["id"], d["name"], mf.parent, d)
    return found


def step_keys(plugin_id: str, plugins: dict[str, Plugin]) -> list[str]:
    p = plugins.get(plugin_id)
    return [f"plugin.{plugin_id}.{i}" for i in range(len(p.steps))] if p else []


def nest(flat: dict[str, Any]) -> dict:
    """{"people.her_name": "A"}  ->  {"people": {"her_name": "A"}}"""
    out: dict = {}
    for k, v in flat.items():
        cur = out
        parts = k.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return out


# ------------------------------------------------------------------------------------------ engine side
@dataclass
class PluginContext:
    """What run(ctx) gets. Everything a plugin needs from the engine, nothing it has to import to get it."""
    plugin: Plugin
    job: dict
    values: dict[str, Any]                       # every field, defaults filled in, flat dotted keys
    emit: Callable[[dict], None]
    out_dir: Path
    preview: bool = False
    scene: Path | None = None                    # scene.json of the finished mosaic (needs == "mosaic")
    cache_dir: Path | None = None                # the tile cache that goes with it
    settings: Any = None                         # mosaicvid.settings.Settings used for the mosaic
    tiles_dir: str = ""
    main_image: str = ""

    @property
    def plugin_dir(self) -> Path:
        return self.plugin.path

    def nested(self) -> dict:
        return nest(self.values)

    def stage(self, stage_id: str, label: str = "") -> None:
        self.emit({"event": "stage", "stage": stage_id, "label": label or stage_id})

    def progress(self, stage_id: str, done: int, total: int) -> None:
        self.emit({"event": "progress", "stage": stage_id, "done": int(done), "total": int(total)})

    def info(self, message: str) -> None:
        self.emit({"event": "info", "message": message})

    @staticmethod
    def ffmpeg() -> str:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()


def load_entry(plugin: Plugin):
    """Import the plugin's entry file (engine process only)."""
    entry = plugin.path / plugin.manifest.get("entry", "plugin.py")
    if not entry.is_file():
        raise PluginError(f"Plugin '{plugin.id}' has no {entry.name}")
    spec = importlib.util.spec_from_file_location(f"mosaicvid_plugin_{plugin.id}", entry)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(plugin.path))         # lets the plugin import its own helper files
    try:
        spec.loader.exec_module(mod)
    finally:
        try:
            sys.path.remove(str(plugin.path))
        except ValueError:
            pass
    if not callable(getattr(mod, "run", None)):
        raise PluginError(f"Plugin '{plugin.id}': {entry.name} must define run(ctx)")
    return mod


def run_plugin(plugin: Plugin, ctx: PluginContext) -> dict:
    mod = load_entry(plugin)
    sys.path.insert(0, str(plugin.path))         # film.py-style helpers import each other at run time too
    try:
        out = mod.run(ctx) or {}
    finally:
        try:
            sys.path.remove(str(plugin.path))
        except ValueError:
            pass
    if not isinstance(out, dict):
        raise PluginError(f"Plugin '{plugin.id}': run() must return a dict of output files")
    return {k: str(v) for k, v in out.items()}


def fill_defaults(plugin: Plugin, given: dict | None) -> dict[str, Any]:
    vals = plugin.defaults()
    for k, v in (given or {}).items():
        if k in vals:
            vals[k] = v
    return vals
