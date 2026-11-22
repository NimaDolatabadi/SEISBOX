"""PyGMT world map of the last 30 days of M4.5+ earthquakes (run in geo).

    python docs/tools/make_map.py [OUTPUT.png]

Catalogue: USGS FDSN event service via ObsPy. Symbol size = magnitude,
colour = depth. Shows that GMT/PyGMT work inside the Ubuntu container.
"""
import sys

import numpy as np
import pandas as pd
import pygmt
from obspy import UTCDateTime
from obspy.clients.fdsn import Client

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/media/quakes-map.png"
end = UTCDateTime()
cat = Client("USGS").get_events(starttime=end - 30 * 86400, endtime=end, minmagnitude=4.5)
rows = []
for ev in cat:
    o, m = ev.preferred_origin() or ev.origins[0], ev.preferred_magnitude() or ev.magnitudes[0]
    rows.append((o.longitude, o.latitude, (o.depth or 0) / 1000, m.mag))
df = pd.DataFrame(rows, columns=["lon", "lat", "depth", "mag"]).sort_values("mag")
print(len(df), "events")

fig = pygmt.Figure()
pygmt.config(MAP_FRAME_TYPE="plain", FONT_TITLE="14p,Helvetica-Bold", FONT_ANNOT_PRIMARY="8p")
fig.basemap(region="d", projection="N150/18c",
            frame=["af", f"+tEarthquakes M4.5+ · last 30 days ({len(df)}) · USGS"])
fig.coast(land="#e6e1d6", water="#dbe9f4", shorelines="0.2p,#8a8a8a", area_thresh=10000)
pygmt.makecpt(cmap="plasma", series=[0, 600], reverse=True)
fig.plot(x=df.lon, y=df.lat, size=0.07 * 2 ** (df.mag - 4.5), fill=df.depth, cmap=True,
         style="cc", pen="0.2p,black", transparency=15)
fig.colorbar(frame=["xa100+lDepth (km)"], position="JBC+w8c/0.3c+h+o0/0.8c")
fig.savefig(OUT, dpi=150)
print("wrote", OUT)
