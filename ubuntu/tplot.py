"""Terminal matplotlib: `import tplot` makes plt.show() draw in the terminal via chafa.

    import tplot, matplotlib.pyplot as plt
    plt.plot(x, y); plt.show()               # fills the terminal
    plt.show(size="100x30")                  # columns x rows

Default look: braille dots only, foreground colour only (braille = 2x4 dots per
character, so lines stay sharp; Termux shows braille via Android's font fallback).
Light figures (matplotlib's default white background) are colour-inverted before
drawing, otherwise every white pixel would become a dot; dark figures are drawn as is.
Override with environment variables, e.g. the older filled-block look:
    export TPLOT_SYMBOLS=block+border+space TPLOT_ARGS=" "
"""
import os, shutil, subprocess, tempfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SYMBOLS = os.environ.get("TPLOT_SYMBOLS", "braille+space")
EXTRA = os.environ.get("TPLOT_ARGS", "--fg-only").split()   # extra chafa options


def _dark_background(path):
    """Invert mostly-light images so the background is black (= not drawn)."""
    try:
        from PIL import Image, ImageOps, ImageStat
        im = Image.open(path).convert("RGB")
        if sum(ImageStat.Stat(im.convert("L")).mean) > 128:
            ImageOps.invert(im).save(path)
    except Exception:
        pass


def tshow(fig=None, size=None, *a, **k):
    if size is None:
        c, r = shutil.get_terminal_size((100, 40))
        size = f"{c}x{max(r - 2, 10)}"
    fd, f = tempfile.mkstemp(suffix=".png"); os.close(fd)
    try:
        (fig or plt.gcf()).savefig(f, dpi=150, bbox_inches="tight")
        _dark_background(f)
        subprocess.run(["chafa", "--symbols", SYMBOLS, "--work", "9", "--bg", "000000", *EXTRA,
                        "-s", size, f])
    finally:
        os.remove(f)
    plt.close(fig or plt.gcf())

plt.show = tshow
