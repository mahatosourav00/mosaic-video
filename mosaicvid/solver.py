"""Mosaic solver: layout (cells + subtiles) -> tile assignment -> still render + scene.json."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .preprocess import Tile, load_rgb
from .settings import Settings
from .subject import subject_centroid, subject_map

ANALYSIS_PX = 24   # analysis pixels per base cell
PATCH = 4          # matching patch is PATCH x PATCH Lab samples
DIM = PATCH * PATCH * 3


@dataclass
class Cell:
    x: float          # top-left, in base-cell units
    y: float
    size: float       # in base-cell units (1.0 or 1/k)
    tile: int = -1
    flip: bool = False
    shift: tuple = (0.0, 0.0, 0.0)   # Lab shift to apply to tile (tint)
    w: float = 0.0                   # subject importance 0..1

    @property
    def cx(self) -> float:
        return self.x + self.size / 2

    @property
    def cy(self) -> float:
        return self.y + self.size / 2


@dataclass
class Mosaic:
    cols: int
    rows: int
    cells: list[Cell]
    tile_paths: list[str]
    main: np.ndarray            # cropped main image, RGB uint8
    stats: dict
    subject: np.ndarray | None = None   # subject map at analysis resolution
    main_path: str = ""


# ------------------------------------------------------------------ layout
def grid_dims(w: int, h: int, n: int) -> tuple[int, int]:
    cols = max(2, round(math.sqrt(n * w / h)))
    rows = max(2, round(n / cols))
    return cols, rows


def crop_to_ratio(img: np.ndarray, ratio: float, focus: tuple[float, float] = (0.5, 0.5)) -> np.ndarray:
    """Crop to w/h == ratio, keeping `focus` (fractions x, y) as centred as the image allows."""
    h, w, _ = img.shape
    if w / h > ratio:
        nw = int(round(h * ratio))
        x = int(np.clip(focus[0] * w - nw / 2, 0, w - nw))
        return img[:, x:x + nw]
    nh = int(round(w / ratio))
    y = int(np.clip(focus[1] * h - nh / 2, 0, h - nh))
    return img[y:y + nh]


def _lab(rgb_u8: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb_u8.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def _patch(lab: np.ndarray, x0, y0, size) -> np.ndarray:
    a = ANALYSIS_PX
    xs, xe = int(round(x0 * a)), int(round((x0 + size) * a))
    ys, ye = int(round(y0 * a)), int(round((y0 + size) * a))
    reg = lab[ys:max(ye, ys + 1), xs:max(xe, xs + 1)]
    return cv2.resize(reg, (PATCH, PATCH), interpolation=cv2.INTER_AREA)


def region_mean(m: np.ndarray, x0, y0, size) -> float:
    a = ANALYSIS_PX
    xs, xe = int(round(x0 * a)), int(round((x0 + size) * a))
    ys, ye = int(round(y0 * a)), int(round((y0 + size) * a))
    return float(m[ys:max(ye, ys + 1), xs:max(xe, xs + 1)].mean())


def build_cells(cols: int, rows: int, analysis_lab: np.ndarray, s: Settings,
                rng: np.random.Generator, subject: np.ndarray | None = None) -> list[Cell]:
    base = [(x, y) for y in range(rows) for x in range(cols)]
    split: set[int] = set()
    if s.use_subtiles and s.subtile_percent > 0:
        m = int(round(len(base) * min(s.subtile_percent, 100) / 100))
        if s.subtile_select == "detail":
            detail = np.array([analysis_lab[int(y * ANALYSIS_PX):int((y + 1) * ANALYSIS_PX),
                                            int(x * ANALYSIS_PX):int((x + 1) * ANALYSIS_PX), 0].std()
                               for x, y in base])
            score = detail / (detail.max() + 1e-6)
            if subject is not None and s.subject_weight > 0:
                wb = np.array([region_mean(subject, x, y, 1) for x, y in base])
                score = (1 - 0.5 * s.subject_weight) * score + 1.5 * s.subject_weight * wb
            split = set(np.argsort(-score)[:m].tolist())
        else:
            split = set(rng.choice(len(base), size=m, replace=False).tolist())
    k = s.subtile_grid
    cells: list[Cell] = []
    for i, (x, y) in enumerate(base):
        if i in split:
            for sy in range(k):
                for sx in range(k):
                    cells.append(Cell(x + sx / k, y + sy / k, 1.0 / k))
        else:
            cells.append(Cell(x, y, 1.0))
    return cells


# --------------------------------------------------------------- matching
def tile_features(tiles: list[Tile]) -> np.ndarray:
    """(T, 2, DIM): Lab patch for normal and horizontally flipped tile."""
    out = np.zeros((len(tiles), 2, DIM), np.float32)
    for i, t in enumerate(tiles):
        p = cv2.resize(_lab(t.image), (PATCH, PATCH), interpolation=cv2.INTER_AREA)
        out[i, 0] = p.ravel()
        out[i, 1] = p[:, ::-1].ravel()
    return out


def _cost_matrix(target: np.ndarray, feats: np.ndarray, allow_flip: bool) -> np.ndarray:
    """(C, T, 2) squared distances."""
    T = feats.shape[0]
    f = feats.reshape(T * 2, DIM)
    d = (target ** 2).sum(1)[:, None] + (f ** 2).sum(1)[None, :] - 2.0 * target @ f.T
    d = np.maximum(d, 0).reshape(len(target), T, 2)
    if not allow_flip:
        d[:, :, 1] = np.inf
    return d


def assign(cells: list[Cell], target: np.ndarray, feats: np.ndarray, s: Settings,
           rng: np.random.Generator) -> dict:
    C, T = len(cells), feats.shape[0]
    cost3 = _cost_matrix(target, feats, s.allow_flip)
    best_flip = cost3.argmin(axis=2)
    cost = np.take_along_axis(cost3, best_flip[:, :, None], axis=2)[:, :, 0]   # (C,T)

    natural = math.ceil(C / T)
    max_uses = s.max_uses if s.max_uses > 0 else 10 ** 9
    raised = False
    if max_uses * T < C:
        max_uses, raised = natural, True
    scale = float(np.median(cost.min(axis=1))) + 1e-6
    pen = s.even_usage * scale

    uses = np.zeros(T, np.int32)
    pos: list[list[tuple[float, float]]] = [[] for _ in range(T)]
    d2 = s.min_distance ** 2
    violations = 0

    def ok(t: int, cx: float, cy: float, skip=None) -> bool:
        if d2 <= 0:
            return True
        for (px, py) in pos[t]:
            if skip is not None and (px, py) == skip:
                continue
            if (px - cx) ** 2 + (py - cy) ** 2 < d2:
                return False
        return True

    if s.subject_weight > 0:     # subject cells pick first -> best tiles, fewest constraints
        wts = np.array([c.w for c in cells])
        order_cells = np.argsort(-(s.subject_weight * wts + 0.15 * rng.random(C)))
    else:
        order_cells = rng.permutation(C)
    for ci in order_cells:
        c = cells[ci]
        adj = cost[ci] + pen * uses
        order = np.argsort(adj)
        chosen = -1
        for t in order:
            if uses[t] < max_uses and ok(t, c.cx, c.cy):
                chosen = int(t); break
        if chosen < 0:                      # relax distance rule
            for t in order:
                if uses[t] < max_uses:
                    chosen = int(t); violations += 1; break
        c.tile = chosen
        c.flip = bool(best_flip[ci, chosen])
        uses[chosen] += 1
        pos[chosen].append((c.cx, c.cy))

    # swap refinement: lowers matching error, keeps usage counts, respects distance
    iters = min(30 * C, 300_000)
    swaps = 0
    ra = rng.integers(0, C, iters); rb = rng.integers(0, C, iters)
    for a, b in zip(ra, rb):
        if a == b:
            continue
        ca, cb = cells[a], cells[b]
        ta, tb = ca.tile, cb.tile
        if ta == tb:
            continue
        if cost[a, tb] + cost[b, ta] >= cost[a, ta] + cost[b, tb] - 1e-6:
            continue
        if not (ok(tb, ca.cx, ca.cy, skip=(cb.cx, cb.cy)) and ok(ta, cb.cx, cb.cy, skip=(ca.cx, ca.cy))):
            continue
        pos[ta].remove((ca.cx, ca.cy)); pos[tb].remove((cb.cx, cb.cy))
        pos[ta].append((cb.cx, cb.cy)); pos[tb].append((ca.cx, ca.cy))
        ca.tile, cb.tile = tb, ta
        ca.flip, cb.flip = bool(best_flip[a, tb]), bool(best_flip[b, ta])
        swaps += 1

    return {"violations": violations, "max_uses_raised": raised, "swaps": swaps,
            "min_used": int(uses.min()), "max_used": int(uses.max()),
            "unused_tiles": int((uses == 0).sum())}


# ----------------------------------------------------------------- driver
def solve(tiles: list[Tile], main_path: str | Path, s: Settings) -> Mosaic:
    s.validate()
    if not tiles:
        raise ValueError("No usable tile photos")
    rng = np.random.default_rng(s.seed)
    main = load_rgb(main_path, max_side=3000)
    h, w, _ = main.shape
    if s.grid_follows_video:            # grid takes the video's shape; crop around the subject
        vw, vh = s.video_dims()
        cols, rows = grid_dims(vw, vh, s.num_tiles)
        focus = subject_centroid(subject_map(main, s.detect_faces))
        main = crop_to_ratio(main, cols / rows, focus)
    else:
        cols, rows = grid_dims(w, h, s.num_tiles)
        main = crop_to_ratio(main, cols / rows)
    ana = cv2.resize(main, (cols * ANALYSIS_PX, rows * ANALYSIS_PX), interpolation=cv2.INTER_AREA)
    ana_lab = _lab(ana)

    subject = None
    if s.subject_weight > 0:
        subject = cv2.resize(subject_map(main, s.detect_faces), (ana.shape[1], ana.shape[0]),
                             interpolation=cv2.INTER_LINEAR)

    cells = build_cells(cols, rows, ana_lab, s, rng, subject)
    if subject is not None:
        for c in cells:
            c.w = region_mean(subject, c.x, c.y, c.size)
    target = np.stack([_patch(ana_lab, c.x, c.y, c.size).ravel() for c in cells]).astype(np.float32)
    feats = tile_features(tiles)
    stats = assign(cells, target, feats, s, rng)

    # tint: Lab shift moving each tile's mean toward its cell's mean (stronger on the subject)
    tile_mean = feats.reshape(len(tiles), 2, PATCH * PATCH, 3).mean(axis=2)[:, 0]
    for c, tgt in zip(cells, target):
        tm = tgt.reshape(PATCH * PATCH, 3).mean(axis=0)
        t_eff = s.tint + (1 - s.tint) * 0.6 * s.subject_weight * c.w
        c.shift = tuple(float(v) for v in (tm - tile_mean[c.tile]) * t_eff)
    stats.update(cols=cols, rows=rows, cells=len(cells), tiles=len(tiles))
    return Mosaic(cols, rows, cells, [t.path for t in tiles], main, stats, subject, str(main_path))


# ----------------------------------------------------------------- render
def tinted_tile(img: np.ndarray, shift) -> np.ndarray:
    lab = _lab(img) + np.array(shift, np.float32)
    lab[..., 0] = np.clip(lab[..., 0], 0, 100)
    rgb = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)


def render_still(m: Mosaic, tiles: list[Tile], s: Settings) -> np.ndarray:
    P = s.cell_px
    W, H = m.cols * P, m.rows * P
    canvas = np.empty((H, W, 3), np.uint8)
    canvas[:] = np.array(s.gap_color, np.uint8)
    for c in m.cells:
        x0, y0 = int(round(c.x * P)), int(round(c.y * P))
        x1, y1 = int(round((c.x + c.size) * P)), int(round((c.y + c.size) * P))
        g = s.gap_px if c.size >= 1 else s.gap_px // 2
        x0 += g; y0 += g; x1 -= g; y1 -= g
        if x1 <= x0 or y1 <= y0:
            continue
        img = tiles[c.tile].image
        if c.flip:
            img = img[:, ::-1]
        img = cv2.resize(np.ascontiguousarray(img), (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        canvas[y0:y1, x0:x1] = tinted_tile(img, c.shift) if s.tint > 0 else img
    if s.main_blend > 0:
        main = cv2.resize(m.main, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
        alpha = blend_alpha(m, s, W, H)
        canvas = (canvas.astype(np.float32) * (1 - alpha) + main * alpha + 0.5).astype(np.uint8)
    return canvas


def blend_alpha(m: Mosaic, s: Settings, W: int, H: int) -> np.ndarray:
    """(H, W, 1) float alpha of the main-image overlay (stronger on the subject)."""
    alpha = np.full((H, W, 1), s.main_blend, np.float32)
    if m.subject is not None and s.subject_weight > 0:
        sm = cv2.resize(m.subject, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
        alpha = np.clip(s.main_blend * (1 + 1.5 * s.subject_weight * sm), 0, 1)
    return alpha


def save_scene(m: Mosaic, s: Settings, path: str | Path) -> None:
    from dataclasses import asdict
    from PIL import Image
    Image.fromarray(m.main).save(Path(path).parent / "main_crop.jpg", quality=95)   # exact crop used
    data = {
        "settings": asdict(s), "cols": m.cols, "rows": m.rows, "stats": m.stats,
        "main": str(Path(m.main_path).resolve()) if m.main_path else "",
        "main_crop": "main_crop.jpg",
        "tiles": m.tile_paths,
        "cells": [[c.x, c.y, c.size, c.tile, int(c.flip), list(c.shift), round(c.w, 3)] for c in m.cells],
    }
    Path(path).write_text(json.dumps(data), encoding="utf-8")


def load_scene(path: str | Path, cache_dir: str | Path | None = None):
    """Rebuild (Mosaic, tiles, Settings) from scene.json (tiles come from the cache)."""
    from .preprocess import load_tiles
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    s = Settings.from_json_dict(data["settings"])
    tiles = load_tiles(data["tiles"], s, cache_dir or Path(path).parent / "cache")
    cells = [Cell(c[0], c[1], c[2], c[3], bool(c[4]), tuple(c[5]), c[6]) for c in data["cells"]]
    crop = Path(path).parent / data.get("main_crop", "main_crop.jpg")
    if crop.exists():
        main = load_rgb(crop, max_side=None)
    else:
        main = crop_to_ratio(load_rgb(data["main"], max_side=3000), data["cols"] / data["rows"])
    subject = None
    if s.subject_weight > 0:
        subject = cv2.resize(subject_map(main, s.detect_faces),
                             (data["cols"] * ANALYSIS_PX, data["rows"] * ANALYSIS_PX))
    return Mosaic(data["cols"], data["rows"], cells, data["tiles"], main, data["stats"], subject,
                  data["main"]), tiles, s
