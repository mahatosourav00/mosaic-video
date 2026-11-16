# Third-party software

Mosaic Studio's own code is released under the [MIT License](LICENSE). The downloadable Windows app also contains
the following open-source software, each under its own licence (see the project sites for the full texts).

| Component | Used for | Licence |
|---|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/) | the window and controls | LGPL-3.0 (the app is shipped as a folder of separate files, so the Qt libraries can be replaced) |
| [OpenCV](https://opencv.org/) (`opencv-python`) | image loading, face detection | Apache-2.0 |
| [NumPy](https://numpy.org/), [SciPy](https://scipy.org/) | numerical work | BSD-3-Clause |
| [Pillow](https://python-pillow.org/) | reading and writing images | MIT-CMU (HPND) |
| [ImageHash](https://github.com/JohannesBuchner/imagehash) | finding near-duplicate photos | BSD-2-Clause |
| [ModernGL](https://github.com/moderngl/moderngl), [glcontext](https://github.com/moderngl/glcontext) | OpenGL video renderer | MIT |
| [qrcode](https://github.com/lincolnloop/python-qrcode) | the QR code in the "Buy me a coffee" window | BSD-3-Clause |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | locates the bundled FFmpeg | BSD-2-Clause |
| [FFmpeg](https://ffmpeg.org/) | encodes videos (MP4, WebM, GIF) | **GPL-3.0** build (`--enable-gpl --enable-version3`) by gyan.dev; it runs as a separate program (`ffmpeg.exe`) and its source is available from [ffmpeg.org](https://ffmpeg.org/download.html#get-sources) |
| [Python](https://www.python.org/) | the runtime | PSF License |
| [PyInstaller](https://pyinstaller.org/) | packages the app | GPL-2.0 with a special exception that allows it to be used for any program |

The sample images in this repository's README are made from public-domain NASA images and Johannes Vermeer's
*Girl with a Pearl Earring* (public domain); see the README for sources.
