# Overhaul wave: power and smoothness numbers, before vs after
date: 2026-10-07 · for: both · plan written by the final-review analyst (Relay task 63)

> **Numbers: not yet taken. This runs last**, after every other lane of the wave has finished (Emerson's note 1054), with Emerson at the laptop for the unplugged part (about 10 minutes off the charger). Until the table below is filled in, every power claim from this wave is reasoning, not measurement.

The code audit this plan follows is `sessions/2026-10-07-overhaul/critics/final-analyst.md`. Every fix it proposes and any that get applied belong in this table too.

## What gets measured

- **Idle CPU %**: percent of one core used by the page's WebKitWebProcess (`/proc/<pid>/stat`).
- **GPU busy %**: render-engine share of that same process, from the kernel's DRM fdinfo (`tools/gpu_use.py`, the per-client figure intel_gpu_top shows). Also the whole-GPU awake % (RC6) that `tools/web_gpu_bench.py` reports.
- **Frame time p50 / p95** and the share of frames over 25 ms (dropped frames), from requestAnimationFrame deltas recorded in the page (recorder below). These come from a separate pass, because the recorder's own rAF keeps a page awake.
- Each figure is the median of 3 runs, with the spread (max - min) beside it. The change is shown as `(after - before) / before` in %.

## The two trees

- **before**: tag `snapshot-2026-10-07-pre-overhaul` (commit 54cc2f9), unpacked without touching the real repo:
  `mkdir -p /tmp/t63/numbers/before && git -C ~/Forge archive snapshot-2026-10-07-pre-overhaul | tar -x -C /tmp/t63/numbers/before`
- **after**: what is committed when the run starts (commit everything first):
  `mkdir -p /tmp/t63/numbers/after && git -C ~/Forge archive HEAD | tar -x -C /tmp/t63/numbers/after`
- The same settings in both. `hub/theme.js` and `hub/status.js` are git-ignored, so copy the live ones into both trees. The scratch Board backend (below) stands in for the app in front:
  ```
  for t in before after; do cp ~/Forge/hub/theme.js /tmp/t63/numbers/$t/hub/; done
  sed 's#http://127.0.0.1:8452#http://127.0.0.1:8901#' ~/Forge/hub/status.js > /tmp/t63/numbers/before/hub/status.js
  sed 's#http://127.0.0.1:8452#http://127.0.0.1:8902#' ~/Forge/hub/status.js > /tmp/t63/numbers/after/hub/status.js
  ```
  Check in each status.js that `board` has `"available": true, "state": "up"`, and edit it if not. Large files (over 5 MB) and git-ignored ones are not in the tag. Copy `shared/assets` or the wallpaper caches only if a page asks for them (the hub's wallpaper comes from `~/.cache/forge`, shared by both trees).
- Scratch app backends, one per tree, on spare ports, stopped by PID (never `pkill -f`):
  ```
  cd /tmp/t63/numbers/before/apps/board && ~/Forge/apps/board/.venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8901 >/tmp/t63/numbers/board-before.log 2>&1 & echo $! > /tmp/t63/numbers/board-before.pid
  cd /tmp/t63/numbers/after/apps/board  && ~/Forge/apps/board/.venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8902 >/tmp/t63/numbers/board-after.log 2>&1 & echo $! > /tmp/t63/numbers/board-after.pid
  # afterwards
  kill "$(cat /tmp/t63/numbers/board-before.pid)" "$(cat /tmp/t63/numbers/board-after.pid)"
  ```
  Emerson's own Forge (port 8445), Relay, Jan and his running apps are never restarted or touched. Laptop CPU power caps stay as they are.

## Part A: the rig, AC power (no need for Emerson to be there)

Run in the private headless GNOME Shell (`tests/browser/headless_gnome.sh`: 3072x1728 like his screen, real GPU, its own session, so his desktop is not touched). Post on the crew board first, because it uses the GPU.

```
~/Forge/tests/browser/headless_gnome.sh start
python3 ~/Forge/tools/quiet_window.py status        # shared budget: 600 s, at most 180 s a pause
```

One run of one cell (12 s measured after 6 s warm, about 20 s with load):
```
cat > /tmp/t63/numbers/run.sh <<'SH'
#!/usr/bin/env bash
# run.sh TREE JS: one measured run of the hub from TREE in the rig, one JSON line out
exec ~/Forge/tests/browser/headless_gnome.sh run python3 ~/Forge/tools/web_gpu_bench.py \
  --root "$1" --page hub/index.html --size 3072x1728 --visible --levels --no-count \
  --seconds 12 --warm 6 --json --js "$2"
SH
chmod +x /tmp/t63/numbers/run.sh
B=/tmp/t63/numbers/before A=/tmp/t63/numbers/after R=/tmp/t63/numbers/run.sh
```

Scenarios (the `--js` for each row; `--levels` feeds real cava levels, so play music during the run). The tiers are simulated through the same inputs forge.py and the GNOME extension give the hub:

| Row | `--js` |
|---|---|
| home, visible, full tier | `""` |
| app in front, full tier | `selectWorkspace('board')` |
| app in front, reduced tier (mostly covered) | `selectWorkspace('board'); forgeShare(0.2)` |
| app in front, battery 60% (simulated) | `selectWorkspace('board'); forgeSetStats({cpu:5,mem:40,battery:60,charging:false,plugged:false})` |
| home, battery 40% (simulated, under battery_saver 50) | `forgeSetStats({cpu:5,mem:40,battery:40,charging:false,plugged:false})` |
| hidden (minimised / covered) | not a `--js` row: `tools/cover_bench.py --root <tree> --seconds 10 --json` in the rig, once per tree, rows "maximised" and "minimised" |

Order: interleave the trees within each scenario (B A B A B A), so drifting load hits both alike. The rig needs no quiet window if no other session is busy. Look at `python3 ~/Forge/tools/gpu_use.py 5` first: if anything other than the rig is above 5% GPU, pause the other sessions for each scenario:
```
python3 ~/Forge/tools/quiet_window.py run --seconds 140 --label "numbers: app in front, AC" -- \
  bash -c 'for i in 1 2 3; do /tmp/t63/numbers/run.sh /tmp/t63/numbers/before "selectWorkspace(\"board\")"; /tmp/t63/numbers/run.sh /tmp/t63/numbers/after "selectWorkspace(\"board\")"; done' >> /tmp/t63/numbers/rig.jsonl
```
(6 runs at about 22 s is about 130 s, under the 180 s limit. Five scenarios like this would need 650 s, more than the budget. So use the quiet window only for the two scenarios that matter most, "home" and "app in front", which is about 280 s, and run the rest unpaused with the load noted.)

Frame time pass (separate, because the recorder keeps the page awake; same rows, 3 runs per tree; no `--no-count` and no quiet window needed):
```
REC='window.__ft=[];(function f(t){if(window.__lt)__ft.push(t-__lt);__lt=t;requestAnimationFrame(f)})(performance.now());'
EVAL='(()=>{const a=__ft.slice().sort((x,y)=>x-y),q=p=>a[Math.floor(p*(a.length-1))]||0;return JSON.stringify({n:a.length,p50:+q(.5).toFixed(1),p95:+q(.95).toFixed(1),over25:+(a.filter(x=>x>25).length/a.length*100).toFixed(1)})})()'
~/Forge/tests/browser/headless_gnome.sh run python3 ~/Forge/tools/web_gpu_bench.py --root "$A" --size 3072x1728 --visible --levels \
  --seconds 12 --warm 6 --json --js "selectWorkspace('board'); $REC" --eval "$EVAL"
```
Mind the order: the scenario's own `--js` comes before `$REC` in the same string. While the mouse moves, frame time is the figure Emerson feels. Add one row with a pointer-move script (`setInterval(()=>document.dispatchEvent(new PointerEvent('pointermove',{clientX:Math.random()*innerWidth,clientY:Math.random()*innerHeight})),16)`) if time allows.

```
~/Forge/tests/browser/headless_gnome.sh stop
```

## Part B: the real laptop, AC then battery (needs Emerson, about 10 minutes unplugged)

His running Forge, measured as it is: read only, never restarted. Reading the per-process counters from `/proc` disturbs nothing.

1. Find the hub's web process: the WebKitWebProcess child of forge.py with the most GPU while Forge is on screen (`python3 ~/Forge/tools/gpu_use.py 5`, top WebKitWebProcess under forge.py).
2. **On AC**, Forge in front and maximised, music playing as he normally has it. For each state below, 3 samples of 15 s: `python3 ~/Forge/tools/gpu_use.py 15 --json > /tmp/t63/numbers/live-ac-<state>-<n>.json`
   - home screen, mouse still
   - an app in front (Board), mouse still
   - Forge minimised (expect about 0)
   With quiet_window: `python3 ~/Forge/tools/quiet_window.py run --seconds 120 --label "numbers: live AC" -- bash -c 'for s in home app; do for n in 1 2 3; do ...; done; done'`. There is no `--js` on his live Forge: Emerson switches between home and the app himself, between the two groups (so run each group as its own pause of about 50 s).
3. **Unplug** (Emerson). Wait 30 s for forge.py's 3 s stats to move the hub to its battery values (check: the bar's battery chip shows no lightning). Repeat the same 3 states x 3 samples. About 3 minutes.
4. Still unplugged, one **after-tree rig run** of "app in front" to get the battery GPU clock behaviour on the real panel: the same `web_gpu_bench.py` line as `run.sh` with `--root /tmp/t63/numbers/after --js "selectWorkspace('board')"`, but run directly on his screen (`--visible`, no `headless_gnome.sh run` prefix) (the bench window covers Forge, which rests). 3 runs, about 1 minute. Before-tree the same if time allows.
5. Plug back in. Total unplugged time is about 8-10 minutes.

There is no live "before" on the real laptop (that would need restarting his Forge on the old tree). The before/after comparison comes from Part A. Part B gives the real-world AC vs battery level of the after state, and checks that the rig's numbers are in the same range.

## Recording

Append every raw JSON line to `/tmp/t63/numbers/*.jsonl` and copy them here under "Raw" when done. Mark any run taken under load (another process above 5% GPU in `gpu_use.py`, or a load average above 2) with "(load)". State the quiet-window seconds used (from `quiet_window.py status`).

## Table (to fill)

Rig (Part A), AC unless the row says simulated battery. Median of 3 (spread).

| Scenario | web CPU % before | after | change | GPU busy % before | after | change | frame p50 / p95 ms before | after | dropped >25 ms % before / after |
|---|---|---|---|---|---|---|---|---|---|
| home, visible, full | | | | | | | | | |
| app in front, full | | | | | | | | | |
| app in front, reduced (mostly covered) | | | | | | | | | |
| app in front, battery 60% (sim.) | | | | | | | | | |
| home, battery 40% (sim., saver) | | | | | | | | | |
| maximised window over Forge (cover_bench) | | | | | | | n/a | n/a | n/a |
| Forge minimised (cover_bench) | | | | | | | n/a | n/a | n/a |

Real laptop (Part B), after tree only. Median of 3 (spread).

| State | AC: CPU % | AC: GPU % | Battery: CPU % | Battery: GPU % | change on battery |
|---|---|---|---|---|---|
| home, mouse still | | | | | |
| app in front | | | | | |
| Forge minimised | | | | | |

Quiet window used: ___ s of 600. Runs under load: ___.

## Raw

(empty until the run)
