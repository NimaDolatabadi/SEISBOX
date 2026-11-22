#!/usr/bin/env python
"""Live seismic waveform viewer: EarthScope (IRIS) SeedLink -> matplotlib window.

Usage: seis_live.py [NET.STA.LOC.CHA ...] [--minutes N] [--filter FMIN FMAX] [--fps F]
Example: seis_live.py IU.ANMO.00.BHZ IU.COLA.00.BHZ --minutes 10 --filter 0.5 5

Why it is fast:
  * samples go into a fixed numpy ring buffer per channel (no Stream merge/trim)
  * the bandpass is causal and stateful: each packet is filtered once, on arrival
  * each frame reduces the visible data to one min/max pair per screen pixel
    column and paints it straight into the canvas pixel buffer with numpy
    (matplotlib's path stroking was the bottleneck: ~20-100 ms per trace)
  * the axes never change, so frames are blitted; a full matplotlib redraw
    happens only when the amplitude scale needs to change
"""
import argparse
import threading
import time
import warnings

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox
from obspy import UTCDateTime
from obspy.clients.seedlink.easyseedlink import EasySeedLinkClient
from scipy.signal import butter, sosfilt, sosfilt_zi

SERVER = "rtserve.earthscope.org:18000"

p = argparse.ArgumentParser()
p.add_argument("ids", nargs="*", default=["IU.ANMO.00.BHZ"])
p.add_argument("--minutes", type=float, default=10)
p.add_argument("--filter", nargs=2, type=float, metavar=("FMIN", "FMAX"))
p.add_argument("--fps", type=float, default=25)
p.add_argument("--color", default="#4fc3f7")
p.add_argument("--no-backfill", action="store_true",
               help="don't request the last N minutes on connect")
args = p.parse_args()

window = args.minutes * 60
status = {"msg": f"connecting to {SERVER} ..."}
warnings.filterwarnings("ignore", "All-NaN slice")
warnings.filterwarnings("ignore", "Mean of empty slice")


class Channel:
    """Ring buffer of (filtered) samples; sample n is at time t0 + n/sr."""

    def __init__(self):
        self.lock = threading.Lock()
        self.sr = None

    def _setup(self, tr):
        self.sr = tr.stats.sampling_rate
        self.t0 = tr.stats.starttime.timestamp
        self.cap = int((window + 120) * self.sr)
        self.data = np.full(self.cap, np.nan)
        self.end = 0          # absolute index of the next sample to write
        self.zi = None        # filter state; None = restart on next sample
        if args.filter:
            hi = min(args.filter[1], 0.45 * self.sr)
            self.sos = butter(4, [args.filter[0], hi], "bandpass", fs=self.sr, output="sos")

    def add(self, tr):
        with self.lock:
            if self.sr is None or tr.stats.sampling_rate != self.sr:
                self._setup(tr)
            x = tr.data.astype(float)
            n0 = int(round((tr.stats.starttime.timestamp - self.t0) * self.sr))
            if n0 < self.end:                    # overlap / duplicate packet
                x = x[self.end - n0:]
                n0 = self.end
            if not len(x):
                return
            if n0 > self.end:                    # gap: blank it, restart filter
                if n0 - self.end >= self.cap:
                    self.data[:] = np.nan
                else:
                    self.data[np.arange(self.end, n0) % self.cap] = np.nan
                self.zi = None
            if args.filter:
                if self.zi is None:
                    self.zi = sosfilt_zi(self.sos) * x[0]
                x, self.zi = sosfilt(self.sos, x, zi=self.zi)
            if len(x) > self.cap:
                n0 += len(x) - self.cap
                x = x[-self.cap:]
            self.data[np.arange(n0, n0 + len(x)) % self.cap] = x
            self.end = n0 + len(x)

    def envelope(self, now, ncols):
        """Return (t, min, max) for the visible window in ~ncols buckets.

        Buckets are aligned to absolute sample numbers so the picture does not
        shimmer as it scrolls."""
        with self.lock:
            if self.sr is None or self.end == 0:
                return None
            sr, end = self.sr, self.end
            k = max(1, int(window * sr / ncols))
            lo = (now - window - self.t0) * sr
            start = max(int(lo // k) * k, -(-(end - self.cap) // k) * k, 0)
            if start >= end:
                return None
            y = self.data[np.arange(start, end) % self.cap]
            rel = self.t0 - now
        if k == 1:
            return rel + np.arange(start, end) / sr, y, y
        pad = -len(y) % k
        if pad:
            y = np.concatenate([y, np.full(pad, np.nan)])
        y = y.reshape(-1, k)
        mn, mx = np.nanmin(y, axis=1), np.nanmax(y, axis=1)
        xc = rel + (start + k * (np.arange(len(mn)) + 0.5)) / sr
        return xc, mn, mx


chans = {sid: Channel() for sid in args.ids}


class Feed(EasySeedLinkClient):
    def on_data(self, trace):
        ch = chans.get(trace.id)
        if ch is not None:
            ch.add(trace)
        status["msg"] = f"last packet {trace.stats.endtime.strftime('%H:%M:%S')} UTC"

    def on_seedlink_error(self):
        status["msg"] = "SeedLink error - reconnecting"


def run_feed():
    while True:
        try:
            c = Feed(SERVER, autoconnect=False)
            # ObsPy bug: connect() crashes when conn.timeout is None, but a set
            # timeout also ends collect() after that many seconds. So set it
            # only for the connect, then clear it for the live stream.
            c.conn.timeout = 60
            c.connect()
            c.conn.timeout = None
            if not args.no_backfill:  # ask the server to replay the window
                c.conn.begin_time = UTCDateTime() - window
            for sid in args.ids:
                net, sta, loc, cha = sid.split(".")
                c.select_stream(net, sta, f"{loc}{cha}")
            c.run()
        except Exception as e:  # keep the viewer alive on network drops
            status["msg"] = f"reconnecting ({e})"
            time.sleep(5)


threading.Thread(target=run_feed, daemon=True).start()

# ---------------------------------------------------------------- display
plt.style.use("dark_background")
fig, axes = plt.subplots(len(args.ids), 1, sharex=True, squeeze=False)
axes = axes[:, 0]
for ax, sid in zip(axes, args.ids):
    ax.set_ylabel(sid, fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_ylim(-1, 1)
axes[-1].set_xlim(-window, 0)
axes[-1].set_xlabel("seconds before now")
fig.tight_layout(rect=(0, 0, 1, 0.96))
title = fig.text(0.5, 0.985, "", ha="center", va="top", fontsize=9, animated=True)
rgba = np.array(matplotlib.colors.to_rgba_array(args.color)[0] * 255, dtype=np.uint8)

try:  # fill the X11 screen (there is no window manager to maximize it)
    w = fig.canvas.manager.window
    w.geometry(f"{w.winfo_screenwidth()}x{w.winfo_screenheight()}+0+0")
except Exception:
    pass

canvas = fig.canvas
bg = None
title_cache = {"text": None}


def on_draw(_):
    """After any full redraw (resize, rescale) re-capture the static background."""
    global bg
    bg = canvas.copy_from_bbox(fig.bbox)
    title_cache["text"] = None


canvas.mpl_connect("draw_event", on_draw)


def needs_rescale(ax, mn, mx):
    lo, hi = np.nanmin(mn), np.nanmax(mx)
    if not np.isfinite(lo) or hi <= lo:
        return False
    cur_lo, cur_hi = ax.get_ylim()
    if lo < cur_lo or hi > cur_hi or (hi - lo) < 0.35 * (cur_hi - cur_lo):
        pad = 0.1 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)
        return True
    return False


def paint(buf, ax, t, mn, mx):
    """Rasterize one trace: a vertical pixel run per column from min to max."""
    H = buf.shape[0]
    bb = ax.bbox
    c0, c1 = int(np.ceil(bb.x0)) + 1, int(bb.x1)
    r0, r1 = int(np.ceil(H - bb.y1)) + 1, int(H - bb.y0)
    w, h = c1 - c0, r1 - r0
    if w <= 0 or h <= 0:
        return
    col = ((t + window) / window * bb.width + bb.x0 - c0).astype(int)
    ok = (col >= 0) & (col < w) & np.isfinite(mn)
    col, mn, mx = col[ok], mn[ok], mx[ok]
    lo = np.full(w, np.inf)
    hi = np.full(w, -np.inf)
    np.minimum.at(lo, col, mn)
    np.maximum.at(hi, col, mx)
    valid = np.isfinite(lo)
    # join each column to its left neighbour so steep slopes stay connected
    plo = np.r_[np.inf, np.where(valid[:-1], lo[:-1], np.inf)]
    phi = np.r_[-np.inf, np.where(valid[:-1], hi[:-1], -np.inf)]
    lo, hi = np.minimum(lo, phi), np.maximum(hi, plo)
    ylo, yhi = ax.get_ylim()
    sc = h / (yhi - ylo)
    cols = np.flatnonzero(valid)
    top = np.clip((yhi - hi[cols]) * sc, 0, h - 1).astype(np.intp)
    bot = np.clip((yhi - lo[cols]) * sc, 0, h - 1).astype(np.intp)
    bot = np.minimum(np.maximum(bot, top + 1), h - 1)   # at least 2 px thick
    n = bot - top + 1                    # write only the covered pixels
    rows = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n - top, n)
    buf[r0 + rows, c0 + np.repeat(cols, n)] = rgba


def frame():
    if bg is None:
        return
    now = time.time()
    ncols = max(100, int(axes[0].bbox.width))
    traces = []
    rescale = False
    for ax, sid in zip(axes, args.ids):
        env = chans[sid].envelope(now, ncols)
        if env is None:
            continue
        t, mn, mx = env
        if not args.filter:
            m = np.nanmean(mn)
            mn, mx = mn - m, mx - m
        rescale |= needs_rescale(ax, mn, mx)
        traces.append((ax, t, mn, mx))
    if rescale:
        canvas.draw()          # repaint axes/ticks; traces follow next frame
        return
    canvas.restore_region(bg)
    buf = np.asarray(canvas.buffer_rgba())
    for tr in traces:
        paint(buf, *tr)
    strip = Bbox([[0, axes[0].bbox.y1], [fig.bbox.x1, fig.bbox.y1]])
    text = (f"{SERVER}   {UTCDateTime(now).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            f"   {status['msg']}")
    if text != title_cache["text"]:      # text rendering is slow: once a second
        title.set_text(text)
        fig.draw_artist(title)
        title_cache["text"] = text
        canvas.blit(strip)
    for ax in axes:
        canvas.blit(ax.bbox)


timer = canvas.new_timer(interval=int(1000 / args.fps))
timer.add_callback(frame)
timer.start()
plt.show()
