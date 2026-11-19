"""Route library: group cached rides into the routes you repeat, and record on
each one where you usually slow or stop, and the climbs that suit repeats. The page turns the stops
into no-stop stretches (stretches() in build_map.py's MATCHER_JS), so its sliders work without a rebuild.

build_map.py calls routes() and draws the result as a layer; nothing is written to disk.

- Two rides are the same route when they start within 500 m of each other, end within 500 m of each
  other, and share at least half their ~250 m map cells (average linkage, so variants merge).
- Each route is described by its medoid: the member most like all the others.
- For each point on the medoid and each speed level in LEVELS, `sh` is the percentage of the route's
  rides that passed it and slowed there (under that share of the ride's usual speed, not on a climb)
  or paused: robots, stop streets, pinch points, sharp turns. The page calls a point a stop when that
  percentage reaches its slider. Defaults: 70% speed on 1 ride in 4 (at half speed and 40% of rides,
  a tested loop showed one 66-min stretch that ran through robots and stop streets).
"""
import math
from collections import Counter, defaultdict
from statistics import median

SAME = 0.5            # Jaccard on map cells to count as one route
END_M = 500           # start and end within this of each other
CELL = 400            # 1/CELL degree grid for route similarity (~250 m)
SPOT = 2000           # 1/SPOT degree grid for interruptions (~50 m)
LEVELS = (50, 60, 70, 80)  # % of usual speed: the page's speed slider steps


def dist(la1, lo1, la2, lo2):
    return math.hypot((lo2 - lo1) * math.cos(math.radians(la1)) * 111320, (la2 - la1) * 110540)


def fill_d(tr):
    """Distance per point; fills gaps from geometry (same as build_map.encode)."""
    out, acc = [], 0.0
    for k, v in enumerate(tr["d"]):
        if v is None:
            if k:
                acc += dist(tr["lat"][k - 1], tr["lon"][k - 1], tr["lat"][k], tr["lon"][k])
            v = acc
        acc = v
        out.append(v)
    return out


def slow_points(tr, d, slow):
    """Indexes where the rider paused or went under `slow` x usual speed, excluding climbs."""
    t, alt, pw, n = tr["t"], tr["alt"], tr["pw"], len(d)
    w = 1  # +-1 point (~40 m): a wider window averaged short slowdowns away
    v = [0.0] * n
    g = [0.0] * n
    for k in range(n):
        a, b = max(0, k - w), min(n - 1, k + w)
        dt, dd = t[b] - t[a], d[b] - d[a]
        v[k] = dd / dt if dt > 0 else 0
        if alt[a] is not None and alt[b] is not None and dd > 0:
            g[k] = (alt[b] - alt[a]) / dd
    moving = [x for x in v if x > 1.5]
    if not moving:
        return set()
    vmed = median(moving)
    pws = [p for p in pw if p]
    pmed = median(pws) if pws else None
    out = set()
    for k in range(n):
        if k and t[k] - t[k - 1] > 30:  # auto-pause or a stop
            out.update((k - 1, k))
        elif v[k] < slow * vmed:
            climbing = g[k] > 0.03 or (pmed and pw[k] and pw[k] > 0.6 * pmed)
            if not climbing:
                out.add(k)
    return out


def _cells(tr, scale):
    return {(round(a * scale), round(b * scale)) for a, b in zip(tr["lat"], tr["lon"])}


def cluster(recs):
    """recs: cache records with tracks. Returns lists of indexes into recs, one per route of 2+ rides."""
    import numpy as np
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    n = len(recs)
    if n < 2:
        return []
    sig = [_cells(r["track"], CELL) for r in recs]
    se = [(r["track"]["lat"][0], r["track"]["lon"][0], r["track"]["lat"][-1], r["track"]["lon"][-1]) for r in recs]
    D = np.ones((n, n))
    np.fill_diagonal(D, 0)
    for i in range(n):
        for j in range(i + 1, n):
            if dist(*se[i][:2], *se[j][:2]) <= END_M and dist(*se[i][2:], *se[j][2:]) <= END_M:
                D[i, j] = D[j, i] = 1 - len(sig[i] & sig[j]) / len(sig[i] | sig[j])
    lab = fcluster(linkage(squareform(D), "average"), 1 - SAME, "distance")
    groups = defaultdict(list)
    for i, l in enumerate(lab):
        groups[l].append(i)
    out = []
    for g in groups.values():
        if len(g) >= 2:
            med = min(g, key=lambda i: sum(D[i, j] for j in g))
            out.append([med] + [i for i in g if i != med])
    return sorted(out, key=len, reverse=True)


def moving_s(t, i, j):
    return sum(t[k] - t[k - 1] for k in range(i + 1, j + 1) if t[k] - t[k - 1] <= 30)


def climbs(tr, d, t):
    """Ascents of 25 m+ at 3%+ that take 1 to 15 min: (i, j, gain, grade)."""
    alt = tr["alt"]
    if sum(a is not None for a in alt) < len(alt) * 0.9:
        return []
    a, last = [], next(x for x in alt if x is not None)  # fill sensor gaps, leading ones included
    for x in alt:
        last = x if x is not None else last
        a.append(last)
    sm = [sum(a[max(0, k - 2):k + 3]) / len(a[max(0, k - 2):k + 3]) for k in range(len(a))]
    out, lo, hi, up = [], 0, 0, False  # hysteresis 8 m between turning points
    for k in range(1, len(sm)):
        if up:
            if sm[k] > sm[hi]:
                hi = k
            elif sm[hi] - sm[k] > 8:
                out.append((lo, hi)); up, lo = False, k
        else:
            if sm[k] < sm[lo]:
                lo = k
            elif sm[k] - sm[lo] > 8:
                up, hi = True, k
    if up:
        out.append((lo, hi))
    res = []
    for i, j in out:
        gain, m = sm[j] - sm[i], d[j] - d[i]
        dur = moving_s(t, i, j)
        if gain >= 25 and m > 0 and gain / m >= 0.03 and 60 <= dur <= 900:
            res.append((i, j, round(gain), round(gain / m * 100, 1)))
    return res


def describe(recs, members):
    """One route: its medoid, stats, slow-down shares and climbs (indexes are into the medoid's track)."""
    rs = [recs[i] for i in members]
    med = rs[0]
    tr = med["track"]
    d = fill_d(tr)
    visits = Counter()
    slowed = {lv: Counter() for lv in LEVELS}
    for r in rs:
        rd = fill_d(r["track"])
        lat, lon = r["track"]["lat"], r["track"]["lon"]
        visits.update(_cells(r["track"], SPOT))
        for lv in LEVELS:
            spots = {(round(lat[k] * SPOT), round(lon[k] * SPOT)) for k in slow_points(r["track"], rd, lv / 100)}
            slowed[lv].update({(a + x, b + y) for a, b in spots for x in (-1, 0, 1) for y in (-1, 0, 1)})
    cells = [(round(la * SPOT), round(lo * SPOT)) for la, lo in zip(tr["lat"], tr["lon"])]
    sh = {lv: [min(100, round(100 * slowed[lv][c] / max(visits[c], 1))) for c in cells] for lv in LEVELS}
    t = tr["t"]
    cl = [{"i": i, "j": j, "s": moving_s(t, i, j), "km": round(d[i] / 1000, 1), "len": round((d[j] - d[i]) / 1000, 1),
           "gain": gain, "g": grade, "at": moving_s(t, 0, i)} for i, j, gain, grade in climbs(tr, d, t)]
    far = max(range(len(d)), key=lambda k: dist(tr["lat"][0], tr["lon"][0], tr["lat"][k], tr["lon"][k]))
    brg = math.degrees(math.atan2((tr["lon"][far] - tr["lon"][0]) * math.cos(math.radians(tr["lat"][0])),
                                  tr["lat"][far] - tr["lat"][0])) % 360
    loop = dist(tr["lat"][0], tr["lon"][0], tr["lat"][-1], tr["lon"][-1]) < END_M
    hours = sorted(r["startTimeLocal"][11:16] for r in rs)
    return {
        "ids": [r["activityId"] for r in rs], "med": med["activityId"], "loop": loop,
        "dir": "N NE E SE S SW W NW".split()[round(brg / 45) % 8],
        "far": round(dist(tr["lat"][0], tr["lon"][0], tr["lat"][far], tr["lon"][far]) / 1000, 1),
        "km": round(median(r["distance"] / 1000 for r in rs if r["distance"]), 1),
        "mv": round(median(r["movingDuration"] or r["duration"] for r in rs)),
        "el": round(median(r["track"]["t"][-1] - r["track"]["t"][0] for r in rs)),  # Garmin duration is timer time
        "up": round(median(r.get("elevationGain") or 0 for r in rs)),
        "start": hours[len(hours) // 2],
        "days": Counter("Mon Tue Wed Thu Fri Sat Sun".split()[_weekday(r["startTimeLocal"])] for r in rs).most_common(3),
        "climbs": cl, "sh": sh, "alt": [None if a is None else round(a, 1) for a in tr["alt"]],
    }


def _weekday(s):
    import datetime
    return datetime.date.fromisoformat(s[:10]).weekday()


def routes(recs):
    """All routes ridden 2+ times, from cycling records with GPS (runs are left out)."""
    rides = [r for r in recs if r["track"]["lat"] and "running" not in r["type"]]
    return [describe(rides, g) for g in cluster(rides)]


# --- places you do repeats: stretches ridden as repeats, back and forth or one way ---------------------------
# A rep is a hard stretch in a ride with power: 5 min+ above 1.12x the ride's median power (30-s mean,
# dips under 30 s allowed), or 90 s to 5 min above 1.25x (dips under 20 s). Reps of one ride on the same
# road (half the ~50 m cells shared) are a session: 3+ reps, or 2 of 5 min+. Sessions on the same road
# across rides (40% shared) are one place. Tuned on real history: without the 90-s floor and
# the session rule, every out-and-back over a hill looked like 2 reps.

def _smooth30(t, pw):
    out, a, acc = [], 0, 0.0
    for k in range(len(t)):
        acc += pw[k] * (t[k] - t[k - 1] if k else 0)
        while t[k] - t[a] > 30:
            acc -= pw[a + 1] * (t[a + 1] - t[a])
            a += 1
        out.append(acc / max(t[k] - t[a], 1))
    return out


def _bearing(tr, i, j):
    return math.degrees(math.atan2((tr["lon"][j] - tr["lon"][i]) * math.cos(math.radians(tr["lat"][i])),
                                   tr["lat"][j] - tr["lat"][i])) % 360


def reps(r):
    """Hard stretches in one ride: dicts with i, j, s (seconds), w (mean watts), brg, cells."""
    tr = r["track"]
    t, pw, n = tr["t"], [x or 0 for x in tr["pw"]], len(tr["t"])
    mv = [p for k, p in enumerate(pw) if p > 0 and k and t[k] - t[k - 1] <= 30]
    if len(mv) < 50 or len(mv) < n * 0.5:
        return []
    sm, m = _smooth30(t, pw), median(mv)

    def spans(th, gap):
        out, st, last = [], None, None
        for k in range(n):
            if sm[k] >= th:
                st = k if st is None else st
                last = k
            elif st is not None and t[k] - t[last] > gap:
                out.append((st, last)); st = None
        if st is not None:
            out.append((st, last))
        return out
    longs = [(i, j) for i, j in spans(1.12 * m, 30) if t[j] - t[i] >= 300]
    shorts = [(i, j) for i, j in spans(1.25 * m, 20)
              if 90 <= t[j] - t[i] < 300 and not any(a <= j and i <= b for a, b in longs)]
    return [{"i": i, "j": j, "s": t[j] - t[i], "w": round(sum(pw[i:j + 1]) / (j - i + 1)), "brg": _bearing(tr, i, j),
             "cells": {(round(a * SPOT), round(b * SPOT)) for a, b in zip(tr["lat"][i:j + 1], tr["lon"][i:j + 1])}}
            for i, j in sorted(longs + shorts)]


def _ov(a, b):
    return len(a & b) / max(1, min(len(a), len(b)))


def sessions(r):
    """Groups of 3+ reps (or 2 of 5 min+) on the same road in one ride."""
    E, used, out = reps(r), set(), []
    for a in range(len(E)):
        if a in used:
            continue
        g = [b for b in range(a, len(E)) if b not in used and (b == a or _ov(E[a]["cells"], E[b]["cells"]) >= 0.5)]
        if len(g) >= 3 or (len(g) == 2 and min(E[b]["s"] for b in g) >= 300):
            used.update(g)
            out.append([E[b] for b in g])
    return out


def places(recs):
    """Places with repeats in 2+ rides, newest session first."""
    found = []
    for r in recs:
        if r["track"]["lat"] and "running" not in r["type"]:
            for g in sessions(r):
                found.append((r, g, set().union(*(x["cells"] for x in g))))
    groups = []
    for r, g, cells in sorted(found, key=lambda x: x[0]["startTimeLocal"], reverse=True):
        for p in groups:
            if _ov(p["cells"], cells) >= 0.4:
                p["cells"] |= cells; p["s"].append((r, g)); break
        else:
            groups.append({"cells": set(cells), "s": [(r, g)]})
    out = []
    for p in groups:
        if len(p["s"]) < 2:
            continue
        ss = []
        for r, g in p["s"]:
            tr, t = r["track"], r["track"]["t"]
            turn = [abs((x["brg"] - g[0]["brg"] + 180) % 360 - 180) > 120 for x in g]
            gaps = [t[b["i"]] - t[a["j"]] for a, b in zip(g, g[1:])]
            ss.append({"id": r["activityId"], "n": r["activityName"], "s": r["startTimeLocal"][:10], "both": any(turn),
                       "rec": round(median(gaps)) if gaps else None,
                       "reps": [{"i": x["i"], "j": x["j"], "s": x["s"], "w": x["w"],
                                 "dir": "N NE E SE S SW W NW".split()[round(x["brg"] / 45) % 8]} for x in g]})
        r0, g0 = p["s"][0]
        tr = r0["track"]
        mid = g0[0]["i"] + (g0[0]["j"] - g0[0]["i"]) // 2
        km = dist(tr["lat"][0], tr["lon"][0], tr["lat"][mid], tr["lon"][mid]) / 1000
        out.append({"name": f'{"N NE E SE S SW W NW".split()[round(_bearing(tr, 0, mid) / 45) % 8]} {km:.0f} km from the start',
                    "sess": ss, "ids": [x["id"] for x in ss],
                    "repmin": round(median(x["s"] for s in ss for x in s["reps"]) / 60, 1),
                    "nreps": Counter(len(s["reps"]) for s in ss).most_common(1)[0][0],
                    "both": sum(s["both"] for s in ss)})
    return sorted(out, key=lambda p: len(p["sess"]), reverse=True)
