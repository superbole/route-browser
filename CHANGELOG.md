# Changelog

Newest first. What shipped and when; why it is like this is in [docs/decisions.md](docs/decisions.md).

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
