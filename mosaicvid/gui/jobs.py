"""Runs an engine job as a separate process and turns its JSON lines into Qt signals."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class JobRunner(QObject):
    event = Signal(dict)          # one engine event (see mosaicvid/runner.py)
    finished = Signal(int, bool)  # exit code, was_cancelled

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc: QProcess | None = None
        self._buf = ""
        self._cancelled = False
        self._got_end = False
        self._tail: list[str] = []

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.NotRunning

    def start(self, job: dict) -> None:
        if self.running:
            return
        self._buf, self._cancelled, self._got_end, self._tail = "", False, False, []
        path = Path(tempfile.mkdtemp(prefix="mosaic_job_")) / "job.json"
        path.write_text(json.dumps(job), encoding="utf-8")
        p = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        p.setProcessEnvironment(env)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._read)
        p.finished.connect(self._done)
        p.errorOccurred.connect(self._error)
        if sys.platform == "win32":                # never let the engine open a console window of its own
            def _no_console(args):
                args.flags |= 0x08000000               # CREATE_NO_WINDOW
            try:
                p.setCreateProcessArgumentsModifier(_no_console)
            except Exception:
                pass
        self.proc = p
        if getattr(sys, "frozen", False):          # packaged .exe: the same exe runs the engine
            p.setWorkingDirectory(str(Path(sys.executable).parent))
            p.start(sys.executable, ["--engine", "run", "--job", str(path)])
        else:
            p.setWorkingDirectory(str(PROJECT_ROOT))
            p.start(sys.executable, ["-u", "-m", "mosaicvid", "run", "--job", str(path)])

    def cancel(self) -> None:
        if self.running:
            self._cancelled = True
            self.proc.kill()

    # ------------------------------------------------------------------
    def _read(self):
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                self._tail = (self._tail + [line])[-12:]       # stray output (warnings etc.), kept for errors
                continue
            if ev.get("event") in ("result", "error"):
                self._got_end = True
            self.event.emit(ev)

    def _done(self, code, _status):
        self._read()
        if not self._cancelled and not self._got_end:         # process died without telling us why
            self.event.emit({"event": "error", "message": "The engine stopped unexpectedly.",
                             "detail": "\n".join(self._tail)})
        self.finished.emit(int(code), self._cancelled)

    def _error(self, err):
        if err == QProcess.FailedToStart:
            self.event.emit({"event": "error", "message": "Could not start the engine.", "detail": str(err)})
