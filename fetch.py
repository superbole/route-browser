"""Pull outdoor rides and runs from the Garmin Personal API into ~/.route-browser/cache/.

One JSON per activity: summary fields + a track downsampled to a point every >=20 m moved, as
columns (lat, lon, t seconds from start, d metres, alt, hr, pw; null where the sensor was absent).
Re-runnable: an activity already cached is never downloaded again. Rides without GPS get a cache
file with an empty track, so they are not re-downloaded either.

    python fetch.py               # last 12 months
    python fetch.py --since 2023-01-01

A failed download is recorded in ~/.route-browser/failed.json and retried on every run, whatever
--since says, until it caches.

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
import xml.etree.ElementTree as ET
from pathlib import Path

import fitdecode

from garmin_personal import Garmin  # same folder; the script dir is on sys.path

CACHE = Path.home() / ".route-browser" / "cache"  # same line in build_map.py
STATUS = CACHE.parent / "fetch_status.json"       # the last fetch's outcome, read by build_map.py
FAILED = CACHE.parent / "failed.json"             # {activityId: summary} of downloads that failed; retried every run
SUMMARY = ("activityId", "activityName", "startTimeLocal", "distance", "movingDuration", "duration",
           "elevationGain", "averageHR", "avgPower")
OUTDOOR = {"cycling", "road_biking", "mountain_biking", "gravel_cycling", "cyclocross", "bmx",
           "running", "trail_running"}  # not treadmill, indoor or virtual
SEMI = 180 / 2**31
MIN_STEP_M = 20
PAUSE_S = 1.5  # between downloads; Garmin publishes no limits, so stay gentle


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))


def thin(raw):
    """(lat, lon, datetime, d, alt, hr, pw) records -> the cache's (lat, lon, t, d, alt, hr, pw), a point every MIN_STEP_M."""
    pts, t0, last = [], None, None
    for la, lo, ts, d, alt, hr, pw in raw:
        if la is None or lo is None or ts is None:
            continue
        t0 = t0 or ts
        if last and haversine(last[0], last[1], la, lo) < MIN_STEP_M:
            continue
        last = (la, lo)
        pts.append((round(la, 5), round(lo, 5), int((ts - t0).total_seconds()), None if d is None else round(d),
                    None if alt is None else round(alt, 1), hr, pw))
    return pts


def parse_fit(raw):
    """FIT bytes -> cache points."""
    def records():
        with fitdecode.FitReader(io.BytesIO(raw)) as fr:
            for f in fr:
                if isinstance(f, fitdecode.FitDataMessage) and f.name == "record":
                    v = {fld.name: fld.value for fld in f.fields}
                    la, lo = v.get("position_lat"), v.get("position_long")
                    yield (None if la is None else la * SEMI, None if lo is None else lo * SEMI, v.get("timestamp"),
                           v.get("distance"), v.get("enhanced_altitude", v.get("altitude")), v.get("heart_rate"), v.get("power"))
    return thin(records())


def parse_tcx(raw):
    """TCX bytes (older or uploaded activities) -> cache points."""
    def val(el, name):  # first descendant with this local name, as float
        for x in el.iter():
            if x.tag.rsplit("}", 1)[-1] == name and x.text and x.text.strip():
                return float(x.text)
        return None

    def records():
        for tp in ET.fromstring(raw).iter():
            if tp.tag.rsplit("}", 1)[-1] != "Trackpoint":
                continue
            ts = next((x.text for x in tp if x.tag.rsplit("}", 1)[-1] == "Time"), None)
            hr, pw = val(tp, "Value"), val(tp, "Watts")
            yield (val(tp, "LatitudeDegrees"), val(tp, "LongitudeDegrees"),
                   dt.datetime.fromisoformat(ts.strip().replace("Z", "+00:00")) if ts else None,
                   val(tp, "DistanceMeters"), val(tp, "AltitudeMeters"),
                   None if hr is None else int(hr), None if pw is None else int(pw))
    return thin(records())


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
    failed_log = json.loads(FAILED.read_text()) if FAILED.exists() else {}
    seen = {str(a["activityId"]) for a in todo}
    # failures older than --since are never listed above, so retry them from their saved summary
    retry = [a for k, a in failed_log.items() if k not in seen and not (CACHE / f"{k}.json").exists()]
    todo += retry
    retried = sum(str(a["activityId"]) in failed_log for a in todo)  # earlier failures, in or out of --since
    print(f"{len(acts)} activities since {args.since}, {len(rides)} outdoor rides, {len(todo) - retried} new, "
          f"{retried} retried from earlier failures")

    no_gps = failed = 0
    for i, a in enumerate(todo, 1):
        aid = a["activityId"]
        try:
            z = g.get(f"/download-service/files/activity/{aid}",
                      accept="application/zip, application/x-zip-compressed, application/octet-stream")
            with zipfile.ZipFile(io.BytesIO(z)) as zf:
                names = zf.namelist()
                fit = next((n for n in names if n.lower().endswith(".fit")), None)
                tcx = next((n for n in names if n.lower().endswith(".tcx")), None)
                if not (fit or tcx):
                    raise ValueError(f"no FIT or TCX file in the download: {names}")
                pts = parse_fit(zf.read(fit)) if fit else parse_tcx(zf.read(tcx))
        except Exception as e:  # one bad file must not stop the pull; it is retried next run
            failed += 1
            failed_log[str(aid)] = {**{k: a.get(k) for k in SUMMARY}, "activityType": {"typeKey": a["activityType"]["typeKey"]}}
            FAILED.write_text(json.dumps(failed_log))
            print(f"  {aid}: skipped ({type(e).__name__}: {e})")
            time.sleep(PAUSE_S)
            continue
        no_gps += not pts
        meta = {k: a.get(k) for k in ("activityId", "activityName", "startTimeLocal", "distance",
                                       "movingDuration", "duration", "elevationGain", "averageHR")}
        meta["type"] = a["activityType"]["typeKey"]
        meta["activityName"] = meta["activityName"] or meta["type"].replace("_", " ").capitalize()  # some have none
        meta["avgPower"] = a.get("avgPower")
        cols = list(zip(*pts)) if pts else [[]] * 7
        meta["track"] = dict(zip(("lat", "lon", "t", "d", "alt", "hr", "pw"), map(list, cols)))
        (CACHE / f"{aid}.json").write_text(json.dumps(meta, separators=(",", ":")))
        if failed_log.pop(str(aid), None) is not None:
            FAILED.write_text(json.dumps(failed_log))
        print(f"  [{i}/{len(todo)}] {a['startTimeLocal'][:10]} {meta['activityName'][:40]}: {len(pts)} pts")
        time.sleep(PAUSE_S)

    print(f"done: {len(todo) - failed} cached ({no_gps} without GPS), {failed} failed, {retried} retried, "
          f"{len(failed_log)} awaiting retry, {len(list(CACHE.glob('*.json')))} in cache")


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
