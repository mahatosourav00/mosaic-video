"""Tile ingestion: EXIF fix, border trim, quality filter, dedupe, smart square crop."""
from __future__ import annotations

import hashlib
import threading
import json
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
    image: np.ndarray       # (cache_px, cache_px*ratio, 3) uint8 RGB
    sharpness: float


def list_images(folders, recursive: bool = True, exclude=()) -> list[Path]:
    """Pictures in one folder or several (a path or a list of paths). `exclude` folders are skipped wherever they
    appear, and the same file is never listed twice."""
    if isinstance(folders, (str, Path)):
        folders = [folders]
    ex = [Path(e).resolve() for e in exclude]
    seen: set[Path] = set()
    out: list[Path] = []
    for f in folders:
        it = Path(f).rglob("*") if recursive else Path(f).glob("*")
        for p in it:
            if p.suffix.lower() not in IMG_EXT:
                continue
            rp = p.resolve()
            if rp in seen or any(e == rp or e in rp.parents for e in ex):
                continue
            seen.add(rp)
            out.append(p)
    return sorted(out)


def to_gray3(arr: np.ndarray) -> np.ndarray:
    """Black & white, kept as 3 channels so the rest of the pipeline is unchanged."""
    g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return np.repeat(g[..., None], 3, axis=2)


def collection_paths(folder, s: Settings) -> list[Path]:
    """All tile photos for a job: the main folder (or list), plus the extra folders, minus excluded ones."""
    base = [folder] if isinstance(folder, (str, Path)) else list(folder)
    return list_images(base + [d for d in s.extra_tile_dirs if d], s.include_subfolders, s.exclude_dirs)


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
    pure = bool(ref.min() >= 250 or ref.max() <= 5)   # pure white / black frame
    if pure:  # strict run, so a soft near-white gradient after the frame is not swallowed
        std_thr, color_tol = 2.5, 5.0
        limit = min(limit, int(len(lines_std) * 0.12))  # wider = blown-out sky/wall, not a frame
    k = 0
    while k < limit and lines_std[k] < std_thr and np.abs(lines_mean[k] - ref).max() < color_tol:
        k += 1
    if k == 0 or k >= limit:
        return 0
    # a real border ends with a sharp jump; a smooth sky/wall does not (pure white/black frames are exempt)
    # (pure white/black frames up to 6% are exempt; thicker ones still need a sharp edge)
    exempt = pure and k <= len(lines_std) * 0.06
    if not exempt and np.abs(lines_mean[k] - lines_mean[k - 1]).max() < jump_min:
        return 0
    return k


def trim_borders(arr: np.ndarray, max_frac: float = 0.3) -> np.ndarray:
    return trim_borders_info(arr, max_frac)[0]


def trim_borders_info(arr: np.ndarray, max_frac: float = 0.3):
    """Returns (trimmed array, (top, bottom, left, right) pixels removed)."""
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
        return arr, (0, 0, 0, 0)
    return arr[t:h - b, l:w - r], (t, b, l, r)


# ------------------------------------------------------------- smart crop
cv2.setNumThreads(1)         # we already parallelise per photo
cv2.ocl.setUseOpenCL(False)  # OpenCV's OpenCL (integrated-GPU driver) path left the process unkillable after cold runs
_FACE = None
_FACE_LOCK = threading.Lock()


class _LockedDetector:
    """One shared CascadeClassifier, calls serialised: it is not thread-safe (concurrent calls crash
    with an access violation) and per-thread copies made the process hang at exit on Windows."""

    def __init__(self, det):
        self._det = det

    def detectMultiScale(self, *args, **kwargs):
        with _FACE_LOCK:
            return self._det.detectMultiScale(*args, **kwargs)


def _face_detector():
    global _FACE
    if _FACE is None:
        with _FACE_LOCK:
            if _FACE is None:
                try:
                    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                    det = cv2.CascadeClassifier(path)
                    _FACE = _LockedDetector(det) if not det.empty() else False
                except Exception:
                    _FACE = False
    return _FACE


def detect_rotation(arr: np.ndarray) -> int:
    """How many 90-degree CCW turns (0-3) make faces upright. Conservative: returns 0 unless an
    upright face is absent AND a face is clearly found in exactly one rotated version."""
    det = _face_detector()
    if not det:
        return 0
    h, w, _ = arr.shape
    sc = 256.0 / max(h, w)
    gray = cv2.cvtColor(cv2.resize(arr, (max(1, int(w * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA),
                        cv2.COLOR_RGB2GRAY)
    scores = []
    for k in range(4):
        g = np.ascontiguousarray(np.rot90(gray, k))
        try:
            # strict: small/low-confidence hits (figures, textures) caused false rotations
            faces = det.detectMultiScale(g, 1.15, 6 if k == 0 else 10, minSize=(24, 24) if k == 0 else (44, 44))
        except Exception:
            faces = []
        scores.append(float(sum(fw * fh for (_, _, fw, fh) in faces)))
        if k == 0 and scores[0] > 0:
            return 0                       # already upright
    best = int(np.argmax(scores))
    others = [s for i, s in enumerate(scores) if i not in (0, best)]
    return best if scores[best] > 0 and all(s == 0 for s in others) else 0


def _window(h: int, w: int, ratio: float) -> tuple[int, int]:
    """Largest (crop_h, crop_w) with w/h == ratio that fits in h x w."""
    if w / h > ratio:
        return h, max(1, int(round(h * ratio)))
    return max(1, int(round(w / ratio))), w


def centre_square_crop(arr: np.ndarray, ratio: float = 1.0) -> np.ndarray:
    h, w, _ = arr.shape
    ch, cw = _window(h, w, ratio)
    y, x = (h - ch) // 2, (w - cw) // 2
    return arr[y:y + ch, x:x + cw]


def smart_square_crop(arr: np.ndarray, ratio: float = 1.0) -> np.ndarray:
    """Crop to w/h == ratio keeping the most salient area (edges + faces)."""
    h, w, _ = arr.shape
    ch, cw = _window(h, w, ratio)
    if (ch, cw) == (h, w):
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
    sch, scw = _window(sh, sw, ratio)
    if cw < w:                      # slide horizontally
        prof, n, side, full_side, total = sal.sum(axis=0), sw, scw, cw, w
    else:                           # slide vertically
        prof, n, side, full_side, total = sal.sum(axis=1), sh, sch, ch, h
    csum = np.concatenate([[0], np.cumsum(prof)])
    starts = np.arange(0, max(n - side, 0) + 1)
    scores = csum[starts + side] - csum[starts]
    centre = (n - side) / 2.0
    bias = 1.0 - 0.15 * np.abs(starts - centre) / max(centre, 1.0)
    best = int(starts[np.argmax(scores * bias)])
    start = min(int(round(best / scale)), total - full_side)
    if cw < w:
        return arr[:, start:start + cw]
    return arr[start:start + ch]


# ------------------------------------------------------------- pipeline
CACHE_VERSION = 5   # bump when preprocessing logic changes (invalidates the disk cache)


@dataclass
class Record:
    """What happened to one input photo (feeds the report / contact sheet)."""
    path: str
    status: str = "ok"          # ok | rejected | duplicate
    reason: str = ""
    size: tuple = (0, 0)        # original (w, h) as loaded (<= WORK_SIDE)
    rotation: int = 0           # degrees CCW applied by auto-rotate (0/90/180/270)
    trim: tuple = (0, 0, 0, 0)  # px removed top, bottom, left, right (at working size)
    sharpness: float = 0.0
    tile_index: int = -1        # index into the final tile list (ok only)
    duplicate_of: str = ""


def _key(path: Path, s: Settings) -> str:
    st = path.stat()
    raw = f"v{CACHE_VERSION}|{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|{s.cache_px}|{s.trim_borders}|{s.auto_rotate}"
    if not s.smart_crop:
        raw += "|centrecrop"          # only added when off, so existing caches stay valid
    if s.grayscale:
        raw += "|gray"
    if s.tile_aspect != "1:1":
        raw += f"|tile{s.tile_aspect}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _sharpness(arr: np.ndarray) -> float:
    g = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    s = 512.0 / max(g.shape)
    if s < 1:
        g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def _process_ex(path: Path, s: Settings, cache: Path | None) -> tuple[Tile | None, Record]:
    rec = Record(str(path))
    key = _key(path, s)
    meta = cache / f"{key}.json" if cache else None
    if cache:
        hit, rej = cache / f"{key}.npy", cache / f"{key}.rej"
        if (rej.exists() or hit.exists()) and meta.exists():
            try:
                rec.__dict__.update({k: tuple(v) if isinstance(v, list) else v
                                     for k, v in json.loads(meta.read_text("utf-8")).items() if k in rec.__dict__})
            except Exception:
                pass
        if rej.exists():
            rec.status = "rejected"
            rec.reason = rec.reason or "rejected (cached)"
            return None, rec
        if hit.exists():
            data = np.load(hit)
            rec.sharpness = rec.sharpness or _sharpness(data)
            return Tile(str(path), data, rec.sharpness), rec

    def save_meta():
        if cache:
            meta.write_text(json.dumps({"status": rec.status, "reason": rec.reason, "size": rec.size,
                                        "trim": rec.trim, "sharpness": rec.sharpness,
                                        "rotation": rec.rotation}), "utf-8")
    try:
        arr = load_rgb(path)
        rec.size = (arr.shape[1], arr.shape[0])
        if s.auto_rotate:
            k = detect_rotation(arr)
            if k:
                arr, rec.rotation = np.ascontiguousarray(np.rot90(arr, k)), 90 * k
        if s.trim_borders:
            arr, rec.trim = trim_borders_info(arr)
        h, w, _ = arr.shape
        rec.sharpness = sharp = _sharpness(arr)
        if min(h, w) < s.min_side:
            rec.status, rec.reason = "rejected", f"too small ({w}x{h} < {s.min_side}px)"
        elif sharp < s.min_sharpness:
            rec.status, rec.reason = "rejected", f"too blurry (sharpness {sharp:.1f} < {s.min_sharpness})"
        if rec.status == "rejected":
            if cache:
                (cache / f"{key}.rej").touch()
                save_meta()
            return None, rec
        tr = s.tile_ratio()
        sq = smart_square_crop(arr, tr) if s.smart_crop else centre_square_crop(arr, tr)
        out = np.asarray(Image.fromarray(sq).resize((max(1, int(round(s.cache_px * tr))), s.cache_px), Image.LANCZOS))
        if s.grayscale:
            out = to_gray3(out)
    except Exception as e:
        rec.status, rec.reason = "rejected", f"unreadable ({type(e).__name__}: {e})"[:120]
        return None, rec
    if cache:
        np.save(cache / f"{key}.npy", out)
        save_meta()
    return Tile(str(path), out, rec.sharpness), rec


def _process_one(path: Path, s: Settings, cache: Path | None) -> Tile | None:
    return _process_ex(path, s, cache)[0]


def _dedupe_ex(tiles: list[Tile], max_dist: int = 4) -> tuple[list[int], dict[int, int]]:
    """Returns (kept indices in original order, {dropped index: kept index it duplicates})."""
    hashes = [int(str(imagehash.phash(Image.fromarray(t.image))), 16) for t in tiles]
    keep: list[int] = []
    dropped: dict[int, int] = {}
    for i in sorted(range(len(tiles)), key=lambda i: -tiles[i].sharpness):
        twin = next((j for j in keep if bin(hashes[i] ^ hashes[j]).count("1") <= max_dist), None)
        if twin is None:
            keep.append(i)
        else:
            dropped[i] = twin
    return sorted(keep), dropped


def _dedupe(tiles: list[Tile], max_dist: int = 4) -> list[Tile]:
    keep, _ = _dedupe_ex(tiles, max_dist)
    return [tiles[i] for i in keep]


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


def prepare_tiles_report(folder: str | Path, s: Settings, cache_dir: str | Path | None = None,
                         progress=None) -> tuple[list[Tile], list[Record]]:
    """Like prepare_tiles but also returns one Record per input photo."""
    paths = collection_paths(folder, s)
    cache = None
    if cache_dir:
        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
    tiles: list[Tile] = []
    recs: list[Record] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (t, r) in enumerate(ex.map(lambda p: _process_ex(p, s, cache), paths)):
            recs.append(r)
            if t is not None:
                tiles.append(t)
            if progress:
                progress(i + 1, len(paths))
    ok = [r for r in recs if r.status == "ok"]            # same order as `tiles`
    if s.dedupe and len(tiles) > 1:
        keep, dropped = _dedupe_ex(tiles)
        for d, k in dropped.items():
            ok[d].status, ok[d].duplicate_of = "duplicate", ok[k].path
            ok[d].reason = f"near-duplicate of {Path(ok[k].path).name}"
        tiles = [tiles[i] for i in keep]
        ok = [ok[i] for i in keep]
    for n, r in enumerate(ok):
        r.tile_index = n
    return tiles, recs


def prepare_tiles(folder: str | Path, s: Settings, cache_dir: str | Path | None = None,
                  progress=None) -> list[Tile]:
    return prepare_tiles_report(folder, s, cache_dir, progress)[0]
