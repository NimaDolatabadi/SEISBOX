#!/usr/bin/env python3
"""
Download the IRSC (Iranian Seismological Center, irsc.ut.ac.ir) earthquake
bulletin with ObsPy.

IRSC has no FDSN web service, but it reports its locations to the ISC
under agency code "TEH". This script queries the ISC FDSN event service
with all contributing agencies' origins, keeps only the IRSC (TEH) origin
and magnitude for each event, and saves a CSV catalogue.

Note: the ISC *reviewed* bulletin lags ~2 years; recent months come from the
preliminary bulletin and may be incomplete.

Examples:
  python irsc_bulletin.py --start 2024-06-01 --end 2024-07-01
  python irsc_bulletin.py --start 2023-01-01 --end 2024-01-01 --minmag 3.5 --out irsc_2023
  python irsc_bulletin.py --start 2024-01-01 --lat 35.7 --lon 51.4 --radius 2   # around Tehran
"""
import argparse
import csv
import os
import time

from obspy import Catalog, UTCDateTime
from obspy.clients.fdsn import Client
from obspy.clients.fdsn.header import FDSNNoDataException

AGENCY = "TEH"   # IRSC's agency code at the ISC
DEFAULT_OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
IRAN_BOX = dict(minlatitude=24, maxlatitude=40, minlongitude=44, maxlongitude=64)


def author(obj):
    ci = obj.creation_info
    return (ci.author or ci.agency_id) if ci else None


def keep_irsc(event, minmag=None, maxmag=None):
    """Return the event with IRSC's origin/magnitude as preferred, or None."""
    origins = [o for o in event.origins if author(o) == AGENCY]
    if not origins:
        return None
    o = origins[0]
    mags = [m for m in event.magnitudes if author(m) == AGENCY]
    m = next((m for m in mags if m.origin_id == o.resource_id), mags[0] if mags else None)
    if minmag is not None and (m is None or m.mag < minmag):
        return None
    if maxmag is not None and (m is None or m.mag > maxmag):
        return None
    event.origins = [o]
    event.magnitudes = [m] if m else []
    event.preferred_origin_id = o.resource_id
    event.preferred_magnitude_id = m.resource_id if m else None
    return event


def fetch(start, end, area=None, minmag=None, maxmag=None,
          chunk_days=30, timeout=300, retries=3):
    """Fetch IRSC (TEH) events from ISC. area = FDSN geographic kwargs.

    Returns (catalog, failed_parts, interrupted). Ctrl-C stops the download
    and returns what was collected so far.
    """
    client = Client("ISC", timeout=timeout)
    area = area or IRAN_BOX
    cat = Catalog()
    failed = []
    interrupted = False
    t = start
    try:
        while t < end:
            t1 = min(t + chunk_days * 86400, end)
            raw = None
            for attempt in range(1, retries + 1):
                try:
                    raw = client.get_events(starttime=t, endtime=t1,
                                            includeallorigins=True,
                                            includeallmagnitudes=True, **area)
                    break
                except FDSNNoDataException:
                    raw = Catalog()
                    break
                except Exception:
                    if attempt < retries:
                        time.sleep(5 * attempt)
            if raw is None:
                failed.append((t, t1))
                raw = Catalog()
            for ev in raw:
                ev = keep_irsc(ev, minmag, maxmag)
                if ev is not None:
                    cat.append(ev)
            t = t1
    except KeyboardInterrupt:
        interrupted = True
    cat.events.sort(key=lambda e: e.origins[0].time)
    return cat, failed, interrupted


def report(cat, path, failed, interrupted):
    """Print the single end-of-run message."""
    note = " (partial: stopped with Ctrl-C)" if interrupted else ""
    print(f"\nDone: {len(cat)} events saved{note} to\n  {path}")
    if failed:
        print(f"Warning: {len(failed)} period(s) could not be downloaded and are missing:")
        for a, b in failed:
            print(f"  {a.date} -> {b.date}")


def save_catalog(cat, outdir, name):
    """Write the CSV to outdir/name.csv (creating outdir) and return its full path."""
    name = name.strip() or "irsc_bulletin"
    if name.lower().endswith(".csv"):
        name = name[:-4]
    outdir = os.path.abspath(os.path.expanduser(outdir or DEFAULT_OUTDIR))
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, name + ".csv")
    write_csv(cat, path)
    return path


def write_csv(cat, path):
    """CSV: year,month,day,hour,minute,second,long,lat,magnitude,magnitude type,depth
    (UTC time, depth in km)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "month", "day", "hour", "minute", "second",
                    "long", "lat", "magnitude", "magnitude type", "depth"])
        for ev in cat:
            o = ev.origins[0]
            m = ev.magnitudes[0] if ev.magnitudes else None
            t = o.time
            w.writerow([t.year, f"{t.month:02d}", f"{t.day:02d}",
                        f"{t.hour:02d}", f"{t.minute:02d}",
                        f"{t.second + t.microsecond / 1e6:05.2f}",
                        o.longitude, o.latitude,
                        "" if m is None else m.mag,
                        "" if m is None else m.magnitude_type,
                        "" if o.depth is None else round(o.depth / 1000, 1)])


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", type=UTCDateTime, required=True)
    p.add_argument("--end", type=UTCDateTime, default=UTCDateTime())
    p.add_argument("--minmag", type=float, help="minimum IRSC magnitude (ML)")
    p.add_argument("--maxmag", type=float, help="maximum IRSC magnitude (ML)")
    p.add_argument("--lat", type=float, help="circle centre latitude (default: all of Iran)")
    p.add_argument("--lon", type=float, help="circle centre longitude")
    p.add_argument("--radius", type=float, default=2.0, help="circle radius in degrees")
    p.add_argument("--chunk-days", type=int, default=30,
                   help="days per ISC request (smaller = fewer timeouts)")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--out", default="irsc_bulletin", help="CSV file name")
    p.add_argument("--outdir", default=DEFAULT_OUTDIR,
                   help=f"folder to save the CSV in (default: {DEFAULT_OUTDIR})")
    args = p.parse_args()

    print("Downloading... (Ctrl-C = stop and save)", flush=True)
    if args.lat is not None and args.lon is not None:
        area = dict(latitude=args.lat, longitude=args.lon, maxradius=args.radius)
    else:
        area = IRAN_BOX
    cat, failed, interrupted = fetch(args.start, args.end, area, args.minmag,
                                     args.maxmag, args.chunk_days, args.timeout)
    if not len(cat):
        print("\nNo events found - nothing saved.")
        return
    path = save_catalog(cat, args.outdir, args.out)
    report(cat, path, failed, interrupted)


if __name__ == "__main__":
    main()
