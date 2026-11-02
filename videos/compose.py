"""Compose recorded frames into the finished clip: wallpaper, rounded window, drawn cursor, click
ripple, then ffmpeg to an MP4 plus a poster PNG.

    .venv/bin/python videos/compose.py out/social/inspect-kit [--still]

Reads <out>-frames/*.png and <out>-track.json written by videos/record.mjs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_SIZE = 1080
ARROW = [(0, 0), (0, 25), (6, 19), (10.5, 29), (14.5, 27.2), (10, 17.8), (18, 17.8)]
HAND = [((-3, 0, 3, 16), 3), ((-3, 9, 15, 26), 5), ((2, 7, 8, 16), 3), ((7, 8, 13, 16), 3),
        ((-9, 11, -2, 20), 3)]  # finger, palm, two knuckles, thumb; (0, 0) is the fingertip


def wallpaper(w: int, h: int) -> Image.Image:
    """Soft cool diagonal gradient."""
    a, b = (176, 196, 222), (210, 190, 230)
    small = Image.new("RGB", (64, 64))
    px = small.load()
    for y in range(64):
        for x in range(64):
            t = (x + y) / 126
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return small.resize((w, h), Image.BICUBIC)


def base(track: dict) -> tuple[Image.Image, Image.Image, tuple[int, int]]:
    """Wallpaper with the window drawn on it, the mask for the app's pixels, and the app's
    top-left corner on the canvas."""
    s, pad, bar = track["scale"], track["pad"], track["bar"]
    w, h = track["width"] * s, track["height"] * s
    canvas = wallpaper(w, h)
    x0, y0, x1, y1 = pad * s, pad * s, w - pad * s, h - pad * s
    radius = 14 * s
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + 10 * s, x1, y1 + 10 * s), radius, fill=120)
    canvas.paste((40, 40, 60), (0, 0), shadow.filter(ImageFilter.GaussianBlur(18 * s)))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x0, y0, x1, y1), radius, fill=(14, 17, 23))
    d.rounded_rectangle((x0, y0, x1, y0 + bar * s + radius), radius, fill=(32, 35, 42))
    d.rectangle((x0, y0 + bar * s, x1, y0 + bar * s + radius), fill=(14, 17, 23))
    for i, color in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        cx, cy = x0 + (20 + i * 20) * s, y0 + bar * s / 2
        d.ellipse((cx - 6 * s, cy - 6 * s, cx + 6 * s, cy + 6 * s), fill=color)
    mask = Image.new("L", (x1 - x0, y1 - y0 - bar * s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, -radius, mask.width, mask.height), radius, fill=255)
    return canvas, mask, (x0, y0 + bar * s)


def draw_cursor(img: Image.Image, x: float, y: float, kind: str, s: int) -> None:
    d = ImageDraw.Draw(img)
    k = 1.15 * s
    if kind == "hand":
        for grow, fill in ((1.4, (0, 0, 0)), (0, (255, 255, 255))):
            for (bx0, by0, bx1, by1), r in HAND:
                d.rounded_rectangle((x + (bx0 - grow) * k, y + (by0 - grow) * k,
                                     x + (bx1 + grow) * k, y + (by1 + grow) * k), r * k, fill=fill)
        return
    d.polygon([(x + px * k, y + py * k) for px, py in ARROW], fill=(0, 0, 0),
              outline=(255, 255, 255), width=round(1.6 * s))


def draw_ripple(img: Image.Image, x: float, y: float, age: int | None, s: int) -> None:
    if age is None or age > 12:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    r = (8 + age * 2.6) * s
    alpha = round(150 * (1 - age / 12))
    ImageDraw.Draw(layer).ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, alpha),
                                  width=3 * s, fill=(255, 255, 255, alpha // 4))
    img.alpha_composite(layer)


def compose(track: dict, frames_dir: Path, index: int, canvas: Image.Image, mask: Image.Image,
            origin: tuple[int, int]) -> Image.Image:
    s, f = track["scale"], track["frames"][index]
    img = canvas.copy().convert("RGBA")
    app = Image.open(frames_dir / f"{index:05d}.png").convert("RGB").resize(mask.size)
    img.paste(app, origin, mask)
    x, y = origin[0] + f["x"] * s, origin[1] + f["y"] * s
    draw_ripple(img, x, y, f["ripple"], s)
    draw_cursor(img, x, y, f["kind"], s)
    return img.convert("RGB")


def main() -> None:
    out = Path(sys.argv[1])
    track = json.loads(Path(f"{out}-track.json").read_text())
    frames_dir = Path(f"{out}-frames")
    canvas, mask, origin = base(track)
    n = len(track["frames"])
    poster = track["poster"] if track["poster"] is not None else n // 2
    compose(track, frames_dir, min(poster, n - 1), canvas, mask, origin) \
        .resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS).save(f"{out}.png")
    print(f"poster -> {out}.png")
    if "--still" in sys.argv:
        return
    w, h = canvas.size
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-r", str(track["fps"]), "-i", "-",
         "-vf", f"scale={OUT_SIZE}:{OUT_SIZE}:flags=lanczos", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow", "-movflags", "+faststart",
         f"{out}.mp4"], stdin=subprocess.PIPE)
    for i in range(n):
        ffmpeg.stdin.write(compose(track, frames_dir, i, canvas, mask, origin).tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(f"video -> {out}.mp4 ({n / track['fps']:.1f} s)")


if __name__ == "__main__":
    main()
