"""PyInstaller entry point: the packaged MosaicStudio.exe starts here."""
import multiprocessing
import os
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from mosaicvid.app import main
    rc = main()
    # Everything is saved and flushed by now. In the packaged build, normal interpreter shutdown crashed about half
    # the time (Windows fast-fail 0xC0000409 while Qt/OpenCV objects were torn down in the wrong order), which can
    # pop up a "has stopped working" window after the user closes the app. Leave immediately instead.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.flush()
        except Exception:
            pass
    os._exit(int(rc or 0))
