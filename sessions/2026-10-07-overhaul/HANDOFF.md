# Overhaul wave handoff
date: 2026-10-07 · for: Claude

Read PLAN.md in this folder first. It holds Emerson's words, lanes H1-H7, state and open questions.

## Commander
Umi (ejb-66) took over from Kaito (ejb-1f) on 2026-10-07 ~20:35, posted crew note 16 asking helpers to report by note --to Umi. Step 2's brief is ready: REVIEW-SWARM-brief.md. Emerson's power direction (note 17): best-guess best practice now (docs/library/power/2026-10-07-power-best-practice.md), proper test only at the end. Quiet window for that test: tools/quiet_window.py (crew note, 600 s budget). Hyprland fix runs separately as session Mei (sessions/2026-10-07-hyprland-fix.md); Forge Browser fix is first in the U1 brief.

## State when the old commander chat stopped
- Done: H1 (Mission Control app, apps/mission, port 8465, 41 tests) and H5 (skills/docs trim).
- Still running in the old chat (keep that chat open until they finish; don't edit their claimed files; `crew.py status overhaul`):
  - H2b, Claude app: critic fixes; slash commands sent without the persona tag; panel_command tool.
  - H3: hub looks, smart power tier, Relay task 60.
  - H4: power sweep and measurements.
  - H6: desktop v2: widgets, Alt+W widgets page, Alt+Q close app, wallpaper zoom fix, GPU cut.
  - H7: Mission Control looks; resolves the static/ collision.
  - Desktop v2 critic/breaker.
- Each helper writes its final report to reports/<lane>.md here; read those. Missing ones: crew notes, `git -C ~/Forge status`, app WIP.md.

## Update 20:55
- All lanes finished (H2b, H3, H4, H6, H7 + critics); reports in reports/. Nothing committed yet.
- To go live: restart Forge and the Claude app, then log out/in to GNOME (H3's extension). Do this only with Emerson's OK.
- Open: at ~20:45 Emerson said via Relay that Forge showed nothing. The hub renders fine headless (/tmp/hubchk/hub.png); waiting on him to say what he sees. Rollback for one file: git checkout snapshot-2026-10-07-pre-overhaul -- <path>.

## New asks from Emerson (21:00)
- Mission Control icon: he doesn't like it. He likes the Claude logo; make something cool built on that idea.
- Jan Tune and Power icons look too similar; make the app icons cooler overall (keep them recognisable, one shared icon style).
  - DONE by Relay task 66 (2026-10-07): shared/forge_icons.js + hub setIcon(); see reports/ICONS.md. Needs only a hub reload, no restart.
- Forge was restarted at about 20:55 and runs the new code. A GNOME re-login is still needed for the extension.

## Next, in order
1. Once all lanes finish: run each touched app's tests and commit per lane. (Done, see Update 22:30.)
2. Final review swarm: harsh critic + analyst + breaker, Opus only ("no sonnet").
3. U1 every-app sweep: run U1-every-app-sweep-brief.md as an ultracode xhigh session.
4. Final analyst table: CPU/GPU/frame-time %, AC vs battery. A ~10 min unplugged run needs Emerson's OK.
5. Docs: PROGRESS.json, WIPs, a docs/library entry.

## Update 22:30 (part 2 finished, Relay task 63)
- Next 1 is done: every lane committed (35ef508, 994989b, be02b98, b132a41, b84d33b); icons by task 66 (acc42c6, 7d13c63) and the New/Classic icon style switch by task 70 (a15cd03).
- The Alt+Shift+M freeze (Frosted/Liquid glass) is found and fixed: live blur on every tile stalled WebKit. Blur now only on the bar, search, dock and popups; a hang watchdog in forge.py ends a stuck hub page and reloads it safe. Verified in a headless GNOME with real WebKit; numbers in docs/library/forge/2026-10-07-glass-blur-freeze.md. Forge needs one restart for the watchdog.
- Next 2-5 (review swarm, U1 sweep, analyst table, docs) are queued as part 3: PART3-brief.md. Performance runs (the analyst table, the glass fps re-measure) go last, after all other work (Emerson, crew note 1054).
- tests/browser/run.sh on 2026-10-07 ~22:15: 6 FAILs outside the glass work (hub_level, hub_music_skip, claude_stream and claude_pic_tag report nothing; "the preset is saved through forge.py"; "the wave moves with the levels"). Part 3 should look at them first.

- ~23:00: a critic found the watchdog ending healthy pages during a confirm() dialog and after Forge's own loop stalled; both fixed and checked in real WebKit (glass-blur-freeze doc, "Critic fixes").
- ~23:20: a second critic found the watchdog blind while a page loads, after a dialog and for print(); fixed, rig 23 PASS, unit tests 39 pass. Known low gaps listed in the glass-blur-freeze doc.

## Update 23:45 (task 63 stops here)
- The glass freeze lane is committed (a5788ee, plus a follow-up for the watchdog's load phase). Frame rate after the fix, headless GNOME, real WebKit: flat 55, frosted 54, liquid 53 fps medians (before: frosted 0, liquid hung). Forge needs one restart for the watchdog.
- Next 2-5 (review swarm, U1 every-app sweep, analyst table, docs) are NOT queued: Kaito's crew note 1074 said no open-ended extra parts tonight, and nobody answered note 1087. The brief is ready: `relay < ~/Forge/sessions/2026-10-07-overhaul/PART3-brief.md`. Emerson decides.
- Leftovers for tomorrow: the 6 browser-check FAILs above; the known low gaps in docs/library/forge/2026-10-07-glass-blur-freeze.md ("Known gaps").

## Update 2026-10-08 ~00:40 (task 63, Nene)
- Next 2 (review swarm) done: critic 5 defects, fixed (f4fcab0; the Mission chip by task 73, f4797a0); analyst audit item 1 fixed (e2770d4, wall tint fade), items 2-5 left as Emerson's call; breaker BREAKER_SHORT.
- Next 3 (U1 sweep) queued as Relay task 74.
- Next 4 (numbers table): plan only (docs/library/power/2026-10-07-overhaul-numbers.md); plugged-in runs at the end of task 74; the 10 min unplugged run needs Emerson.
- Next 5 (docs): docs/library/forge/2026-10-08-overhaul-wave-part-2.md, PROGRESS.json session_2026_10_08_overhaul_part2, apps/claude/WIP.md.
- tests/browser/run.sh 1050 PASS 0 FAIL (b698e2f fixed the 6 FAILs listed above).

## Update 2026-10-08 ~01:25 (task 74, Kiko: U1 sweep runs as Relay tasks)
- Task 74's first four sessions handed over at 170-199k context and each hand-over killed its in-session workers; only 97bfd48 (Browser first page hidden, forge.py) got in.
- Now `u1_sequencer.py` (here; transient user unit `u1-sequencer`, no usage) queues each sweep group as its own Relay task, paced by the 5-hour meter (3 at once under 70 %, 1 to 92 %, none above), Browser first. Every group task runs its own Opus critic. After the last group it queues one summary task (docs/library/power/2026-10-07-every-app-sweep.md, idle-CPU after-runs or a plan, this file, PROGRESS.json).
- Watch: `u1-sequencer.json` (group -> task id, status), `u1-sequencer.log`, `relay status`. Stop: `systemctl --user stop u1-sequencer`. Restarting it carries on from the json.

## Update 2026-10-08 ~06:05 (task 93, Noa: U1 summary)
- U1 sweep finished: 34 apps in 18 groups (Relay tasks 75-92), all ended done, every group ran its own Opus critic; per-app summary with commits, tests, critic findings, "measure this" list, shared/ recommendations and questions: docs/library/power/2026-10-07-every-app-sweep.md.
- Gaps in the record: G9 has no critic file (findings only in its report); Codec Lab/Player code sits uncommitted in ~/anime-codec-lab (repo has no commits).
- Idle-CPU before/after: NOT measured. The laptop crashed (~05:58, reboot 06:00) during the first try at Part A in the headless rig; cause unknown. Not retried unattended. Run plan stays docs/library/power/2026-10-07-overhaul-numbers.md; next try with Emerson at the laptop, one 20 s cell first.
- Still open: final-breaker.md breaks 1-5 (hub, Claude app); the shared/ list in the sweep doc needs its own task; every backend fix waits for Emerson's next Forge restart.

## Queued by Emerson during the wave
- Text size / app size settings work badly (pre-existing): fix after helpers 3 and 6 release shared/forge_theme.py, forge.js/css, forge.py; details in sessions/QUICKSTART.md.

- Hub top bar: many app icons push the non-app icons off screen (pre-existing); asked helper-3 (note 25), else fix after; QUICKSTART.

## Rules
- Upgrade in place; superseded apps are hidden via hidden_apps, never deleted.
- Never restart his Forge, port 8445, Relay or Jan. Never touch the CPU power caps.
- Rollback: tag snapshot-2026-10-07-pre-overhaul.
- Keep replies short.
- Batch hard: each request should carry at least ~10 seconds of work (many tool calls per turn, no thin turns). Tell every helper this too.

## Open questions for Emerson
- Queue part 3 (review swarm, U1 sweep, docs)? One line: `relay < ~/Forge/sessions/2026-10-07-overhaul/PART3-brief.md`.
- Is "no sonnet" global (Relay too)?
- Approve the CLAUDE.md proposal (docs/library/tokens/2026-10-07-claude-md-proposed.md)?
- Alt+Q: close the current app (assumed) or all apps?
