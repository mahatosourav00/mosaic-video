"""Generate the app icon (assets/icon.png + icon.ico): a dark rounded square holding a small mosaic."""
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "mosaicvid" / "gui" / "assets"


def make(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size * 0.22, fill=(18, 21, 28, 255))
    n, pad = 7, size * 0.17
    cell = (size - 2 * pad) / n
    rnd = random.Random(11)
    for i in range(n):
        for j in range(n):
            dist = (((i - (n - 1) / 2) ** 2 + (j - (n - 1) / 2) ** 2) ** 0.5) / (n / 1.35)
            t = min(dist, 1.0)
            r = int(139 * (1 - t) + 70 * t + rnd.randint(-14, 14))
            g = int(124 * (1 - t) + 110 * t + rnd.randint(-14, 14))
            b = int(255 * (1 - t) + 230 * t + rnd.randint(-10, 10))
            a = int(255 - 130 * t)
            g2 = 10 if (i + j) % 5 == 0 else 0
            x0, y0 = pad + i * cell + cell * 0.07, pad + j * cell + cell * 0.07
            d.rounded_rectangle([x0, y0, x0 + cell * 0.86, y0 + cell * 0.86], radius=cell * 0.14,
                                fill=(max(0, min(255, r)), max(0, min(255, g + g2)), max(0, min(255, b)), a))
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    big = make(512)
    big.save(OUT / "icon.png")
    big.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written to", OUT)
