# Route browser

Your outdoor rides and runs on one map: the routes you repeat with their no-stop stretches and climbs,
the places you do repeats, possible new spots for them, every ride that passed point A then point
B, and a route builder that plans a ride along roads you have ridden. It runs on your own computer
with your own Garmin key (Garmin's free Personal API), and nothing leaves it except the calls to Garmin
and the map (its library and tiles).

## Set it up (once)

You need Python 3 (python.org) on Windows. Get this folder: on GitHub, Code, Download ZIP, and unzip
it somewhere it can stay (or `git clone` it). In PowerShell, in this folder:

```powershell
pip install -r requirements.txt
```

Make a Garmin key (section "The Garmin key" below) and save it for your Windows user, so the nightly
run can read it too:

```powershell
[Environment]::SetEnvironmentVariable("GARMIN_PERSONAL_API_KEY", "paste-the-key-here", "User")
```

Close and reopen PowerShell, then pull your history (the first run takes a while: about 2 to 8
seconds per activity; change the year to how far back you want):

```powershell
python fetch.py --since 2015-01-01
```

```powershell
python build_map.py
```

Open the page by double-clicking `routes.html` in your `.route-browser` folder
(`C:\Users\<you>\.route-browser\routes.html`). Bookmark it.

Where a browser will not open a file directly, `python serve.py` serves the page on
http://localhost:8124/routes.html.

To update the tool itself later: `git pull`, or download the ZIP again and replace these files. Your
rides and settings are not in this folder, so nothing is lost.

## Keep it up to date: the nightly run

`refresh.ps1` fetches new activities (seconds) and rebuilds the page. To run it every night at 21:00,
paste this once into PowerShell in this folder:

```powershell
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PWD\refresh.ps1`""; $t = New-ScheduledTaskTrigger -Daily -At 21:00; $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; Register-ScheduledTask -TaskName "Route browser refresh" -Action $a -Trigger $t -Settings $s
```

If the computer is off or asleep at 21:00, it runs when it next wakes, on battery too (Windows holds
scheduled tasks on battery unless told otherwise). A key saved after you logged in is picked up
without logging out. The top of the page says when
it was last built and the date of your latest ride. If Garmin refuses the key, the page shows a red
banner until a fetch works again. The last run's output is in `.route-browser\refresh.log`.

To run it now: `.\refresh.ps1`. To remove the nightly run:

```powershell
Unregister-ScheduledTask -TaskName "Route browser refresh" -Confirm:$false
```

## Using the page

- Hover a ride to see its name; click it for the details and a Garmin Connect link.
- Elapsed includes stops; Moving, km/h, W and bpm leave out stops (gaps over 30 s).
- The map opens on the area within 30 km of home, so a holiday ride, or a watch left recording across a
  flight, does not zoom it out.
  "Started and ended at home" uses your most common start point, worked out in the page each time.
- Runs start unticked. The filters apply to every tab; a route shows when any of its rides passes them. Leaving a tab puts the map back to all rides
  (the route builder keeps its route). The tab, ticks and sliders are remembered in your browser.
- In the A to B and Route builder tabs, a click on the map or on a ride drops a point.

### Routes you repeat

Your rides (not runs) grouped into the routes you ride more than once: same start, same finish
(within 500 m), and at least half the same roads. Click a route to see only its rides, drawn on its
most typical ride:

- green = stretches with no stops at your usual pace (two shades, so neighbours stand apart; ★ = 20
  min+, long enough for a 20-min rep). A spot counts as a stop when enough of the rides that passed it
  slowed there, or paused, and were not climbing. Three sliders set how strict that is: the speed
  (default under 70% of usual), the share of rides (default 25%, so a robot that is red 1 time in 4
  breaks a stretch and one coffee stop does not), and the shortest stretch shown (default 8 min, up
  to 60), with an optional longest.
- red = climbs of 25 m+ at 3%+ that take 1 to 15 min.
- warm-up to the first stretch, and last stretch to the finish, in minutes.

Click a column heading to sort the table. Above it, pick loops only or one way only and a moving
time range: loops, 50 to 70 min finds your 1-hour loops. Click a stretch or climb to light it up in orange; its box hides or shows it. Routes that never go more
than 1 km from the start (trainer rides, circuits) are left out.

### Places you do repeats

Roads where a ride with power had 3 or more hard efforts on the same stretch (or 2 of 5 min+), in 2 or
more rides. A hard effort is 5 min+ above 1.12x that ride's median power, or 90 s to 5 min above 1.25x
(30-s average). Each place lists its sessions with the ride name, reps, watts, whether the reps went
both ways or one way, and the easy time between them. Click a session to draw its reps: magenta one
way, teal the other. Rides without power are not searched.

### Possible new spots

The no-stop stretches and climbs on your routes that no repeat place covers, longest first, using the
same sliders and route filters as Routes you repeat, which show on both tabs; here the length limits
apply to climbs too. The Ride column is the whole route's moving time. The same road on several routes is listed once; "Both ways" means it is also stop-free
heading the other way on one of your routes, so back-and-forth reps should work there.

Click a spot to show only its route's rides, with the spot in orange. Under the sliders:

- Each ride on this stretch opens A to B with A and B on its ends: every ride's time, W and bpm there.
- Test N min at a speed you set: a blue window you slide along the stretch, with the km of the ride
  to start and finish at, and a warning when the stretch is too short. Use the speed you would hold
  (A to B shows what you held there before).

### A to B

Click the map to drop A, click again for B. Drag either to move it, or press Move A / Move B and click.
The list shows every ride that came within the radius of A and later of B (tick Either direction to
include B-then-A, marked ↩). Click a column to sort, click a row to highlight the ride and its A-to-B
stretch in orange. A search also narrows the map to the rides it found; Clear brings them all back.

### Route builder

Click the map to drop point 1, then 2, 3 and so on. Each point snaps to the nearest road you have
ridden (within 300 m; a red point found none), and you can drag it. Each leg takes the fastest way
between its two points along roads you have ridden, joining pieces of different rides, timed at your
average moving time on each ~50 m piece. It turns only where one of your rides turned, so it never
drops off a bridge onto the road below or crosses to the other side of a dual carriageway. Up to two
other ways are listed when they differ enough and are less than half as slow again; click one to use
it, hover to see it in orange. The total adds up the ways you picked. Roads count only in the direction you rode them; tick Use roads both ways to drop that
(the time is the one for the way you rode). The filters choose which rides make up the roads: untick
mountain biking to plan on the road only.

## Privacy

Every track starts at your home. Everything the tool downloads or builds lives in your `.route-browser`
folder (`cache\`, `routes.html`, `fetch_status.json`, `refresh.log`), outside this folder and any git
repo. Never upload or share the page or the cache: they show where you live.

## The Garmin key

Garmin Connect web, Settings, Personal API token (`connect.garmin.com/app/settings/personalApiToken`),
Create Key, accept the terms, pick an expiry (at most a year), copy the key: it is shown once. Garmin
emails about a week before it expires; make a new one the same way and save it with the
`SetEnvironmentVariable` line above (or in `.env`). Garmin's terms let a key be used only by its owner,
in tools they run for their own use: share this folder, never someone's key.

## For developers

- `fetch.py` pulls the last 12 months by default; `--since` goes further. It only downloads activities
  it has not cached, and goes slowly on purpose (Garmin publishes no rate limits). Types: `cycling`,
  `road_biking`, `mountain_biking`, `gravel_cycling`, `cyclocross`, `bmx`, `running`, `trail_running`
  (not indoor, treadmill or virtual). It reads FIT and TCX downloads; GPX not yet.
- A download that fails is saved in `~/.route-browser/failed.json` and retried at the start of every
  run, whatever `--since` says; the entry goes once the activity is cached. The `done:` line counts them.
- `loops.py` groups routes, records where rides slow down, and finds repeat places. `build_map.py`
  writes the page; the stretch finder, A-to-B matcher and route builder are its JavaScript.
- `python build_map.py --self-test` checks all of them on made-up tracks. It needs `node`, but no network
  and no key.
- What changed is in [CHANGELOG.md](CHANGELOG.md), why it is built this way in
  [docs/decisions.md](docs/decisions.md), and what is planned in [NEXT.md](NEXT.md) and
  [BACKLOG.md](BACKLOG.md).
