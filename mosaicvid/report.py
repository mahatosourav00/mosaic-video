"""Preprocessing report: contact sheets + CSV so you can check accepted/rejected photos before building."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .preprocess import Record, load_rgb

COLORS = {"ok": (60, 180, 90), "rotated": (60, 170, 230), "trimmed": (240, 170, 40), "rejected": (220, 60, 60), "duplicate": (150, 100, 220)}


def _thumb(rec: Record, tiles, cell: int) -> Image.Image:
    if rec.status == "ok" and rec.tile_index >= 0:
        im = Image.fromarray(tiles[rec.tile_index].image).resize((cell, cell), Image.LANCZOS)
    else:
        try:
            im = Image.fromarray(load_rgb(rec.path, max_side=cell * 2))
            im.thumbnail((cell, cell), Image.LANCZOS)
        except Exception:
            im = Image.new("RGB", (cell, cell), (40, 40, 40))
    bg = Image.new("RGB", (cell, cell), (24, 24, 24))
    bg.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2))
    return bg


def _sheet(recs: list[Record], tiles, title: str, cell=144, cols=10, label_h=26) -> Image.Image:
    rows = max(1, -(-len(recs) // cols))
    top = 30
    sheet = Image.new("RGB", (cols * cell, top + rows * (cell + label_h)), (14, 14, 18))
    d = ImageDraw.Draw(sheet)
    d.text((8, 9), f"{title}  ({len(recs)})", fill=(235, 235, 235))
    for n, r in enumerate(recs):
        x, y = (n % cols) * cell, top + (n // cols) * (cell + label_h)
        sheet.paste(_thumb(r, tiles, cell), (x, y))
        kind = r.status
        if r.status == "ok":
            kind = "rotated" if r.rotation else ("trimmed" if any(r.trim) else "ok")
        d.rectangle([x, y, x + cell - 1, y + cell - 1], outline=COLORS[kind], width=3)
        name = Path(r.path).name
        bits = ([f"rot {r.rotation}"] if r.rotation else []) + ([f"trim {r.trim}"] if any(r.trim) else [])
        note = r.reason if r.status != "ok" else " ".join(bits)
        d.text((x + 3, y + cell + 2), name[:24], fill=(220, 220, 220))
        d.text((x + 3, y + cell + 13), note[:24], fill=COLORS[kind])
    return sheet


def write_report(recs: list[Record], tiles, out_dir: str | Path, per_sheet: int = 150) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "status", "reason", "width", "height", "trim_top", "trim_bottom", "trim_left",
                    "trim_right", "sharpness", "rotation"])
        for r in recs:
            w.writerow([r.path, r.status, r.reason, *r.size, *r.trim, f"{r.sharpness:.1f}", r.rotation])
    groups = {
        "accepted": [r for r in recs if r.status == "ok" and not any(r.trim) and not r.rotation],
        "rotated": [r for r in recs if r.status == "ok" and r.rotation],
        "trimmed": [r for r in recs if r.status == "ok" and any(r.trim) and not r.rotation],
        "rejected": [r for r in recs if r.status == "rejected"],
        "duplicates": [r for r in recs if r.status == "duplicate"],
    }
    files = []
    for name, items in groups.items():
        for p in range(0, len(items), per_sheet):
            chunk = items[p:p + per_sheet]
            fn = out / f"contact_{name}{'' if len(items) <= per_sheet else f'_{p // per_sheet + 1}'}.jpg"
            _sheet(chunk, tiles, name.upper()).save(fn, quality=88)
            files.append(fn.name)
    return {"counts": {k: len(v) for k, v in groups.items()}, "files": files}
