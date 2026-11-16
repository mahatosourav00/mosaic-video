r"""Build the double-clickable app:   .\.venv\Scripts\python.exe packaging\build_exe.py

Result: dist\MosaicStudio\MosaicStudio.exe  (a folder; zip it or point an installer at it to share).
Everything the app needs (Python, Qt, OpenCV, FFmpeg) is inside, so the target PC needs nothing installed.

Also produced: dist\MosaicStudio-v<version>-windows.zip and dist\SHA256SUMS.txt (publish the checksums next to the
download so people can verify it).

Code signing (what makes Windows SmartScreen stop warning): set the environment variable SIGN_CMD to a command that
signs one file, with {file} where the path goes, e.g.
    set SIGN_CMD=signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f my.pfx /p PASSWORD "{file}"
The exe is signed BEFORE it is zipped. Without SIGN_CMD the build is simply unsigned.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "mosaicvid" / "gui" / "assets"

# Qt modules we never import. Leaving them out keeps the app a few hundred MB smaller.
EXCLUDE = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebView",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtBluetooth", "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6",
]


def version_file(path: Path) -> None:
    """Windows 'Details' tab info (product, company, version). An exe with none looks anonymous to antivirus."""
    sys.path.insert(0, str(ROOT))
    from mosaicvid import __version__
    from mosaicvid.gui import branding
    nums = tuple((list(int(x) for x in __version__.split(".") if x.isdigit()) + [0, 0, 0, 0])[:4])
    v = ".".join(map(str, nums))
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{branding.AUTHOR}'),
      StringStruct('FileDescription', 'Mosaic Studio - photo mosaic images and videos'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'MosaicStudio'),
      StringStruct('LegalCopyright', 'Copyright (c) {branding.AUTHOR}'),
      StringStruct('OriginalFilename', 'MosaicStudio.exe'),
      StringStruct('ProductName', 'Mosaic Studio'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")


def sign(exe: Path) -> bool:
    cmd = os.environ.get("SIGN_CMD", "").strip()
    if not cmd:
        print("\nNot signed (set SIGN_CMD to sign; see the top of this file). Windows SmartScreen will warn.")
        return False
    subprocess.check_call(cmd.replace("{file}", str(exe)), shell=True)
    print("Signed:", exe)
    return True


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    subprocess.check_call([sys.executable, str(ROOT / "packaging" / "make_icon.py")])
    import PyInstaller.__main__ as pyi
    vfile = ROOT / "build" / "version_info.txt"
    vfile.parent.mkdir(exist_ok=True)
    version_file(vfile)
    args = [
        str(ROOT / "packaging" / "entry.py"),
        "--name", "MosaicStudio",
        "--windowed", "--noconfirm", "--clean",
        "--noupx",                                # packed (UPX) exes are flagged far more often by antivirus
        "--version-file", str(vfile),
        "--icon", str(ASSETS / "icon.ico"),
        "--paths", str(ROOT),
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
        "--add-data", f"{ASSETS};mosaicvid/gui/assets",
        "--collect-all", "imageio_ffmpeg",        # bundles the ffmpeg.exe used to write videos
        "--collect-data", "cv2",                  # face-detection model files
        "--hidden-import", "glcontext",           # OpenGL context for the video renderer
        "--hidden-import", "moderngl",
    ]
    for m in EXCLUDE:
        args += ["--exclude-module", m]
    pyi.run(args)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):            # licence texts travel with the app
        shutil.copy(ROOT / name, ROOT / "dist" / "MosaicStudio" / name)
    exe = ROOT / "dist" / "MosaicStudio" / "MosaicStudio.exe"
    print("\nBuilt:", exe, "(exists)" if exe.exists() else "(MISSING)")
    if not exe.exists():
        return 1
    from mosaicvid import __version__
    sign(exe)
    zip_base = ROOT / "dist" / f"MosaicStudio-v{__version__}-windows"
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", ROOT / "dist", "MosaicStudio"))
    sums = ROOT / "dist" / "SHA256SUMS.txt"
    sums.write_text(f"{sha256(zip_path)}  {zip_path.name}\n{sha256(exe)}  MosaicStudio.exe\n", encoding="utf-8")
    print("Zip:", zip_path, f"({zip_path.stat().st_size / 1e6:.0f} MB)\nChecksums:", sums)
    return 0


if __name__ == "__main__":
    sys.exit(main())
