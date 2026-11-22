"""Render term_capture.py JSON into a PNG (one frame) or animated GIF (run in geo).

    python docs/tools/term_render.py IN.json OUT.png|OUT.gif [--title "Termux — Events"] [--frame N]

Draws a dark terminal window with DejaVu Sans Mono, keeping the app's colours.
"""
import argparse
import json

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
SIZE = 16
BG, FG = (13, 17, 23), (201, 209, 217)
CHROME = (22, 27, 34)
NAMED = {  # GitHub-dark-like ANSI palette
    "black": (72, 79, 88), "red": (255, 123, 114), "green": (63, 185, 80),
    "brown": (210, 153, 34), "yellow": (210, 153, 34), "blue": (88, 166, 255),
    "magenta": (188, 140, 255), "cyan": (57, 197, 207), "white": (177, 186, 196),
    "brightblack": (110, 118, 129), "brightred": (255, 161, 152), "brightgreen": (86, 211, 100),
    "brightbrown": (227, 179, 65), "brightyellow": (227, 179, 65), "brightblue": (121, 192, 255),
    "brightmagenta": (210, 168, 255), "brightcyan": (86, 212, 221), "brightwhite": (240, 246, 252),
}


def color(c, default):
    if c == "default":
        return default
    if c in NAMED:
        return NAMED[c]
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return default


BRAILLE_DOTS = [(0x01, 0, 0), (0x02, 0, 1), (0x04, 0, 2), (0x40, 0, 3),
                (0x08, 1, 0), (0x10, 1, 1), (0x20, 1, 2), (0x80, 1, 3)]


def draw_braille(d, ch, px, py, cw, chh, fill):
    """DejaVu Sans Mono has no braille glyphs: draw the 2x4 dots like a terminal font would."""
    bits = ord(ch) - 0x2800
    r = max(1.2, cw * 0.16)
    for bit, cx, cy in BRAILLE_DOTS:
        if bits & bit:
            x = px + cw * (0.3 + 0.4 * cx)
            y = py + chh * (0.14 + 0.24 * cy)
            d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def render(frame, cols, rows, title, fonts):
    reg, bold = fonts
    cw = round(reg.getlength("M"))
    ch = round(SIZE * 1.32)
    pad, bar = 18, 34
    W, H = cols * cw + 2 * pad, rows * ch + 2 * pad + bar
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, bar], fill=CHROME)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 20, bar / 2 - 6, 26 + i * 20, bar / 2 + 6], fill=c)
    tw = bold.getlength(title)
    d.text(((W - tw) / 2, bar / 2 - SIZE * 0.6), title, font=bold, fill=(139, 148, 158))
    for y, row in enumerate(frame):
        for x, (txt, fg, bg, isbold, rev) in enumerate(row):
            f, b = color(fg, FG), color(bg, BG)
            if isbold and fg in NAMED and "bright" + fg in NAMED:
                f = NAMED["bright" + fg]
            if rev:
                f, b = b, f
            px, py = pad + x * cw, bar + pad + y * ch
            if b != BG:
                d.rectangle([px, py, px + cw - 1, py + ch - 1], fill=b)
            if txt and 0x2800 < ord(txt[0]) <= 0x28FF:
                draw_braille(d, txt[0], px, py, cw, ch, f)
            elif txt.strip():
                d.text((px, py + (ch - SIZE) / 2 - 1), txt, font=bold if isbold else reg, fill=f)
    return img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("inp"); p.add_argument("out")
    p.add_argument("--title", default="Termux")
    p.add_argument("--frame", type=int, default=-1, help="frame for PNG output (default last)")
    a = p.parse_args()
    data = json.load(open(a.inp))
    fonts = (ImageFont.truetype(FONT_DIR + "DejaVuSansMono.ttf", SIZE),
             ImageFont.truetype(FONT_DIR + "DejaVuSansMono-Bold.ttf", SIZE))
    frames = data["frames"]
    if a.out.endswith(".png"):
        render(frames[a.frame]["cells"], data["cols"], data["rows"], a.title, fonts).save(a.out, optimize=True)
    else:
        imgs = [render(f["cells"], data["cols"], data["rows"], a.title, fonts) for f in frames]
        pal = [im.quantize(colors=64, method=Image.Quantize.MEDIANCUT) for im in imgs]
        pal[0].save(a.out, save_all=True, append_images=pal[1:], loop=0, optimize=True,
                    duration=[f["ms"] for f in frames], disposal=1)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
