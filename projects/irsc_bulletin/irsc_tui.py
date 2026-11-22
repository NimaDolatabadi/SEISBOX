#!/usr/bin/env python3
"""
TUI for downloading the IRSC bulletin (via ISC, agency TEH).

Keys:  Up/Down or Tab  move between fields      Enter  next field / press button
       type            edit field               Backspace  delete,  Ctrl-U  clear field
       F5 / Ctrl-R     run download             Esc / Ctrl-Q  quit
"""
import curses
import os
import sys

from obspy import UTCDateTime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from irsc_bulletin import DEFAULT_OUTDIR, fetch, report, save_catalog  # noqa: E402

now = UTCDateTime()
ago = now - 30 * 86400

# (key, label, default, kind)  kind: date | time | float | optfloat | text
FIELDS = [
    ("sdate", "Start date (YYYY-MM-DD)", ago.strftime("%Y-%m-%d"), "date"),
    ("stime", "Start time (HH:MM:SS)", "00:00:00", "time"),
    ("edate", "End date   (YYYY-MM-DD)", now.strftime("%Y-%m-%d"), "date"),
    ("etime", "End time   (HH:MM:SS)", now.strftime("%H:%M:%S"), "time"),
    ("minlat", "Min latitude", "24", "float"),
    ("maxlat", "Max latitude", "40", "float"),
    ("minlon", "Min longitude", "44", "float"),
    ("maxlon", "Max longitude", "64", "float"),
    ("minmag", "Min magnitude (ML, blank=any)", "", "optfloat"),
    ("maxmag", "Max magnitude (ML, blank=any)", "", "optfloat"),
    ("out", "Output file name", "irsc_bulletin", "text"),
    ("outdir", "Output folder", DEFAULT_OUTDIR, "text"),
]
BUTTONS = ["[ Run ]", "[ Quit ]"]


def validate(v):
    """Return (params dict, None) or (None, error message)."""
    try:
        start = UTCDateTime(f"{v['sdate']}T{v['stime']}")
    except Exception:
        return None, "Invalid start date/time"
    try:
        end = UTCDateTime(f"{v['edate']}T{v['etime']}")
    except Exception:
        return None, "Invalid end date/time"
    if end <= start:
        return None, "End must be after start"
    p = {"start": start, "end": end}
    for k, label, _, kind in FIELDS:
        if kind in ("float", "optfloat"):
            s = v[k].strip()
            if not s and kind == "optfloat":
                p[k] = None
                continue
            try:
                p[k] = float(s)
            except ValueError:
                return None, f"{label.split('(')[0].strip()}: not a number"
    if not -90 <= p["minlat"] < p["maxlat"] <= 90:
        return None, "Latitude range must satisfy -90 <= min < max <= 90"
    if not -180 <= p["minlon"] < p["maxlon"] <= 180:
        return None, "Longitude range must satisfy -180 <= min < max <= 180"
    if p["minmag"] is not None and p["maxmag"] is not None and p["minmag"] > p["maxmag"]:
        return None, "Min magnitude is larger than max magnitude"
    p["out"] = v["out"].strip() or "irsc_bulletin"
    p["outdir"] = v["outdir"].strip() or DEFAULT_OUTDIR
    return p, None


def form(stdscr, values, message=""):
    curses.curs_set(1)
    curses.use_default_colors()
    try:
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
    except curses.error:
        pass
    n_items = len(FIELDS) + len(BUTTONS)
    cur = 0
    msg, msg_color = message, 3
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        lw = min(31, max(12, w // 2))          # label column width
        fw = max(6, w - lw - 3)                # field width
        stdscr.addnstr(0, 0, " IRSC bulletin downloader (ISC / TEH) ".center(w - 1, "="),
                       w - 1, curses.color_pair(1) | curses.A_BOLD)
        for i, (k, label, _, _) in enumerate(FIELDS):
            y = 2 + i
            if y >= h - 3:
                break
            attr = curses.A_REVERSE if i == cur else curses.A_NORMAL
            stdscr.addnstr(y, 1, label, lw - 1)
            stdscr.addnstr(y, lw + 1, values[k][-fw:].ljust(fw), fw, attr)
        by = min(3 + len(FIELDS), h - 3)
        x = 1
        for j, b in enumerate(BUTTONS):
            attr = curses.A_REVERSE | curses.A_BOLD if cur == len(FIELDS) + j else curses.A_BOLD
            stdscr.addnstr(by, x, b, w - x - 1, attr)
            x += len(b) + 2
        stdscr.addnstr(h - 2, 0, msg[: w - 1], w - 1, curses.color_pair(msg_color))
        stdscr.addnstr(h - 1, 0, "Up/Down move  Enter next  F5 run  Ctrl-U clear  Esc quit"[: w - 1],
                       w - 1, curses.A_DIM)
        if cur < len(FIELDS):
            k = FIELDS[cur][0]
            y = 2 + cur
            if y < h - 3:
                stdscr.move(y, lw + 1 + min(len(values[k]), fw - 1))
        else:
            curses.curs_set(0)
        stdscr.refresh()

        ch = stdscr.get_wch()
        curses.curs_set(1)
        msg = ""
        if ch in (curses.KEY_UP, curses.KEY_BTAB):
            cur = (cur - 1) % n_items
        elif ch in (curses.KEY_DOWN, "\t"):
            cur = (cur + 1) % n_items
        elif ch in (curses.KEY_LEFT, curses.KEY_RIGHT) and cur >= len(FIELDS):
            cur = len(FIELDS) + (cur - len(FIELDS) + 1) % len(BUTTONS)
        elif ch in ("\x1b", "\x11"):                      # Esc, Ctrl-Q
            return None
        elif ch in (curses.KEY_F5, "\x12") or (ch in ("\n", "\r", curses.KEY_ENTER)
                                               and cur == len(FIELDS)):
            params, err = validate(values)
            if err:
                msg, msg_color = err, 2
                continue
            return params
        elif ch in ("\n", "\r", curses.KEY_ENTER):
            if cur == len(FIELDS) + 1:                    # Quit button
                return None
            cur = (cur + 1) % n_items
        elif cur < len(FIELDS):
            k = FIELDS[cur][0]
            if ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                values[k] = values[k][:-1]
            elif ch == "\x15":                            # Ctrl-U
                values[k] = ""
            elif isinstance(ch, str) and ch.isprintable():
                values[k] += ch


def run(params):
    area = dict(minlatitude=params["minlat"], maxlatitude=params["maxlat"],
                minlongitude=params["minlon"], maxlongitude=params["maxlon"])
    print("\nDownloading... (Ctrl-C = stop and save)", flush=True)
    try:
        cat, failed, interrupted = fetch(params["start"], params["end"], area,
                                         params["minmag"], params["maxmag"])
    except Exception as e:
        print(f"\nERROR: {e.__class__.__name__}: {e}")
        return f"Download failed: {e.__class__.__name__}"
    if not len(cat):
        print("\nNo events found - nothing saved.")
        return "No events found"
    try:
        path = save_catalog(cat, params["outdir"], params["out"])
    except OSError as e:
        print(f"\nERROR saving file: {e}")
        return f"Could not save: {e}"
    report(cat, path, failed, interrupted)
    note = " (partial)" if interrupted or failed else ""
    return f"Saved {len(cat)} events{note} -> {path}"


def main():
    values = {k: d for k, _, d, _ in FIELDS}
    os.environ.setdefault("ESCDELAY", "25")
    message = "Edit the fields, then press F5 or select [ Run ]"
    while True:
        params = curses.wrapper(form, values, message)
        if params is None:
            print("Bye.")
            return
        message = run(params)
        try:
            input("\nPress Enter to return to the form (Ctrl-C to quit) ...")
        except (KeyboardInterrupt, EOFError):
            print()
            return


if __name__ == "__main__":
    main()
