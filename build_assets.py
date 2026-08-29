#!/usr/bin/env python3
"""Generate the PWA icons and the social share card.

Run by hand when the look changes -- not in CI, since the output is static and
committing identical binaries on every cron run would be noise.

    python3 build_assets.py

Deliberately typographic: the club crest is copyrighted, so the marks here use a
plain wordmark. Crests shown in the app are hotlinked from ESPN at runtime,
which is a different thing from bundling them.
"""
import os
from PIL import Image, ImageDraw, ImageFont

DIR = os.path.dirname(os.path.abspath(__file__))
RED, BG, TX, MUT = (224, 36, 47), (13, 15, 18), (233, 236, 241), (139, 146, 158)
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def centred(d, box, text, f, fill):
    x0, y0, x1, y1 = box
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text((x0 + (x1 - x0 - (r - l)) / 2 - l, y0 + (y1 - y0 - (b - t)) / 2 - t),
           text, font=f, fill=fill)


def icon(size, path):
    """Red rounded square, white W. Reads at 40px on a home screen."""
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    pad = round(size * 0.055)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=round(size * 0.22), fill=RED)
    centred(d, (0, 0, size, size * 0.97), "W", font(BLACK, round(size * 0.6)), (255, 255, 255))
    img.save(os.path.join(DIR, path))


def share_card():
    """1200x630 og:image -- what a link renders as when shared."""
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 9], fill=RED)                      # accent rule

    d.text((80, 168), "WREXHAM", font=font(BLACK, 96), fill=TX)
    l, t, r, b = d.textbbox((80, 168), "WREXHAM", font=font(BLACK, 96))
    d.text((r + 6, 168), ".", font=font(BLACK, 96), fill=RED)
    d.text((80, 278), "TRACKER", font=font(BLACK, 96), fill=TX)

    d.text((80, 420), "EFL Championship 2026/27", font=font(BOLD, 34), fill=RED)
    d.text((80, 476), "Fixtures  ·  Table  ·  Chances  ·  Squad  ·  News  ·  Podcasts",
           font=font(BOLD, 27), fill=MUT)
    d.text((80, 530), "danpune.github.io/wrexham-tracker", font=font(BOLD, 24), fill=MUT)
    img.save(os.path.join(DIR, "preview.jpg"), quality=88)


if __name__ == "__main__":
    icon(192, "icon-192.png")
    icon(512, "icon-512.png")
    icon(180, "apple-touch-icon.png")
    share_card()
    print("wrote icon-192 icon-512 apple-touch-icon preview.jpg")
