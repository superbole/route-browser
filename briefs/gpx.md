# Read GPX downloads

**Why:** one activity in the 2026-11-19 backfill downloaded as a `.gpx`, which `fetch.py` does not
read ("no FIT or TCX file in the download"), so it is missing. FIT and TCX are read already.

**Do:** add `parse_gpx(raw)` beside `parse_tcx` in `fetch.py`, feeding the same `thin()`: `trkpt`
lat/lon attributes, `time`, `ele`, and heart rate and power from extensions where present
(e.g. `gpxtpx:hr`, `power`), matching tags by local name as `parse_tcx` does. GPX has no
distance, so pass `None` (the page fills it from geometry). Pick `.gpx` after `.fit` and `.tcx`.

**Done when:** a made-up GPX of a few points parses in a small check (or the self-test), the
failing activity caches on the next `--since 2000-01-01` run, and the self-test passes.
Commit locally and stop: the push to the public repo waits for him.
