"""Plugin library: a catalog of plugins people can install from inside Mosaic Studio.

The catalog is one JSON file (`registry.json`) that lists plugins; each entry points at a .zip of the plugin folder::

    {"api": 1, "plugins": [
        {"id": "birthday", "name": "Birthday video", "version": "1.0.0", "author": "...",
         "description": "A personal film...", "chips": ["Names + message", "Music"],
         "download": "birthday-1.0.0.zip",          # URL, or a path relative to the catalog's own location
         "sha256": "<hex digest of the zip>"}       # required: the download is rejected if it does not match
    ]}

Where the catalog comes from: `MOSAICVID_CATALOG` (a URL or a file path, handy for a private library or testing),
otherwise CATALOG_URL. Installing unpacks the zip into %APPDATA%/MosaicStudio/plugins/<id> (see `plugins.user_plugin_dir`).

A plugin runs Python code on the user's computer, so the library only installs what matches the catalog's checksum and
the window warns before every install. Standard library only: this module is safe to import in the window.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import plugins as P

CATALOG_URL = "https://raw.githubusercontent.com/mahatosourav00/mosaic-video/main/catalog/registry.json"
MAX_ZIP = 100 * 1024 * 1024
TIMEOUT = 20
INSTALLED_MARK = ".from-library"            # file inside an installed plugin: remembers the version it came with


class LibraryError(Exception):
    """The catalog or a download could not be used (message is safe to show to the user)."""


@dataclass
class Entry:
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    chips: list[str] = field(default_factory=list)
    download: str = ""                      # absolute URL or path (already resolved against the catalog)
    sha256: str = ""
    homepage: str = ""


def catalog_source() -> str:
    return os.environ.get("MOSAICVID_CATALOG", "").strip() or CATALOG_URL


def _is_url(s: str) -> bool:
    return urllib.parse.urlparse(s).scheme in ("http", "https")


def _read(src: str, limit: int) -> bytes:
    try:
        if _is_url(src):
            req = urllib.request.Request(src, headers={"User-Agent": "MosaicStudio"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:                  # noqa: S310 - http(s) only
                data = r.read(limit + 1)
        else:
            data = Path(src).read_bytes()
    except (OSError, ValueError) as e:
        raise LibraryError(f"Could not reach the plugin library. Check your internet connection. ({e})") from None
    if len(data) > limit:
        raise LibraryError("That download is larger than allowed.")
    return data


def _resolve(base: str, ref: str) -> str:
    if _is_url(ref):
        return ref
    if _is_url(base):
        return urllib.parse.urljoin(base, ref)
    return str((Path(base).parent / ref).resolve())


def parse_catalog(data: dict, base: str = "") -> list[Entry]:
    """Entries of a catalog; malformed ones are skipped, never fatal."""
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise LibraryError("The plugin library has an unexpected format.")
    out: list[Entry] = []
    for d in data["plugins"]:
        try:
            pid, name, ver, dl, sha = d["id"], d["name"], str(d["version"]), d["download"], d["sha256"]
            if not (isinstance(pid, str) and pid and all(c.isalnum() or c in "-_" for c in pid)):
                continue
            out.append(Entry(pid, str(name), ver, str(d.get("description", "")), str(d.get("author", "")),
                             [str(c) for c in d.get("chips") or []], _resolve(base, str(dl)), str(sha).lower(),
                             str(d.get("homepage", ""))))
        except (KeyError, TypeError):
            continue
    return out


def fetch_catalog(source: str | None = None) -> list[Entry]:
    src = source or catalog_source()
    try:
        data = json.loads(_read(src, 2 * 1024 * 1024).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise LibraryError("The plugin library has an unexpected format.") from None
    return parse_catalog(data, src)


# ------------------------------------------------------------------------------------------ installed state
def installed_version(plugin_id: str) -> str | None:
    """Version of a library-installed plugin, or None if it was not installed from the library."""
    mark = P.user_plugin_dir() / plugin_id / INSTALLED_MARK
    try:
        return mark.read_text(encoding="utf-8").strip() or "0"
    except OSError:
        return None


def _vkey(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in v.replace("-", ".").split("."))


def status(entry: Entry, installed: dict[str, P.Plugin] | None = None) -> str:
    """'install' | 'update' | 'installed' | 'added' (the id is already there, but not from the library)."""
    have = installed_version(entry.id)
    if have is not None:
        return "update" if _vkey(entry.version) > _vkey(have) else "installed"
    return "added" if installed and entry.id in installed else "install"


# ------------------------------------------------------------------------------------------ install / remove
def install(entry: Entry) -> P.Plugin:
    """Download, verify and unpack a plugin into the user's plugin folder. Returns the discovered plugin."""
    if not entry.sha256:
        raise LibraryError("This plugin has no checksum in the library, so it will not be installed.")
    blob = _read(entry.download, MAX_ZIP)
    if hashlib.sha256(blob).hexdigest() != entry.sha256:
        raise LibraryError("The download does not match the library's checksum, so it was not installed.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        raise LibraryError("The download is not a valid plugin package.") from None
    with zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        for n in names:                                         # no path tricks out of the plugin folder
            parts = Path(n).parts
            if Path(n).is_absolute() or ".." in parts or ":" in n:
                raise LibraryError("The plugin package contains unsafe file paths.")
        prefix = _common_root(names)
        if f"{prefix}plugin.json" not in names:
            raise LibraryError("The plugin package has no plugin.json.")
        try:
            manifest = json.loads(zf.read(f"{prefix}plugin.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise LibraryError("The plugin's plugin.json is not valid.") from None
        bad = P.validate_manifest(manifest)
        if bad:
            raise LibraryError("The plugin is not valid: " + "; ".join(bad))
        if manifest["id"] != entry.id:
            raise LibraryError("The package does not match the library entry.")
        dest = P.user_plugin_dir() / entry.id
        tmp = dest.with_name(f".{entry.id}.installing")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        try:
            for n in names:
                target = tmp / n[len(prefix):]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(n))
            (tmp / INSTALLED_MARK).write_text(entry.version, encoding="utf-8")
            shutil.rmtree(dest, ignore_errors=True)
            tmp.replace(dest)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    found = P.discover()
    if entry.id not in found:
        raise LibraryError("The plugin was unpacked but could not be loaded.")
    return found[entry.id]


def _common_root(names: list[str]) -> str:
    """'' if plugin.json sits at the top of the zip, else the single folder that holds everything ('name/')."""
    if "plugin.json" in names:
        return ""
    tops = {Path(n).parts[0] for n in names}
    return f"{tops.pop()}/" if len(tops) == 1 else ""


def remove(plugin_id: str) -> bool:
    """Uninstall a plugin that came from the library. False if it was not installed that way."""
    if not (plugin_id and all(c.isalnum() or c in "-_" for c in plugin_id)) or installed_version(plugin_id) is None:
        return False
    shutil.rmtree(P.user_plugin_dir() / plugin_id, ignore_errors=True)
    return True
