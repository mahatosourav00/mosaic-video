"""Subject map: where in the main image detail matters most (faces first, then saliency)."""
from __future__ import annotations

import cv2
import numpy as np

from .preprocess import _face_detector


def subject_centroid(m: np.ndarray) -> tuple[float, float]:
    """Weighted centre of the subject map, as fractions (x, y) of the image."""
    w = m.astype(np.float64) ** 2
    if w.sum() < 1e-9:
        return 0.5, 0.5
    h, wd = m.shape
    ys, xs = np.mgrid[0:h, 0:wd]
    return float((w * xs).sum() / w.sum() / wd), float((w * ys).sum() / w.sum() / h)


def subject_map(rgb: np.ndarray, use_faces: bool = True) -> np.ndarray:
    """Float32 map in 0..1, same aspect as `rgb` (computed at ~512px)."""
    h, w, _ = rgb.shape
    s = 512.0 / max(h, w)
    small = cv2.resize(rgb, (max(8, int(w * s)), max(8, int(h * s))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    sh, sw = gray.shape

    # saliency: local contrast + edges, blurred, with a mild centre prior
    blur = cv2.GaussianBlur(gray, (0, 0), max(sh, sw) / 12.0).astype(np.float32)
    contrast = np.abs(gray.astype(np.float32) - blur)
    edges = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1))
    sal = cv2.GaussianBlur(contrast + 0.5 * edges, (0, 0), max(sh, sw) / 40.0)
    sal /= sal.max() + 1e-6
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    centre = np.exp(-(((xx / sw - 0.5) / 0.45) ** 2 + ((yy / sh - 0.5) / 0.45) ** 2))
    sal = 0.7 * sal + 0.3 * sal * centre

    faces = np.zeros_like(sal)
    det = _face_detector() if use_faces else False
    if det:
        try:
            for (x, y, fw, fh) in det.detectMultiScale(gray, 1.1, 5, minSize=(max(24, sw // 25),) * 2):
                cx, cy = x + fw / 2, y + fh / 2
                g = np.exp(-(((xx - cx) / (fw * 0.75)) ** 2 + ((yy - cy) / (fh * 0.85)) ** 2))
                faces = np.maximum(faces, g)
        except Exception:
            pass
    m = np.maximum(faces, 0.6 * sal / (sal.max() + 1e-6))
    return np.clip(m, 0, 1).astype(np.float32)
