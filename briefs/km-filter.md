# Filter New spots by distance (km)

Sonnet · medium · AFK/Auto. BACKLOG B3, issue #3.

## Why
Stretch length on the page is minutes at the rider's usual pace. For an effort at threshold the
rider goes faster, so a "30 min" stretch is too short (Akasia, Loop 61 km E: 20 km, 31 min usual,
about 26 min at 270 W). What decides whether a test fits is km.

## Do
- In `build_map.py`, add a "at least __ km" number box (id `minkm`, blank = any) in the
  `stopsliders` block next to "longest __ min", and add `minkm` to `KEEP`.
- Apply it in `findSpots()` to both kinds, on `c.d.len` (km). Routes tab: leave unchanged.
- Re-render on input the same way `maxlen` does.
- One README line under "Possible new spots"; a CHANGELOG entry.

## Done when
- `python build_map.py --self-test` passes, `python build_map.py` rebuilds.
- In the page (preview `routes` in .claude/launch.json), New spots with 22 km at least lists only
  stretches of 22 km+.
- Commit locally, then stop: the push waits for Sheldon (AFK item).
