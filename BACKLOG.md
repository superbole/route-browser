# BACKLOG — route-browser
<!-- next-id: 3 -->

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
