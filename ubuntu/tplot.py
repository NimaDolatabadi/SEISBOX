"""Terminal matplotlib: `import tplot` makes plt.show() draw in the terminal via chafa.

    import tplot, matplotlib.pyplot as plt
    plt.plot(x, y); plt.show()               # fills the terminal
    plt.show(size="100x30")                  # columns x rows

Default look: braille dots only, foreground colour only (braille = 2x4 dots per
character, so lines stay sharp; Termux shows braille via Android's font fallback).
Override with environment variables, e.g. the older filled-block look:
    export TPLOT_SYMBOLS=block+border+space TPLOT_ARGS=" "
"""
import os, shutil, subprocess, tempfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SYMBOLS = os.environ.get("TPLOT_SYMBOLS", "braille+space")
EXTRA = os.environ.get("TPLOT_ARGS", "--fg-only").split()   # extra chafa options


def tshow(fig=None, size=None, *a, **k):
    if size is None:
        c, r = shutil.get_terminal_size((100, 40))
        size = f"{c}x{max(r - 2, 10)}"
    fd, f = tempfile.mkstemp(suffix=".png"); os.close(fd)
    try:
        (fig or plt.gcf()).savefig(f, dpi=150, bbox_inches="tight")
        subprocess.run(["chafa", "--symbols", SYMBOLS, "--work", "9", *EXTRA, "-s", size, f])
    finally:
        os.remove(f)
    plt.close(fig or plt.gcf())

plt.show = tshow
