"""GUI logic that needs no window: which steps are shown and how choices become an engine job."""
from mosaicvid.gui.state import AppState, nearest_aspect


def test_steps_follow_the_goal():
    s = AppState(goal="image")
    assert s.steps() == ["photos", "prepare", "look", "create"]
    s.goal = "both"
    assert s.steps() == ["photos", "prepare", "look", "video", "create"]
    s.goal, s.use_existing = "video", True            # reuse a saved mosaic: no preparing or designing
    assert s.steps() == ["photos", "video", "create"]


def test_skip_preparation_turns_every_cleanup_off():
    s = AppState(goal="image", tiles_dir="t", main_image="m", out_dir="o")
    assert s.final_settings()["trim_borders"] and s.final_settings()["dedupe"]
    s.skip_prep = True
    f = s.final_settings()
    assert not (f["trim_borders"] or f["dedupe"] or f["smart_crop"] or f["auto_rotate"])
    assert f["min_sharpness"] == 0 and f["min_side"] == 0
    s.skip_prep, s.filter_bad = False, False           # only the blur/size filter off
    f = s.final_settings()
    assert f["trim_borders"] and f["min_sharpness"] == 0


def test_job_shapes():
    s = AppState(goal="both", tiles_dir="t", main_image="m", out_dir="o", quality="draft")
    j = s.to_job()
    assert j["mode"] == "both" and j["preview"] is True and j["tiles_dir"] == "t" and j["main_image"] == "m"
    assert AppState(goal="image", quality="draft").to_job()["preview"] is False   # draft only affects video
    v = AppState(goal="video", use_existing=True, scene="scene.json", out_dir="o")
    jv = v.to_job()
    assert jv["mode"] == "video" and jv["scene"] == "scene.json" and "tiles_dir" not in jv
    hq = AppState(goal="video", quality="high", tiles_dir="t", main_image="m", out_dir="o")
    assert hq.to_job()["settings"]["crf"] == 18


def test_nearest_aspect():
    assert nearest_aspect(1080, 1920) == "9:16"
    assert nearest_aspect(1000, 1000) == "1:1"
    assert nearest_aspect(1600, 900) == "16:9"
    assert nearest_aspect(800, 1000) == "4:5"


def test_preset_round_trip_keeps_private_folders_out_and_updates_in_place():
    from mosaicvid.gui.state import apply_preset, to_preset
    a = AppState(goal="both", tiles_dir="t", main_image="m", out_dir="o")
    a.settings.tint, a.settings.grayscale, a.settings.style = 0.9, True, "zoom"
    a.settings.extra_tile_dirs = ["C:/private/folder"]
    a.print_on, a.print_w, a.print_dpi, a.quality = True, 30.0, 600, "high"
    preset = to_preset(a)
    assert "extra_tile_dirs" not in preset["settings"]              # folders of this computer are not shared
    b = AppState(goal="image")
    mine = b.settings                                               # the pages' controls hold this exact object
    b.settings.extra_tile_dirs = ["C:/mine"]
    apply_preset(b, preset)
    assert b.settings is mine                                       # updated in place, not replaced
    assert (b.settings.tint, b.settings.grayscale, b.settings.style) == (0.9, True, "zoom")
    assert b.settings.extra_tile_dirs == ["C:/mine"]                # keeps its own folders
    assert (b.print_on, b.print_w, b.print_dpi, b.quality) == (True, 30.0, 600, "high")
    import pytest
    with pytest.raises(ValueError):
        apply_preset(b, {"app": "SomethingElse"})


def test_print_pixels_follow_size_unit_dpi_and_shape():
    s = AppState(goal="image", print_on=True, print_w=24.0, print_dpi=300)
    s.settings.mosaic_aspect = "4:5"
    assert s.print_pixels() == (7200, 9000)
    s.print_unit, s.print_w = "cm", 30.48                            # = 12 inches
    assert s.print_pixels() == (3600, 4500)
    j = s.to_job()["settings"]
    assert j["print_width_px"] == 3600 and j["print_dpi"] == 300
    s.print_on = False
    assert s.to_job()["settings"]["print_width_px"] == 0


def test_upi_link_and_qr_round_trip():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")        # pictures need an application object, no screen
    import cv2
    import numpy as np
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])           # noqa: F841 - must stay alive
    from mosaicvid.gui import branding
    from mosaicvid.gui.coffee import qr_pixmap
    uri = branding.upi_uri("test.user@okbank", "Test User")
    assert uri == "upi://pay?pa=test.user@okbank&pn=Test%20User&cu=INR"
    img = qr_pixmap(uri, 400).toImage().convertToFormat(QImage.Format_RGB888) 
    ptr = img.constBits()
    arr = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine())[:, : img.width() * 3]
    arr = arr.reshape(img.height(), img.width(), 3).copy()
    text, _pts, _ = cv2.QRCodeDetector().detectAndDecode(arr)
    assert text == uri                                          # a real scanner reads exactly the payment link


def test_coffee_button_hidden_until_a_upi_id_is_set():
    from mosaicvid.gui import branding
    assert branding.CREDIT == "Developed by Sourav"
    assert branding.has_upi() == bool(branding.UPI_ID.strip())


def test_coffee_dialog_shows_the_whole_qr_and_it_scans():
    """Regression: the dialog once squeezed the QR so its bottom was cut off (unscannable)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import cv2
    import numpy as np
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QLabel
    app = QApplication.instance() or QApplication([])           # noqa: F841
    from mosaicvid.gui import branding
    from mosaicvid.gui.coffee import CoffeeDialog
    d = CoffeeDialog()
    d.show()
    QApplication.processEvents()
    lab = [x for x in d.findChildren(QLabel) if x.pixmap() is not None and not x.pixmap().isNull()][0]
    assert (lab.width(), lab.height()) == (lab.pixmap().width(), lab.pixmap().height())     # nothing cropped
    img = d.grab().toImage().convertToFormat(QImage.Format_RGB888)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, : img.width() * 3]
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(a.reshape(img.height(), img.width(), 3).copy())
    assert text == branding.upi_uri()
