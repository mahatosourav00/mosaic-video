"""The app must exit cleanly (code 0), not with a Windows access violation (0xC0000005) while shutting down.

A QPushButton connected to a lambda that captured the page (`self`) made the whole window crash on exit. This runs the
real entry point (`packaging/entry.py --selftest`: builds the window offscreen, renders it, exits).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_exits_with_code_zero(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT), "QT_QPA_PLATFORM": "offscreen", "QT_QPA_FONTDIR": "C:/Windows/Fonts"}
    r = subprocess.run([sys.executable, str(ROOT / "packaging" / "entry.py"), "--selftest", str(tmp_path / "w.png")],
                       env=env, capture_output=True, timeout=180)
    assert r.returncode == 0, (hex(r.returncode & 0xFFFFFFFF), r.stderr[-500:])
