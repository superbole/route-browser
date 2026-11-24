# BACKLOG — route-browser
<!-- next-id: 4 -->

Everything worth doing that is NOT in `NEXT.md`'s Queue. Unbounded and unordered —
the ordering that matters lives in the Queue, which is capped at 5 and refilled from here.

Items marked `queued` are on the Queue right now and stay listed here until the work lands.
Where the repo has GitHub Issues, `tools/sync_backlog.py` mirrors this file to them; the
file is the writer and Issues is the copy that survives a lost machine.

## B1. Retry failed downloads on every run
`Sonnet` · effort `medium` · `AFK/Auto` · added `2026-11-19` · issue `#1` · queued
Brief: [retry-failed](briefs/retry-failed.md)

Four activities older than a year failed with Garmin 504s in the first full-history pull, and the
nightly run only looks back 12 months, so they would never be tried again.

## B2. Read GPX downloads
`Sonnet` · effort `medium` · `AFK/Auto` · added `2026-11-19` · issue `#2` · queued
Brief: [gpx](briefs/gpx.md)

One activity downloads as GPX, which fetch.py does not read yet (FIT and TCX it does).

## B3. Filter New spots by distance (km), not only minutes
`Sonnet` · effort `medium` · `AFK/Auto` · added `2026-11-24`
Brief: none yet; write one when queued.

Stretch length is minutes at your usual pace, so for a test at FTP (faster) a "30 min" stretch is
too short: the Akasia stretch (Loop 61 km E, 20 km, 31 min usual) takes about 26 min at 270 W
(A to B, 2025-04/05 rides). A min-km box beside Shortest stretch, applied in findSpots() in
build_map.py on c.d.len, would list what fits directly (about 22 km+ for 30 min at 45 km/h).
The test window added 2026-11-24 already answers "does it fit" for one spot; this is the search.
