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


def test_runner_image_job_and_errors(tmp_path):
    from mosaicvid.runner import run_job
    rng = np.random.default_rng(3)
    d = tmp_path / "tiles"; d.mkdir()
    for i in range(30):
        make_photo(rng).save(d / f"p{i}.jpg")
    main = tmp_path / "main.png"
    make_photo(rng, 300, 400).save(main)
    ev = []
    rc = run_job({"mode": "image", "tiles_dir": str(d), "main_image": str(main), "out_dir": str(tmp_path / "out"),
                  "settings": {"num_tiles": 150, "cell_px": 16, "max_uses": 12, "min_distance": 2, "dedupe": False,
                               "min_sharpness": 0, "smart_crop": False}}, ev.append)
    assert rc == 0
    kinds = [e["event"] for e in ev]
    assert kinds[0] == "start" and kinds[-1] == "result"
    assert [e["stage"] for e in ev if e["event"] == "stage"] == ["prepare", "solve", "still"]
    assert (tmp_path / "out" / "mosaic.png").exists() and (tmp_path / "out" / "scene.json").exists()
    bad = []
    assert run_job({"mode": "image", "tiles_dir": str(d)}, bad.append) == 1
    assert bad[-1]["event"] == "error" and "main_image" in bad[-1]["message"]


def test_every_image_format_is_written_and_readable(tmp_path):
    from mosaicvid.runner import save_image
    from mosaicvid.settings import IMAGE_FORMATS
    img = np.random.default_rng(0).integers(0, 255, (60, 40, 3), dtype=np.uint8)
    sizes = {}
    for fmt, ext in IMAGE_FORMATS.items():
        s = Settings(image_format=fmt, image_quality=80)
        p = save_image(img, tmp_path, s)
        assert p.name == f"mosaic.{ext}" and p.exists()
        with Image.open(p) as im:
            assert im.size == (40, 60)
        sizes[fmt] = p.stat().st_size
    assert sizes["jpg"] < sizes["png"]
    assert save_image(img, tmp_path, Settings(image_format="bogus")).name == "mosaic.png"   # unknown -> PNG


def test_collection_folders_subfolders_and_excludes(tmp_path):
    from mosaicvid.preprocess import list_images
    rng = np.random.default_rng(5)
    a, b = tmp_path / "a", tmp_path / "b"
    (a / "sub").mkdir(parents=True); (a / "skip").mkdir(); b.mkdir()
    for d, n in ((a, 3), (a / "sub", 2), (a / "skip", 4), (b, 5)):
        for i in range(n):
            make_photo(rng, 64, 64).save(d / f"{d.name}{i}.jpg")
    assert len(list_images(a)) == 9                                        # sub-folders included by default
    assert len(list_images(a, recursive=False)) == 3
    assert len(list_images([a, b])) == 14                                  # several folders
    assert len(list_images([a, b], exclude=[a / "skip"])) == 10            # excluded folder left out
    assert len(list_images([a, a])) == 9                                   # same file is never listed twice


def test_black_and_white_print_size_and_dpi(tmp_path):
    from mosaicvid.runner import run_job
    rng = np.random.default_rng(8)
    d = tmp_path / "tiles"; d.mkdir()
    for i in range(24):
        make_photo(rng).save(d / f"p{i}.jpg")
    main = tmp_path / "main.png"
    make_photo(rng, 300, 400).save(main)
    cache = tmp_path / "shared_cache"
    ev = []
    rc = run_job({"mode": "image", "tiles_dir": str(d), "main_image": str(main), "out_dir": str(tmp_path / "out"),
                  "cache_dir": str(cache),
                  "settings": {"num_tiles": 120, "max_uses": 12, "min_distance": 2, "dedupe": False, "min_sharpness": 0,
                               "grayscale": True, "print_width_px": 1200, "print_dpi": 300, "image_format": "tiff"}},
                 ev.append)
    assert rc == 0, ev[-1]
    res = ev[-1]
    w, h = res["stats"]["image_px"]
    assert 1200 <= w <= 1200 + 8 * 60            # within one tile column of the requested width
    assert any(cache.iterdir())                  # the shared cache folder was used
    with Image.open(tmp_path / "out" / "mosaic.tif") as im:
        assert im.size == (w, h) and round(im.info["dpi"][0]) == 300
        a = np.asarray(im.convert("RGB")).astype(int)
    assert np.abs(a[..., 0] - a[..., 1]).max() <= 3 and np.abs(a[..., 1] - a[..., 2]).max() <= 3   # grey


def test_tile_and_video_shapes(tmp_path):
    rng = np.random.default_rng(3)
    d = tmp_path / "tiles"; d.mkdir()
    for i in range(30):
        make_photo(rng).save(d / f"p{i}.jpg")
    main = tmp_path / "main.png"
    make_photo(rng, 400, 300).save(main)                     # 4:3 picture
    s = Settings(num_tiles=200, cell_px=16, tile_aspect="3:2", dedupe=False, min_sharpness=0)
    tiles = prepare_tiles(d, s, cache_dir=tmp_path / "c")
    assert abs(tiles[0].image.shape[1] / tiles[0].image.shape[0] - 1.5) < 0.02
    m = solve(tiles, main, s)
    assert abs(s.mosaic_ratio - 400 / 300) < 0.15            # mosaic follows the picture
    assert abs(m.world_w / m.rows - s.mosaic_ratio) < 1e-9
    W, H = s.video_dims()
    assert abs(W / H - s.mosaic_ratio) < 0.02                # video defaults to the mosaic's shape
    img = render_still(m, tiles, s)
    assert img.shape == (m.rows * 16, m.cols * 24, 3)
    s.video_aspect = "9:16"
    assert s.video_dims() == (1080, 1920)
    from mosaicvid.animation import make_plan
    p = make_plan(m, tiles, s)
    assert np.isfinite(p.inst).all()
