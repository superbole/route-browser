"""Write ~/.route-browser/routes.html from the fetch.py cache.

One self-contained page: every cached ride and run drawn faintly (runs start unticked) on an OSM map, an A-to-B search (rides
that passed within a radius of A and later of B), and filters (dates, ride type, home loops).

    python build_map.py              # build the page
    python build_map.py --self-test  # route library, stretch finder and A-to-B matcher on made-up tracks (needs node)

The page embeds your tracks, so it stays on your computer: never publish or upload it.
The matcher lives in MATCHER_JS below; the self-test runs that same string under node.
"""
import argparse
import datetime as dt
import html
import json
import math
import subprocess
import sys
from pathlib import Path

import loops

HOME = Path.home() / ".route-browser"  # outside every checkout, beside the cache (as in fetch.py)
CACHE, OUT, STATUS = HOME / "cache", HOME / "routes.html", HOME / "fetch_status.json"
LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4"


def encode(r):
    """Cache record -> compact page record. lat/lon/t/d are delta-coded ints (lat/lon in 1e-5 deg)."""
    tr = r["track"]
    lat = [round(x * 1e5) for x in tr["lat"]]
    lon = [round(x * 1e5) for x in tr["lon"]]
    d, acc = [], 0.0  # fill missing distance from geometry
    for k, v in enumerate(tr["d"]):
        if v is None:
            if k:
                p, q = math.radians(tr["lat"][k - 1]), math.radians(tr["lat"][k])
                acc += 6371000 * math.hypot(q - p, math.radians(tr["lon"][k] - tr["lon"][k - 1]) * math.cos(p))
            v = round(acc)
        acc = v
        d.append(v)
    delta = lambda xs: [b - a for a, b in zip([0] + xs, xs)]  # noqa: E731
    out = {"id": r["activityId"], "n": r["activityName"], "s": r["startTimeLocal"], "y": r["type"],
           "km": round((r["distance"] or d[-1]) / 1000, 1), "mv": round(r["movingDuration"] or r["duration"] or 0),
           "hr": r.get("averageHR"), "w": r.get("avgPower"),
           "la": delta(lat), "lo": delta(lon), "t": delta(tr["t"]), "d": delta(d)}
    for k in ("hr", "pw"):
        if any(v is not None for v in tr[k]):
            out["s" + k] = tr[k]
    return out


MATCHER_JS = r"""
function decode(r) {  // undo the delta coding from build_map.encode
  const cum = (xs, s) => { let a = 0; return xs.map(x => (a += x) * s); };
  r.lat = cum(r.la, 1e-5); r.lon = cum(r.lo, 1e-5); r.tt = cum(r.t, 1); r.dd = cum(r.d, 1);
  return r;
}
function dist(la1, lo1, la2, lo2) {  // metres, equirectangular: fine at these scales
  const x = (lo2 - lo1) * Math.cos((la1 + la2) * Math.PI / 360) * 111320, y = (la2 - la1) * 110540;
  return Math.hypot(x, y);
}
function passes(r, P, rad) {  // index of the closest point in each separate pass through the circle
  const out = []; let best = -1, bestD = Infinity;
  for (let k = 0; k < r.lat.length; k++) {
    const m = dist(r.lat[k], r.lon[k], P[0], P[1]);
    if (m <= rad) { if (m < bestD) { best = k; bestD = m; } }
    else if (best >= 0) { out.push(best); best = -1; bestD = Infinity; }
  }
  if (best >= 0) out.push(best);
  return out;
}
function matchDir(r, A, B, rad) {  // first B pass that has an A pass before it, with the latest such A
  const pa = passes(r, A, rad), pb = passes(r, B, rad);
  for (const j of pb) {
    const before = pa.filter(i => i < j);
    if (before.length) return {i: before[before.length - 1], j};
  }
  return null;
}
function matchAB(r, A, B, rad, either) {
  const m = matchDir(r, A, B, rad);
  if (m || !either) return m;
  const b = matchDir(r, B, A, rad);
  return b && {i: b.i, j: b.j, rev: true};
}
function segStats(r, i, j) {  // time-weighted averages; gaps over 30 s count as stops
  let mov = 0, hw = 0, ht = 0, pw = 0, pt = 0;
  for (let k = i + 1; k <= j; k++) {
    const dt = r.tt[k] - r.tt[k - 1];
    if (dt > 30) continue;
    mov += dt;
    if (r.shr && r.shr[k] != null) { hw += r.shr[k] * dt; ht += dt; }
    if (r.spw && r.spw[k] != null) { pw += r.spw[k] * dt; pt += dt; }
  }
  return {el: r.tt[j] - r.tt[i], mov, m: r.dd[j] - r.dd[i],
          hr: ht ? Math.round(hw / ht) : null, w: pt ? Math.round(pw / pt) : null};
}
function stretches(r, x, lvl, share, minS) {  // no-stop runs on route x's medoid r (loops.py writes x.sh)
  const sh = x.sh[lvl], n = sh.length, out = [];
  const mov = (i, j) => { let s = 0; for (let k = i + 1; k <= j; k++) { const dt = r.tt[k] - r.tt[k - 1]; if (dt <= 30) s += dt; } return s; };
  const push = (i, j) => {
    const s = mov(i, j), a = x.alt[i], b = x.alt[j], m = r.dd[j] - r.dd[i];
    if (s >= minS) out.push({i, j, s, km: +(r.dd[i] / 1000).toFixed(1), len: +(m / 1000).toFixed(1), long: s >= 1200, at: mov(0, i),
                             g: a != null && b != null && m > 0 ? +((b - a) / m * 100).toFixed(1) : null});
  };
  let st = null;
  for (let k = 0; k < n; k++) {
    const stop = k === 0 || k === n - 1 || sh[k] >= share;
    if (!stop && st === null) st = k;
    else if (stop && st !== null) { push(st, k - 1); st = null; }
  }
  const total = mov(0, n - 1), last = out[out.length - 1];
  out.warm = out.length ? out[0].at : null; out.home = last ? total - last.at - last.s : null;
  return out;
}
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ride routes</title>
<link rel="stylesheet" href="LEAFLET/leaflet.min.css">
<script src="LEAFLET/leaflet.min.js"></script>
<style>
:root { --bg:#fff; --fg:#1d1d1f; --mute:#6e6e73; --line:#e3e3e8; --acc:#d9480f; --hl:#1c7ed6; }
@media (prefers-color-scheme: dark) { :root { --bg:#1c1c1e; --fg:#f2f2f7; --mute:#a1a1a6; --line:#3a3a3c; } }
* { box-sizing: border-box; }
html, body { margin:0; height:100%; background:var(--bg); color:var(--fg); font:14px/1.4 system-ui, sans-serif; }
#wrap { display:flex; height:100%; }
#map { flex:1; }
#side { width:500px; overflow:auto; padding:12px 16px; border-left:1px solid var(--line); }
h2 { font-size:15px; margin:14px 0 6px; }
.row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:4px 0; }
.mute { color:var(--mute); font-size:12px; }
button { font:inherit; padding:3px 9px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); cursor:pointer; }
button.on { border-color:var(--acc); color:var(--acc); }
input[type=date], input[type=number], select { font:inherit; background:var(--bg); color:var(--fg); border:1px solid var(--line); border-radius:4px; }
table { width:100%; border-collapse:collapse; font-size:12.5px; }
th { text-align:left; cursor:pointer; border-bottom:1px solid var(--line); padding:3px 4px; white-space:nowrap; user-select:none; }
td { padding:3px 4px; border-bottom:1px solid var(--line); white-space:nowrap; }
tr.res { cursor:pointer; } tr.res:hover, tr.sel { background:rgba(28,126,214,.12); }
td.n { max-width:120px; overflow:hidden; text-overflow:ellipsis; }
.leaflet-container { background:#ddd; }
@media (max-width: 760px) { #wrap { flex-direction:column; } #map { flex:none; height:55vh; } #side { width:auto; border:0; } }
</style></head><body>
<div id="wrap"><div id="map"></div><div id="side">
  __BANNER__<div class="mute">__UPDATED__</div>
  <div class="row"><span class="mute"><span id="count"></span>. With A to B ticked, click the map to drop A, then B; drag them to adjust.</span>
    <button id="zoom">Zoom to shown rides</button></div>
  <h2>Filters</h2>
  <div class="row">From <input type="date" id="from"> to <input type="date" id="to"></div>
  <div class="row" id="types"></div>
  <div class="row"><label><input type="checkbox" id="home"> Only rides that started and ended at home</label></div>
  <h2><label><input type="checkbox" id="showroutes" checked> Routes you repeat</label></h2>
  <div id="routebox"><div class="mute">Rides grouped by route (same start, same finish, mostly the same roads). Click one to see it alone:
    <span style="color:#2f9e44">green</span> (two shades, so neighbours stand apart) = stretches with no stops at your usual pace;
    <span style="color:#e03131">red</span> = climbs that suit repeats. ★ = 20 min+, long enough for a 20-min rep.</div>
  <div class="row">A stop is slowing under <input type="range" id="slow" min="50" max="80" step="10" value="70"> <span id="slowv"></span> of usual speed</div>
  <div class="row">on at least <input type="range" id="share" min="10" max="60" step="5" value="25"> <span id="sharev"></span> of the rides there</div>
  <div class="row">Shortest stretch <input type="range" id="minlen" min="4" max="20" step="1" value="8"> <span id="minv"></span></div>
  <div class="mute">Less strict: speed slider left (only real slowdowns count), rides slider right (only spots where you often slow count).</div>
  <div class="row">Show <select id="rkind"><option value="">loops and one way</option><option value="loop">loops only</option>
    <option value="one">one way only</option></select> moving <input type="number" id="rmin" min="0" step="5" placeholder="any" style="width:64px">
    to <input type="number" id="rmax" min="0" step="5" placeholder="any" style="width:64px"> min</div>
  <table id="routes"></table>
  <div id="rdetail"></div></div>
  <h2><label><input type="checkbox" id="showplaces" checked> Places you do repeats</label></h2>
  <div id="placebox"><div class="mute">Roads where a ride with power had 3+ hard efforts on the same stretch (or 2 of 5 min+),
    in 2+ rides. Click one to see its sessions; reps are <span style="color:#ae3ec9">magenta</span> one way and
    <span style="color:#1098ad">teal</span> the other.</div>
  <table id="places"></table>
  <div id="pdetail"></div></div>
  <h2><label><input type="checkbox" id="showspots" checked> Possible new spots</label></h2>
  <div id="spotbox"><div class="mute">No-stop stretches and climbs on routes you ride that you have not used for repeats yet,
    longest first. The route sliders above set what counts. "Both ways" = also stop-free heading the other way on one of your routes.
    Click one to see it in orange.</div>
  <table id="spots"></table></div>
  <h2><label><input type="checkbox" id="showab" checked> A to B</label></h2>
  <div id="abbox"><div class="row">
    <button id="setA">Move A</button><button id="setB">Move B</button><button id="clear">Clear</button>
    <label><input type="checkbox" id="either"> Either direction</label>
  </div>
  <div class="row">Radius <input type="range" id="rad" min="30" max="500" step="10" value="100"> <span id="radv">100 m</span></div>
  <div id="summary" class="mute"></div>
  <table id="res"></table></div>
</div></div>
<script>
const RIDES = __RIDES__, ROUTES = __ROUTES__, PLACES = __PLACES__;
__MATCHER__
const $ = id => document.getElementById(id);
// ticks and sliders are remembered in this browser (per viewer, never shared); the page works without it
const KEEP = ['showroutes', 'showplaces', 'showspots', 'showab', 'home', 'either', 'slow', 'share', 'minlen', 'rad', 'rkind', 'rmin', 'rmax'];
const kept = (() => { try { return JSON.parse(localStorage.getItem('route-browser-ui') || '{}'); } catch (e) { return {}; } })();
KEEP.forEach(id => { if (id in kept) { const e = $(id); if (e.type === 'checkbox') e.checked = kept[id]; else e.value = kept[id]; } });
function keep() {
  const o = Object.fromEntries(KEEP.map(id => { const e = $(id); return [id, e.type === 'checkbox' ? e.checked : e.value]; }));
  o.types = [...$('types').querySelectorAll('input')].filter(i => i.checked).map(i => i.value);
  try { localStorage.setItem('route-browser-ui', JSON.stringify(o)); } catch (e) {}
}
document.addEventListener('change', keep);
RIDES.forEach(decode);
const map = L.map('map', {preferCanvas: true});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'}).addTo(map);
const fmtT = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}` : `${m}:${String(x).padStart(2,'0')}`; };
const link = r => `https://connect.garmin.com/modern/activity/${r.id}`;
const FAINT = {color: '#7048e8', weight: 2, opacity: 0.35}, HOVER = {color: '#7048e8', weight: 4, opacity: 0.9};

// home = the most common start point (~200 m grid), computed here and never written anywhere
const cells = {};
RIDES.forEach(r => { const k = Math.round(r.lat[0] * 500) + ',' + Math.round(r.lon[0] * 500); (cells[k] = cells[k] || []).push(r); });
const homeRides = Object.values(cells).sort((a, b) => b.length - a.length)[0] || [];
const HOME = homeRides.length ? [homeRides.reduce((s, r) => s + r.lat[0], 0) / homeRides.length,
                                 homeRides.reduce((s, r) => s + r.lon[0], 0) / homeRides.length] : null;
RIDES.forEach(r => { const e = r.lat.length - 1;
  r.homeLoop = !!HOME && dist(r.lat[0], r.lon[0], HOME[0], HOME[1]) < 400 && dist(r.lat[e], r.lon[e], HOME[0], HOME[1]) < 400; });

RIDES.forEach(r => {
  r.line = L.polyline(r.lat.map((la, k) => [la, r.lon[k]]), FAINT)
    .bindTooltip(`${r.n} · ${r.s.slice(0, 10)}`, {sticky: true})
    .bindPopup(`<b>${r.n}</b><br>${r.s.slice(0, 16)} · ${r.y.replace(/_/g, ' ')}<br>${r.km} km · ${fmtT(r.mv)} moving` +
               `${r.w ? ' · ' + Math.round(r.w) + ' W' : ''}${r.hr ? ' · ' + Math.round(r.hr) + ' bpm' : ''}` +
               `<br><a href="${link(r)}" target="_blank" rel="noopener">Open in Garmin Connect</a>`)
    .on('mouseover', e => { if (r !== sel) e.target.setStyle(HOVER); })
    .on('mouseout', e => { if (r !== sel) e.target.setStyle(FAINT); });
});
// open on the rides that start within 30 km of home, so a holiday ride does not zoom out to the country
const local = RIDES.filter(r => HOME && dist(r.lat[0], r.lon[0], HOME[0], HOME[1]) < 30000);
if (RIDES.length) map.fitBounds(L.featureGroup((local.length ? local : RIDES).map(r => r.line)).getBounds());
else map.setView([0, 0], 2);

// filters
const types = [...new Set(RIDES.map(r => r.y))].sort();
const typeOn = t => kept.types ? kept.types.includes(t) : !t.includes('running');  // a new type not seen before shows unless it is running
$('types').innerHTML = types.map(t => `<label><input type="checkbox" value="${t}"${typeOn(t) ? ' checked' : ''}> ${t.replace(/_/g, ' ')}</label>`).join(' ');
const dates = RIDES.map(r => r.s.slice(0, 10)).sort();
$('from').value = dates[0] || ''; $('to').value = dates[dates.length - 1] || '';
function visible() {
  const on = new Set([...$('types').querySelectorAll('input:checked')].map(i => i.value));
  const f = $('from').value, t = $('to').value, h = $('home').checked;
  const only = (selRoute || selPlace) && new Set((selRoute || selPlace).ids);
  return RIDES.filter(r => on.has(r.y) && (!f || r.s.slice(0, 10) >= f) && (!t || r.s.slice(0, 10) <= t) && (!h || r.homeLoop) &&
                           (!only || only.has(r.id)));
}

// routes you repeat (loops.py): click one to see only its rides, its stretches and its climbs
let selRoute = null, routeLayer = null, parts = [], hot = null;
const byId = Object.fromEntries(RIDES.map(r => [r.id, r]));
const rname = x => `${x.loop ? 'Loop' : 'One way'} ${Math.round(x.km)} km ${x.dir}`;
const min = s => Math.round(s / 60) + ' min';
const GREENS = ['#2b8a3e', '#94d82d'], RED = '#e03131', HOT = '#f76707';  // alternate so neighbours stand apart
const pstyle = p => ({color: p.c, weight: 7, opacity: .95});
function recompute() {
  const lvl = +$('slow').value, share = +$('share').value, minS = +$('minlen').value * 60;
  $('slowv').textContent = lvl + '%'; $('sharev').textContent = share + '%'; $('minv').textContent = $('minlen').value + ' min';
  ROUTES.forEach(x => { x.stretches = stretches(byId[x.med], x, lvl, share, minS); x.warm = x.stretches.warm; x.home = x.stretches.home; });
}
recompute();
['slow', 'share', 'minlen'].forEach(id => $(id).oninput = () => { recompute(); if (selRoute) pickRoute(selRoute, true); else { renderRoutes(); renderSpots(); } });
// routes table: click a heading to sort; the kind and moving-time filters narrow it (e.g. a 1-hour loop: loops, 50 to 70)
let rSort = 'n', rDir = -1;
const RCOLS = [['name', 'Route', x => rname(x)], ['n', 'Rides', x => x.ids.length], ['km', 'km', x => x.km], ['mv', 'Moving', x => x.mv],
               ['up', 'Climb', x => x.up], ['start', 'Usually', x => x.start], ['ns', 'Stretches', x => x.stretches.length]];
['rkind', 'rmin', 'rmax'].forEach(id => $(id).oninput = () => { renderRoutes(); keep(); });
function renderRoutes() {
  const on = $('showroutes').checked;
  $('routebox').style.display = on ? '' : 'none';
  if (!on) return;
  const kind = $('rkind').value, lo = $('rmin').value, hi = $('rmax').value;
  const rows = ROUTES.filter(x => (!kind || x.loop === (kind === 'loop')) && (lo === '' || x.mv >= lo * 60) && (hi === '' || x.mv <= hi * 60))
    .sort((a, b) => { const x = RCOLS.find(c => c[0] === rSort)[2](a), y = RCOLS.find(c => c[0] === rSort)[2](b);
      return (x < y ? -1 : x > y ? 1 : 0) * rDir; });
  $('routes').innerHTML = '<tr>' + RCOLS.map(([k, l]) => `<th data-k="${k}">${l}${k === rSort ? (rDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    (rows.length ? '' : '<tr><td colspan="7" class="mute">No route matches. Widen the moving time or show both kinds.</td></tr>') +
    rows.map(x => `<tr class="res${x === selRoute ? ' sel' : ''}" data-k="${ROUTES.indexOf(x)}"><td>${rname(x)}</td><td>${x.ids.length}</td>` +
      `<td>${x.km}</td><td>${fmtT(x.mv)}</td><td>${x.up} m</td><td>${x.days.map(d => d[0]).join(' ')} ${x.start}</td>` +
      `<td>${x.stretches.length}${x.stretches.some(s => s.long) ? ' (' + x.stretches.filter(s => s.long).length + ' of 20 min+)' : ''}</td></tr>`).join('');
  $('routes').querySelectorAll('th').forEach(th => th.onclick = () => {
    const k = th.dataset.k; rDir = k === rSort ? -rDir : (k === 'name' || k === 'start' ? 1 : -1); rSort = k; renderRoutes(); });
  $('routes').querySelectorAll('tr.res').forEach(tr => tr.onclick = () => pickRoute(ROUTES[+tr.dataset.k]));
  const x = selRoute;
  const box = p => `<td><input type="checkbox" data-p="${parts.indexOf(p)}"${p.on ? ' checked' : ''} title="Show on the map"></td>`;
  const sw = p => `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${p === hot ? HOT : p.c}"></span>`;
  const st = parts.filter(p => p.kind === 's'), cl = parts.filter(p => p.kind === 'c');
  $('rdetail').innerHTML = !x ? '' : `<p><b>${rname(x)}</b>, ridden ${x.ids.length} times. Typical ride: ${x.km} km, ${fmtT(x.mv)} moving, ` +
    `${fmtT(x.el)} elapsed, ${x.up} m climbing. Drawn on your ${byId[x.med].s.slice(0, 10)} ride, the most typical one. ` +
    `<button id="unroute">Show all rides</button></p>` +
    (st.length ? `<p>Warm-up to the first stretch: ${min(x.warm)}. Last stretch to the finish: ${min(x.home)}. Click a row to light it up in orange.</p>` +
      '<table><tr><th></th><th>Stretch starts</th><th>Lasts</th><th>km</th><th>Gradient</th></tr>' +
      st.map(p => `<tr class="res${p === hot ? ' sel' : ''}" data-p="${parts.indexOf(p)}">${box(p)}<td>${sw(p)} km ${p.d.km} (${min(p.d.at)} in)</td>` +
        `<td>${min(p.d.s)}${p.d.long ? ' ★' : ''}</td><td>${p.d.len}</td><td>${p.d.g ?? ''}%</td></tr>`).join('') + '</table>'
      : '<p>No stretch of 8 min+ without stops.</p>') +
    (cl.length ? '<table><tr><th></th><th>Climb starts</th><th>Lasts</th><th>km</th><th>Gain</th><th>Gradient</th></tr>' +
      cl.map(p => `<tr class="res${p === hot ? ' sel' : ''}" data-p="${parts.indexOf(p)}">${box(p)}<td>${sw(p)} km ${p.d.km} (${min(p.d.at)} in)</td>` +
        `<td>${fmtT(p.d.s)}</td><td>${p.d.len}</td><td>${p.d.gain} m</td><td>${p.d.g}%</td></tr>`).join('') + '</table>' : '');
  if (!x) return;
  $('unroute').onclick = () => pickRoute(null);
  $('rdetail').querySelectorAll('input[data-p]').forEach(cb => cb.onclick = e => {
    e.stopPropagation(); const p = parts[+cb.dataset.p]; p.on = cb.checked;
    if (p.on) routeLayer.addLayer(p.line); else { routeLayer.removeLayer(p.line); if (p === hot) hot = null; }
    renderRoutes(); });
  $('rdetail').querySelectorAll('tr[data-p]').forEach(tr => tr.onclick = () => light(parts[+tr.dataset.p]));
}
const part = (r, p) => { const ll = []; for (let k = p.i; k <= p.j; k++) ll.push([r.lat[k], r.lon[k]]); return ll; };
function light(p) {  // one stretch or climb in orange; click it again to put it back
  if (hot) hot.line.setStyle(pstyle(hot));
  hot = p === hot ? null : p;
  if (hot) {
    if (!hot.on) { hot.on = true; routeLayer.addLayer(hot.line); }
    hot.line.setStyle({color: HOT, weight: 10, opacity: 1}).bringToFront();
    map.fitBounds(hot.line.getBounds(), {maxZoom: 16});
  }
  renderRoutes();
}
function pickRoute(x, keepView) {
  if (x && selPlace) pickPlace(null);
  selRoute = x; hot = null; parts = [];
  if (routeLayer) { routeLayer.remove(); routeLayer = null; }
  if (x) {
    const r = byId[x.med];
    parts = [...x.stretches.map((d, k) => ({kind: 's', d, c: GREENS[k % 2]})), ...x.climbs.map(d => ({kind: 'c', d, c: RED}))];
    parts.forEach(p => { p.on = true;
      p.line = L.polyline(part(r, p.d), pstyle(p)).on('click', () => light(p)).bindTooltip(p.kind === 's'
        ? `No stops: ${min(p.d.s)}, ${p.d.len} km, ${p.d.g ?? '?'}%, from km ${p.d.km}`
        : `Climb: ${fmtT(p.d.s)}, ${p.d.len} km, +${p.d.gain} m at ${p.d.g}%, from km ${p.d.km}`, {sticky: true}); });
    routeLayer = L.featureGroup([L.polyline(part(r, {i: 0, j: r.lat.length - 1}), {color: '#1c7ed6', weight: 4, opacity: .8}),
                                 ...parts.map(p => p.line)]).addTo(map);
    if (!keepView) map.fitBounds(routeLayer.getBounds());
  }
  update();
}
$('showroutes').onchange = () => { if (!$('showroutes').checked && selRoute) pickRoute(null); else renderRoutes(); };

// places you do repeats (loops.places): click one for its sessions, a session to draw its reps
let selPlace = null, selSess = null, placeLayer = null;
const REPCOL = ['#ae3ec9', '#1098ad'];
function renderPlaces() {
  const on = $('showplaces').checked;
  $('placebox').style.display = on ? '' : 'none';
  if (!on) return;
  $('places').innerHTML = !PLACES.length ? '<tr><td class="mute">None found yet: it needs rides with power.</td></tr>' :
    '<tr><th>Place</th><th>Times</th><th>Usually</th><th>Both ways</th><th>Last</th></tr>' +
    PLACES.map((p, k) => `<tr class="res${p === selPlace ? ' sel' : ''}" data-k="${k}"><td>${p.name}</td><td>${p.sess.length}</td>` +
      `<td>${p.nreps} x ${p.repmin} min</td><td>${p.both} of ${p.sess.length}</td><td>${p.sess[0].s}</td></tr>`).join('');
  $('places').querySelectorAll('tr.res').forEach(tr => tr.onclick = () => pickPlace(PLACES[+tr.dataset.k]));
  const p = selPlace;
  $('pdetail').innerHTML = !p ? '' : `<p><b>${p.name}</b>: repeats in ${p.sess.length} rides. Click a session to draw its reps. ` +
    `<button id="unplace">Show all rides</button></p><table><tr><th>Date</th><th>Ride</th><th>Reps</th><th>W</th><th>Style</th><th>Between</th></tr>` +
    p.sess.map((x, k) => `<tr class="res${x === selSess ? ' sel' : ''}" data-k="${k}"><td>${x.s}</td><td class="n" title="${x.n}">${x.n}</td>` +
      `<td>${x.reps.length} x ${Math.round(x.reps.reduce((a, r) => a + r.s, 0) / x.reps.length / 60 * 10) / 10} min</td>` +
      `<td>${Math.round(x.reps.reduce((a, r) => a + r.w, 0) / x.reps.length)}</td><td>${x.both ? 'both ways' : 'one way'}</td>` +
      `<td>${x.rec != null ? min(x.rec) : ''}</td></tr>`).join('') + '</table>';
  if (!p) return;
  $('unplace').onclick = () => pickPlace(null);
  $('pdetail').querySelectorAll('tr.res').forEach(tr => tr.onclick = () => drawSess(p.sess[+tr.dataset.k]));
}
function drawSess(x) {
  selSess = x;
  if (placeLayer) placeLayer.remove();
  const r = byId[x.id], d0 = x.reps[0].dir;
  placeLayer = L.featureGroup([L.polyline(part(r, {i: 0, j: r.lat.length - 1}), {color: '#1c7ed6', weight: 3, opacity: .7}),
    ...x.reps.map((p, k) => L.polyline(part(r, p), {color: REPCOL[p.dir === d0 ? 0 : 1], weight: 7, opacity: .9})
      .bindTooltip(`Rep ${k + 1}: ${fmtT(p.s)}, ${p.w} W, heading ${p.dir}`, {sticky: true}))]).addTo(map);
  map.fitBounds(L.featureGroup(placeLayer.getLayers().slice(1)).getBounds(), {maxZoom: 16});
  renderPlaces();
}
function pickPlace(p) {
  if (p && selRoute) pickRoute(null);
  selPlace = p; selSess = null;
  if (placeLayer) { placeLayer.remove(); placeLayer = null; }
  update();
  if (p) drawSess(p.sess[0]);
}
$('showplaces').onchange = () => { if (!$('showplaces').checked && selPlace) pickPlace(null); else renderPlaces(); };

// possible new spots: route stretches and climbs that no repeat place covers (~50 m cells, as in loops.py)
const ck = (la, lo) => Math.round(la * 2000) + ',' + Math.round(lo * 2000);
const usedCells = new Set();
PLACES.forEach(p => p.sess.forEach(x => { const r = byId[x.id];
  x.reps.forEach(q => { for (let k = q.i; k <= q.j; k++) usedCells.add(ck(r.lat[k], r.lon[k])); }); }));
let SPOTS = [], selSpot = null, spotLine = null;
const brg = (r, d) => (Math.atan2((r.lon[d.j] - r.lon[d.i]) * Math.cos(r.lat[d.i] * Math.PI / 180), r.lat[d.j] - r.lat[d.i]) * 180 / Math.PI + 360) % 360;
const share = (a, b) => { let n = 0; a.forEach(q => n += b.has(q)); return n / Math.min(a.size, b.size); };
function findSpots() {
  const all = [];
  ROUTES.forEach(x => { const r = byId[x.med];
    [...x.stretches.map(d => ({x, r, d, kind: 'No stops'})), ...x.climbs.map(d => ({x, r, d, kind: 'Climb'}))].forEach(c => {
      c.cells = new Set(); for (let k = c.d.i; k <= c.d.j; k++) c.cells.add(ck(r.lat[k], r.lon[k]));
      let u = 0; c.cells.forEach(q => u += usedCells.has(q));
      if (u / c.cells.size < .2) { c.b = brg(r, c.d); all.push(c); } }); });
  all.sort((a, b) => b.d.s - a.d.s);
  SPOTS = [];
  for (const c of all) {  // the same road on several routes is one spot; seen the other way round, it is "both ways"
    const o = SPOTS.find(o => o.kind === c.kind && share(c.cells, o.cells) >= .5);
    if (!o) SPOTS.push(c); else if (Math.abs((c.b - o.b + 540) % 360 - 180) > 120) o.both = true;
  }
  if (selSpot && !SPOTS.includes(selSpot)) pickSpot(null);
}
function renderSpots() {
  const on = $('showspots').checked;
  $('spotbox').style.display = on ? '' : 'none';
  if (!on) return;
  findSpots();
  $('spots').innerHTML = !SPOTS.length ? '<tr><td class="mute">None at these settings.</td></tr>' :
    '<tr><th>On</th><th>Starts</th><th>Kind</th><th>Lasts</th><th>km</th><th>Grad.</th><th>Both ways</th></tr>' +
    SPOTS.slice(0, 30).map((c, k) => `<tr class="res${c === selSpot ? ' sel' : ''}" data-k="${k}"><td>${rname(c.x)}</td><td>km ${c.d.km}</td>` +
      `<td>${c.kind}</td><td>${min(c.d.s)}</td><td>${c.d.len}</td><td>${c.d.g ?? ''}%</td><td>${c.both ? '✓' : ''}</td></tr>`).join('');
  $('spots').querySelectorAll('tr.res').forEach(tr => tr.onclick = () => pickSpot(SPOTS[+tr.dataset.k]));
}
function pickSpot(c) {
  if (spotLine) { spotLine.remove(); spotLine = null; }
  selSpot = c === selSpot ? null : c;
  if (selSpot) {
    spotLine = L.polyline(part(selSpot.r, selSpot.d), {color: HOT, weight: 10, opacity: 1})
      .bindTooltip(`${selSpot.kind}: ${min(selSpot.d.s)}, ${selSpot.d.len} km, ${selSpot.d.g ?? '?'}%`, {sticky: true}).addTo(map);
    map.fitBounds(spotLine.getBounds(), {maxZoom: 15});
  }
  renderSpots();
}
$('showspots').onchange = () => { if (!$('showspots').checked && selSpot) pickSpot(selSpot); else renderSpots(); };

// A-to-B
let A = null, B = null, active = null, sel = null, segLine = null, results = [], shown = [], sortKey = 's', sortDir = -1;
$('zoom').onclick = () => { if (shown.length) map.fitBounds(L.featureGroup(shown.map(r => r.line)).getBounds()); };
const mk = (lbl, col) => L.marker([0, 0], {draggable: true, icon: L.divIcon({className: '', iconSize: [24, 24], iconAnchor: [12, 12],
  html: `<div style="width:24px;height:24px;border-radius:50%;background:${col};color:#fff;font-weight:700;text-align:center;line-height:24px;border:2px solid #fff">${lbl}</div>`})});
const pt = {A: {m: mk('A', '#2b8a3e'), c: L.circle([0, 0], {radius: +$('rad').value, color: '#2b8a3e', weight: 1, fillOpacity: .08})},
            B: {m: mk('B', '#c92a2a'), c: L.circle([0, 0], {radius: +$('rad').value, color: '#c92a2a', weight: 1, fillOpacity: .08})}};
$('radv').textContent = $('rad').value + ' m';
function place(which, ll) {
  const p = pt[which]; p.m.setLatLng(ll).addTo(map); p.c.setLatLng(ll).addTo(map);
  if (which === 'A') A = [ll.lat, ll.lng]; else B = [ll.lat, ll.lng];
}
['A', 'B'].forEach(w => pt[w].m.on('drag', e => { pt[w].c.setLatLng(e.latlng); }).on('dragend', e => { place(w, e.target.getLatLng()); update(); }));
map.on('click', e => {
  if (!$('showab').checked) return;
  const w = active || (!A ? 'A' : !B ? 'B' : null);
  if (!w) return;
  place(w, e.latlng); active = null; $('setA').className = $('setB').className = ''; update();
});
['A', 'B'].forEach(w => $('set' + w).onclick = () => { active = active === w ? null : w;
  $('setA').className = active === 'A' ? 'on' : ''; $('setB').className = active === 'B' ? 'on' : ''; });
$('clear').onclick = () => { A = B = null; ['A', 'B'].forEach(w => { pt[w].m.remove(); pt[w].c.remove(); }); update(); };
function showAB() { $('abbox').style.display = $('showab').checked ? '' : 'none'; }
$('showab').onchange = () => { if (!$('showab').checked && (A || B)) $('clear').onclick(); showAB(); };
showAB();
$('rad').oninput = () => { $('radv').textContent = $('rad').value + ' m'; pt.A.c.setRadius(+$('rad').value); pt.B.c.setRadius(+$('rad').value); };
$('rad').onchange = update;
['from', 'to', 'home', 'either'].forEach(id => $(id).onchange = update);
$('types').onchange = update;

const COLS = [['s', 'Date'], ['n', 'Ride'], ['el', 'Elapsed'], ['mov', 'Moving'], ['m', 'km'], ['kmh', 'km/h'], ['w', 'W'], ['hr', 'bpm']];
function update() {
  let vis = visible();
  results = [];
  if (A && B) {
    const rad = +$('rad').value, either = $('either').checked;
    for (const r of vis) {
      const m = matchAB(r, A, B, rad, either);
      if (m) { const s = segStats(r, m.i, m.j); results.push({r, ...m, ...s, s: r.s, n: r.n, kmh: s.mov ? s.m / s.mov * 3.6 : 0}); }
    }
    vis = results.map(x => x.r);  // a search narrows the map to its matches too
    $('summary').textContent = `${results.length} ride${results.length === 1 ? '' : 's'} went ${either ? 'between A and B' : 'from A to B'}. Clear to see all rides again.`;
  } else $('summary').textContent = A ? 'Now drop B.' : '';
  const vset = new Set(vis);
  RIDES.forEach(r => { if (vset.has(r)) r.line.addTo(map); else r.line.remove(); });
  shown = vis;
  $('count').textContent = `${vis.length} of ${RIDES.length} rides shown`;
  if (sel && !results.some(x => x.r === sel)) select(null);
  if (routeLayer) routeLayer.bringToFront();
  render(); renderRoutes(); renderPlaces(); renderSpots();
}
function render() {
  const rows = [...results].sort((a, b) => { const x = a[sortKey], y = b[sortKey];
    return (x == null) - (y == null) || (x < y ? -1 : x > y ? 1 : 0) * sortDir; });
  $('res').innerHTML = !results.length ? '' :
    '<tr>' + COLS.map(([k, l]) => `<th data-k="${k}">${l}${k === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>' +
    rows.map((x, k) => `<tr class="res${x.r === sel ? ' sel' : ''}" data-k="${k}"><td>${x.s.slice(0, 10)}</td>` +
      `<td class="n" title="${x.n}">${x.rev ? '↩ ' : ''}${x.n}</td><td>${fmtT(x.el)}</td><td>${fmtT(x.mov)}</td><td>${(x.m / 1000).toFixed(1)}</td>` +
      `<td>${x.kmh.toFixed(1)}</td><td>${x.w ?? ''}</td><td>${x.hr ?? ''}</td></tr>`).join('');
  $('res').querySelectorAll('th').forEach(th => th.onclick = () => {
    const k = th.dataset.k; sortDir = k === sortKey ? -sortDir : (k === 'n' ? 1 : -1); sortKey = k; render(); });
  $('res').querySelectorAll('tr.res').forEach(tr => tr.onclick = () => select(rows[+tr.dataset.k]));
}
function select(x) {
  if (sel) sel.line.setStyle(FAINT);
  if (segLine) { segLine.remove(); segLine = null; }
  sel = x ? x.r : null;
  if (x) {
    sel.line.setStyle({color: '#1c7ed6', weight: 4, opacity: 0.9}).bringToFront();
    const ll = []; for (let k = x.i; k <= x.j; k++) ll.push([sel.lat[k], sel.lon[k]]);
    segLine = L.polyline(ll, {color: '#d9480f', weight: 6, opacity: 0.95}).addTo(map);
    map.fitBounds(L.featureGroup([sel.line]).getBounds(), {maxZoom: 15});
  }
  render();
}
update();
</script></body></html>
"""


def build():
    recs = [json.loads(p.read_text()) for p in sorted(CACHE.glob("*.json"))]
    rides = sorted((encode(r) for r in recs if r["track"]["lat"]), key=lambda r: r["s"])
    rts = [x for x in loops.routes(recs) if x["far"] >= 1]  # under 1 km out = trainer or a circuit
    pls = loops.places(recs)
    st = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    latest = max((r["s"][:10] for r in rides), default="none")
    updated = f"Updated {dt.datetime.now():%Y-%m-%d %H:%M}. Latest ride {latest}."
    banner = "" if st.get("ok", True) else (
        '<div style="background:#c92a2a;color:#fff;padding:6px 9px;border-radius:6px;margin-bottom:6px">'
        f'The last Garmin fetch failed ({html.escape(st["when"])}): {html.escape(st["msg"])}. New rides are missing. '
        'If the key was refused, make a new one (README: The Garmin key).</div>')
    page = (PAGE.replace("LEAFLET", LEAFLET).replace("__MATCHER__", MATCHER_JS)
            .replace("__BANNER__", banner).replace("__UPDATED__", updated)
            .replace("__ROUTES__", json.dumps(rts, separators=(",", ":")))
            .replace("__PLACES__", json.dumps(pls, separators=(",", ":")))
            .replace("__RIDES__", json.dumps(rides, separators=(",", ":"))))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"{len(rides)} rides ({len(recs) - len(rides)} without GPS skipped), {len(rts)} routes, {len(pls)} repeat places -> {OUT} "
          f"({OUT.stat().st_size / 1e6:.1f} MB)")


def self_test():
    """Synthetic tracks along a meridian: A at 0.000 lat, B at 0.010 (about 1.1 km apart)."""
    def ride(rid, lats, lon=0.0):
        n = len(lats)
        return encode({"activityId": rid, "activityName": rid, "startTimeLocal": "2026-01-01 08:00:00",
                       "type": "cycling", "distance": None, "movingDuration": n * 10, "duration": None,
                       "track": {"lat": lats, "lon": [lon] * n, "t": [k * 10 for k in range(n)],
                                 "d": [None] * n, "alt": [None] * n, "hr": [140] * n, "pw": [200] * n}})
    up = [k / 1000 for k in range(-3, 14)]           # passes A then B
    fixture = [ride("ab", up), ride("ba", up[::-1]), ride("miss", up, lon=0.01),  # 'miss' runs ~1.1 km east
               ride("loop", up + up[::-1] + up)]                                  # A, B, A, B: shortest A->B wins
    js = MATCHER_JS + """
const R = %s.map(decode), A = [0, 0], B = [0.01, 0], by = id => R.find(r => r.id === id);
const assert = (c, m) => { if (!c) { console.error('FAIL: ' + m); process.exit(1); } };
const ab = matchAB(by('ab'), A, B, 100, false);
assert(ab && ab.i === 3 && ab.j === 13, 'A then B matches at the closest points ' + JSON.stringify(ab));
const s = segStats(by('ab'), ab.i, ab.j);
assert(s.el === 100 && Math.abs(s.m - 1112) < 5 && s.hr === 140 && s.w === 200, 'segment stats ' + JSON.stringify(s));
assert(matchAB(by('ba'), A, B, 100, false) === null, 'B then A does not match one-way');
const rev = matchAB(by('ba'), A, B, 100, true);
assert(rev && rev.rev, 'B then A matches with either direction');
assert(matchAB(by('miss'), A, B, 100, true) === null, 'a track that misses A never matches');
const lp = matchAB(by('loop'), A, B, 100, false);
assert(lp && lp.i === 3 && lp.j === 13, 'first A->B pass on a repeated loop ' + JSON.stringify(lp));
assert(matchAB(by('miss'), A, B, 1200, false) !== null, 'radius is honoured');
console.log('matcher OK: 7 assertions');
""" % json.dumps(fixture)
    # the route library: two rides of one road with a stop at the same place both times, plus another road
    def rec(rid, lon, stop_at=None):
        lat, t, now = [k * 0.0002 for k in range(500)], [], 0  # 11 km north at 20 km/h
        for k in range(500):
            now += 64 if k == stop_at else 4
            t.append(now)
        return {"activityId": rid, "activityName": rid, "startTimeLocal": "2026-01-05 06:00:00", "type": "road_biking",
                "distance": 11000.0, "movingDuration": 2000, "duration": 2060, "elevationGain": 0,
                "track": {"lat": lat, "lon": [lon] * 500, "t": t, "d": [None] * 500, "alt": [1000.0] * 500,
                          "hr": [None] * 500, "pw": [200] * 500}}
    recs = [rec("a", 0.0, 250), rec("b", 0.0, 250), rec("c", 0.05)]
    rts = loops.routes(recs)
    assert len(rts) == 1 and sorted(rts[0]["ids"]) == ["a", "b"], "two rides of one road make one route; c is apart"
    sh = rts[0]["sh"][70]
    assert max(sh[:240]) == 0 and max(sh[240:260]) == 100 and max(sh[262:]) == 0, f"only the shared stop is marked: {sh[240:262]}"
    def reps_ride(rid):
        lat, lon, pw = [0.0] * 200, [-0.04 + k * 0.0002 for k in range(200)], [150] * 200  # warm-up east
        for _ in range(3):
            up = [k * 0.0002 for k in range(110)]
            lat += up + up[::-1]; lon += [0.0] * 220; pw += [300] * 110 + [150] * 110      # rep north, easy back
        lat += [0.0] * 200; lon += [-k * 0.0002 for k in range(200)]; pw += [150] * 200
        n = len(lat)
        return {"activityId": rid, "activityName": rid, "startTimeLocal": "2026-01-06 06:00:00", "type": "road_biking",
                "distance": None, "movingDuration": n * 4, "duration": n * 4, "elevationGain": 0,
                "track": {"lat": lat, "lon": lon, "t": [k * 4 for k in range(n)], "d": [None] * n, "alt": [1000.0] * n,
                          "hr": [None] * n, "pw": pw}}
    pls = loops.places([reps_ride("r1"), reps_ride("r2"), rec("flat", 0.0)])
    assert len(pls) == 1 and sorted(pls[0]["ids"]) == ["r1", "r2"], f"two sessions on one road make one place: {pls}"
    assert pls[0]["nreps"] == 3 and pls[0]["both"] == 0, f"3 reps, all heading north: {pls[0]}"
    assert all(380 <= x["rec"] <= 500 for x in pls[0]["sess"]), f"~7 min easy between reps: {pls[0]['sess']}"
    print("route library OK: 5 assertions")
    js += """
const X = %s, M = decode(%s);
const st = stretches(M, X, 70, 25, 480);
assert(st.length === 2 && st[0].j < 250 && st[1].i > 250, 'the shared stop splits the road in two ' + JSON.stringify(st));
assert(st.every(x => x.s >= 960 && x.s <= 1000), 'each half is ~16 min moving ' + JSON.stringify(st));
assert(stretches(M, X, 70, 101, 480).length === 1, 'a stop no ride reaches the threshold for does not split');
assert(stretches(M, X, 70, 25, 1200).length === 0, 'the shortest-stretch slider drops short ones');
console.log('stretch finder OK: 4 assertions');
""" % (json.dumps(rts[0]), json.dumps(encode(next(r for r in recs if r["activityId"] == rts[0]["med"]))))
    try:
        res = subprocess.run(["node", "-"], input=js, text=True, capture_output=True)
    except FileNotFoundError:
        sys.exit("self-test needs node on PATH (the matcher is the page's own JavaScript)")
    print(res.stdout.strip() or res.stderr.strip())
    sys.exit(res.returncode)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    self_test() if ap.parse_args().self_test else build()
