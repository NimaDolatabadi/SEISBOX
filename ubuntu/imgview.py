#!/root/geo/bin/python
"""imgview — show image files in an X11 window (used by `seisview` via Termux:X11).

    imgview image.png [more.png ...]

Toolbar: zoom (magnifier), pan (arrows), home = reset.  Keys: q close,
right/left (or n/p) next/previous image.
"""
import os
import sys

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

files = [f for f in sys.argv[1:] if os.path.isfile(f)]
if not files:
    sys.exit("imgview: no image files given")

plt.rcParams["toolbar"] = "toolbar2"
fig = plt.figure(facecolor="white")
ax = fig.add_axes([0, 0, 1, 1])
state = {"i": 0}


def draw():
    f = files[state["i"]]
    ax.clear()
    ax.imshow(mpimg.imread(f), interpolation="antialiased")
    ax.set_axis_off()
    title = os.path.basename(f) + (f"  ({state['i'] + 1}/{len(files)})" if len(files) > 1 else "")
    fig.canvas.manager.set_window_title(title)
    fig.canvas.draw_idle()


def key(ev):
    if ev.key in ("right", "n", " ") and len(files) > 1:
        state["i"] = (state["i"] + 1) % len(files); draw()
    elif ev.key in ("left", "p", "backspace") and len(files) > 1:
        state["i"] = (state["i"] - 1) % len(files); draw()


fig.canvas.mpl_connect("key_press_event", key)
draw()
try:                                    # fill the Termux:X11 screen (no window manager there)
    win = fig.canvas.manager.window
    win.update_idletasks()
    win.geometry(f"{win.winfo_screenwidth()}x{win.winfo_screenheight()}+0+0")
except Exception:
    pass
if os.environ.get("IMGVIEW_TIMEOUT"):   # for automated tests
    fig.canvas.new_timer(interval=int(float(os.environ["IMGVIEW_TIMEOUT"]) * 1000),
                         callbacks=[(plt.close, [fig], {})]).start()
plt.show()
