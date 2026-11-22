"""Terminal plot demo: a real seismogram drawn inside Termux with tplot (run in geo).

Fetches the M6.8 Banda Sea earthquake (2026-11-21) recorded at IU.CTAO,
Australia (22°), filters it and shows it with plt.show() — which tplot turns
into coloured text characters via chafa.
"""
import tplot  # noqa: F401  (must come before pyplot use: makes plt.show() draw in the terminal)
import matplotlib.pyplot as plt
from obspy import UTCDateTime
from obspy.clients.fdsn import Client

t0 = UTCDateTime("2026-11-21T09:42:07")
st = Client("IRIS").get_waveforms("IU", "CTAO", "00", "BHZ", t0, t0 + 20 * 60)
st.detrend("demean").filter("bandpass", freqmin=0.02, freqmax=1.0)
tr = st[0]
print(f"{tr.id}  {tr.stats.starttime.strftime('%Y-%m-%d %H:%M:%S')}  {tr.stats.npts} samples @ {tr.stats.sampling_rate:g} Hz")

fig, ax = plt.subplots(figsize=(10, 4), facecolor="#0d1117")
ax.set_facecolor("#0d1117")
ax.plot(tr.times() / 60, tr.data, color="#4fc3f7", lw=1.0)
ax.set_title("M6.8 Banda Sea · IU.CTAO (22°) · BHZ 0.02–1 Hz", color="white")
ax.set_xlabel("minutes after origin", color="white")
ax.tick_params(colors="white")
for s in ax.spines.values():
    s.set_color("#30363d")
plt.show(size="82x24")
