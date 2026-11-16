import numpy as np
from PIL import Image, ImageDraw

from mosaicvid.preprocess import prepare_tiles, trim_borders, smart_square_crop
from mosaicvid.settings import Settings
from mosaicvid.solver import solve, render_still


def make_photo(rng, w=320, h=240):
    base = rng.integers(20, 235, 3)
    arr = np.zeros((h, w, 3), np.float32)
    arr[:] = base
    arr += np.linspace(-40, 40, w)[None, :, None] * rng.uniform(-1, 1, 3)[None, None, :]
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for _ in range(12):
        x, y = rng.integers(0, w), rng.integers(0, h)
        d.ellipse([x, y, x + rng.integers(10, 60), y + rng.integers(10, 60)],
                  fill=tuple(int(v) for v in rng.integers(0, 255, 3)))
    return im


def test_trim_borders_removes_white_frame():
    rng = np.random.default_rng(1)
    im = np.asarray(make_photo(rng, 200, 200))
    framed = np.full((260, 260, 3), 255, np.uint8)
    framed[30:230, 30:230] = im
    out = trim_borders(framed)
    assert abs(out.shape[0] - 200) <= 4 and abs(out.shape[1] - 200) <= 4


def test_trim_keeps_smooth_gradient():
    g = np.tile(np.linspace(100, 160, 200, dtype=np.uint8)[None, :, None], (200, 1, 3))
    assert trim_borders(g).shape == g.shape


def test_square_crop():
    assert smart_square_crop(np.zeros((100, 300, 3), np.uint8)).shape[:2] == (100, 100)


def test_full_pipeline_constraints(tmp_path):
    rng = np.random.default_rng(0)
    d = tmp_path / "tiles"; d.mkdir()
    for i in range(60):
        make_photo(rng).save(d / f"p{i}.jpg")
    main = tmp_path / "main.png"
    make_photo(rng, 400, 300).save(main)
    s = Settings(num_tiles=300, cell_px=16, max_uses=14, min_distance=3, use_subtiles=True,
                 subtile_percent=20, dedupe=False, min_sharpness=0)
    tiles = prepare_tiles(d, s, cache_dir=tmp_path / "c")
    assert len(tiles) == 60
    m = solve(tiles, main, s)
    counts = np.bincount([c.tile for c in m.cells], minlength=len(tiles))
    assert counts.max() <= 14
    assert m.stats["violations"] == 0
    for t in range(len(tiles)):
        pts = [(c.cx, c.cy) for c in m.cells if c.tile == t]
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                assert (pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2 >= 9 - 1e-6
    img = render_still(m, tiles, s)
    assert img.shape == (m.rows * 16, m.cols * 16, 3)


def test_animation_styles_make_valid_plans(tmp_path):
    from mosaicvid.animation import STYLES, N_COLS, make_plan
    rng = np.random.default_rng(1)
    d = tmp_path / "tiles"; d.mkdir()
    for i in range(30):
        make_photo(rng).save(d / f"p{i}.jpg")
    main = tmp_path / "main.png"
    make_photo(rng, 300, 400).save(main)
    s = Settings(num_tiles=200, cell_px=16, max_uses=12, min_distance=2, dedupe=False, min_sharpness=0)
    tiles = prepare_tiles(d, s, cache_dir=tmp_path / "c")
    m = solve(tiles, main, s)
    assert set(STYLES) >= {"swarm", "vortex", "wave", "zoom"}
    for name in STYLES:
        s.style = name
        p = make_plan(m, tiles, s)
        assert p.inst.shape == (len(m.cells), N_COLS)
        assert np.isfinite(p.inst).all(), name
        assert (p.inst[:, 8] + p.inst[:, 9]).max() < s.duration * 0.9, name   # everyone landed before the finale
        eye, target, _ = p.camera(s.duration)
        assert np.isfinite(eye).all() and np.isfinite(target).all()
