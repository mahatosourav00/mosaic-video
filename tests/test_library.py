"""Plugin library: catalog parsing, checksummed install/update/remove, and the "?" guide of plugin options."""
import hashlib
import io
import json
import os
import zipfile

import pytest

from mosaicvid import library as L
from mosaicvid import plugins as P

MANIFEST = {"api": 1, "id": "hello", "name": "Hello", "version": "1.0.0", "needs": "none", "steps": []}


def make_zip(path, files, root=""):
    with zipfile.ZipFile(path, "w") as z:
        for n, d in files.items():
            z.writestr(root + n, d)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait(app, cond, seconds=10):
    import time
    end = time.time() + seconds
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.02)


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("MOSAICVID_PLUGINS", raising=False)
    zp = tmp_path / "hello-1.0.0.zip"
    sha = make_zip(zp, {"plugin.json": json.dumps(MANIFEST), "plugin.py": "def run(ctx): return {}"}, root="hello/")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"api": 1, "plugins": [
        {"id": "hello", "name": "Hello", "version": "1.0.0", "description": "d", "chips": ["a"],
         "download": "hello-1.0.0.zip", "sha256": sha},
        {"id": "bad id", "name": "x", "version": "1", "download": "x", "sha256": "x"},
        {"name": "no id"}]}), encoding="utf-8")
    monkeypatch.setenv("MOSAICVID_CATALOG", str(reg))
    return tmp_path


def test_catalog_skips_malformed_entries_and_resolves_relative_downloads(lib):
    entries = L.fetch_catalog()
    assert [e.id for e in entries] == ["hello"]
    assert entries[0].download == str(lib / "hello-1.0.0.zip")


def test_install_update_remove(lib):
    e = L.fetch_catalog()[0]
    assert L.status(e, P.discover()) == "install"
    pl = L.install(e)
    assert pl.id == "hello" and (pl.path / "plugin.py").is_file()
    assert L.status(e, P.discover()) == "installed"
    newer = L.Entry(**{**e.__dict__, "version": "1.1.0"})
    assert L.status(newer, P.discover()) == "update"
    assert L.remove("hello") and "hello" not in P.discover()
    assert not L.remove("hello") and not L.remove("../x")


def test_wrong_checksum_is_rejected_and_nothing_is_installed(lib):
    e = L.fetch_catalog()[0]
    e.sha256 = "0" * 64
    with pytest.raises(L.LibraryError, match="checksum"):
        L.install(e)
    assert "hello" not in P.discover()


def test_unsafe_zip_paths_are_rejected(lib):
    zp = lib / "evil.zip"
    sha = make_zip(zp, {"plugin.json": json.dumps(MANIFEST), "../../evil.py": "x"})
    e = L.Entry("hello", "Hello", "1", download=str(zp), sha256=sha)
    with pytest.raises(L.LibraryError, match="unsafe"):
        L.install(e)


def test_package_must_match_entry_and_be_valid(lib):
    zp = lib / "other.zip"
    sha = make_zip(zp, {"plugin.json": json.dumps(dict(MANIFEST, id="other"))})
    with pytest.raises(L.LibraryError, match="match"):
        L.install(L.Entry("hello", "Hello", "1", download=str(zp), sha256=sha))
    with pytest.raises(L.LibraryError, match="checksum"):
        L.install(L.Entry("hello", "Hello", "1", download=str(zp), sha256=""))


def test_unreachable_catalog_gives_a_friendly_error(monkeypatch, tmp_path):
    monkeypatch.setenv("MOSAICVID_CATALOG", str(tmp_path / "missing.json"))
    with pytest.raises(L.LibraryError, match="library"):
        L.fetch_catalog()


def test_every_plugin_field_gets_a_guide():
    pytest.importorskip("PySide6")
    from mosaicvid.gui.plugin_form import field_guide
    t, body, rec = field_guide({"key": "a", "type": "number", "label": "Size", "min": 1, "max": 9, "unit": "s",
                                "default": 3, "help": "How big."})
    assert t == "Size" and "How big." in body and "1 s to 9 s" in body and rec == "3 (the default)"
    t, body, rec = field_guide({"key": "m", "type": "choice", "label": "Mode", "options": [["x", "Fast"], ["y", "Slow"]],
                                "default": "y", "tip": "Long text", "required": True})
    assert "Long text" in body and "Fast, Slow" in body and "required" in body and rec == "Slow (the default)"
    assert field_guide({"key": "k", "type": "text"})[0] == "k"


def test_window_library_installs_a_plugin_and_every_option_has_a_question_mark(lib, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    from mosaicvid.gui.widgets import HelpButton
    from mosaicvid.gui.window import MainWindow
    app = QApplication.instance() or QApplication([])
    # give the packaged plugin a real form so the guide buttons can be counted
    man = dict(MANIFEST, steps=[{"id": "a", "title": "A", "sections": [{"title": "S", "fields": [
        {"key": "who", "type": "text", "label": "Name"}, {"key": "loud", "type": "toggle", "label": "Loud"}]}]}])
    zp = lib / "hello-1.0.0.zip"
    sha = make_zip(zp, {"plugin.json": json.dumps(man), "plugin.py": "def run(ctx): return {}"}, root="hello/")
    reg = json.loads((lib / "registry.json").read_text())
    reg["plugins"][0]["sha256"] = sha
    (lib / "registry.json").write_text(json.dumps(reg), encoding="utf-8")

    w = MainWindow()
    assert "hello" not in w.state.plugins
    w._open_library()
    wait(app, lambda: w.library.entries)                    # the catalog loads in a background thread
    assert [e.id for e in w.library.entries] == ["hello"] and w.top.currentWidget() is w.library
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    w._confirm_install(w.library.entries[0])
    wait(app, lambda: "hello" in w.state.plugins)           # and so does the install
    assert "hello" in w.state.plugins and w.top.currentWidget() is w.library
    page = w.pages["plugin.hello.0"]
    assert len(page.findChildren(HelpButton)) == 2          # one "?" per option
