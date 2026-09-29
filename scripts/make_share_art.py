#!/usr/bin/env python3
"""Social share card for the SimScan page.

Measured 2026-09-30: the live page at caseone115.github.io/simscan/ carries no
`og:image` and no `<img>` at all, so every share of it (a Discord post, a Reddit
comment, a forum answer) renders a grey placeholder instead of the tool, and the
Gumroad listing falls back to Gumroad's generic card. This draws the card in the
page's own palette so the share and the page look like one thing.

    python3 scripts/make_share_art.py
"""
import pathlib
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "og"
FONTS = pathlib.Path("/usr/share/fonts/truetype/dejavu")

BG, PANEL, LINE = (15, 20, 32), (23, 30, 46), (35, 44, 64)
INK, MUTED, DIM = (232, 236, 244), (139, 152, 173), (93, 106, 128)
ACCENT, BAD, WARN, GOOD = (79, 140, 255), (239, 68, 68), (245, 158, 11), (127, 209, 166)

W, H = 1200, 630
PAD = 64


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def card(path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=(int(BG[0] + 12 * (1 - t)), int(BG[1] + 13 * (1 - t)),
                     int(BG[2] + 16 * (1 - t))))
    d.rectangle([0, 0, W, 6], fill=ACCENT)

    f_badge = font("DejaVuSans-Bold.ttf", 20)
    f_title = font("DejaVuSans-Bold.ttf", 52)
    f_sub = font("DejaVuSans.ttf", 25)
    f_chip = font("DejaVuSans.ttf", 20)
    f_price = font("DejaVuSans-Bold.ttf", 29)
    f_mono = font("DejaVuSansMono.ttf", 20)

    # badge
    label = "WINDOWS  ·  OFFLINE  ·  NO ACCOUNT"
    w = d.textlength(label, font=f_badge)
    d.rounded_rectangle([PAD, 50, PAD + w + 36, 50 + 40], radius=20, fill=ACCENT)
    d.text((PAD + 18, 71), label, font=f_badge, fill=BG, anchor="lm")

    y = 122
    for line in ["Something in your Sims 4", "Mods folder is silently", "doing nothing."]:
        d.text((PAD, y), line, font=f_title, fill=INK)
        y += 62
    y += 8
    for line in ["SimScan reads the folder offline and reports the script mods that",
                 "will never load, duplicates under different names, and which mod",
                 "actually wins a conflict."]:
        d.text((PAD, y), line, font=f_sub, fill=MUTED)
        y += 36

    # explicit rows: two chips per row, so nothing can wrap where it was not
    # planned to (the first version packed four into one row and ran 83px over).
    chip_rows = [[("script mod too deep", WARN),
                  ("duplicate by content hash", WARN)],
                 [("conflict winner named", GOOD),
                  ("no account, no network", GOOD)]]
    cy = 372
    for row in chip_rows:
        x = PAD
        for text, colour in row:
            cw = d.textlength(text, font=f_chip) + 48
            assert x + cw <= W - PAD, f"chip overflows the card: {text!r}"
            d.rounded_rectangle([x, cy, x + cw, cy + 40], radius=20,
                                outline=LINE, width=2)
            d.ellipse([x + 16, cy + 16, x + 25, cy + 25], fill=colour)
            d.text((x + 34, cy + 21), text, font=f_chip, fill=MUTED, anchor="lm")
            x += cw + 14
        cy += 50

    d.text((PAD, H - 106), "US$14  ·  Windows installer + portable build  ·  source is MIT", font=f_price, fill=ACCENT)
    d.text((PAD, H - 58), "caseone115.github.io/simscan", font=f_mono, fill=DIM)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG", optimize=True)
    return path


def assert_not_clipped(path):
    """Structural proof the card is not cut off: the outer margins hold no ink."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    worst = 0
    for x0, y0, x1, y1, name in ((0, 12, 40, h - 12, "left"),
                                 (w - 40, 12, w, h - 12, "right"),
                                 (0, h - 14, w, h, "bottom")):
        for x in range(x0, x1, 3):
            for y in range(y0, y1, 3):
                r, g, b = px[x, y]
                worst = max(worst, max(r, g, b))
    assert worst < 90, (f"{name} margin of {path.name} holds bright pixels "
                        f"(max={worst}) - text is running off the card")
    return worst


if __name__ == "__main__":
    p = card(OUT / "simscan-share-1200x630.png")
    worst = assert_not_clipped(p)
    print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024}KB  "
          f"{Image.open(p).size}  margins clean (max={worst})")
