"""Plugin system: manifests, discovery/linking, the 'plugin' job mode, and the form pages built from a manifest."""
import json
import os

import pytest

from mosaicvid import plugins as P
from mosaicvid.runner import run_job

MANIFEST = {
    "api": 1, "id": "hello", "name": "Hello", "version": "0.1", "needs": "none", "button": "Make hello",
    "stages": [["render", "Say hello"]], "summary": ["who"], "preview": {"start": 1, "seconds": 2},
    "steps": [{"id": "a", "title": "Who", "sections": [{"title": "T", "fields": [
        {"key": "who", "type": "text", "label": "Name", "required": True, "default": ""},
        {"key": "style.size", "type": "number", "label": "Size", "default": 3, "min": 1, "max": 9, "step": 1},
        {"key": "loud", "type": "toggle", "label": "Loud", "default": False},
        {"key": "lines", "type": "list", "label": "Lines", "default": ["a", "b"]},
        {"key": "mode", "type": "choice", "label": "Mode", "default": "x", "options": [["x", "X"], ["y", "Y"]]},
    ]}]}],
}
ENTRY = '''
def run(ctx):
    ctx.stage("render", "hi")
    ctx.progress("render", 1, 2)
    out = ctx.out_dir / "hello.txt"
    out.write_text(repr((ctx.values["who"], ctx.nested()["style"]["size"], ctx.preview)), encoding="utf-8")
    return {"video": out}
'''


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated 'AppData' so linking never touches the real one, plus a plugin project folder."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("MOSAICVID_PLUGINS", raising=False)
    proj = tmp_path / "My Hello Project"                    # a plugin lives in its own folder, with spaces and all
    proj.mkdir()
    (proj / "plugin.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (proj / "plugin.py").write_text(ENTRY, encoding="utf-8")
    return proj


def test_manifest_validation_reports_problems():
    assert P.validate_manifest(MANIFEST) == []
    bad = dict(MANIFEST, api=2, id="no spaces", summary=["nope"])
    problems = " ".join(P.validate_manifest(bad))
    assert "api must be" in problems and "id must be" in problems and "unknown field" in problems
    dup = json.loads(json.dumps(MANIFEST))
    dup["steps"][0]["sections"][0]["fields"].append({"key": "who", "type": "text"})
    assert any("duplicate" in p for p in P.validate_manifest(dup))


def test_link_discover_unlink(home):
    assert "hello" not in P.discover()
    assert P.link(home) == "hello"
    found = P.discover()
    assert found["hello"].path == home.resolve()
    assert found["hello"].defaults()["style.size"] == 3
    assert P.unlink(home) and "hello" not in P.discover()
    with pytest.raises(P.PluginError):
        P.link(home.parent)                                  # no plugin.json there


def test_broken_plugin_is_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    d = tmp_path / "plugins" / "broken"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("MOSAICVID_PLUGINS", str(tmp_path / "plugins"))
    assert P.discover() == {}


def test_plugin_job_runs_the_entry_and_reports_events(home, tmp_path):
    P.link(home)
    events = []
    out = tmp_path / "out"
    job = {"mode": "plugin", "out_dir": str(out), "settings": {}, "preview": True,
           "plugin": {"id": "hello", "values": {"who": "Ann", "style.size": 7, "bogus": 1}}}
    assert run_job(job, events.append) == 0
    kinds = [e["event"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "result" and "progress" in kinds
    assert (out / "hello.txt").read_text(encoding="utf-8") == "('Ann', 7, True)"      # unknown keys are dropped
    assert events[-1]["outputs"]["video"].endswith("hello.txt")


def test_unknown_plugin_and_failing_plugin_give_an_error_event(home, tmp_path):
    events = []
    assert run_job({"mode": "plugin", "out_dir": str(tmp_path), "plugin": {"id": "ghost"}}, events.append) == 1
    assert events[-1]["event"] == "error" and "not installed" in events[-1]["message"]
    (home / "plugin.py").write_text("def run(ctx):\n    raise ValueError('boom')\n", encoding="utf-8")
    P.link(home)
    events.clear()
    assert run_job({"mode": "plugin", "out_dir": str(tmp_path), "plugin": {"id": "hello"}}, events.append) == 1
    assert events[-1]["message"] == "boom"


def test_state_steps_job_and_preset(home):
    pytest.importorskip("PySide6")
    from mosaicvid.gui.state import AppState, apply_preset, to_preset
    P.link(home)
    s = AppState(goal="plugin:hello", out_dir="o")
    s.plugins = P.discover()
    assert s.steps() == ["plugin.hello.0", "create"]                    # needs "none": no photo step
    s.values_of("hello")["who"] = "Bo"
    s.plugin_preview.update(on=True, start=5, seconds=9)
    j = s.to_job()
    assert j["mode"] == "plugin" and j["preview"] is True and j["plugin"]["values"]["who"] == "Bo"
    assert j["plugin"]["preview"] == {"start": 5, "seconds": 9} and "tiles_dir" not in j
    preset = to_preset(s)
    vals = s.values_of("hello")                                         # same dict object must survive a load
    vals["who"] = "changed"
    apply_preset(s, preset)
    assert s.values_of("hello") is vals and vals["who"] == "Bo"


def test_form_page_is_built_from_the_manifest(home, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from mosaicvid.gui.plugin_form import PluginStepPage
    from mosaicvid.gui.state import AppState
    app = QApplication.instance() or QApplication([])
    P.link(home)
    st = AppState(goal="plugin:hello")
    st.plugins = P.discover()
    pg = PluginStepPage(st, st.plugins["hello"], 0)
    assert pg.validate() == "Fill in: Name."                            # required text is empty
    pg.setters["who"]("Cy")
    assert st.values_of("hello")["who"] == "Cy" and pg.validate() is None
    pg.setters["loud"](True)
    pg.setters["lines"](["x", "y", "z"])
    from mosaicvid.gui.widgets import SliderField
    pg.findChildren(SliderField)[0].set_value(8)                       # a user moving the slider
    v = st.values_of("hello")
    assert v["loud"] is True and v["lines"] == ["x", "y", "z"] and v["style.size"] == 8
    from mosaicvid.gui.widgets import Segmented
    pg.findChildren(Segmented)[0].buttons["y"].click()                  # a user picking the other option
    assert v["mode"] == "y"
    v["style.size"] = 5                                                 # a loaded preset changes values, then sync()
    pg.sync()
    assert pg.findChildren(SliderField)[0].value() == 5 and v["style.size"] == 5
    app.processEvents()


def test_add_plugin_button_links_and_shows_the_new_card(home, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from mosaicvid.gui.window import MainWindow
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    assert "hello" not in w.state.plugins and "plugin.hello.0" not in w.pages
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(home)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    w._add_plugin()
    assert "hello" in w.state.plugins and "plugin.hello.0" in w.pages
    assert w.top.currentIndex() == 0 and w.top.count() == 3          # home rebuilt in place; flow and library follow it
    assert "hello" in P.discover()                                    # and remembered for the next start
    w.start_flow("plugin:hello")
    assert w.keys == ["plugin.hello.0", "create"]
    app.processEvents()
