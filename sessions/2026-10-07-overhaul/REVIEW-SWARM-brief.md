# Final review swarm brief (step 2 of HANDOFF "Next")
date: 2026-10-07 · for: Claude · commander: Umi (ejb-66), crew `overhaul`

Launch only after lanes H2, H3, H4, H6, H7 are done and step 1 (tests + commit per lane) is finished. Three Opus helpers ("no sonnet"), in parallel, each read-only on the source except the breaker's scratch servers. Reports go to `critics/final-<role>.md` in this folder (same format as critics/claude-look-feel.md: ranked real defects, each with file:line, how seen, and the exact fix). Then the commander fixes or hands fixes out.

Scope for all three: everything this wave changed, `git -C ~/Forge diff --stat snapshot-2026-10-07-pre-overhaul..HEAD` (hub/, desktop/, shared/forge_*.js|css|py, apps/claude, apps/mission, the per-app static files from the power sweep). Emerson's words are in PLAN.md; "looks top priority alongside power, never remove a feature, smooth on battery too".

Common rules: never restart Emerson's Forge (port 8445), Relay, Jan or any running app; scratch servers on spare ports with PID files, stopped by PID; headless Chrome via Flatpak for screenshots (verify skill) at 760/1100/1500/1920; measure per process (/proc CPU time, intel_gpu_top per client), 3+ runs, median and spread, load logged next to each run; never touch CPU power caps.

## Harsh critic (looks and feel)
Screenshot hub, desktop page, Claude app (classic + Enjoy), Mission Control and 6 power-sweep apps in every state (empty, loading, error, full, in-app, widgets page Alt+W). Rank what looks cheap, jumps, flashes, clashes with shared/forge.css, or regressed against the snapshot tag (check out the old file to a temp dir to compare, never into the tree).

## Analyst (numbers)
Emerson 2026-10-07: until the proper test, no long measuring. So the analyst first audits the code against docs/library/power/2026-10-07-power-best-practice.md (every loop/poll gated, tier obeyed, DPR/fps caps, CSS cost) and ranks what's left; the table below is the one proper test at the end, with Emerson.
One table: idle CPU %, GPU busy %, frame time p50/p95 (or dropped frames), visible vs hidden, full vs reduced power tier (simulate battery through forge_power.js inputs), before (snapshot tag, run from a temp checkout on a scratch port) vs after, as % change. Write it to `~/Forge/docs/library/power/2026-10-07-overhaul-numbers.md` too. Mark numbers taken under load. For the real before/after runs, pause the other sessions with `python3 ~/Forge/tools/quiet_window.py run --seconds N --label ... -- <cmd>` (Emerson's 10-minute total budget, check `status` first for what's left).

## Breaker
Try to break it: rapid clicks, Alt+W/Alt+Q/Esc spam with and without an app open, server down mid-page, bad JSON, huge inputs, hidden/shown toggling (forge-visible events), power tier flapping (CPU 70%/50% hysteresis edges), two Claude tabs at once, Mission Control with 0 and 50 sessions. Report each break with repro steps.
