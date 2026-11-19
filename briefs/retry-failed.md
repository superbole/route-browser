# Retry failed downloads on every run

**Why:** the full-history backfill (2026-11-19) left 4 activities from before the last 12 months
that failed with Garmin 504 Gateway Timeouts. The nightly run only lists the last 12 months
(`fetch.py` default `--since`), so those are never tried again and stay missing from the map.

**Do:** when a download fails in `fetch.py`, record the activity summary (the same fields
`meta` takes) in `~/.route-browser/failed.json`. At the start of each run, retry everything in
that file whatever `--since` says; drop an entry once it caches. Keep the 1.5 s pause.

**Done when:** a run with no new activities retries the failed ones and reports them in its
`done:` line; `python build_map.py --self-test` passes; README "For developers" mentions it.
Commit locally and stop: the push to the public repo waits for him.
