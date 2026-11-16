"""Headless ModernGL renderer: Plan + Mosaic -> frames -> FFmpeg.

Passes per frame: backdrop -> shadow/glow -> tiles (defocus + fog) -> main-image overlay + light
sweep -> particles (additive).
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
import imageio_ffmpeg
import moderngl
import numpy as np

from .animation import FOV_DEG, Plan, make_plan
from .solver import Mosaic, blend_alpha
from .settings import Settings

TILE_VS = """
#version 330
in vec2 in_vert;
in vec4 i_end; in vec4 i_start; in vec4 i_time; in vec3 i_off; in vec3 i_ext; in vec3 i_mid;
uniform mat4 u_vp; uniform float u_time; uniform float u_gap;
uniform vec3 u_eye; uniform vec3 u_fwd; uniform float u_focus; uniform float u_dof;
out vec3 v_uv; out vec3 v_off; out float v_alpha; out float v_light; out float v_blur; out float v_fog;
flat out float v_hero;
void main() {
    if (u_time < i_time.x) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        v_uv = vec3(0.0); v_off = vec3(0.0); v_alpha = 0.0; v_light = 1.0; v_blur = 0.0; v_fog = 0.0;
        v_hero = -1.0;
        return;
    }
    bool hero = i_ext.z >= 0.5;                       // showcase tile (value - 1 = hi-res layer)
    v_hero = hero ? i_ext.z - 1.0 : -1.0;
    float p = clamp((u_time - i_time.x) / i_time.y, 0.0, 1.0);
    float pp = p + 0.8 * sin(6.2831853 * p) / 6.2831853;           // dwell in the middle (slow in front of the camera)
    float e = hero ? pp * pp * (3.0 - 2.0 * pp) : 1.0 - pow(1.0 - p, 3.0);
    vec3 E = vec3(i_end.xy, 0.0);
    vec3 pos = (1.0 - e) * (1.0 - e) * i_start.xyz + 2.0 * (1.0 - e) * e * i_mid + e * e * E;
    float ang = i_start.w * (1.0 - e);
    float tilt = i_time.w * (1.0 - e);
    float sc = mix(i_ext.x, 1.0, smoothstep(i_ext.y, 1.0, p));
    float side = max(i_end.z - u_gap * (i_end.z >= 0.99 ? 1.0 : 0.5), 0.02);
    vec3 l = vec3(in_vert * side * sc, 0.0);
    float ct = cos(tilt), st = sin(tilt);
    l = vec3(ct * l.x + st * l.z, l.y, -st * l.x + ct * l.z);
    float ca = cos(ang), sa = sin(ang);
    l = vec3(ca * l.x - sa * l.y, sa * l.x + ca * l.y, l.z);
    vec3 wp = pos + l;
    gl_Position = u_vp * vec4(wp, 1.0);
    float vx = in_vert.x + 0.5;
    if (i_time.z > 0.5) vx = 1.0 - vx;
    v_uv = vec3(vx, 0.5 - in_vert.y, i_end.w);
    v_off = i_off;
    v_alpha = smoothstep(0.0, 0.2, p);
    float ts = u_time - (i_time.x + i_time.y);
    v_light = 1.0 + (ts > 0.0 ? 0.35 * exp(-ts * 6.0) : 0.0);
    // depth of field + fog (showcase tiles stay sharp)
    float depth = dot(wp - u_eye, u_fwd);
    float off = abs(depth - u_focus) / u_focus;
    v_blur = hero ? 0.0 : clamp((off - 0.10) * 2.0, 0.0, 1.0) * 2.6 * u_dof;
    v_fog = hero ? 0.0 : clamp((depth - u_focus) / (u_focus * 0.9), 0.0, 1.0) * 0.55 * u_dof;
}
"""

TILE_FS = """
#version 330
in vec3 v_uv; in vec3 v_off; in float v_alpha; in float v_light; in float v_blur; in float v_fog;
flat in float v_hero;
uniform sampler2DArray u_tiles; uniform sampler2DArray u_hero; uniform vec3 u_bgc;
out vec4 f_color;
void main() {
    if (v_alpha < 0.02) discard;
    vec3 c;
    if (v_hero > -0.5) c = texture(u_hero, vec3(v_uv.xy, floor(v_hero + 0.5))).rgb;   // sharp hi-res showcase photo
    else c = textureLod(u_tiles, v_uv, v_blur + 0.5).rgb;                              // +0.5: settled tiles don't shimmer
    c = clamp((c + v_off) * v_light, 0.0, 1.0);
    f_color = vec4(mix(c, u_bgc, v_fog), v_alpha);
}
"""

OVER_VS = """
#version 330
in vec2 in_vert;
uniform mat4 u_vp; uniform vec2 u_size;
out vec2 v_uv;
void main() {
    gl_Position = u_vp * vec4(in_vert * u_size, 0.05, 1.0);
    v_uv = vec2(in_vert.x + 0.5, 0.5 - in_vert.y);
}
"""

OVER_FS = """
#version 330
in vec2 v_uv;
uniform sampler2D u_main; uniform float u_ramp; uniform float u_shine;
out vec4 f_color;
void main() {
    vec4 m = texture(u_main, v_uv);
    float a = m.a * u_ramp;
    float d = v_uv.x * 0.55 + v_uv.y * 0.45;
    float band = exp(-pow((d - u_shine) / 0.05, 2.0));
    vec3 rgb = mix(m.rgb, vec3(1.0), band * 0.7);
    f_color = vec4(rgb, max(a, band * 0.30));
}
"""

BACK_VS = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() { gl_Position = vec4(in_vert * 2.0, 0.999, 1.0); v_uv = in_vert + 0.5; }
"""

BACK_FS = """
#version 330
in vec2 v_uv;
uniform sampler2D u_blur; uniform vec3 u_bg; uniform vec3 u_accent; uniform vec3 u_accent2;
uniform float u_amt; uniform vec2 u_shift; uniform float u_time; uniform vec2 u_res;
out vec4 f_color;
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
    vec3 col = texture(u_blur, (v_uv - 0.5) / 1.3 + 0.5 + u_shift).rgb;
    vec2 q = (v_uv - 0.5) * vec2(1.0, 1.1);
    float r = length(q);
    float vig = mix(0.40, 1.0, smoothstep(0.9, 0.1, r));
    // slow drifting colour light (two soft blobs) + centre bloom
    vec2 c1 = vec2(0.28 + 0.10 * sin(u_time * 0.31), 0.22 + 0.08 * cos(u_time * 0.23));
    vec2 c2 = vec2(0.74 + 0.09 * cos(u_time * 0.27), 0.80 + 0.07 * sin(u_time * 0.35));
    float b1 = exp(-dot(v_uv - c1, v_uv - c1) * 7.0);
    float b2 = exp(-dot(v_uv - c2, v_uv - c2) * 7.0);
    vec3 back = col * vig + u_accent * (0.22 * exp(-r * r * 4.0) + 0.20 * b1) + u_accent2 * 0.13 * b2;
    vec3 o = mix(u_bg, back, u_amt);
    o += (hash(v_uv * u_res + fract(u_time)) - 0.5) * (5.0 / 255.0);   // dither: no banding in gradients
    f_color = vec4(o, 1.0);
}
"""

GLOW_VS = """
#version 330
in vec2 in_vert;
uniform mat4 u_vp; uniform vec2 u_quad;
out vec2 v_p;
void main() {
    v_p = in_vert * u_quad;
    gl_Position = u_vp * vec4(v_p, -0.08, 1.0);
}
"""

GLOW_FS = """
#version 330
in vec2 v_p;
uniform vec2 u_half; uniform float u_scale; uniform float u_mode; uniform float u_fade;
uniform vec3 u_accent; uniform float u_glow;
out vec4 f_color;
float sdf(vec2 p) { vec2 q = abs(p) - u_half; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0); }
void main() {
    if (u_mode < 0.5) {            // soft drop shadow, offset down
        float d = sdf(v_p + vec2(0.0, 0.018 * u_scale));
        float a = 0.75 * exp(-max(d, 0.0) / (0.05 * u_scale));
        f_color = vec4(0.0, 0.0, 0.0, a * u_fade);
    } else {                       // accent glow + hairline rim (additive)
        float d = sdf(v_p);
        float g = exp(-max(d, 0.0) / (0.14 * u_scale)) * step(0.0, d);
        float rim = exp(-pow((d - 0.004 * u_scale) / (0.0035 * u_scale), 2.0));
        vec3 c = u_accent * 1.15 * g * u_glow + vec3(1.0, 0.95, 0.88) * rim * 0.60 * u_glow;
        f_color = vec4(c * u_fade, 1.0);
    }
}
"""

PART_VS = """
#version 330
in vec2 in_vert;
in vec4 p_a; in vec4 p_b;
uniform mat4 u_vp; uniform float u_time; uniform vec3 u_right; uniform vec3 u_up;
uniform vec2 u_box; uniform vec2 u_mos; uniform float u_shine; uniform float u_amt;
out vec2 v_q; out float v_a;
void main() {
    float y = mod(p_a.y + p_b.x * u_time + u_box.y, 2.0 * u_box.y) - u_box.y;
    float x = p_a.x + p_b.z * sin(u_time * 0.35 + p_b.y);
    vec3 c = vec3(x, y, p_a.z);
    vec3 w = c + (u_right * in_vert.x + u_up * in_vert.y) * p_a.w;
    gl_Position = u_vp * vec4(w, 1.0);
    v_q = in_vert * 2.0;
    float tw = 0.55 + 0.45 * sin(u_time * 1.3 + p_b.y * 5.0);
    vec2 uvm = vec2(x / u_mos.x + 0.5, 0.5 - y / u_mos.y);
    float band = exp(-pow((uvm.x * 0.55 + uvm.y * 0.45 - u_shine) / 0.08, 2.0));
    float edge = smoothstep(0.0, 0.1, (y + u_box.y) / (2.0 * u_box.y)) * smoothstep(1.0, 0.9, (y + u_box.y) / (2.0 * u_box.y));
    v_a = u_amt * tw * (0.75 + 2.5 * band) * p_b.w * edge;
}
"""

PART_FS = """
#version 330
in vec2 v_q; in float v_a;
uniform vec3 u_color;
out vec4 f_color;
void main() {
    float r = length(v_q);
    float disc = smoothstep(1.0, 0.92, r);                       // bokeh disc ...
    float rim = 0.55 + 0.9 * smoothstep(0.45, 0.95, r);          // ... brighter at the edge
    float core = pow(smoothstep(1.0, 0.0, r), 3.0);              // tiny sparkles stay soft
    float a = 0.5 * core + 0.5 * disc * rim * 0.55;
    f_color = vec4(u_color, a * v_a);
}
"""


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2)
    m = np.zeros((4, 4), np.float32)
    m[0, 0], m[1, 1] = f / aspect, f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2 * far * near / (near - far)
    m[3, 2] = -1
    return m


def look_at(eye, target, roll: float) -> np.ndarray:
    up = np.array([math.sin(roll), math.cos(roll), 0.0])
    f = target - eye; f /= np.linalg.norm(f)
    r = np.cross(f, up); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3], m[1, :3], m[2, :3] = r, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def _accent(main: np.ndarray) -> np.ndarray:
    """A pleasant accent colour taken from the main image (saturated, brightened). RGB 0..1."""
    small = cv2.resize(main, (64, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV).reshape(-1, 3).astype(np.float32)
    sel = hsv[(hsv[:, 1] > 70) & (hsv[:, 2] > 90)]
    h = sel.mean(axis=0) if len(sel) > 20 else hsv.mean(axis=0)
    h[1] = min(max(h[1], 90), 200); h[2] = max(h[2], 190)
    rgb = cv2.cvtColor(h.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_HSV2RGB)[0, 0] / 255.0
    return rgb.astype(np.float32)


def _accent2(accent: np.ndarray) -> np.ndarray:
    """Harmonious second light: the accent hue rotated ~150 degrees."""
    hsv = cv2.cvtColor((accent.reshape(1, 1, 3) * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)[0, 0].astype(np.float32)
    hsv[0] = (hsv[0] + 75) % 180
    return (cv2.cvtColor(hsv.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_HSV2RGB)[0, 0] / 255.0).astype(np.float32)


def _ffmpeg_cmd(s: Settings, W: int, H: int, fps: int, out: Path) -> list[str]:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    src = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    fmt = s.video_format
    if fmt == "mp4":
        return src + ["-vf", "vflip", "-c:v", "libx264", "-preset", "medium", "-crf", str(s.crf),
                      "-tune", "grain", "-x264-params", "aq-mode=3", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    if fmt == "mp4-h265":
        return src + ["-vf", "vflip", "-c:v", "libx265", "-preset", "medium", "-crf", str(s.crf + 4),
                      "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-movflags", "+faststart", str(out)]
    if fmt == "webm":
        return src + ["-vf", "vflip", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(s.crf + 12),
                      "-pix_fmt", "yuv420p", str(out)]
    if fmt == "gif":
        vf = "vflip,fps=15,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
        return src + ["-vf", vf, str(out)]
    raise ValueError(f"Unknown video_format '{fmt}'")


JITTER = [(-0.25, -0.30), (0.30, -0.20), (-0.35, 0.15), (0.20, 0.35), (0.0, 0.0), (0.40, 0.05)]


def smooth(a: float, b: float, x: float) -> float:
    u = min(max((x - a) / (b - a), 0.0), 1.0)
    return u * u * (3 - 2 * u)


def render_video(m: Mosaic, tiles, s: Settings, out_path: str | Path, preview: bool = False,
                 progress=None, max_seconds: float | None = None, cache_dir=None) -> Path:
    out_path = Path(out_path)
    plan: Plan = make_plan(m, tiles, s)
    D = s.duration
    W, H = s.video_dims()
    fps = s.fps
    if preview:
        sc = 360 / min(W, H)
        W, H = int(round(W * sc / 2) * 2), int(round(H * sc / 2) * 2)
        fps = min(fps, 15)

    ctx = moderngl.create_standalone_context()
    samples = 2 if preview else 4
    fbo_ms = ctx.framebuffer([ctx.renderbuffer((W, H), 4, samples=samples)],
                             ctx.depth_renderbuffer((W, H), samples=samples))
    fbo = ctx.framebuffer([ctx.renderbuffer((W, H), 4)])

    # tile texture array (mip-mapped; mips double as the defocus blur)
    tex_px = 64 if preview else min(256, s.cache_px)
    layers = np.stack([cv2.resize(t.image, (tex_px, tex_px), interpolation=cv2.INTER_AREA) for t in tiles])
    rgba = np.concatenate([layers, np.full((*layers.shape[:3], 1), 255, np.uint8)], axis=3)
    tex = ctx.texture_array((tex_px, tex_px, len(tiles)), 4, np.ascontiguousarray(rgba).tobytes())
    tex.build_mipmaps()
    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    tex.anisotropy = 8.0
    tex.repeat_x = tex.repeat_y = False

    # hi-res textures for the showcase tiles (reloaded from the original photos at 512 px)
    from .preprocess import load_tiles
    import copy
    hmask = plan.inst[:, 17] >= 1.0
    n_hero = int(hmask.sum())
    hero_px = 128 if preview else 512
    if n_hero:
        order_h = np.argsort(plan.inst[hmask, 17])
        hero_ids = plan.inst[hmask, 3][order_h].astype(int)
        s_hi = copy.copy(s); s_hi.cache_px = hero_px
        hi = load_tiles([m.tile_paths[i] for i in hero_ids], s_hi, cache_dir)
        hlayers = np.stack([cv2.resize(t.image, (hero_px, hero_px), interpolation=cv2.INTER_AREA) for t in hi])
    else:
        hlayers = np.zeros((1, hero_px, hero_px, 3), np.uint8)
    hrgba = np.concatenate([hlayers, np.full((*hlayers.shape[:3], 1), 255, np.uint8)], axis=3)
    hero_tex = ctx.texture_array((hero_px, hero_px, len(hlayers)), 4, np.ascontiguousarray(hrgba).tobytes())
    hero_tex.build_mipmaps()
    hero_tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    hero_tex.anisotropy = 8.0
    hero_tex.repeat_x = hero_tex.repeat_y = False

    # main-image overlay texture; alpha channel = blend map
    mw = 1024 if preview else 2048
    mh = int(round(mw * m.rows / m.cols))
    main = cv2.resize(m.main, (mw, mh), interpolation=cv2.INTER_AREA)
    alpha = (np.clip(blend_alpha(m, s, mw, mh), 0, 1) * 255 + 0.5).astype(np.uint8)
    main_tex = ctx.texture((mw, mh), 4, np.ascontiguousarray(np.concatenate([main, alpha], 2)).tobytes())
    main_tex.build_mipmaps()
    main_tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)

    # blurred backdrop texture
    bw = 96
    bh = max(8, int(round(bw * m.rows / m.cols)))
    blur = cv2.GaussianBlur(cv2.resize(m.main, (bw, bh), interpolation=cv2.INTER_AREA), (0, 0), 4)
    bf = blur.astype(np.float32) / 255.0                      # lift dark photos to a rich mid-dark tone
    lum = float((bf @ np.array([.299, .587, .114], np.float32)).mean())
    gray = (bf @ np.array([.299, .587, .114], np.float32))[..., None]
    bf = np.clip(gray + (bf - gray) * 1.6, 0, 1) * float(np.clip(0.42 / max(lum, 1e-3), 0.5, 3.5))
    blur = (np.clip(bf, 0, 0.75) * 255).astype(np.uint8)
    back_tex = ctx.texture((bw, bh), 3, np.ascontiguousarray(blur).tobytes())
    back_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    back_tex.repeat_x = back_tex.repeat_y = False
    accent = _accent(m.main)

    prog = ctx.program(vertex_shader=TILE_VS, fragment_shader=TILE_FS)
    over = ctx.program(vertex_shader=OVER_VS, fragment_shader=OVER_FS)
    back = ctx.program(vertex_shader=BACK_VS, fragment_shader=BACK_FS)
    glow = ctx.program(vertex_shader=GLOW_VS, fragment_shader=GLOW_FS)
    part = ctx.program(vertex_shader=PART_VS, fragment_shader=PART_FS)
    quad = ctx.buffer(np.array([-.5, -.5, .5, -.5, -.5, .5, .5, .5], np.float32).tobytes())
    inst_buf = ctx.buffer(plan.inst.tobytes())
    vao = ctx.vertex_array(prog, [(quad, "2f", "in_vert"),
                                  (inst_buf, "4f 4f 4f 3f 3f 3f/i", "i_end", "i_start", "i_time",
                                   "i_off", "i_ext", "i_mid")])
    vao_over = ctx.vertex_array(over, [(quad, "2f", "in_vert")])
    vao_back = ctx.vertex_array(back, [(quad, "2f", "in_vert")])
    vao_glow = ctx.vertex_array(glow, [(quad, "2f", "in_vert")])

    # particles (dust / bokeh): static random attributes, motion is analytic in the shader
    n_p = 0 if preview and s.particles > 60 else s.particles
    box = (m.cols * 0.78, m.rows * 0.72)
    vao_part = None
    if n_p > 0:
        prng = np.random.default_rng(s.anim_seed + 5)
        pa = np.stack([prng.uniform(-box[0], box[0], n_p), prng.uniform(-box[1], box[1], n_p),
                       prng.uniform(-0.12, 0.25, n_p) * plan.d_full,
                       prng.uniform(0.0022, 0.0085, n_p) * plan.d_full], 1).astype(np.float32)
        pb = np.stack([prng.uniform(0.04, 0.16, n_p) * (m.rows / 60),          # rise speed
                       prng.uniform(0, 6.28, n_p),                              # phase
                       prng.uniform(0.2, 1.2, n_p),                             # sway
                       prng.uniform(0.35, 1.0, n_p)], 1).astype(np.float32)     # brightness
        pbuf = ctx.buffer(np.concatenate([pa, pb], 1).tobytes())
        vao_part = ctx.vertex_array(part, [(quad, "2f", "in_vert"),
                                           (pbuf, "4f 4f/i", "p_a", "p_b")])
        part["u_box"].value = box
        part["u_mos"].value = (float(m.cols), float(m.rows))
        pc = 0.55 * accent + 0.45 * np.array([1.0, 0.93, 0.82], np.float32)
        part["u_color"].value = tuple(float(v) for v in pc)

    prog["u_tiles"].value = 0
    prog["u_hero"].value = 3
    over["u_main"].value = 1
    back["u_blur"].value = 2
    bgc = tuple(v / 255 for v in s.bg_color)
    prog["u_gap"].value = s.gap_px / max(s.cell_px, 1)
    prog["u_dof"].value = s.dof
    prog["u_bgc"].value = bgc
    over["u_size"].value = (float(m.cols), float(m.rows))
    back["u_bg"].value = bgc
    back["u_accent"].value = tuple(float(v) for v in accent)
    back["u_accent2"].value = tuple(float(v) for v in _accent2(accent))
    back["u_res"].value = (float(W), float(H))
    pad = 0.55 * max(m.cols, m.rows)
    glow["u_quad"].value = (m.cols + pad, m.rows + pad)
    glow["u_half"].value = (m.cols / 2, m.rows / 2)
    glow["u_scale"].value = float(m.cols)
    glow["u_accent"].value = tuple(float(v) for v in accent)
    glow["u_glow"].value = s.glow
    proj = perspective(FOV_DEG, W / H, 0.5, plan.d_full * 6)

    total = int(round((max_seconds or D) * fps))
    proc = subprocess.Popen(_ffmpeg_cmd(s, W, H, fps, out_path), stdin=subprocess.PIPE)
    try:
        for i in range(total):
            t = i / fps
            nsub = 1 if (preview or t < 0.80 * D) else 6        # finale: jittered supersampling kills crawling detail
            acc = None
            for sj in range(nsub):
                jx, jy = JITTER[sj] if nsub > 1 else (0.0, 0.0)
                eye, target, roll = plan.camera(t)
                view = look_at(eye, target, roll)
                pj = (perspective(plan.fov(t), W / H, 0.5, plan.d_full * 6) if plan.fov else proj).copy()
                pj[0, 2] += jx * 2.0 / W; pj[1, 2] += jy * 2.0 / H
                vpb = (pj @ view).T.astype("f4").tobytes()
                right, up, fwd = view[0, :3], view[1, :3], -view[2, :3]
                for pr in (prog, over, glow, part):
                    pr["u_vp"].write(vpb)
                prog["u_time"].value = t
                prog["u_eye"].value = tuple(float(v) for v in eye)
                prog["u_fwd"].value = tuple(float(v) for v in fwd)
                prog["u_focus"].value = float(np.linalg.norm(target - eye))

                fbo_ms.use()
                ctx.clear(*bgc, 1.0)
                ctx.disable(moderngl.DEPTH_TEST | moderngl.BLEND)

                # 1) backdrop
                if s.backdrop:
                    back["u_amt"].value = 0.15 + 0.85 * smooth(0.45 * D, 0.90 * D, t)
                    back["u_shift"].value = (float(target[0]) / m.cols * 0.03, float(target[1]) / m.rows * 0.03)
                    back["u_time"].value = t
                    back_tex.use(2)
                    ctx.depth_mask = False
                    vao_back.render(moderngl.TRIANGLE_STRIP)
                    ctx.depth_mask = True

                ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)

                # 2) shadow + glow behind the mosaic
                fade = smooth(0.66 * D, 0.88 * D, t)
                if s.glow > 0 and fade > 0:
                    glow["u_fade"].value = fade
                    ctx.depth_mask = False
                    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                    glow["u_mode"].value = 0.0
                    vao_glow.render(moderngl.TRIANGLE_STRIP)
                    ctx.blend_func = moderngl.ONE, moderngl.ONE
                    glow["u_mode"].value = 1.0
                    vao_glow.render(moderngl.TRIANGLE_STRIP)
                    ctx.depth_mask = True

                # 3) tiles
                ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                tex.use(0)
                hero_tex.use(3)
                vao.render(moderngl.TRIANGLE_STRIP, instances=len(plan.inst))

                # 4) main-image overlay + light sweep
                ramp = smooth(*plan.ramp, t)
                sh0, sh1 = plan.shine
                shining = sh0 <= t <= sh1
                shine = -0.2 + 1.4 * (t - sh0) / (sh1 - sh0) if shining else -5.0
                if ramp > 0 or shining:
                    over["u_ramp"].value = ramp
                    over["u_shine"].value = shine
                    main_tex.use(1)
                    ctx.depth_mask = False
                    ctx.disable(moderngl.DEPTH_TEST)          # drawn on top: no depth-fighting with the tiles
                    vao_over.render(moderngl.TRIANGLE_STRIP)
                    ctx.enable(moderngl.DEPTH_TEST)
                    ctx.depth_mask = True

                # 5) drifting dust, sparkling as the sweep passes
                if vao_part is not None:
                    part["u_time"].value = t
                    part["u_right"].value = tuple(float(v) for v in right)
                    part["u_up"].value = tuple(float(v) for v in up)
                    part["u_shine"].value = shine
                    part["u_amt"].value = 0.25 + 0.75 * smooth(0.45 * D, 0.90 * D, t)
                    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
                    ctx.depth_mask = False
                    vao_part.render(moderngl.TRIANGLE_STRIP, instances=n_p)
                    ctx.depth_mask = True

                ctx.copy_framebuffer(fbo, fbo_ms)
                raw = fbo.read(components=3, alignment=1)
                if nsub > 1:
                    cur = np.frombuffer(raw, np.uint8).astype(np.float32)
                    acc = cur if acc is None else acc + cur
            out_bytes = raw if nsub == 1 else (acc / nsub + 0.5).astype(np.uint8).tobytes()
            proc.stdin.write(out_bytes)
            if progress and i % 10 == 0:
                progress(i + 1, total)
    finally:
        proc.stdin.close()
        proc.wait()
        ctx.release()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed")
    return out_path
