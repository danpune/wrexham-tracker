#!/usr/bin/env python3
"""Generate the PWA icons and the social share card.

Run by hand when the look changes -- not in CI, since the output is static and
committing identical binaries on every cron run would be noise.

    python3 build_assets.py

Deliberately typographic: the club crest is copyrighted, so the marks here use a
plain wordmark. Crests shown in the app are hotlinked from ESPN at runtime,
which is a different thing from bundling them.
"""
import io, json, os
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

DIR = os.path.dirname(os.path.abspath(__file__))
RED, BG, TX, MUT = (224, 36, 47), (13, 15, 18), (233, 236, 241), (139, 146, 158)
def _font_path(*candidates):
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[-1]

# macOS locally, DejaVu on the CI runner — resolved at import so the same script
# works in both places.
BOLD = _font_path("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
BLACK = _font_path("/System/Library/Fonts/Supplemental/Arial Black.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


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
    out, buf = os.path.join(DIR, path), io.BytesIO()
    img.save(buf, "PNG")
    if not os.path.exists(out) or open(out, "rb").read() != buf.getvalue():
        open(out, "wb").write(buf.getvalue())


def share_card():
    """1200x630 og:image — what a WhatsApp/iMessage link preview renders.

    Driven by data.json so a shared link says something current ("WON 3-0 AT
    MILLWALL / NEXT: SWANSEA") rather than listing tab names. Written only when
    the pixels actually change, so a cron run does not commit an identical JPEG
    every time — the same churn the ics DTSTAMP fix removed.
    """
    W, H = 1200, 630
    try:
        d = json.load(open(os.path.join(DIR, "data.json")))
    except (OSError, ValueError):
        d = {}

    img = Image.new("RGB", (W, H), (200, 16, 46))
    px = img.load()
    for y in range(H):                                  # the site's header gradient
        for x in range(0, W, 4):
            t = (x / W) * 0.35 + (y / H) * 0.65
            c = (int(224 - 83 * t), int(30 - 20 * t), int(45 - 15 * t))
            for dx in range(4):
                if x + dx < W:
                    px[x + dx, y] = c
    d_ = ImageDraw.Draw(img)

    d_.text((72, 52), "WREXHAM", font=font(BLACK, 74), fill=(255, 255, 255))
    l, t, r, b = d_.textbbox((72, 52), "WREXHAM", font=font(BLACK, 74))
    d_.text((r + 4, 52), ".", font=font(BLACK, 74), fill=(255, 209, 102))
    d_.text((78, 146), "EFL CHAMPIONSHIP 2026/27", font=font(BOLD, 26),
            fill=(255, 255, 255, 220))

    last = [m for m in d.get("matches", []) if m.get("completed")]
    nxt = next((m for m in d.get("matches", [])
                if not m.get("completed") and not m.get("awaitingResult")), None)
    proj = d.get("projection") or {}

    if last:
        m = last[-1]
        verb = {"W": "WON", "L": "LOST", "D": "DREW"}.get(m.get("result"), "")
        where = "AT" if not m.get("home") else "V"
        line = f"{verb} {m['us']}-{m['them']} {where} {m['opponent'].upper()}"
        d_.text((72, 252), line[:34], font=font(BLACK, 62), fill=(255, 255, 255))

    if nxt:
        when = datetime.fromisoformat(nxt["date"]).astimezone(
            ZoneInfo("Europe/London")).strftime("%a %-d %b, %H:%M")
        d_.text((72, 372), "NEXT", font=font(BOLD, 24), fill=(255, 209, 102))
        d_.text((72, 408), f"{nxt['opponent'].upper()} "
                           f"({'H' if nxt.get('home') else 'A'}) · {when} UK",
                font=font(BOLD, 34), fill=(255, 255, 255))

    if proj:
        d_.text((72, 496), f"{proj.get('rank','')}TH IN THE TABLE · "
                           f"{proj.get('points','')} PTS · {proj.get('played','')} PLAYED",
                font=font(BOLD, 26), fill=(255, 255, 255, 220))

    d_.rectangle([0, H - 58, W, H], fill=(20, 10, 14))
    d_.text((72, H - 44), "danpune.github.io/wrexham-tracker",
            font=font(BOLD, 24), fill=(255, 255, 255))

    out = os.path.join(DIR, "preview.jpg")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=86)
    new = buf.getvalue()
    if not os.path.exists(out) or open(out, "rb").read() != new:
        open(out, "wb").write(new)
        print(f"preview.jpg updated ({len(new)//1024} KB)")
    else:
        print("preview.jpg unchanged")


if __name__ == "__main__":
    icon(192, "icon-192.png")
    icon(512, "icon-512.png")
    icon(180, "apple-touch-icon.png")
    share_card()
    print("wrote icon-192 icon-512 apple-touch-icon preview.jpg")
