"""Terminal matplotlib: `import tplot` makes plt.show() draw in the terminal via chafa."""
import os, shutil, subprocess, tempfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def tshow(fig=None, size=None, *a, **k):
    if size is None:
        c, r = shutil.get_terminal_size((100, 40))
        size = f"{c}x{max(r - 2, 10)}"
    fd, f = tempfile.mkstemp(suffix=".png"); os.close(fd)
    try:
        (fig or plt.gcf()).savefig(f, dpi=120, bbox_inches="tight")
        subprocess.run(["chafa", "--symbols", "all", "-s", size, f])
    finally:
        os.remove(f)
    plt.close(fig or plt.gcf())

plt.show = tshow
