"""Terminal line plot with plotext: the same seismogram as quake_tplot.py, drawn
natively in the terminal (braille dots for the line, real characters for labels).
"""
import plotext as plt
from obspy import UTCDateTime
from obspy.clients.fdsn import Client

t0 = UTCDateTime("2026-11-21T09:42:07")
st = Client("IRIS").get_waveforms("IU", "CTAO", "00", "BHZ", t0, t0 + 20 * 60)
st.detrend("demean").filter("bandpass", freqmin=0.02, freqmax=1.0)
tr = st[0].decimate(4, no_filter=True)          # 10 Hz is plenty for a 120-column plot
print(f"{tr.id}  {tr.stats.starttime.strftime('%Y-%m-%d %H:%M:%S')}  M6.8 Banda Sea, 22°")

plt.plot((tr.times() / 60).tolist(), (tr.data / 1000).tolist(), marker="braille", color="cyan")
plt.title("M6.8 Banda Sea  ·  IU.CTAO (22°)  ·  BHZ 0.02-1 Hz")
plt.xlabel("minutes after origin")
plt.ylabel("counts / 1000")
plt.theme("dark")
plt.plotsize(118, 34)
plt.show()
