"""Tile ingestion: EXIF fix, border trim, quality filter, dedupe, smart square crop."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageOps

from .settings import Settings

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
WORK_SIDE = 1600


@dataclass
class Tile:
    path: str
    image: np.ndarray       # (cache_px, cache_px, 3) uint8 RGB
    sharpness: float


def list_images(folder: str | Path) -> list[Path]:
    return sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in IMG_EXT)


def load_rgb(path: str | Path, max_side: int | None = WORK_SIDE) -> np.ndarray:
    """Load, apply EXIF orientation, convert to RGB, optionally downscale."""
    with Image.open(path) as im:
        if max_side:
            im.draft("RGB", (max_side, max_side))
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max_side and max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
        return np.asarray(im)


# ---------------------------------------------------------------- borders
def _trim_side(lines_std: np.ndarray, lines_mean: np.ndarray, limit: int,
               std_thr: float = 7.0, color_tol: float = 14.0, jump_min: float = 18.0) -> int:
    """Count uniform border lines at the start of a (n, 3) profile."""
    ref = lines_mean[0]
    k = 0
    while k < limit and lines_std[k] < std_thr and np.abs(lines_mean[k] - ref).max() < color_tol:
        k += 1
    if k == 0 or k >= limit:
        return 0
    # a real border ends with a sharp jump; a smooth sky/wall does not
    if np.abs(lines_mean[k] - lines_mean[k - 1]).max() < jump_min:
        return 0
    return k


def trim_borders(arr: np.ndarray, max_frac: float = 0.3) -> np.ndarray:
    h, w, _ = arr.shape
    a = arr.astype(np.float32)
    row_std = a.std(axis=1).max(axis=1)      # (h,)
    row_mean = a.mean(axis=1)                # (h,3)
    col_std = a.std(axis=0).max(axis=1)      # (w,)
    col_mean = a.mean(axis=0)                # (w,3)
    lim_h, lim_w = int(h * max_frac), int(w * max_frac)
    top = _trim_side(row_std, row_mean, lim_h)
    bot = _trim_side(row_std[::-1], row_mean[::-1], lim_h)
    left = _trim_side(col_std, col_mean, lim_w)
    right = _trim_side(col_std[::-1], col_mean[::-1], lim_w)
    pad = 1  # also drop anti-aliased fringe
    t, b = (top + pad if top else 0), (bot + pad if bot else 0)
    l, r = (left + pad if left else 0), (right + pad if right else 0)
    if h - t - b < h * 0.4 or w - l - r < w * 0.4:
        return arr
    return arr[t:h - b, l:w - r]


# ------------------------------------------------------------- smart crop
_FACE = None


def _face_detector():
    global _FACE
    if _FACE is None:
        try:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            det = cv2.CascadeClassifier(path)
            _FACE = det if not det.empty() else False
        except Exception:
            _FACE = False
    return _FACE


def smart_square_crop(arr: np.ndarray) -> np.ndarray:
    """Crop to a square keeping the most salient area (edges + faces)."""
    h, w, _ = arr.shape
    if h == w:
        return arr
    scale = 256.0 / max(h, w)
    small = cv2.resize(arr, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    sal = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    sal = cv2.GaussianBlur(sal, (0, 0), 3) + 1e-3
    det = _face_detector()
    if det:
        try:
            for (x, y, fw, fh) in det.detectMultiScale(gray, 1.15, 5, minSize=(18, 18)):
                sal[y:y + fh, x:x + fw] += sal.max() * 3.0
        except Exception:
            pass
    sh, sw = gray.shape
    side = min(sh, sw)
    if sw > sh:
        prof = sal.sum(axis=0)
        n = sw
    else:
        prof = sal.sum(axis=1)
        n = sh
    csum = np.concatenate([[0], np.cumsum(prof)])
    starts = np.arange(0, n - side + 1)
    scores = csum[starts + side] - csum[starts]
    centre = (n - side) / 2.0
    bias = 1.0 - 0.15 * np.abs(starts - centre) / max(centre, 1.0)
    best = int(starts[np.argmax(scores * bias)])
    start = int(round(best / scale))
    full_side = min(h, w)
    if w > h:
        start = min(start, w - full_side)
        return arr[:, start:start + full_side]
    start = min(start, h - full_side)
    return arr[start:start + full_side]


# ------------------------------------------------------------- pipeline
def _key(path: Path, s: Settings) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|{s.cache_px}|{s.trim_borders}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _sharpness(arr: np.ndarray) -> float:
    g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    s = 512.0 / max(g.shape)
    if s < 1:
        g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def _process_one(path: Path, s: Settings, cache: Path | None) -> Tile | None:
    key = _key(path, s)
    if cache:
        hit, rej = cache / f"{key}.npy", cache / f"{key}.rej"
        if rej.exists():
            return None
        if hit.exists():
            data = np.load(hit)
            return Tile(str(path), data, _sharpness(data))
    try:
        arr = load_rgb(path)
        if s.trim_borders:
            arr = trim_borders(arr)
        h, w, _ = arr.shape
        sharp = _sharpness(arr)
        if min(h, w) < s.min_side or sharp < s.min_sharpness:
            if cache:
                (cache / f"{key}.rej").touch()
            return None
        sq = smart_square_crop(arr)
        out = np.asarray(Image.fromarray(sq).resize((s.cache_px, s.cache_px), Image.LANCZOS))
    except Exception:
        return None
    if cache:
        np.save(cache / f"{key}.npy", out)
    return Tile(str(path), out, sharp)


def _dedupe(tiles: list[Tile], max_dist: int = 4) -> list[Tile]:
    hashes = [int(str(imagehash.phash(Image.fromarray(t.image))), 16) for t in tiles]
    keep: list[int] = []
    for i in sorted(range(len(tiles)), key=lambda i: -tiles[i].sharpness):
        if all(bin(hashes[i] ^ hashes[j]).count("1") > max_dist for j in keep):
            keep.append(i)
    return [tiles[i] for i in sorted(keep)]


def load_tiles(paths: list[str], s: Settings, cache_dir: str | Path | None = None) -> list[Tile]:
    """Reload exactly these tiles, in order (uses the cache written by prepare_tiles)."""
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    out = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for p, t in zip(paths, ex.map(lambda p: _process_one(Path(p), s, cache), paths)):
            if t is None:
                raise RuntimeError(f"Tile could not be reloaded: {p}")
            out.append(t)
    return out


def prepare_tiles(folder: str | Path, s: Settings, cache_dir: str | Path | None = None,
                  progress=None) -> list[Tile]:
    paths = list_images(folder)
    cache = None
    if cache_dir:
        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
    tiles: list[Tile] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, t in enumerate(ex.map(lambda p: _process_one(p, s, cache), paths)):
            if t is not None:
                tiles.append(t)
            if progress:
                progress(i + 1, len(paths))
    if s.dedupe and len(tiles) > 1:
        tiles = _dedupe(tiles)
    return tiles
