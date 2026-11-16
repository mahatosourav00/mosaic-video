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
    fov: Callable[[float], float] | None = None   # t -> vertical FOV in degrees (None = constant FOV_DEG)


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
def _place_heroes(s, rng, camera, aspect, n_tiles, flight, size, cell_tile, t0, dur, S, C, E, kmul, shrink,
                  ease, spin, tilt, tan_fn=None, edge_bias=False, size_scale=1.0, min_gap=0.0, q_hi=0.88) -> None:
    """Showcase tiles: distinct photos, large, sweeping through the foreground in front of the camera.
    Mutates the per-tile arrays in place (shared by every style).
    edge_bias: pass near the frame edges (keeps the subject's face visible); size_scale: shrink them;
    min_gap: minimum seconds between two showcase tiles' arrival (never a pile-up)."""
    N = len(t0)
    order = np.argsort(t0)
    used_tiles: set[int] = set()
    chosen_t: list[float] = []
    n_h = min(s.hero_tiles, n_tiles)
    n_sel = 0
    for q in np.linspace(0.03, q_hi, max(n_h, 1)) if n_h > 0 else []:
        i0 = int(q * (N - 1))
        for j in range(i0, min(i0 + 400, N)):
            ci = int(order[j])
            if (size[ci] >= 1 and int(cell_tile[ci]) not in used_tiles and kmul[ci] > 0
                    and all(abs(t0[ci] - tc) >= min_gap for tc in chosen_t)):
                used_tiles.add(int(cell_tile[ci]))
                chosen_t.append(float(t0[ci]))
                break
        else:
            continue
        dur[ci] = flight * 1.65
        th = t0[ci] + 0.5 * dur[ci]
        eye, target, roll = camera(th)
        f, r, u = _basis(eye, target, roll)
        dist = float(np.linalg.norm(target - eye))
        dh = 0.48 * dist
        tn = tan_fn(th) if tan_fn else TAN
        visw, vish = 2 * dh * tn * aspect, 2 * dh * tn
        if edge_bias:   # glide past the side of the frame, not across the face
            lat = rng.uniform(.26, .38) * (1 if n_sel % 2 == 0 else -1)
            Hp = eye + f * dh + r * lat * visw + u * rng.uniform(-.30, .30) * vish
        else:
            Hp = eye + f * dh + r * rng.uniform(-.18, .18) * visw + u * rng.uniform(-.2, .2) * vish
        side = rng.choice([-1, 1])
        S[ci] = Hp + r * side * visw * 1.1 + u * rng.uniform(-.6, .6) * vish - f * dh * 0.25
        C[ci] = 2 * Hp - 0.5 * (S[ci] + E[ci])
        kmul[ci] = s.hero_size * size_scale * visw / size[ci]
        shrink[ci] = 0.66
        ease[ci] = 1.0 + n_sel          # >=1 marks a showcase tile; value-1 = its hi-res texture layer
        n_sel += 1
        spin[ci] = rng.uniform(0.2, 0.7) * rng.choice([-1, 1])
        tilt[ci] = rng.uniform(0.2, 0.6) * rng.choice([-1, 1])


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
    _place_heroes(s, rng, camera, aspect, len(tiles), flight, size, cell_tile, t0, dur, S, C, E, kmul, shrink,
                  ease, spin, tilt)

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


# --------------------------------------------------- simple styles (vortex / wave / zoom)
def _simple_plan(mosaic, tiles, s, S, C, key, camera, d_full, *, spin_amp, tilt_amp, kmul_rng, flight_frac,
                 window=(0.04, 0.60), heroes=False, fov=None, pulse_phase=-math.pi / 2,
                 opening=None, hero_kw=None) -> Plan:
    """Shared tail of the simple styles: arrival order from `key`, pulses, instance rows.
    opening=(fraction, seconds): that fraction of the earliest tiles lands within the first `seconds`, from
    nearby, so the opening close-up is never empty. hero_kw: extra options for _place_heroes."""
    rng = np.random.default_rng(s.anim_seed + 7)
    D = s.duration
    wx, wy, size = _world(mosaic)
    N = len(wx)
    W, H = s.video_dims()
    t_a, t_b = window[0] * D, window[1] * D
    rank = np.argsort(np.argsort(key)) / max(N - 1, 1)
    tt = np.linspace(t_a, t_b, 2000)
    rho = np.clip(1 + s.pulse_depth * np.sin(2 * math.pi * s.pulses * (tt - t_a) / (t_b - t_a) + pulse_phase),
                  0.12, None) if s.pulses > 0 else np.ones_like(tt)
    cdf = np.cumsum(rho); cdf = (cdf - cdf[0]) / (cdf[-1] - cdf[0])
    t0 = np.interp(rank, cdf, tt)
    dur = flight_frac * D * rng.uniform(0.85, 1.15, N)
    if opening:
        n_o = int(opening[0] * N)
        early = np.argsort(key)[:n_o]
        t0[early] = np.sort(rng.uniform(-0.7, opening[1], n_o))   # some already mid-flight at frame 0
        dur[early] *= 0.7
        old_mid = 0.5 * (S[early] + np.stack([wx[early], wy[early], np.zeros(n_o)], 1))
        E_e = np.stack([wx[early], wy[early], np.zeros(n_o)], 1)
        S[early] = E_e + (S[early] - E_e) * (opening[2] if len(opening) > 2 else 0.35)   # start close by: in the tight first shot
        C[early] += 0.5 * (S[early] + E_e) - old_mid       # keep each arc's bend relative to its new midpoint
    cell_tile = np.array([c.tile for c in mosaic.cells])
    spin = rng.uniform(0.3, 1.0, N) * spin_amp * rng.choice([-1, 1], N)
    tilt = rng.uniform(0.3, 1.0, N) * tilt_amp * rng.choice([-1, 1], N)
    kmul = s.flight_scale * rng.uniform(*kmul_rng, N)
    shrink = np.full(N, 0.30)
    ease = np.zeros(N)
    if heroes:
        E = np.stack([wx, wy, np.zeros(N)], 1)
        _place_heroes(s, rng, camera, W / H, len(tiles), flight_frac * D, size, cell_tile, t0, dur, S, C, E,
                      kmul, shrink, ease, spin, tilt,
                      tan_fn=(lambda t: math.tan(math.radians(fov(t)) / 2)) if fov else None, **(hero_kw or {}))
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
    return Plan(inst, camera, d_full, (0.78 * D, 0.92 * D), (0.84 * D, 0.97 * D), fov)


def _path_camera(mosaic, D: float, seed: int, kt, tx, ty, dist, yaw, pitch, roll, fov_boost: float = 9.0,
                 drift: float = 1.0, arc: float = 1.0):
    """Keyframed travelling camera shared by the styles. All arrays share the key times `kt` (fractions of D):
    tx/ty target (world units), dist (world units), yaw/pitch/roll (rad; roll is banking only).
    Adds hand-held drift that fades before the finale, a wide-to-normal lens, and a living finale: one very
    slow ~5% push-in with a small sideways arc that returns to dead straight (eased, zero speed at both ends).
    Pacing comes from the key spacing: linger -> fast sweeps -> quick pull-back reveal -> slow calm hold."""
    rng = np.random.default_rng(seed + 202)
    ph = rng.uniform(0, 6.28, 6)
    lim_x, lim_y = mosaic.cols * 0.44, mosaic.rows * 0.44
    kt = np.asarray(kt, float) * D
    rows_k = [np.clip(tx, -lim_x, lim_x), np.clip(ty, -lim_y, lim_y), dist, yaw, pitch, roll]
    spl = [PchipInterpolator(kt, np.array(r, float)) for r in rows_k]

    def state(t: float):
        tt = min(max(t, 0.0), D)
        x, y, dd, ya, pi_, ro = (float(f(min(tt, kt[-1]))) for f in spl)
        k = drift * (1.0 - _smooth(0.55 * D, 0.84 * D, tt))   # hand-held drift (0 = locked off) fades before the finale
        x += k * (.30 * math.sin(2 * math.pi * tt / 6.3 + ph[0]) + .15 * math.sin(2 * math.pi * tt / 2.9 + ph[1]))
        y += k * (.30 * math.sin(2 * math.pi * tt / 5.7 + ph[2]) + .15 * math.sin(2 * math.pi * tt / 2.5 + ph[3]))
        ro += k * .006 * math.sin(2 * math.pi * tt / 5.3 + ph[4])
        ya += k * .02 * math.sin(2 * math.pi * tt / 8.9 + ph[5])
        u = _smooth(0.66 * D, D, tt)                     # living finale
        dd *= 1.0 - 0.05 * u
        ya += arc * 0.05 * math.sin(math.pi * u)
        x += arc * 0.012 * mosaic.cols * math.sin(math.pi * u)
        return x, y, dd, ya, pi_, ro

    def fov(t: float) -> float:
        return FOV_DEG + fov_boost * (1.0 - _smooth(0.0, 0.45 * D, min(max(t, 0.0), D)))

    def camera(t: float):
        x, y, dd, ya, pi_, ro = state(t)
        target = np.array([x, y, 0.0])
        eye = target + dd * np.array([math.sin(ya) * math.cos(pi_), math.sin(pi_), math.cos(ya) * math.cos(pi_)])
        return eye, target, ro

    return camera, state, fov


def _vortex_camera(mosaic, cen, d_full: float, D: float, seed: int):
    """Helix around the subject: big yaw swings, crane, dolly surges, then a quick pull-back as the face resolves."""
    th0 = np.random.default_rng(seed + 202).uniform(0, 6.28)
    m = min(mosaic.cols, mosaic.rows)
    kt = [0.0, .08, .20, .30, .38, .48, .60, .72, .90]
    # ONE continuous circling move, in the same sense the tiles swirl (clockwise): ~2 full laps of the subject.
    ang = th0 - 2 * math.pi * np.array([0.0, .20, .60, 1.00, 1.40, 1.70, 1.90, 2.0, 2.0])
    rad = np.array([.02, .10, .24, .26, .22, .14, .06, 0.0, 0.0]) * m              # orbit radius around subject
    w = np.array([0.0, 0.0, 0.0, .05, .20, .55, .90, 1.0, 1.0])                    # blend subject -> frame centre
    tx = (1 - w) * (cen[0] + rad * np.cos(ang))
    ty = (1 - w) * (cen[1] + rad * np.sin(ang))
    return _path_camera(mosaic, D, seed, kt, tx, ty,
                        np.array([.26, .30, .32, .34, .36, .50, .88, 1.0, .985]) * d_full,   # stays tight: circling
                        [1.00, .75, .40, .0, -.40, -.50, -.15, -.02, 0],        # yaw sweeps steadily one way: orbiting
                        [-.22, -.05, .20, .12, -.12, -.05, .04, 0, 0],          # gentle rise and fall: a helix
                        [.20, .16, .12, .06, 0, -.04, .02, 0, 0])               # banks into the turn


def _basics(mosaic, s):
    rng = np.random.default_rng(s.anim_seed)
    W, H = s.video_dims()
    d_full = full_distance(mosaic.cols, mosaic.rows, W / H, 1.0 / max(s.frame_margin, 0.3))
    wx, wy, _ = _world(mosaic)
    E = np.stack([wx, wy, np.zeros(len(wx))], 1)
    return rng, d_full, wx, wy, E, _subject_centroid(mosaic, wx, wy)


def vortex(mosaic, tiles, s) -> Plan:
    """Tiles spiral in from a wide swirl, centre first, while the camera unwinds into the full frame."""
    rng, d_full, wx, wy, E, cen = _basics(mosaic, s)
    N = len(wx)
    r = np.hypot(wx - cen[0], wy - cen[1])
    rn = r / max(r.max(), 1e-6)
    phi = 2.6 + 1.6 * rn                                   # swirl angle: outer tiles wind further
    c, sn = np.cos(phi), np.sin(phi)
    rel = E[:, :2] - cen
    scale = 1.8 + 1.5 * rn
    S = np.zeros((N, 3))
    S[:, 0] = cen[0] + (c * rel[:, 0] - sn * rel[:, 1]) * scale
    S[:, 1] = cen[1] + (sn * rel[:, 0] + c * rel[:, 1]) * scale
    S[:, 2] = d_full * rng.uniform(0.05, 0.45, N)
    ph2 = phi * 0.5
    c2, s2 = np.cos(ph2), np.sin(ph2)
    C = np.zeros((N, 3))
    C[:, 0] = cen[0] + (c2 * rel[:, 0] - s2 * rel[:, 1]) * (1.0 + scale) * 0.7
    C[:, 1] = cen[1] + (s2 * rel[:, 0] + c2 * rel[:, 1]) * (1.0 + scale) * 0.7
    C[:, 2] = d_full * rng.uniform(0.2, 0.5, N)
    D = s.duration
    camera, state, fov = _vortex_camera(mosaic, cen, d_full, D, s.anim_seed)
    # tiles land where the camera is looking at that moment (keeps the visible sky from being crowded)
    t_a, t_b = 0.0, 0.62 * D
    ts = np.linspace(t_a, t_b, 80)
    st = np.array([state(t) for t in ts])
    vis_h = 2 * st[:, 2] * np.array([math.tan(math.radians(fov(t)) / 2) for t in ts])
    dd = np.hypot(wx[:, None] - st[None, :, 0], wy[:, None] - st[None, :, 1]) / vis_h[None, :]
    key = ts[dd.argmin(axis=1)] + rng.normal(0, 0.07 * D, N) + 0.05 * D * rn
    return _simple_plan(mosaic, tiles, s, S, C, key, camera, d_full, spin_amp=4.0, tilt_amp=1.4,
                        kmul_rng=(0.55, 0.95), flight_frac=0.14, window=(0.0, 0.62), heroes=True, fov=fov,
                        pulse_phase=0.4,       # open on an arrival burst, not on the quietest beat
                        opening=(0.08, 1.2),   # 8% of tiles land in the first 1.2 s: the opening shot is never empty
                        hero_kw=dict(edge_bias=True, size_scale=0.85, min_gap=0.04 * D, q_hi=0.62))   # showcase tiles stay off the face


def wave(mosaic, tiles, s) -> Plan:
    """A reveal wave: tiles rise from below and sweep across the picture left to right while the camera
    travels along the wave front (tracking shot), looks back across it, then pulls back to the full frame."""
    rng, d_full, wx, wy, E, cen = _basics(mosaic, s)
    N = len(wx)
    D = s.duration
    cols, rows = mosaic.cols, mosaic.rows
    xn = (wx - wx.min()) / max(np.ptp(wx), 1e-6)
    yn = (wy - wy.min()) / max(np.ptp(wy), 1e-6)
    key = xn + 0.18 * np.sin(2.4 * math.pi * yn) + rng.normal(0, 0.03, N)
    S = E + np.stack([rng.normal(-0.25, 0.1, N) * cols, -rng.uniform(0.55, 0.9, N) * rows,
                      d_full * rng.uniform(0.15, 0.55, N)], 1)
    C = 0.5 * (S + E)
    C[:, 2] += d_full * rng.uniform(0.2, 0.5, N)
    C[:, 0] += rng.normal(0, 0.05, N) * cols
    # A level TRACKING SHOT: the camera slides sideways at the speed of the wave front, at a constant distance
    # and constant angle (no orbiting, no dolly, no roll), so you watch the wave travel. Then it pulls back.
    kt = [0.0, .12, .24, .36, .48, .58, .70, .82, .90]
    f = np.clip((np.array(kt) - 0.02) / 0.58, 0, 1)                                   # wave-front progress
    track = (-0.5 + f) * cols * 0.9
    w = np.array([0, 0, 0, 0, 0, .25, .70, 1.0, 1.0])                                 # then glide to the frame centre
    camera, state, fov = _path_camera(
        mosaic, D, s.anim_seed, kt, track * (1 - w), np.array([-.04, -.04, -.03, -.02, -.01, 0, 0, 0, 0]) * rows,
        np.array([.42, .42, .42, .42, .44, .62, .92, 1.0, .985]) * d_full,            # constant distance while tracking
        [.30, .30, .30, .30, .26, .12, .03, 0, 0],                                    # fixed side angle: parallax depth
        [-.12, -.12, -.12, -.10, -.08, -.03, 0, 0, 0],                                # low angle, looking up at the rise
        [0, 0, 0, 0, 0, 0, 0, 0, 0], fov_boost=3.0, drift=0.25, arc=0.4)
    return _simple_plan(mosaic, tiles, s, S, C, key, camera, d_full, spin_amp=2.2, tilt_amp=1.6,
                        kmul_rng=(0.55, 0.95), flight_frac=0.16, window=(0.02, 0.60), heroes=True, fov=fov,
                        opening=(0.12, 1.2, 0.12), hero_kw=dict(edge_bias=True, size_scale=0.85, min_gap=0.04 * D, q_hi=0.62))


def zoom(mosaic, tiles, s) -> Plan:
    """Tiles drop out of the lens toward their cells, centre first. The camera starts macro-close on the face,
    drifts and swings, then pulls straight back to reveal the whole portrait."""
    rng, d_full, wx, wy, E, cen = _basics(mosaic, s)
    N = len(wx)
    D = s.duration
    m = min(mosaic.cols, mosaic.rows)
    r = np.hypot(wx - cen[0], wy - cen[1])
    key = r / max(r.max(), 1e-6) + rng.normal(0, 0.06, N)
    S = E + np.stack([rng.normal(0, 0.05, N) * mosaic.cols, rng.normal(0, 0.05, N) * mosaic.rows,
                      d_full * rng.uniform(0.08, 0.24, N)], 1)                    # start just in front of the lens
    C = 0.5 * (S + E) + np.stack([rng.normal(0, 0.06, N) * mosaic.cols, rng.normal(0, 0.06, N) * mosaic.rows,
                                  d_full * rng.uniform(0.0, 0.15, N)], 1)
    # A pure LENS-AXIS move: dead centred, no yaw / pitch / roll, no drift. It starts macro-close with a long
    # telephoto lens and accelerates straight back while the lens widens, so it reads as one big zoom.
    w = np.array([0.0, 0.0, 0.0, .10, .30, .60, .90, 1.0, 1.0])                       # glide from face to frame centre
    z = np.zeros(9)
    camera, state, fov = _path_camera(
        mosaic, D, s.anim_seed, [0.0, .10, .22, .34, .44, .54, .64, .76, .90],
        (1 - w) * cen[0], (1 - w) * cen[1],
        np.array([.17, .19, .23, .30, .46, .72, .94, 1.0, .985]) * d_full,            # macro -> accelerating pull-back
        z, z, z, fov_boost=-9.0, drift=0.0, arc=0.0)                                   # narrow lens at first, widening
    return _simple_plan(mosaic, tiles, s, S, C, key, camera, d_full, spin_amp=1.4, tilt_amp=1.0,
                        kmul_rng=(0.6, 1.0), flight_frac=0.14, window=(0.0, 0.62), heroes=True, fov=fov,
                        pulse_phase=0.4, opening=(0.10, 1.2),
                        hero_kw=dict(edge_bias=True, size_scale=0.85, min_gap=0.04 * D, q_hi=0.62))


STYLES = {"swarm": swarm, "vortex": vortex, "wave": wave, "zoom": zoom}


def make_plan(mosaic, tiles, s) -> Plan:
    if s.style not in STYLES:
        raise ValueError(f"Unknown style '{s.style}'. Available: {', '.join(STYLES)}")
    return STYLES[s.style](mosaic, tiles, s)
