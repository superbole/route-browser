# Decisions

Why it is like this, and what was rejected. A row per decision, written when it is made.

| Decision | Rejected, and what it would have cost |
|---|---|
| **Downloads and the page live in `~/.route-browser`, not in this folder** (2026-11-19). | In the code folder: a fresh download, `git clean` or a deleted worktree takes years of downloads with it, and the page (which shows where you live) sits one `git add` from a public repo. |
| **Its own public repo** (2026-11-19). | Sending zips: every fix means a new zip, and nobody knows which version they have. Private: each person needs a GitHub account and an invite. The repo holds code only, so public shows nothing personal. |
| **The page computes no-stop stretches; `loops.py` only records where rides slowed, per speed level** (2026-11-19). | Stretches in Python: the strictness sliders would need a rebuild for every change. |
| **Default stop rule: slowing under 70% of usual speed on 1 ride in 4** (2026-11-19). | Half speed on 40% of rides: a tested loop showed one 66-min "stretch" through robots, stop streets and pinch points that a rider cannot hold an effort through. |
| **A repeat needs 90 s+ efforts, and a session 3+ of them (or 2 of 5 min+)** (2026-11-19). | Any two efforts on one road: every out-and-back over a hill looked like 2 reps. |
| **Ride data gzipped and base64 inside the page, unpacked by the browser's DecompressionStream** (2026-11-19). | Plain JSON: 85 MB for a full history. A separate data file: a page opened by double-click cannot fetch a local file. |
| **A nightly scheduled task, not a "fetch new" button** (2026-11-19). | A button: a plain file cannot run Python, so it needs a local server running whenever the page is open. |
| **A failed fetch writes `fetch_status.json` and the page shows a red banner** (2026-11-19). | A log file only: an expired key would stop updates silently, and nobody reads the log. |
