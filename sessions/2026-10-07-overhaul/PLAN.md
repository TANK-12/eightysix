# Overhaul wave: Forge, desktop, Claude app, Mission Control
date: 2026-10-07 · for: both · commander: Kaito (ejb-1f), crew `overhaul`

## Emerson's words (2026-10-07, verbatim excerpts)
- "i want a better gui ... have a session with critiques for making forge and the desktop better and use less power ... super effective super good looking and smooth interface. i dont want to lower the looks of anything too much though"
- "make a new interface so that huge sessions like these can be better communicated with and watched over and visualised maybe, and upgrade and combine board, forge claude app and crew room"
- "i want new features and optimization please dont remove features i like what i have"
- Claude app: "i dont want the live 2d to happen automatically in the normal forge claude app"; "make an ultracode and normal toggle and like limits on agents and effort levels"; "do a run on the app itself with critique agents to make it look, feel and act better"
- "the enjoy copy ... for some other day" (reference: https://enjoy.dev/, an agent-orchestration desktop app: projects, conversations, Needs you / Working / Unread, every agent side by side)
- Sudo: allowed for helpers above medium effort (password in ~/.claude/projects/-home-ejb/memory/sudo-password-in-chat-preference.md). Laptop CPU power caps are deliberate (Power app): never change them.

- Later the same day: "basically the goal is a forge v2 and desktop particles and visualiser and widgets v2 and stuff like that"; "i want agents to have critics and analysts ... try to break it and be critical"; "make new skills when needed, delete old ones when useless".

- "i want everything to look nice great pretty and smooth" (looks are top priority alongside power; final every-app sweep includes a looks pass per app).

- "dont actually make a v2 just keep it as v1 and maybe just hide the apps that you remove in settings ... and add new ones": upgrades are in place, no copies; a superseded app is hidden via Forge's hidden_apps setting, never deleted.

- Later (to Umi): "about the power optimization and efficiency thing just do general things until proper test can take place, do best guess and research only on how to do the best it can". So: no long measuring runs now; apply docs/library/power/2026-10-07-power-best-practice.md; one proper test (AC + unplugged) at the end.
- Then: "if the power thing needs to it can tell sessions to stop and then it can run tests, i'm allowing up to 10 mins total of stoppage, and then it starts them again". Tool: tools/quiet_window.py (600 s shared budget, 180 s per pause, watchdog).

## Safety copy
Git tag `snapshot-2026-10-07-pre-overhaul` (commit 54cc2f9) holds every file in ~/Forge except files over 5 MB (assets, untouched by this wave) and git-ignored ones (.venv, models). Restore one file: `git -C ~/Forge checkout snapshot-2026-10-07-pre-overhaul -- <path>`. The real index and working tree were not touched by taking it.

## Lanes (each helper owns its files; claim more with crew claim)
- H1 Mission Control (crew-deep): new app apps/mission/ combining Board + Claude app "Everyone" + Crew Room, Enjoy-style. Owns apps/mission/ only.
- H2 Claude app (crew-deep): Live2D off at load, Normal/Ultracode toggle, agent limits, then critic-led look/feel/behaviour polish. Owns apps/claude/.
- H3 Hub look + smoothness + hub/desktop power (crew-deep): shared/forge.css, shared/forge.js, hub/, forge.py (claim per edit), apps/wallpapers. Covers the queued Relay task 60 ("Forge desktop and hub keep using the GPU when they are hidden").
- H4 App power sweep (crew-worker): idle CPU/GPU of every other app page (polling, animation loops running while hidden); fix the worst offenders in their own static files. Not claude, mission, hub, shared, wallpapers.
- H6 Desktop v2 (crew-deep): widgets v2, particles v2, visualiser v2, glass/depth: shared/forge_widgets.js/.css, forge_particles.js, forge_visual.js, forge_glass.js, forge_depth.js. hub/index.html stays helper-3's: mount-point changes are agreed by board note.
- H5 Skills and docs leaner, same info (crew-deep): ~/.claude/skills (own skills), big app WIP/handoff docs outside this wave (old sections moved to an archive file, never deleted), a proposed tighter ~/.claude/CLAUDE.md for Emerson to approve (not applied). Emerson: "where you can make skills and documents more efficient but still have info".
- Final review swarm after all helpers report: a harsh critic, an analyst (numbers, power, speed) and a breaker, as an ultracode session if helper-2's live check shows ultracode works, else a parallel crew.

## State
- [x] H1 Mission Control: built and checked (apps/mission, port 8465, 41 tests, pyright 0, screenshots looked at by commander: works, tidy but plain)
- [ ] H7 Mission Control looks pass to Enjoy level (fresh Opus helper)
- [ ] H2 Claude app (fixes and polish continue with a fresh Opus helper from critics/claude-behaviour-breaker.md and critics/claude-look-feel.md): tweaks done, two critics ran; extra fix sent: usage bar flip-flop (stale 4-day usage.py reading overwrote fresh stream numbers every 120 s; main account's usage endpoint answers 429 for days, server side)
- [ ] H3 Hub + desktop
- [ ] H4 App power sweep: Sonnet helper stopped (Emerson: "no sonnet") after wiring 12 apps to shared/forge_idle.js (pytest green, no browser check); Opus helper-4 relaunched to browser-check, measure, break, finish
- [ ] H6 Desktop v2
- [x] H5 Skills and docs: done, checked (skills -12.6%, pace retired to trash, 5 WIPs archived; CLAUDE.md proposal in docs/library/tokens awaits Emerson)
- [ ] Critic pass + fixes
- [ ] Final analyst: one table of % improvements (idle CPU, GPU busy, frame time p50/p95) on AC and on battery, visible and hidden; real unplugged run with Emerson (ask him to unplug for ~10 min). Emerson: "i want percentage and smoothness even when unplugged".
- [ ] Docs: PROGRESS.json, app WIPs, library doc of power measurements

## Commander notes (for a fresh context)
- Helpers are subagents of the commander session (Claude app tab, ejb-1f); their reports arrive there. Crew board: `crew status overhaul`.
- Open questions to Emerson: is "no sonnet" for big waves only or everywhere (Relay too)? Add an Opus-xhigh helper type for new helpers? Approve the CLAUDE.md proposal (docs/library/tokens/2026-10-07-claude-md-proposed.md), and keep or drop its list of Docs places?
- Next after reports: integrate, run each touched app's tests, then the final review swarm (critic + analyst + breaker; ultracode at xhigh if helper-2's live check shows it works), then an every-app sweep (ultracode fan-out, Emerson wants more helpers), then docs: PROGRESS.json, app WIPs, commit per lane.
- Relay is paused by Riku (ejb-55) for tasks 59/61; `hey` account was at 100% 5-hour. Task 60 is covered by helper-3.
- Usage meter for the main account is stale (429 for days): pace by helper reports, not by usage.py.
