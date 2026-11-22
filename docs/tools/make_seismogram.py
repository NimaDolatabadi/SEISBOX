"""Animated seismogram GIF of a real earthquake (run in geo).

    python docs/tools/make_seismogram.py [OUTPUT.gif]

Downloads vertical-component records of the M6.8 Banda Sea earthquake
(2026-11-21 09:42:07 UTC, 116 km deep) from EarthScope (IRIS) at stations
at increasing distance, marks the predicted P and S arrivals (TauP, iasp91)
and animates them being drawn, like `seislive` does in real time.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from obspy import UTCDateTime
from obspy.clients.fdsn import Client
from obspy.geodetics import locations2degrees
from obspy.taup import TauPyModel

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/media/seismogram.gif"
ORIGIN = UTCDateTime("2026-11-21T09:42:07")
EV_LAT, EV_LON, EV_DEP = -7.62, 127.39, 116.0
TITLE = "M6.8 Banda Sea · 2026-11-21 09:42 UTC · depth 116 km"
STATIONS = ["IU.CTAO.00.BHZ", "IU.MAJO.00.BHZ", "II.KAPI.00.BHZ", "IU.KONO.00.BHZ", "IU.ANMO.00.BHZ"]
WINDOW = 40 * 60          # seconds after origin
BG, FG, TRACE, P_COL, S_COL = "#0d1117", "#c9d1d9", "#4fc3f7", "#f78166", "#d2a8ff"

client = Client("IRIS")
model = TauPyModel("iasp91")
inv = client.get_stations(network=",".join({s.split(".")[0] for s in STATIONS}),
                          station=",".join(s.split(".")[1] for s in STATIONS),
                          location="00", channel="BHZ", starttime=ORIGIN, level="channel")
traces = []
for sid in STATIONS:
    net, sta, loc, cha = sid.split(".")
    try:
        st = client.get_waveforms(net, sta, loc, cha, ORIGIN - 60, ORIGIN + WINDOW)
    except Exception as e:
        print("skip", sid, e.__class__.__name__); continue
    st.merge(fill_value=0)
    tr = st[0]
    tr.detrend("demean"); tr.taper(0.02)
    tr.filter("bandpass", freqmin=0.02, freqmax=1.0, corners=4, zerophase=True)
    c = inv.get_coordinates(tr.id, ORIGIN)
    dist = locations2degrees(EV_LAT, EV_LON, c["latitude"], c["longitude"])
    arr = {}
    for a in model.get_travel_times(EV_DEP, dist, ["p", "P", "Pdiff", "s", "S"]):
        arr.setdefault(a.name, a.time)          # first arrival of each phase
    # near a deep quake the first arrival is the upgoing p/s; far away P/S or Pdiff
    p = min((arr[k] for k in ("p", "P", "Pdiff") if k in arr), default=None)
    s = min((arr[k] for k in ("s", "S") if k in arr), default=None)
    t = tr.times() + (tr.stats.starttime - ORIGIN)
    traces.append((sid, dist, t, tr.data / (np.abs(tr.data).max() or 1), p, s))
    print(f"{sid:16} {dist:6.1f}°  P {p/60 if p else float('nan'):.1f} min")
traces.sort(key=lambda x: x[1])

fig, axes = plt.subplots(len(traces), 1, figsize=(8, 1.15 * len(traces) + 0.9), sharex=True,
                         facecolor=BG)
fig.subplots_adjust(left=0.13, right=0.98, top=0.9, bottom=0.1, hspace=0.12)
fig.suptitle(TITLE, color=FG, fontsize=12, fontweight="bold")
lines = []
for ax, (sid, dist, t, y, p, s) in zip(axes, traces):
    ax.set_facecolor(BG)
    ax.set_xlim(0, WINDOW / 60); ax.set_ylim(-1.1, 1.1)
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#30363d")
    ax.tick_params(colors=FG, labelsize=8)
    ax.text(-0.01, 0.5, f"{sid.rsplit('.', 2)[0]}\n{dist:.0f}°", transform=ax.transAxes,
            ha="right", va="center", color=FG, fontsize=8, family="monospace")
    if p: ax.axvline(p / 60, color=P_COL, lw=0.9, ls="--")
    if s: ax.axvline(s / 60, color=S_COL, lw=0.9, ls="--")
    (ln,) = ax.plot([], [], color=TRACE, lw=0.6)
    lines.append(ln)
axes[0].text(0.995, 1.06, "P", color=P_COL, transform=axes[0].transAxes, ha="right", fontsize=9,
             fontweight="bold")
axes[0].text(0.975, 1.06, "S", color=S_COL, transform=axes[0].transAxes, ha="right", fontsize=9,
             fontweight="bold")
axes[-1].set_xlabel("minutes after origin  ·  BHZ, 0.02–1 Hz  ·  data: EarthScope (IRIS)",
                    color=FG, fontsize=9)

FRAMES = 60
def draw(i):
    tmax = WINDOW * (i + 1) / FRAMES
    for ln, (_, _, t, y, _, _) in zip(lines, traces):
        m = t <= tmax
        step = max(1, m.sum() // 4000)      # thin the points: keeps GIF small
        ln.set_data(t[m][::step] / 60, y[m][::step])
    return lines

anim = FuncAnimation(fig, draw, frames=FRAMES + 12, blit=False)   # +12: hold last frame
anim.save(OUT, writer=PillowWriter(fps=12), dpi=80, savefig_kwargs={"facecolor": BG})
print("wrote", OUT)
