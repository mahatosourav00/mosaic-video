"""Animation planning: per-tile flight parameters + camera path. Pure numpy, no GL.

An animation *style* is a function (Mosaic, tiles, Settings) -> Plan. The renderer
only needs the Plan, so new styles never touch the GPU code.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np
from scipy.interpolate import PchipInterpolator

FOV_DEG = 35.0
TAN = math.tan(math.radians(FOV_DEG) / 2)


@dataclass
class Plan:
    inst: np.ndarray                 # (N, 21) float32, see below
    camera: Callable[[float], tuple]  # t -> (eye, target, roll)
    d_full: float                    # camera distance that frames the whole mosaic
    ramp: tuple                      # main-image blend ramp (t0, t1) seconds
    shine: tuple                     # light-sweep (t0, t1) seconds


# columns of Plan.inst:
#  0-3   end x, y, size, tile layer
#  4-7   start x, y, z, spin (rad)
#  8-11  t0, duration, flip, tilt (rad)
#  12-14 rgb offset (tint approximation)
#  15-17 start-scale multiplier, shrink start (0..1 of flight), ease mix (0 cubic-out, 1 smoothstep)
#  18-20 bezier control point
N_COLS = 21


def full_distance(cols: int, rows: int, aspect: float, margin: float = 1.04) -> float:
    return max(rows * margin / (2 * TAN), cols * margin / (aspect * 2 * TAN))


def _rgb_offsets(mosaic, tiles) -> np.ndarray:
    """Approximate each cell's Lab tint shift as an additive RGB offset."""
    lab = np.stack([cv2.cvtColor(cv2.resize(t.image, (1, 1), interpolation=cv2.INTER_AREA)
                                 .astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)[0, 0] for t in tiles])
    tl = np.array([c.tile for c in mosaic.cells])
    sh = np.array([c.shift for c in mosaic.cells], np.float32)
    base = lab[tl]
    after = base + sh
    after[:, 0] = np.clip(after[:, 0], 0, 100)
    a = cv2.cvtColor(base[None].astype(np.float32), cv2.COLOR_LAB2RGB)[0]
    b = cv2.cvtColor(after[None].astype(np.float32), cv2.COLOR_LAB2RGB)[0]
    return (np.clip(b, 0, 1) - np.clip(a, 0, 1)).astype(np.float32)


def _world(mosaic):
    """Cell centres in world units (1 unit = 1 base cell, mosaic centred, y up)."""
    x = np.array([c.cx for c in mosaic.cells]) - mosaic.cols / 2
    y = mosaic.rows / 2 - np.array([c.cy for c in mosaic.cells])
    size = np.array([c.size for c in mosaic.cells])
    return x, y, size


def _subject_centroid(mosaic, wx, wy) -> np.ndarray:
    w = np.array([c.w for c in mosaic.cells]) ** 2
    if w.sum() < 1e-6:
        return np.zeros(2)
    return np.array([(w * wx).sum() / w.sum(), (w * wy).sum() / w.sum()])


def _smooth(a, b, x):
    u = min(max((x - a) / (b - a), 0.0), 1.0)
    return u * u * (3 - 2 * u)


# ------------------------------------------------------------------ camera
def orbit_camera(mosaic, cen, d_full: float, D: float, seed: int):
    """Multi-phase move: tight orbit on the subject -> crane/sweep across the picture ->
    spiral pull-back -> settle on the full frame with a gentle push. Returns (camera, state)."""
    rng = np.random.default_rng(seed + 101)
    cols, rows = mosaic.cols, mosaic.rows
    cx, cy = cen
    lim_x, lim_y = cols * 0.42, rows * 0.42
    clip = lambda x, y: (float(np.clip(x, -lim_x, lim_x)), float(np.clip(y, -lim_y, lim_y)))
    pts = [
        clip(cx, cy),                                  # 0.00 on the face
        clip(cx + .05 * cols, cy - .03 * rows),
        clip(cx + .16 * cols, cy - .22 * rows),        # 0.25 swoops down to the shoulder
        clip(cx - .16 * cols, cy + .18 * rows),        # 0.40 up to the hair, other side
        clip(cx * .5 + .06 * cols, cy * .5),           # 0.55 drifting back
        clip(cx * .2, cy * .2),
        (0.0, 0.0),
        (0.0, 0.0),
    ]
    kt = np.array([0.0, .12, .25, .40, .55, .70, .84, .93]) * D   # camera is fully still after .93 D
    rows_k = [
        [p[0] for p in pts],
        [p[1] for p in pts],
        np.array([.32, .36, .42, .50, .62, .82, 1.0, .985]) * d_full,  # dolly (very slow float-in at the end)
        [.55, .30, -.10, -.48, -.26, .14, 0, .012],                    # yaw (orbit, tiny drift at end)
        [-.18, -.05, .12, .24, .10, -.05, 0, -.005],                   # pitch (crane)
        [-.10, .05, .08, -.07, -.03, .02, 0, 0],                       # roll
    ]
    spl = [PchipInterpolator(kt, np.array(r, float)) for r in rows_k]
    ph = rng.uniform(0, 6.28, 6)

    def state(t: float):
        tt = min(max(t, 0.0), D)
        tx, ty, dist, yaw, pitch, roll = (float(f(min(tt, kt[-1]))) for f in spl)   # still after the last key
        k = 1.0 - _smooth(0.66 * D, 0.86 * D, tt)       # hand-held drift fades to nothing before the finale
        tx += k * (.30 * math.sin(2 * math.pi * tt / 7.3 + ph[0]) + .15 * math.sin(2 * math.pi * tt / 3.1 + ph[1]))
        ty += k * (.30 * math.sin(2 * math.pi * tt / 6.1 + ph[2]) + .15 * math.sin(2 * math.pi * tt / 2.7 + ph[3]))
        roll += k * .006 * math.sin(2 * math.pi * tt / 5.3 + ph[4])
        yaw += k * .015 * math.sin(2 * math.pi * tt / 8.9 + ph[5])
        return tx, ty, dist, yaw, pitch, roll

    def camera(t: float):
        tx, ty, dist, yaw, pitch, roll = state(t)
        target = np.array([tx, ty, 0.0])
        eye = target + dist * np.array([math.sin(yaw) * math.cos(pitch), math.sin(pitch),
                                        math.cos(yaw) * math.cos(pitch)])
        return eye, target, roll

    return camera, state


def _basis(eye, target, roll):
    f = target - eye; f /= np.linalg.norm(f)
    up = np.array([math.sin(roll), math.cos(roll), 0.0])
    r = np.cross(f, up); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return f, r, u


# ------------------------------------------------------------------ styles
def swarm(mosaic, tiles, s) -> Plan:
    """Tiles fly in on curved arcs while the camera orbits; showcase photos sweep past big."""
    rng = np.random.default_rng(s.anim_seed)
    D = s.duration
    W, H = s.video_dims()
    aspect = W / H
    d_full = full_distance(mosaic.cols, mosaic.rows, aspect, 1.0 / max(s.frame_margin, 0.3))

    wx, wy, size = _world(mosaic)
    N = len(wx)
    cen = _subject_centroid(mosaic, wx, wy)
    camera, state = orbit_camera(mosaic, cen, d_full, D, s.anim_seed)

    # --- tiles land where the camera is looking at that moment
    t_a, t_b = 0.03 * D, 0.60 * D
    ts = np.linspace(t_a, t_b, 80)
    st = np.array([state(t) for t in ts])                         # (80, 6)
    vis_h = 2 * st[:, 2] * TAN
    d = np.hypot(wx[:, None] - st[None, :, 0], wy[:, None] - st[None, :, 1]) / vis_h[None, :]
    pref = ts[d.argmin(axis=1)]
    key = pref + rng.normal(0, 0.06 * D, N) + (size < 1) * 0.04 * D
    rank = np.argsort(np.argsort(key)) / max(N - 1, 1)
    flight = 0.17 * D
    # arrival density pulses: bursts of landing with calmer beats in between
    tt = np.linspace(t_a, t_b, 2000)
    rho = np.clip(1 + s.pulse_depth * np.sin(2 * math.pi * s.pulses * (tt - t_a) / (t_b - t_a) - math.pi / 2),
                  0.12, None) if s.pulses > 0 else np.ones_like(tt)
    cdf = np.cumsum(rho); cdf = (cdf - cdf[0]) / (cdf[-1] - cdf[0])
    t0 = np.interp(rank, cdf, tt)
    dur = flight * rng.uniform(0.85, 1.15, N)

    # --- ordinary tiles: arcs from random directions, bigger while flying
    dirs = rng.normal(size=(N, 3))
    dirs[:, 2] = np.abs(dirs[:, 2]) * 0.8 + 0.15
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    R = d_full * rng.uniform(0.30, 0.9, N)
    E = np.stack([wx, wy, np.zeros(N)], 1)
    S = E + dirs * R[:, None]
    off = rng.normal(size=(N, 3))
    off /= np.linalg.norm(off, axis=1, keepdims=True)
    C = 0.5 * (S + E) + 2 * off * (np.linalg.norm(S - E, axis=1) * rng.uniform(0.08, 0.30, N))[:, None]
    spin = rng.uniform(1.5, 5.0, N) * rng.choice([-1, 1], N)
    tilt = rng.uniform(0.8, 2.2, N) * rng.choice([-1, 1], N)
    kmul = s.flight_scale * rng.uniform(0.75, 1.35, N)
    shrink = np.full(N, 0.30)
    ease = np.zeros(N)

    # --- showcase tiles: distinct photos, large, sweeping through the foreground
    cell_tile = np.array([c.tile for c in mosaic.cells])
    order = np.argsort(t0)
    used_tiles: set[int] = set()
    n_h = min(s.hero_tiles, len(tiles))
    n_sel = 0
    for q in np.linspace(0.03, 0.88, max(n_h, 1)) if n_h > 0 else []:
        i0 = int(q * (N - 1))
        for j in range(i0, min(i0 + 400, N)):
            ci = int(order[j])
            if size[ci] >= 1 and int(cell_tile[ci]) not in used_tiles and kmul[ci] > 0:
                used_tiles.add(int(cell_tile[ci]))
                break
        else:
            continue
        dur[ci] = flight * 1.65
        th = t0[ci] + 0.5 * dur[ci]
        eye, target, roll = camera(th)
        f, r, u = _basis(eye, target, roll)
        dist = float(np.linalg.norm(target - eye))
        dh = 0.48 * dist
        visw, vish = 2 * dh * TAN * aspect, 2 * dh * TAN
        Hp = eye + f * dh + r * rng.uniform(-.18, .18) * visw + u * rng.uniform(-.2, .2) * vish
        side = rng.choice([-1, 1])
        S[ci] = Hp + r * side * visw * 1.1 + u * rng.uniform(-.6, .6) * vish - f * dh * 0.25
        C[ci] = 2 * Hp - 0.5 * (S[ci] + E[ci])
        kmul[ci] = s.hero_size * visw / size[ci]
        shrink[ci] = 0.66
        ease[ci] = 1.0 + n_sel          # >=1 marks a showcase tile; value-1 = its hi-res texture layer
        n_sel += 1
        spin[ci] = rng.uniform(0.2, 0.7) * rng.choice([-1, 1])
        tilt[ci] = rng.uniform(0.2, 0.6) * rng.choice([-1, 1])

    inst = np.zeros((N, N_COLS), np.float32)
    inst[:, 0], inst[:, 1], inst[:, 2] = wx, wy, size
    inst[:, 3] = cell_tile
    inst[:, 4:7] = S
    inst[:, 7] = spin
    inst[:, 8], inst[:, 9] = t0, dur
    inst[:, 10] = [1.0 if c.flip else 0.0 for c in mosaic.cells]
    inst[:, 11] = tilt
    inst[:, 12:15] = _rgb_offsets(mosaic, tiles) if s.tint > 0 else 0.0
    inst[:, 15], inst[:, 16], inst[:, 17] = kmul, shrink, ease
    inst[:, 18:21] = C

    return Plan(inst, camera, d_full, (0.78 * D, 0.92 * D), (0.84 * D, 0.97 * D))


STYLES = {"swarm": swarm}


def make_plan(mosaic, tiles, s) -> Plan:
    if s.style not in STYLES:
        raise ValueError(f"Unknown style '{s.style}'. Available: {', '.join(STYLES)}")
    return STYLES[s.style](mosaic, tiles, s)
