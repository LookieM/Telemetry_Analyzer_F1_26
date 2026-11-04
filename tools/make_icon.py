"""Draw desktop/telemetria.ico: the favicon from frontend/index.html (red rounded square, white trace).

Run once after changing the design: `python tools/make_icon.py` (needs Pillow).
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
RED = (224, 60, 49, 255)  # #e03c31
SIZE = 256  # drawn large, saved with every standard size


def draw() -> Image.Image:
    k = SIZE / 16  # the SVG is a 16x16 viewBox
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=int(3 * k), fill=RED)
    pts = [(3 * k, 11 * k), (6 * k, 6 * k), (9 * k, 9 * k), (13 * k, 3 * k)]
    width = int(1.6 * k)
    d.line(pts, fill="white", width=width, joint="curve")
    for x, y in (pts[0], pts[-1]):  # round caps
        r = width / 2
        d.ellipse((x - r, y - r, x + r, y + r), fill="white")
    return img


if __name__ == "__main__":
    out = ROOT / "desktop" / "telemetria.ico"
    out.parent.mkdir(exist_ok=True)
    draw().save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(out)
