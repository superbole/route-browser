# Changelog

Newest first. What shipped and when; why it is like this is in [docs/decisions.md](docs/decisions.md).

### 2026-11-24 — New spots for finding a test road
- Stop sliders and the loop / one-way / ride-time filters show on both Routes and New spots (one set,
  moved between tabs). Shortest stretch goes to 60 min, with an optional longest.
- New spots: a Ride column (the route's moving time); the length limits cover climbs too.
- Fixed: the Filters box (types, dates, home) never applied to Routes or New spots, so one-way routes
  showed with "home" ticked. A route now shows when any of its rides passes.
- Fixed: clicking a New spots row dropped the pick at once (the list rebuilt with new rows). It now
  stays picked, draws in orange, and narrows the map to that route's rides.
- A picked spot has "Each ride on this stretch", which opens A to B on its ends (time, W, bpm per
  ride), and a test window: N min at a speed you set, slid along the stretch, giving start and finish
  km and a warning when it does not fit.

### 2026-11-21 — Tabs and a route builder
- The side panel's sections are tabs under the filters: Routes you repeat, Repeat places, New spots,
  A to B and the new Route builder. Leaving a tab puts the map back to all rides.
- Route builder: click points in order; each leg is routed along roads you have ridden (pieces of
  different rides joined) by your average moving time, with up to two alternatives, and a total.
  It turns only where a ride turned, so a bridge is not a junction and there is no U-turn across a
  central barrier onto the other carriageway.
- Fixed: a click right on a ride opened its popup instead of dropping the A-to-B point.
- Fixed: a double-clicked `routes.html` showed OpenStreetMap's "Access blocked" squares instead of a
  map. Tiles now come from Esri's World Street Map.
- Self-test covers the router: three rides joined, the slower alternative, a detour left out, one-way
  roads, a bridge, and a dual carriageway.

### 2026-11-19 — First release
- Fetches outdoor rides and runs from the Garmin Personal API (FIT and TCX downloads) into
  `~/.route-browser/cache`, incrementally, and builds one local page.
- The page: every ride on a map with date, type and home-loop filters; routes you repeat, with no-stop
  stretches (three strictness sliders), climbs, warm-up and time home, a sortable table filtered by
  loop or one way and moving time; places you do repeats; possible new spots; an A-to-B search.
- Ticks, sliders and filters are remembered in the browser. The ride data is gzipped inside the page
  (a full 3,000-ride history is about 22 MB, unpacked in about a second).
- `refresh.ps1` and a nightly 21:00 scheduled task keep it current; the page shows when it was built
  and a red banner when the last fetch failed (an expired or missing key).
- Self-test: route grouping, slow-down shares, repeat places, the stretch finder and the A-to-B matcher
  on made-up tracks.
