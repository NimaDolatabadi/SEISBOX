#!/root/geo/bin/python
"""quakemt — focal mechanism / moment tensor of an earthquake (runs in geo).

Layer 1  published solutions (seconds):
         USGS (W-phase Mww, body-wave Mwb, centroid Mwc, regional Mwr, first-motion)
         and GFZ GEOFON moment tensors for the event.
Layer 2  own fast inversion (--invert, ~2-5 min):
         downloads long-period 3-component waveforms (LH, 1 sps) from global
         networks via the IRIS federator (all FDSN data centres), computes Green's
         functions with IRIS Syngine (AxiSEM, PREM), and solves a deviatoric
         moment tensor by least squares with a grid search over centroid depth and
         time shift. Long-period (40-100 s) full waveforms: Mw >= ~5.5 at 25-90 deg.

Usage
  quakemt --time 2026-11-21T09:42:07 --lat -7.62 --lon 127.39 --depth 116 --mag 6.8
  quakemt ... --invert                 also run the waveform inversion
  quakemt ... --invert --stations 30 --depths 90,110,130
Output: text summary + beachballs in the terminal, and files in a folder named
after the quake (or --name), under $SEISBOX_PROJECTS/mt/:
  published_mechanisms.png  published_summary.txt  published.json      (layer 1 run)
  inversion_mechanism.png   inversion_waveform_fits.png
  inversion_summary.txt     inversion.json                             (--invert run)
and one line per run in $SEISBOX_PROJECTS/mt/index.csv.
"""
import argparse
import io
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings("ignore")
import numpy as np  # noqa: E402
from obspy import UTCDateTime, read_events  # noqa: E402
from obspy.geodetics import gps2dist_azimuth  # noqa: E402
from obspy.imaging.beachball import MomentTensor, aux_plane, mt2axes, mt2plane  # noqa: E402

UA = {"User-Agent": "SEISBOX-quakemt/1.0"}
NETWORKS = "IU,II,G,GE,IC,CU,GT,MN"     # global broadband networks with long-period LH data
MODEL = "prem_a_10s"                    # Syngine/AxiSEM database (18000 s long)
DT = 2.0                                # common sampling interval for the inversion (s)
PAD = 600.0                             # seconds of padding before origin
C = {"ok": "\033[32m", "warn": "\033[33m", "bad": "\033[31m", "h": "\033[1;36m", "dim": "\033[2m",
     "b": "\033[1m", "0": "\033[0m"}


TEE = None          # set in main(): copies terminal output into the summary file


def say(msg, kind="h"):
    print(f"{C[kind]}{msg}{C['0']}", flush=True)


def detail(msg):
    """Only for the saved summary file, not the terminal."""
    if TEE is not None:
        TEE.buf.append(msg + "\n")


def progress(msg):
    """One self-overwriting status line on the terminal (not saved)."""
    out = TEE.stream if TEE is not None else sys.stdout
    out.write(f"\r\033[K{C['dim']}  {msg}{C['0']}" if msg else "\r\033[K")
    out.flush()


def show(text):
    """Print lines; lines starting with '~' go to the summary file only."""
    for line in text.splitlines():
        if line.startswith("~"):
            detail(line[1:])
        else:
            print(line)


def http(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ===================================================================== MT maths
def fault_type(p_pl, t_pl, b_pl):
    """Classify by principal-axis plunges (after Frohlich 1992)."""
    if t_pl >= 50:
        return "thrust (reverse)"
    if p_pl >= 60:
        return "normal"
    if b_pl >= 60:
        return "strike-slip"
    if t_pl >= p_pl:
        return "oblique thrust" if b_pl < t_pl else "oblique strike-slip / thrust"
    return "oblique normal" if b_pl < p_pl else "oblique strike-slip / normal"


def slip_sense(rake):
    r = (rake + 180) % 360 - 180
    if -30 <= r <= 30:
        return "left-lateral"
    if r >= 150 or r <= -150:
        return "right-lateral"
    if 60 <= r <= 120:
        return "reverse"
    if -120 <= r <= -60:
        return "normal"
    return ("reverse" if r > 0 else "normal") + (" + left-lateral" if abs(r) < 90 else " + right-lateral")


def mt_props(m):
    """m = [Mrr, Mtt, Mpp, Mrt, Mrp, Mtp] in N·m  ->  source parameters."""
    m = np.asarray(m, float)
    M = np.array([[m[0], m[3], m[4]], [m[3], m[1], m[5]], [m[4], m[5], m[2]]])
    iso = np.trace(M) / 3
    ev = np.linalg.eigvalsh(M - iso * np.eye(3))
    M0 = math.sqrt(np.sum(M ** 2) / 2)                  # Silver & Jordan (1982)
    Mw = 2 / 3 * (math.log10(M0) - 9.1)                 # Hanks & Kanamori, N·m
    o = np.argsort(np.abs(ev))
    eps = -ev[o[0]] / abs(ev[o[2]]) if ev[o[2]] else 0
    dc = max(0.0, 100 * (1 - 2 * abs(eps)))
    expo = int(math.floor(math.log10(M0)))
    mt = MomentTensor(list(m / 10 ** expo), expo)
    np1 = mt2plane(mt)
    s2, d2, r2 = aux_plane(np1.strike, np1.dip, np1.rake)
    t, b, p = mt2axes(mt)
    return {
        "m": [float(x) for x in m], "M0": M0, "Mw": Mw, "dc": dc, "clvd": 100 - dc,
        "np1": [np1.strike % 360, np1.dip, np1.rake], "np2": [s2 % 360, d2, r2],
        "T": [t.strike % 360, t.dip], "P": [p.strike % 360, p.dip], "B": [b.strike % 360, b.dip],
        "type": fault_type(p.dip, t.dip, b.dip),
    }


def kagan_angle(m1, m2):
    """Minimum rotation angle (deg) between two double-couple mechanisms."""
    def axes(m):
        M = np.array([[m[0], m[3], m[4]], [m[3], m[1], m[5]], [m[4], m[5], m[2]]])
        w, v = np.linalg.eigh(M)
        v = v[:, [2, 1, 0]]                             # T, B, P
        v[:, 2] = np.cross(v[:, 0], v[:, 1])            # right-handed frame
        return v
    a, b = axes(m1), axes(m2)
    best = 180.0
    for s in ([1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]):
        R = a @ np.diag(s) @ b.T
        ang = math.degrees(math.acos(max(-1, min(1, (np.trace(R) - 1) / 2))))
        best = min(best, ang)
    return best


# ===================================================================== layer 1
def usgs_solutions(ev):
    q = dict(format="geojson", starttime=(ev["time"] - 120).isoformat(),
             endtime=(ev["time"] + 120).isoformat(), latitude=ev["lat"], longitude=ev["lon"],
             maxradius=3, minmagnitude=max(0, ev["mag"] - 1.2))
    feats = json.loads(http("https://earthquake.usgs.gov/fdsnws/event/1/query?" +
                            urllib.parse.urlencode(q)))["features"]
    if not feats:
        return [], None
    f = min(feats, key=lambda f: abs(f["properties"]["time"] / 1000 - ev["time"].timestamp))
    det = json.loads(http(f["properties"]["detail"]))
    out = []
    for typ in ("moment-tensor", "focal-mechanism"):
        for p in det["properties"]["products"].get(typ, []):
            pr = p["properties"]
            label = pr.get("derived-magnitude-type") or pr.get("beachball-type") or typ
            sol = {"agency": f"USGS {label}", "source": p["source"],
                   "depth": float(pr["derived-depth"]) if pr.get("derived-depth") else None,
                   "preferred": p.get("preferredWeight", 0)}
            if pr.get("tensor-mrr"):
                sol.update(mt_props([float(pr[f"tensor-{k}"]) for k in
                                     ("mrr", "mtt", "mpp", "mrt", "mrp", "mtp")]))
            elif pr.get("nodal-plane-1-strike"):
                sol["np1"] = [float(pr[f"nodal-plane-1-{k}"]) for k in ("strike", "dip", "rake")]
                sol["np2"] = [float(pr[f"nodal-plane-2-{k}"]) for k in ("strike", "dip", "rake")]
            else:
                continue
            out.append(sol)
    out.sort(key=lambda s: -s["preferred"])
    return out, f["id"]


def gfz_solutions(ev):
    q = dict(format="text", starttime=(ev["time"] - 120).isoformat(),
             endtime=(ev["time"] + 120).isoformat(), latitude=ev["lat"], longitude=ev["lon"],
             maxradius=3)
    txt = http("https://geofon.gfz-potsdam.de/fdsnws/event/1/query?" +
               urllib.parse.urlencode(q)).decode()
    ids = [ln.split("|")[0] for ln in txt.splitlines() if ln and not ln.startswith("#")]
    out = []
    for eid in ids[:1]:
        xml = http("https://geofon.gfz-potsdam.de/fdsnws/event/1/query?" +
                   urllib.parse.urlencode({"eventid": eid, "includefocalmechanism": "true"}))
        cat = read_events(io.BytesIO(xml))
        for fm in cat[0].focal_mechanisms:
            mt = fm.moment_tensor
            if mt and mt.tensor:
                t = mt.tensor
                sol = {"agency": "GFZ MT", "source": eid, "preferred": 1}
                sol.update(mt_props([t.m_rr, t.m_tt, t.m_pp, t.m_rt, t.m_rp, t.m_tp]))
                if mt.variance_reduction:
                    sol["vr"] = float(mt.variance_reduction) * (100 if mt.variance_reduction <= 1 else 1)
                org = next((o for o in cat[0].origins if o.resource_id == mt.derived_origin_id), None)
                sol["depth"] = org.depth / 1000 if org and org.depth else None
                out.append(sol)
    return out


def published(ev):
    sols, usgs_id = [], None
    with ThreadPoolExecutor(2) as ex:
        fu, fg = ex.submit(usgs_solutions, ev), ex.submit(gfz_solutions, ev)
        try:
            s, usgs_id = fu.result()
            sols += s
        except Exception as e:
            say(f"  USGS: not available ({e.__class__.__name__})", "warn")
        try:
            sols += fg.result()
        except Exception as e:
            say(f"  GFZ: not available ({e.__class__.__name__})", "warn")
    return sols, usgs_id


# ===================================================================== layer 2
def band_for(mag):
    """Period band (s) for long-period full-waveform inversion."""
    # Tested on M6.8 Banda Sea (2026-11-21): 50-100 s gave VR 65 % and a mechanism 8-9 deg
    # from USGS/GFZ; 40-100 s only VR 52 % (more 3-D Earth effects at shorter periods).
    if mag < 6.0:
        return 40.0, 90.0
    return 50.0, 100.0          # Syngine DBs are accurate up to ~100 s periods


def select_stations(ev, nmax, dmin, dmax):
    from obspy.clients.fdsn import RoutingClient
    t0 = ev["time"]
    inv = RoutingClient("iris-federator").get_stations(
        network=NETWORKS, channel="LH?", starttime=t0, endtime=t0 + 3600,
        latitude=ev["lat"], longitude=ev["lon"], minradius=dmin, maxradius=dmax, level="channel")
    cands = {}
    for net in inv:
        for sta in net:
            locs = {}
            for ch in sta:
                locs.setdefault(ch.location_code, set()).add(ch.code[-1])
            best = None
            for loc in ("00", "10", "", "20", "60", "01"):
                comps = locs.get(loc, set())
                if "Z" in comps and ({"N", "E"} <= comps or {"1", "2"} <= comps):
                    best = loc
                    break
            if best is None:
                continue
            d, az, baz = gps2dist_azimuth(ev["lat"], ev["lon"], sta.latitude, sta.longitude)
            cands[f"{net.code}.{sta.code}"] = dict(net=net.code, sta=sta.code, loc=best,
                                                   lat=sta.latitude, lon=sta.longitude,
                                                   dist=d / 111194.9, az=az, baz=baz)
    # spread in azimuth: one station per sector first (prefer ~60 deg distance), then fill
    nb = max(8, nmax)
    sectors = {}
    for c in sorted(cands.values(), key=lambda c: abs(c["dist"] - 60)):
        sectors.setdefault(int(c["az"] // (360 / nb)), []).append(c)
    chosen = []
    while len(chosen) < nmax and any(sectors.values()):
        for k in sorted(sectors):
            if sectors[k] and len(chosen) < nmax:
                chosen.append(sectors[k].pop(0))
    return chosen, len(cands)


def to_grid(tr, t0, n):
    """Resample a trace onto the common time grid t0-PAD + i*DT (zeros outside)."""
    tg = -PAD + np.arange(n) * DT
    tt = tr.times() + (tr.stats.starttime - t0)
    return np.interp(tg, tt, tr.data.astype(float), left=0.0, right=0.0)


def filt(x, band):
    from obspy.signal.filter import bandpass
    from scipy.signal.windows import tukey
    x = x * tukey(len(x), 0.05)
    return bandpass(x, 1 / band[1], 1 / band[0], 1 / DT, corners=4, zerophase=True)


def download_data(ev, stations, t_end, band, n):
    from obspy.clients.fdsn import RoutingClient
    t0 = ev["time"]
    rc = RoutingClient("iris-federator")
    bulk = [(s["net"], s["sta"], s["loc"], "LH?", t0 - PAD - 300, t0 + t_end + 300) for s in stations]
    st = rc.get_waveforms_bulk(bulk)
    inv = rc.get_stations_bulk(bulk, level="response")
    data = {}
    for s in stations:
        sub = st.select(network=s["net"], station=s["sta"], location=s["loc"]).copy()
        try:
            gaps = sub.get_gaps()
            if sum(gp[6] for gp in gaps) > 30:            # more than 30 s missing in total
                raise ValueError("data gaps")
            sub.merge(method=1, fill_value="interpolate")   # bridge short gaps
            if len(sub) < 3:
                raise ValueError("missing components")
            t1 = max(tr.stats.starttime for tr in sub)
            t2 = min(tr.stats.endtime for tr in sub)
            if t2 - t1 < t_end + PAD:
                raise ValueError("record too short")
            sub.trim(t1, t2)                                # common span (needed for rotation)
            sub.detrend("linear")
            sub.taper(0.05)
            sub.remove_response(inventory=inv, output="DISP", pre_filt=(0.002, 0.004, 0.1, 0.2))
            sub.rotate("->ZNE", inventory=inv)
            sub.rotate("NE->RT", back_azimuth=s["baz"])
            data[f"{s['net']}.{s['sta']}"] = {c: filt(to_grid(sub.select(component=c)[0], t0, n), band)
                                               for c in "ZRT"}
        except Exception as e:
            detail(f"    skip {s['net']}.{s['sta']}: {str(e)[:70] or e.__class__.__name__}")
    return data


ELEMENTS = ("Mrr", "Mtt", "Mpp", "Mrt", "Mrp", "Mtp")
UNIT = 1e20


def greens(ev, stations, depth_km, t_end, band, n):
    """Synthetics for the six unit moment-tensor elements at one depth (Syngine bulk)."""
    from obspy.clients.syngine import Client as SynClient
    sc = SynClient()
    bulk = [{"latitude": s["lat"], "longitude": s["lon"], "networkcode": s["net"],
             "stationcode": s["sta"]} for s in stations]

    def one(i):
        mt = [0.0] * 6
        mt[i] = UNIT
        for attempt in range(3):
            try:
                return sc.get_waveforms_bulk(
                    model=MODEL, bulk=bulk, sourcelatitude=ev["lat"], sourcelongitude=ev["lon"],
                    sourcedepthinmeters=depth_km * 1000, sourcemomenttensor=mt,
                    origintime=ev["time"], starttime=ev["time"], endtime=ev["time"] + t_end + 200,
                    components="ZRT", units="displacement", dt=DT)
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(3)

    with ThreadPoolExecutor(3) as ex:
        streams = list(ex.map(one, range(6)))
    g = {}
    for i, st in enumerate(streams):
        for tr in st:
            key = f"{tr.stats.network}.{tr.stats.station}"
            g.setdefault(key, {}).setdefault(tr.stats.channel[-1], [None] * 6)[i] = \
                filt(to_grid(tr, ev["time"], n), band)
    return g


def windows(ev, stations, n):
    from obspy.taup import TauPyModel
    model = TauPyModel("iasp91")
    w = {}
    for s in stations:
        arr = model.get_travel_times(max(ev["depth"], 0), s["dist"], ["P", "Pdiff", "p"])
        tp = min(a.time for a in arr) if arr else s["dist"] * 111.19 / 8
        t1 = s["dist"] * 111.19 / 3.4 + 250            # past the fundamental Rayleigh wave
        i0, i1 = int((tp - 60 + PAD) / DT), min(n - 1, int((t1 + PAD) / DT))
        w[f"{s['net']}.{s['sta']}"] = (i0, i1, int((tp - 60 - 400 + PAD) / DT))
    return w


def lag_group(c):
    return "T" if c == "T" else "ZR"        # Rayleigh (Z, R) and Love (T) get separate lags


def build_system(keys, data, g, win, shift_s, lags=None):
    """Weighted linear system d = G a for a deviatoric MT (a = Mrr, Mtt, Mrt, Mrp, Mtp).
    shift_s: common centroid time shift; lags: extra per-station/wave-type shifts that
    absorb travel-time errors of the 1-D Earth model (CAP-style)."""
    rows_d, rows_G, idx = [], [], []
    for key, c in keys:
        k = int(round((shift_s + (lags or {}).get((key, lag_group(c)), 0.0)) / DT))
        i0, i1, _ = win[key]
        d = data[key][c][i0:i1]
        G6 = np.array([gi[i0 - k:i1 - k] for gi in g[key][c]]).T / UNIT
        G5 = np.column_stack([G6[:, 0] - G6[:, 2], G6[:, 1] - G6[:, 2], G6[:, 3], G6[:, 4], G6[:, 5]])
        w = 1.0 / (np.abs(d).max() or 1.0)                # every trace counts equally
        idx.append((key, c, 0, len(d)))
        rows_d.append(d * w)
        rows_G.append(G5 * w)
    return np.concatenate(rows_d), np.vstack(rows_G), idx


def lsq(keys, data, g, win, sh, lags):
    d, G, idx = build_system(keys, data, g, win, sh, lags)
    a, *_ = np.linalg.lstsq(G, d, rcond=None)
    res = d - G @ a
    return {"vr": 100 * (1 - res @ res / (d @ d)), "m": [a[0], a[1], -a[0] - a[1], a[2], a[3], a[4]],
            "a": a, "shift": sh, "d": d, "syn": G @ a, "idx": idx, "lags": dict(lags)}


def best_lags(keys, data, g, win, sol, maxlag):
    """Per station and wave group: lag (s) that best aligns synthetic with data."""
    m = np.array(sol["m"])
    groups = {}
    for key, c in keys:
        groups.setdefault((key, lag_group(c)), []).append(c)
    out = {}
    nl = int(maxlag / DT)
    for (key, grp), comps in groups.items():
        i0, i1, _ = win[key]
        k0 = int(round(sol["shift"] / DT))
        best, bl = -np.inf, 0
        for L in range(-nl, nl + 1):
            num = den_s = 0.0
            for c in comps:
                d = data[key][c][i0:i1]
                syn = sum(m[j] * g[key][c][j][i0 - k0 - L:i1 - k0 - L] for j in range(6)) / UNIT
                num += d @ syn
                den_s += syn @ syn
            cc = num / math.sqrt(den_s or 1)
            if cc > best:
                best, bl = cc, L
        out[(key, grp)] = bl * DT
    return out


def solve(keys, data, g, win, shifts, maxlag=30.0, iters=4):
    # 1) common centroid shift, no station lags
    best = max((lsq(keys, data, g, win, sh, {}) for sh in shifts), key=lambda r: r["vr"])
    # 2) iterate: align each station's Rayleigh/Love waves to the current model, re-solve
    for _ in range(iters):
        lags = best_lags(keys, data, g, win, best, maxlag)
        new = lsq(keys, data, g, win, best["shift"], lags)
        if new["vr"] <= best["vr"] + 0.2:
            break
        best = new
    return best


def trace_vr(sol):
    out = {}
    pos = 0
    for key, c, _, n in sol["idx"]:
        d, s = sol["d"][pos:pos + n], sol["syn"][pos:pos + n]
        out[(key, c)] = 100 * (1 - np.sum((d - s) ** 2) / (np.sum(d ** 2) or 1))
        pos += n
    return out


def invert(ev, args, outdir):
    band = tuple(float(x) for x in args.band.split(",")) if args.band else band_for(ev["mag"])
    say("\n▶ Own inversion (about 1-3 min)")
    detail(f"  waveform inversion: periods {band[0]:.0f}-{band[1]:.0f} s, model {MODEL}")
    t_start = time.time()
    dmin = args.dmin if args.dmin is not None else (12.0 if ev["mag"] < 6.0 else 25.0)
    dmax = args.dmax if args.dmax is not None else (60.0 if ev["mag"] < 6.0 else 90.0)
    # ask for ~40 % more stations: some always lack a component or have gaps
    stations, ncand = select_stations(ev, int(args.stations * 1.4), dmin, dmax)
    if len(stations) < 6:
        raise RuntimeError(f"only {len(stations)} usable stations at {dmin:.0f}-{dmax:.0f}°")
    gap = azimuthal_gap([s["az"] for s in stations])
    detail(f"  stations: {len(stations)} requested of {ncand} available at {dmin:.0f}-{dmax:.0f}° "
           f"(azimuthal gap {gap:.0f}°)")
    t_end = max(s["dist"] for s in stations) * 111.19 / 3.4 + 400
    n = int((t_end + PAD) / DT)
    progress(f"downloading waveforms from {len(stations)} stations…")
    data = download_data(ev, stations, t_end, band, n)
    stations = [s for s in stations if f"{s['net']}.{s['sta']}" in data]
    detail(f"  usable 3-component records: {len(stations)}")
    if len(stations) < 6:
        raise RuntimeError("too few usable records")
    win = windows(ev, stations, n)

    # signal-to-noise check on the long-period band
    keys = []
    for s in stations:
        key = f"{s['net']}.{s['sta']}"
        i0, i1, n0 = win[key]
        for c in "ZRT":
            x = data[key][c]
            noise = np.sqrt(np.mean(x[max(0, n0):i0] ** 2)) if i0 - max(0, n0) > 20 else 0
            sig = np.sqrt(np.mean(x[i0:i1] ** 2))
            if sig > 0 and (noise == 0 or sig / noise > 3):
                keys.append((key, c))

    nsta_clear = len({k for k, _ in keys})
    detail(f"  traces with clear signal (SNR > 3): {len(keys)} from {nsta_clear} stations")
    if len(keys) < 8 or nsta_clear < 4:
        raise RuntimeError("too few records with a clear long-period signal "
                           f"({len(keys)} traces). The quake may be too small, or masked by a "
                           "larger quake's surface waves shortly before it.")
    if args.depths:
        depths = [float(x) for x in args.depths.split(",")]
    else:
        d0 = ev["depth"]
        step = 10 if d0 < 70 else 20
        depths = sorted({max(5.0, d0 + k * step) for k in (-2, -1, 0, 1, 2)})
    shifts = np.arange(-10, 31, 2.0)
    results = []
    gcache = {}
    step = (depths[1] - depths[0]) if len(depths) > 1 else 10.0
    queue = list(depths)
    while queue:
        dep = queue.pop(0)
        progress(f"Green's functions + inversion at {dep:.0f} km depth "
                 f"({len(results) + 1}/{len(results) + len(queue) + 1})…")
        gcache[dep] = greens(ev, stations, dep, t_end, band, n)
        use = [k for k in keys if k[0] in gcache[dep] and k[1] in gcache[dep][k[0]]
               and all(x is not None for x in gcache[dep][k[0]][k[1]])]
        sol = solve(use, data, gcache[dep], win, shifts, maxlag=args.maxlag)
        # quality control: drop traces the model cannot fit at all, solve again
        tv = trace_vr(sol)
        good = [k for k in use if tv[k] > -20]
        if len(good) >= 8 and len(good) < len(use):
            sol = solve(good, data, gcache[dep], win, shifts, maxlag=args.maxlag)
            use = good
        sol.update(depth=dep, keys=use)
        results.append(sol)
        lg = np.abs(list(sol["lags"].values())) if sol["lags"] else np.zeros(1)
        detail(f"    depth {dep:5.0f} km   VR {sol['vr']:5.1f} %   shift {sol['shift']:+.0f} s   "
               f"station lags median {np.median(lg):.0f} s   traces {len(use)}")
        if not queue and len(results) < 9 and not args.depths:   # best at an edge -> extend
            done = sorted(r["depth"] for r in results)
            top = max(results, key=lambda r: r["vr"])["depth"]
            if top == done[-1] and top + step <= 700:
                queue.append(top + step)
            elif top == done[0] and top - step >= 5:
                queue.append(top - step)
    best = max(results, key=lambda r: r["vr"])
    mw_best = mt_props(best["m"])["Mw"]
    if best["vr"] < 20 or abs(mw_best - ev["mag"]) > 1.0:
        raise RuntimeError(f"no reliable solution (best VR {best['vr']:.0f} %, Mw {mw_best:.1f} vs "
                           f"catalogue M{ev['mag']:.1f}); data do not constrain the mechanism")
    near = [r["depth"] for r in results if r["vr"] >= best["vr"] - 2.0]   # depths fitting ~as well
    props = mt_props(best["m"])
    props.update(agency="SEISBOX inversion", depth=best["depth"], vr=best["vr"],
                 shift=best["shift"], depth_range=(min(near), max(near)), ntraces=len(best["keys"]), nsta=len({k for k, _ in best["keys"]}),
                 gap=gap, band=band, model=MODEL, runtime=time.time() - t_start,
                 depth_curve=[(r["depth"], r["vr"]) for r in results])
    progress("")
    plot_fits(ev, best, stations, win, outdir, band)
    return props


def azimuthal_gap(az):
    a = sorted(x % 360 for x in az)
    return max((b - a_) for a_, b in zip(a, a[1:] + [a[0] + 360])) if a else 360


# ===================================================================== output
def fmt_sol(s):
    name = "Own inversion (SEISBOX)" if s["agency"].startswith("SEISBOX") else s["agency"]
    lines = [f"{C['b']}{name}{C['0']}"]
    if "Mw" in s:
        lines.append(f"  Mw {s['Mw']:.2f}   M0 {s['M0']:.2e} N·m   depth "
                     f"{s['depth']:.0f} km" if s.get("depth") is not None else
                     f"  Mw {s['Mw']:.2f}   M0 {s['M0']:.2e} N·m")
    elif s.get("depth") is not None:
        lines.append(f"  depth {s['depth']:.0f} km")
    lines.append(f"  NP1 strike {s['np1'][0]:5.0f}° dip {s['np1'][1]:3.0f}° rake {s['np1'][2]:5.0f}°"
                 f"  ({slip_sense(s['np1'][2])})")
    lines.append(f"  NP2 strike {s['np2'][0]:5.0f}° dip {s['np2'][1]:3.0f}° rake {s['np2'][2]:5.0f}°"
                 f"  ({slip_sense(s['np2'][2])})")
    if "P" in s:
        lines.append(f"  P axis {s['P'][0]:3.0f}°/{s['P'][1]:2.0f}°  T axis {s['T'][0]:3.0f}°/{s['T'][1]:2.0f}°"
                     f"  B axis {s['B'][0]:3.0f}°/{s['B'][1]:2.0f}°   (azimuth/plunge)")
        lines.append(f"  type: {s['type']}   double-couple {s['dc']:.0f} %  CLVD {s['clvd']:.0f} %")
        m = s["m"]
        e = int(math.floor(math.log10(s["M0"])))
        lines.append(f"~  Mrr {m[0]/10**e:+.2f}  Mtt {m[1]/10**e:+.2f}  Mpp {m[2]/10**e:+.2f}  "
                     f"Mrt {m[3]/10**e:+.2f}  Mrp {m[4]/10**e:+.2f}  Mtp {m[5]/10**e:+.2f}  ×10^{e} N·m")
    if "vr" in s:
        lines.append(f"~  variance reduction {s['vr']:.0f} %")
    return "\n".join(lines)


def beach_figure(sols, title, path, terminal):
    import matplotlib
    import matplotlib.pyplot as plt
    from obspy.imaging.beachball import beach
    sols = [s for s in sols if "np1" in s][:6]
    if not sols:
        return
    fig, ax = plt.subplots(figsize=(2.6 * len(sols), 3.2), facecolor="white")
    ax.set_xlim(0, 2.6 * len(sols)); ax.set_ylim(-0.4, 2.6); ax.set_aspect("equal"); ax.axis("off")
    for i, s in enumerate(sols):
        mine = s["agency"].startswith("SEISBOX")
        fm = s["m"] if "m" in s else s["np1"]
        ax.add_collection(beach(fm, xy=(1.3 + 2.6 * i, 1.3), width=2.1, linewidth=1,
                                facecolor="#d62728" if mine else "#1f77b4"))
        lab = s["agency"].replace("SEISBOX inversion", "SEISBOX (own)")
        sub = f"Mw {s['Mw']:.1f}" if "Mw" in s else ""
        if s.get("depth") is not None:
            sub += f"  {s['depth']:.0f} km"
        ax.text(1.3 + 2.6 * i, -0.1, lab, ha="center", fontsize=10, fontweight="bold")
        ax.text(1.3 + 2.6 * i, -0.38, sub, ha="center", fontsize=9)
    fig.suptitle(title, fontsize=11)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    if terminal:
        try:
            import tplot  # noqa: F401
            plt.show(size=f"{min(100, 26 * len(sols))}x{14}")
        except Exception:
            pass
    plt.close(fig)


def plot_fits(ev, best, stations, win, outdir, band):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tv = trace_vr(best)
    info = {f"{s['net']}.{s['sta']}": s for s in stations}
    keys = sorted({k for k, _ in best["keys"]}, key=lambda k: info[k]["az"])[:16]
    fig, axes = plt.subplots(len(keys), 3, figsize=(10, 1.0 * len(keys) + 1), squeeze=False)
    pos = {}
    p = 0
    for key, c, _, n in best["idx"]:
        pos[(key, c)] = (p, n)
        p += n
    for r, key in enumerate(keys):
        for j, c in enumerate("ZRT"):
            ax = axes[r][j]
            ax.axis("off")
            if (key, c) in pos:
                p, n = pos[(key, c)]
                t = np.arange(n) * DT / 60
                ax.plot(t, best["d"][p:p + n], "k", lw=0.7)
                ax.plot(t, best["syn"][p:p + n], "r", lw=0.7)
                ax.text(0.99, 0.85, f"{tv[(key, c)]:.0f}%", transform=ax.transAxes, ha="right", fontsize=7,
                        color="green" if tv[(key, c)] > 50 else "gray")
            if j == 0:
                s = info[key]
                ax.text(-0.02, 0.5, f"{key}\n{s['dist']:.0f}° az{s['az']:.0f}°", transform=ax.transAxes,
                        ha="right", va="center", fontsize=7)
            if r == 0:
                ax.set_title(c, fontsize=9)
    fig.suptitle(f"Waveform fit: data (black) vs synthetic (red), {band[0]:.0f}-{band[1]:.0f} s, "
                 f"depth {best['depth']:.0f} km, VR {best['vr']:.0f} %", fontsize=10)
    fig.savefig(os.path.join(outdir, "inversion_waveform_fits.png"), dpi=100, bbox_inches="tight")
    plt.close(fig)


# ===================================================================== main
def safe_name(text):
    """Folder-safe ASCII: 'M6.8 45 km SE of Ürümqi, China' -> 'M6.8_45km-SE-of-Urumqi-China'."""
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"(\d)\s+km\b", r"\1km", t)
    t = re.sub(r"[^A-Za-z0-9.+-]+", "-", t).strip("-")
    return t[:60]


def default_folder(t, mag, region):
    """e.g. 2026-11-21_0942UTC_M6.8_Banda-Sea (same rule as Events)."""
    return f"{t.strftime('%Y-%m-%d_%H%M')}UTC_M{mag:.1f}_" + safe_name(region or "event")


class Tee:
    """Copy everything printed to a buffer, saved later as the run's summary.txt."""
    def __init__(self, stream):
        self.stream, self.buf = stream, []

    def write(self, x):
        self.buf.append(x)
        return self.stream.write(x)

    def flush(self):
        self.stream.flush()

    def text(self):
        import re
        return re.sub(r"\x1b\[[0-9;]*m", "", "".join(self.buf))


def append_index(mtdir, folder, ev, region, layer, best):
    path = os.path.join(mtdir, "index.csv")
    new = not os.path.exists(path)
    row = [ev["time"].strftime("%Y-%m-%d %H:%M:%S"), f"{ev['mag']:.1f}", region.replace(",", " "),
           f"{ev['lat']:.3f}", f"{ev['lon']:.3f}", layer, folder,
           f"{best['agency']}" if best else "none",
           f"{best['Mw']:.2f}" if best and "Mw" in best else "",
           "/".join(f"{x:.0f}" for x in best["np1"]) if best else "",
           best.get("type", "") if best else "",
           f"{best['vr']:.0f}" if best and "vr" in best else ""]
    with open(path, "a") as f:
        if new:
            f.write("quake_time_utc,catalog_mag,region,lat,lon,layer,folder,solution,Mw,"
                    "strike/dip/rake,fault_type,VR_percent\n")
        f.write(",".join(row) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--time", required=True, help="origin time (UTC, ISO)")
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--depth", type=float, default=20.0, help="catalogue depth, km")
    p.add_argument("--mag", type=float, default=6.0)
    p.add_argument("--region", default="")
    p.add_argument("--invert", action="store_true", help="also run the waveform inversion")
    p.add_argument("--stations", type=int, default=24, help="max stations (default 24)")
    p.add_argument("--dmin", type=float, default=None, help="min distance, deg (default 25; 12 below M6)")
    p.add_argument("--dmax", type=float, default=None, help="max distance, deg (default 90; 60 below M6)")
    p.add_argument("--depths", default="", help="comma list of trial depths, km")
    p.add_argument("--band", default="", help="period band 'Tmin,Tmax' in s (default by magnitude)")
    p.add_argument("--maxlag", type=float, default=30.0, help="max per-station time lag, s (default 30)")
    p.add_argument("--name", default="", help="folder name under $SEISBOX_PROJECTS/mt "
                   "(default: date_time_magnitude_region)")
    p.add_argument("--outdir", default="", help="full output folder path (overrides --name)")
    p.add_argument("--no-terminal-plot", action="store_true", help=argparse.SUPPRESS)  # kept for old calls
    a = p.parse_args()

    ev = {"time": UTCDateTime(a.time), "lat": a.lat, "lon": a.lon, "depth": a.depth, "mag": a.mag}
    mtdir = os.path.join(os.environ.get("SEISBOX_PROJECTS", "/sdcard/termux/projects"), "mt")
    folder = safe_name(a.name) if a.name else default_folder(ev["time"], a.mag, a.region)
    outdir = a.outdir or os.path.join(mtdir, folder)
    os.makedirs(outdir, exist_ok=True)
    layer = "inversion" if a.invert else "published"
    global TEE
    tee = TEE = Tee(sys.stdout)
    sys.stdout = tee
    title = f"M{a.mag:.1f} {a.region}  {ev['time'].strftime('%Y-%m-%d %H:%M:%S')} UTC  " \
            f"{a.lat:.2f}°, {a.lon:.2f}°  {a.depth:.0f} km"
    say(f"━━ {title}")

    say("\n▶ Published solutions")
    sols, usgs_id = published(ev)
    if not sols:
        say("  none published (yet). USGS/GFZ usually publish M5+ within ~20-60 min.", "warn")
    for s in sols:
        show(fmt_sol(s))
    if len(sols) > 1 and "m" in sols[0]:
        ref = sols[0]
        for s in sols[1:]:
            if "m" in s:
                detail(f"  {s['agency']} vs {ref['agency']}: Kagan angle "
                       f"{kagan_angle(s['m'], ref['m']):.0f}°")

    mine = None
    if a.invert:
        if a.mag < 5.3:
            say(f"  M{a.mag:.1f} is too small for teleseismic long-period inversion (needs ~M5.5+).", "warn")
        else:
            try:
                mine = invert(ev, a, outdir)
                show(fmt_sol(mine))
                lo, hi = mine["depth_range"]
                if hi > lo:
                    print(f"  depth range {lo:.0f}-{hi:.0f} km (fits nearly as well)")
                detail(f"  centroid time shift {mine['shift']:+.0f} s   stations {mine['nsta']}  traces "
                       f"{mine['ntraces']}   azimuthal gap {mine['gap']:.0f}°   ({mine['runtime']:.0f} s)")
                curve = "  ".join(f"{d:.0f}km:{v:.0f}%" for d, v in mine["depth_curve"])
                detail(f"  VR by depth  {curve}")
                q = mine["vr"]
                qual = ("good", "ok") if q >= 60 else (("fair", "warn") if q >= 40 else ("poor", "bad"))
                say(f"  fit quality: {qual[0]} (VR {q:.0f} %, {mine['nsta']} stations)", qual[1])
                refs = [s for s in sols if "m" in s]
                for s in refs[:3]:
                    detail(f"  vs {s['agency']:12}: Kagan angle {kagan_angle(mine['m'], s['m']):3.0f}°   "
                           f"ΔMw {mine['Mw'] - s['Mw']:+.2f}")
                detail("  Note: the data cannot tell which nodal plane is the actual fault;"
                       " use aftershocks or known faults.")
            except Exception as e:
                progress("")
                say(f"  inversion failed: {e}", "bad")

    allsols = ([mine] if mine else []) + sols
    files = []
    if allsols:
        png = "inversion_mechanism.png" if a.invert else "published_mechanisms.png"
        beach_figure(allsols, title, os.path.join(outdir, png), False)   # images: seisview / Termux:X11
        files.append(png)
    if mine:
        files.append("inversion_waveform_fits.png")
    with open(os.path.join(outdir, f"{layer}.json"), "w") as f:
        json.dump({"event": {**ev, "time": str(ev["time"]), "region": a.region, "usgs_id": usgs_id},
                   "solutions": [{k: v for k, v in s.items() if k not in ("d", "syn", "idx")}
                                 for s in allsols]}, f, indent=1, default=float)
    files += [f"{layer}_summary.txt", f"{layer}.json"]
    say(f"\nSaved: {outdir}/", "dim")
    for fn in files:
        detail(f"   {fn}")
    sys.stdout = tee.stream
    with open(os.path.join(outdir, f"{layer}_summary.txt"), "w") as f:
        f.write(tee.text())
    try:
        append_index(mtdir, os.path.basename(outdir.rstrip("/")), ev, a.region, layer,
                     mine or (sols[0] if sols else None))
    except OSError:
        pass


if __name__ == "__main__":
    main()
