"""Pull outdoor rides and runs from the Garmin Personal API into ~/.route-browser/cache/.

One JSON per activity: summary fields + a track downsampled to a point every >=20 m moved, as
columns (lat, lon, t seconds from start, d metres, alt, hr, pw; null where the sensor was absent).
Re-runnable: an activity already cached is never downloaded again. Rides without GPS get a cache
file with an empty track, so they are not re-downloaded either.

    python fetch.py               # last 12 months
    python fetch.py --since 2023-01-01

The cache sits in the home folder, outside every checkout, so a cleaned-up worktree cannot take it
with it. It holds your home in every track: never commit or upload it.
"""
import argparse
import datetime as dt
import io
import json
import math
import sys
import time
import zipfile
from pathlib import Path

import fitdecode

from garmin_personal import Garmin  # same folder; the script dir is on sys.path

CACHE = Path.home() / ".route-browser" / "cache"  # same line in build_map.py
STATUS = CACHE.parent / "fetch_status.json"       # the last fetch's outcome, read by build_map.py
OUTDOOR = {"cycling", "road_biking", "mountain_biking", "gravel_cycling", "cyclocross", "bmx",
           "running", "trail_running"}  # not treadmill, indoor or virtual
SEMI = 180 / 2**31
MIN_STEP_M = 20
PAUSE_S = 1.5  # between downloads; Garmin publishes no limits, so stay gentle


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))


def parse_fit(raw):
    """FIT bytes -> list of (lat, lon, t, d, alt, hr, pw), downsampled."""
    pts, t0, last = [], None, None
    with fitdecode.FitReader(io.BytesIO(raw)) as fr:
        for f in fr:
            if not isinstance(f, fitdecode.FitDataMessage) or f.name != "record":
                continue
            v = {fld.name: fld.value for fld in f.fields}
            la, lo, ts = v.get("position_lat"), v.get("position_long"), v.get("timestamp")
            if la is None or lo is None or ts is None:
                continue
            la, lo = la * SEMI, lo * SEMI
            if t0 is None:
                t0 = ts
            if last and haversine(last[0], last[1], la, lo) < MIN_STEP_M:
                continue
            alt = v.get("enhanced_altitude", v.get("altitude"))
            last = (la, lo)
            pts.append((round(la, 5), round(lo, 5), int((ts - t0).total_seconds()),
                        None if v.get("distance") is None else round(v["distance"]),
                        None if alt is None else round(alt, 1), v.get("heart_rate"), v.get("power")))
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=(dt.date.today() - dt.timedelta(days=365)).isoformat())
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")  # ride names carry emoji; the Windows console is cp1252
    CACHE.mkdir(parents=True, exist_ok=True)
    g = Garmin()

    acts, start = [], 0
    while True:
        page = g.get("/activitylist-service/activities/search/activities", start=start, limit=100,
                     startDate=args.since, endDate=dt.date.today().isoformat())
        acts += page
        start += 100
        if len(page) < 100:
            break
        time.sleep(PAUSE_S)
    rides = [a for a in acts if a["activityType"]["typeKey"] in OUTDOOR]
    todo = [a for a in rides if not (CACHE / f"{a['activityId']}.json").exists()]
    print(f"{len(acts)} activities since {args.since}, {len(rides)} outdoor rides, {len(todo)} new")

    no_gps = failed = 0
    for i, a in enumerate(todo, 1):
        aid = a["activityId"]
        try:
            z = g.get(f"/download-service/files/activity/{aid}",
                      accept="application/zip, application/x-zip-compressed, application/octet-stream")
            with zipfile.ZipFile(io.BytesIO(z)) as zf:
                fit = next(n for n in zf.namelist() if n.lower().endswith(".fit"))
                pts = parse_fit(zf.read(fit))
        except Exception as e:  # one bad file must not stop the pull; it is retried next run
            failed += 1
            print(f"  {aid}: skipped ({type(e).__name__}: {e})")
            continue
        no_gps += not pts
        meta = {k: a.get(k) for k in ("activityId", "activityName", "startTimeLocal", "distance",
                                       "movingDuration", "duration", "elevationGain", "averageHR")}
        meta["type"] = a["activityType"]["typeKey"]
        meta["avgPower"] = a.get("avgPower")
        cols = list(zip(*pts)) if pts else [[]] * 7
        meta["track"] = dict(zip(("lat", "lon", "t", "d", "alt", "hr", "pw"), map(list, cols)))
        (CACHE / f"{aid}.json").write_text(json.dumps(meta, separators=(",", ":")))
        print(f"  [{i}/{len(todo)}] {a['startTimeLocal'][:10]} {a['activityName'][:40]}: {len(pts)} pts")
        time.sleep(PAUSE_S)

    print(f"done: {len(todo) - failed} cached ({no_gps} without GPS), {failed} failed, "
          f"{len(list(CACHE.glob('*.json')))} in cache")


def run():
    """main(), leaving STATUS for build_map.py, so a refused key shows on the page, not only in a log."""
    when = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        main()
    except BaseException as e:  # SystemExit from a refused key included
        if not (isinstance(e, SystemExit) and e.code in (0, None)):
            STATUS.write_text(json.dumps({"ok": False, "when": when, "msg": str(e) or type(e).__name__}))
        raise
    STATUS.write_text(json.dumps({"ok": True, "when": when}))


if __name__ == "__main__":
    run()
