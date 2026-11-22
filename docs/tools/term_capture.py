"""Record a scripted terminal session as screen snapshots (JSON) for term_render.py.

Runs a command in a pseudo-terminal, sends keys on a schedule and stores what
the screen looked like (characters + colours) at chosen moments. Needs `pyte`
(pip install pyte). Runs on Termux's python.

    python docs/tools/term_capture.py events    docs/media/events.json
    python docs/tools/term_capture.py welcome   docs/media/welcome.json
    python docs/tools/term_capture.py tplot     docs/media/tplot.json
"""
import fcntl
import json
import os
import pty
import select
import struct
import sys
import termios
import time

import pyte

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def typed(text, ms=110):
    """Type text one key at a time, snapshot after each key."""
    return [(ch.encode(), 0.12, ms) for ch in text]


SESSIONS = {
    # name: (argv, cols, rows, steps)   step = (keys, wait_s, snapshot_ms or None)
    "events": (["Events"], 62, 24, [
        (b"", 4.0, 1800),
        (b"\x1b[B", 0.3, 250), (b"\x1b[B", 0.3, 250), (b"\x1b[B", 0.3, 600),
        (b"c", 0.5, 700), *typed("japan,chile"), (b"\n", 1.2, 2200),
        (b"\n", 0.8, 4000),                       # details popup
        (b"x", 0.5, None),
        (b"c", 0.4, None), (b"\n", 0.8, 1000),    # clear region filter
        (b"m", 0.4, 500), *typed("5.5"), (b"\n", 1.2, 2000),
        (b"l", 1.5, 1300), (b"", 1.0, 1000), (b"", 1.0, 1000), (b"", 1.0, 1600),
        (b"?", 0.8, 3200),
        (b"x", 0.3, None), (b"q", 0.5, None),
    ]),
    "plotext": (["bash", "-c",
                 "printf '\\033[32m~/projects $\\033[0m python quake_plotext.py\\n'; "
                 f"proot-distro login ubuntu --bind {REPO}:/opt/seisbox -- "
                 "env TERM=xterm-256color PYTHONWARNINGS=ignore /root/geo/bin/python "
                 "/opt/seisbox/docs/tools/quake_plotext.py"], 120, 40, [(b"", 45.0, 1000)]),
    "welcome": (["bash", "-c", f"cat {REPO}/termux/welcome.txt"], 50, 36, [(b"", 1.0, 1000)]),
    "tplot": (["bash", "-c",
               "printf '\\033[32m~/projects $\\033[0m python quake_tplot.py\\n'; "
               f"proot-distro login ubuntu --bind {REPO}:/opt/seisbox -- "
               "env TERM=xterm-256color PYTHONWARNINGS=ignore ${TPLOT_SYMBOLS:+TPLOT_SYMBOLS=$TPLOT_SYMBOLS} ${TPLOT_ARGS:+TPLOT_ARGS=\"$TPLOT_ARGS\"} /root/geo/bin/python "
               "/opt/seisbox/docs/tools/quake_tplot.py"], 120, 40, [(b"", 45.0, 1000)]),
}


def snapshot(scr):
    rows = []
    for y in range(scr.lines):
        line = scr.buffer[y]
        rows.append([[line[x].data, line[x].fg, line[x].bg, line[x].bold, line[x].reverse]
                     for x in range(scr.columns)])
    return rows


def run(name):
    argv, cols, rows, steps = SESSIONS[name]
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(TERM="xterm-256color", COLUMNS=str(cols), LINES=str(rows),
                          NCURSES_NO_UTF8_ACS="1")  # box lines as Unicode, which pyte renders
        os.environ.pop("COLORTERM", None)
        os.execvp(argv[0], argv)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    scr = pyte.Screen(cols, rows)
    stream = pyte.ByteStream(scr)
    frames = []

    def pump(t, until_exit=False):
        end = time.time() + t
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    return
                if not data:
                    return
                stream.feed(data)

    for keys, wait, ms in steps:
        if keys:
            os.write(fd, keys)
        pump(wait)
        if ms:
            frames.append({"ms": ms, "cells": snapshot(scr)})
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pass
    os.waitpid(pid, 0)
    return {"cols": cols, "rows": rows, "title": name, "frames": frames}


if __name__ == "__main__":
    name, out = sys.argv[1], sys.argv[2]
    data = run(name)
    with open(out, "w") as f:
        json.dump(data, f)
    print(f"{name}: {len(data['frames'])} frames -> {out}")
