# U1 every-app sweep: what changed in each app
date: 2026-10-08 · for: both · summary by Takumi (relay-93-work), Relay task 93, from the 18 group reports

**In one line:** 34 apps in 18 groups were swept (Relay tasks 75-92, all ended "done"), every app has a sweep commit and a critic follow-up commit in `~/Forge`, and every group ran its own fresh Opus critic. Nothing was checked inside Emerson's real Forge window (WebKitGTK): all checks ran in headless Chrome against scratch copies on spare ports. Page changes reach his Forge on the next page reload, backend (`.py`) changes only on his next Forge restart (nobody restarted it).

Sources: `sessions/2026-10-07-overhaul/u1-sequencer.json`, `reports/u1-G*.md`, `critics/u1-G*-critic.md`, `git log --grep "Relay task 74"` (57 commits) plus the follow-up commits named per app below.

## What is missing or odd in the record

- **Every group task ended done** (sequencer json: G1-G18, tasks 75-92, all `done`). No group was parked, stopped or blocked.
- **G9 (Cosmos, Eighty Six) has no critic file.** `critics/u1-G9-critic.md` was never written; the critic's six findings are only in the report's Critic section (commit 15f708e holds the report alone). 17 of 18 critic files exist.
- **G12 (Dossier, Foresight) has no "report and critic report" commit**: the report and critic file went in with the Foresight follow-up 57d4de6.
- **Codec Lab and Codec Player code is not committed.** It lives in `~/anime-codec-lab`, a git repo with no commits (its first commit is Emerson's call). Only the Forge stubs (`apps/codec-lab`, `apps/codec-player`: WIP.md, README.md) are committed. Backups of the originals: `backups/2026-10-07-overhaul/sweep/codec-lab/`.
- Some follow-up hashes are missing from the reports; found in git: Browser b33d408, Dossier 195105e, Foresight 57d4de6, PulseForge 37daa47, Codec Lab stub 5ebb411, Codec Player stub 98f2936.
- Other sessions' uncommitted work is still in the tree and was never committed by the sweep (on purpose): `apps/board` (5 files), `apps/crewroom` (7), `apps/novelforge` (the 2026-09-28 rework, 20 paths), `apps/acchan/qwen.py`, `apps/files/tests/last_ui.png`.

## Per app

"Verified" below means run, in headless Chrome or pytest on a scratch copy. "Not verified" for every app: the real Forge window (WebKitGTK) and Emerson's real data.

### G1 Browser (Relay task 75)
- Changed: the root cause of "the forge app browser lowkey never works": forge.py dropped the hub's `owner` and `inset` messages sent before the first native view, so the first page stayed hidden until another app had been opened (97bfd48, forge.py, needs a Forge restart). Page: calm offline strip with backoff 3-30 s, typed addresses open while the server is away, notes above the page area, star double click guarded, Ctrl+Shift+T reopens closed tabs; backend `/api/session` sanitised, never a 500.
- Commits: 97bfd48 (forge.py), b777562 (sweep), b33d408 (critic follow-up).
- Tests: pytest 43, check_ui 21/21, shown-window rig 9/9 (private headless GNOME, real WebKit views).
- Not verified: real keyboard and mouse input into a page in a shown window (rig limit).
- Critic: 9 findings, 8 fixed. Open: Ctrl+T/W/L/D do nothing while a native page has focus (needs a hub change in forge.py / forge_views.py).

### G2 Board, Calendar (Relay task 76)
- Board: backs off and recovers by itself, dash-led notes no longer crash crew.py (500), no double send, new-notes chip, opacity-only pulse, size caps on note/name/answer. Commits da1da83, a9891e0. pytest 19.
- Calendar: offline chip with backoff, odd times/tags/keep days a 400 not a 500, newest draw wins, no double save, wrapping top bar. Commits 2fa25d2, a953ac8. pytest 23.
- Verified: hidden 10 s 0 fetches both; server killed and back: recover in 13.5 s / 4.5 s; triple submit = 1; screenshots 760-1920.
- Not verified: Calendar's "Sum up this day with Jan".
- Critic: 6 findings, 4 fixed. Open: a hidden Board with its backend down still ticks every 15 s (desktop alerts; needs a shared change); first visit no longer rings unseen notes (kept on purpose).

### G3 Files, Comix (Relay task 78)
- Files: drive poll rests and backs off, offline chip, newest folder wins, no twin paste, lost jobs reported, thumbnails return after a backend restart. Commits e1207cc, d0b77db. pytest 40, check_ui 20/20 (six runs). Static only: next page reload.
- Comix: offline bar, no double sends, title filter (new), 400/404 for bad settings, ids past SQLite range and broken CBZ. Commits 7e495db, 1fa29a3. pytest 44.
- Verified: hidden 0/0/0 both; recovery after restart 13 s / 28 s.
- Not verified: real comix downloads.
- Critic: 9 findings, 7 fixed. Open: Comix jobs through shared `pollJob` poll while hidden (shared fix); `DELETE` of an unknown series answers 200 (kept). Also left: Files trash error names "/" for a missing path (cosmetic).

### G4 Terminal, Crew Room (Relay task 79)
- Terminal: socket reconnects back off and learn why they closed (4403 stale token, 4404 shell gone, 4409 taken by another window); malformed and binary messages ignored; calm boot card. Commits a05fa70, 04ec41f. pytest 14, check_ui 40/40.
- Crew Room: room poll backs off, draw loop rests behind other apps, no stacked polls, no double launch, newest room wins, counts layout at 1100 px. Commits e62eb91, 87bf457. pytest 37.
- Not verified: a real Crew Room launch.
- Critic: 5 findings, 3 fixed. Open: with 15 tabs the shared `forge_chrome.js` hub buttons wrap (shared); each lost pane retries on its own (design note).

### G5 Settings, Code, Logins (Relay task 80)
- Settings: calm card until it works, changes made while down kept and re-sent, Reset needs a second press, unticking "Follow my desktop wallpaper" now says why. Commits 3dcd150, 51e2e69. pytest 34. Static only.
- Code: "Waiting for Code's backend" instead of "Failed to fetch", one start at a time, a deleted remembered folder opens home, NUL in `/api/url` a 400. Commits f2866b2, 4b4df76. pytest 14.
- Logins: calm card for down backend or broken accounts.json, per-account Bring login in lock, tabs are real buttons. Commits ecd27cf, b7c2b80. pytest 7.
- Not verified: a real signed-in account, Code with the real code-server data dir.
- Critic: 9 findings, 7 fixed. Open (both shared/forge_theme.py): a wallpaper in a sub-folder counts as "not in the folder"; the `wallpaper` setting accepts any string (200 kB went in).

### G6 Emberfield (Relay task 81)
- Changed: one frame loop (a double click on Begin ran the game at 2-4x), no double submits (two presses at the cave mouth lost the valley), boot retry, audio and tutorial rest while paused or hidden, no overlap at narrow widths, settings type-checked (`heavy_cores: "abc"` bricked boot), `Cache-Control: no-cache` and `?v=` on scripts.
- Commits: d68f95d, 1805b10.
- Tests: pytest 130, check_ui 18/18, in-game selftest 64/64.
- Critic: 6 findings, all fixed (Escape on a death screen resumed at 0 hp and could write a permadeath save back).

### G7 Arcade, Drift Peaks (Relay task 82)
- Arcade: sound timers stop with the sound, status re-asked on show, Jan proxy input checks, Hearsay save capped and atomic, first tests. Commits 59ac54c, 2fcf73c. pytest 21, check_ui 13/13.
- Drift Peaks: music pauses while hidden, failed saves retried with backoff, Art save locked. Commits f3315e5, 08d9ad3. pytest 21, node 13, check_ui 13/13.
- Not verified: sound by ear.
- Critic: 6 findings, all fixed (parallel Hearsay saves shared a temp file; Waveguide and Lanternfall intros threw every frame). Finding 3 (Drift Peaks show-wait) reasoned, hide/show count not re-run.

### G8 Janhollow (Relay task 83)
- Changed: header wraps at 760 px (buttons were unreachable), polls back off, boot card retries, one request per button, Start over asks twice, AudioContext suspended out of sight, NaN walking direction and bad settings guarded (were a 500 on every state call).
- Commits: 3b1ba20, 2d3dd9c.
- Tests: pytest 133.
- Not verified: real Jan, sound by ear.
- Critic: 6 findings, all fixed.

### G9 Cosmos, Eighty Six (Relay task 84)
- Cosmos: menu sky 30 fps through `ForgeIdle.loop` and rests while hidden, saves retried with backoff while the server is down, puzzle sound sleeps while hidden, Close app button pinned beside Full screen. Commits 11358c9, ffa4ae0. pytest 45, node 61, check_ui 39/39.
- Eighty Six: one test run at a time (pid file survives a backend restart), repeated launches refused for 5 s, escaped names and fps log values, watchers with backoff. Commits aa02df6, 9eab667. pytest 35, check_ui 20/20.
- Not verified: a real Play click starting the game.
- Critic: 6 findings, all fixed. **No critic file** (see above).

### G10 Acchan, Jan Tune (Relay task 85)
- Jan Tune: Advanced panel hides again, poll backs off (20 requests a minute idle down to about 2), knob names and values checked (they become llama-server flags). Commits fe828a1, d63828a. pytest 32.
- Acchan: poll backs off, composer row below 1000 px, conversation ids must be plain names (`"../settings"` wrote a chat over settings.json), settings type-checked. Commits 9cb582f, 51e5bdd. pytest 221.
- Not verified: a real tuning run, any Acchan reply from Jan, voice.
- Critic: 6 findings, all fixed. Note: Acchan's `test_shells.py` timing test failed twice under load (not touched; load-sensitive).

### G11 AI Studio, PixelForge (Relay task 86)
- PixelForge: links shared forge.css, preview and audio rest when hidden, calm first-load retry, malformed packs/plans/sounds a 422. Commits e03fd10, c198cc6. pytest 62.
- AI Studio: library search safe from FTS5 syntax (was a 500), request bounds, newest search wins, preview video rests while hidden, lazy thumbs. Commits 625af42, ef9dd4d. pytest 49; pyright 7 errors, all older.
- Not verified: real generation or Jan drawing.
- Critic: 10 findings, 9 fixed or handled. Open: `preload=metadata` thumbs reverted to default (could not be checked headless); edit-counter fix reasoned only.

### G12 Dossier, Foresight (Relay task 77)
- Dossier: slugs that climb out of the library refused (`DELETE /api/subject/%2E%2E` resolved to the whole library), wrong-typed numbers a 400, watchers rest and back off, triple-click deepen no longer queues 75. Commits 4416aa7, 195105e. pytest 319.
- Foresight: reads the library Dossier is pointed at (saw 2 subjects instead of 2,450 since the 2026-09-25 move), data root follows it, bad sweep input a 400, boot retries. Commits 6f78d95, 57d4de6. pytest 126.
- Not verified: live Foresight against `~/AN3-backup` (its backend was not running).
- Critic: 6 findings, all fixed.

### G13 NovelForge, InkForge (Relay task 87)
- InkForge: fit-width pages scroll, tall strips open fit to width, click zones, resume at Komikku's page, broken PDF imports refused and cleaned up, safe JSON writes. Commits f8325f2, 7b06634. pytest 15.
- NovelForge (kept small around the uncommitted 09-28 rework): state poll backs off, the committed `index.html` had a script tag inside its inline script (live file was fine), unknown project/series reads no longer create folders, "." and ".." stay inside the data folder. Commits db58dff, 386c9c9. pytest 43 in the working tree, 10 on a HEAD export; pyright 2 older errors.
- Not verified: a timed large PDF import, NovelForge generation.
- Critic: 7 findings, all fixed. Left for whoever lands the rework: other NovelForge routes still build `Project(name)` for unknown names.

### G14 PanelForge, PrintForge (Relay task 88)
- PrintForge: first committed as found (08649f9), then: 3D view draws on change and the turntable rests while hidden, settings type-checked, damaged STL a 422, narrow layout. Commits 0d16caa, ebecce6. pytest 31, check_ui 15/15.
- PanelForge: Infinity/NaN in a body a 422, over-long ids a 404, `.`/`..` ids refused, polls back off, a lost job stops after three 404s. Commits a81eda5, d67fc22. pytest 593.
- Incident on the scratch copy only: a `null` body fuzz started render/voice/script jobs and Jan's llama-server router; all stopped by PID, nothing generated, real data untouched.
- Not verified: Open folder, real 36 MB STLs, a real render job end to end.
- Critic: 10 findings, 9 fixed. Open: at 760 px standalone the shared floating Close app / Full screen buttons cover the bottom of the check panel (shared chrome).

### G15 PulseForge (Relay task 89)
- Changed: `DELETE /api/projects/%2E%2E` deleted all of `~/PulseForgeData` (confirmed on the scratch copy only); any `.`/`..` segment is now a 400. NaN/Infinity bodies a 400 (one could brick a project), names capped, copies never overwrite, queue poll backs off, one request per press, escaped names. The fuzz of every write route went from 76 answers of 500 to 0.
- Commits: 2af9e5a, 37daa47.
- Tests: pytest 362 + 1 skipped, check_ui 15/15.
- Critic: 8 findings, all fixed. Note: Emerson's real `~/PulseForgeData` settings.json had picked up `"x": -Infinity` from the sweep's own test run; removed by hand (backup in `backups/2026-10-07-overhaul/sweep/pulseforge/critic/`); tests now use a temp file.

### G16 Media, MediaForge (Relay task 90)
- Media: calm start-up retry, empty and error states, one request per click, bounds (`limit -5` started a real yt-dlp search), NUL-safe paths, 760 px header. Commits 2fc302e, ba3e85e. pytest 35.
- MediaForge: **security fix**: `/api/dedupe/thumbnail?path=/etc/passwd` returned the file; now only pages of a pending review. Settings type-checked (a bad saved value crashed start-up), one request per click on 21 buttons, start-up banner with backoff, calmer copy. Commits b6b51ba, b5b9a43. pytest 21; pyright 54 to 40 errors, none new.
- Critic: 6 findings, 4 fixed, 1 not confirmed. Open: the MediaForge banner says unreachable when any of its four start-up requests fails (none fail that way today).

### G17 Power, Keymap, Study Companion (Relay task 91)
- Power: one `ForgeIdle.poll` (5 s shown, nothing hidden; was a 30 s tick behind other apps), backs off with a calm strip, one mode apply at a time with the slider locked. Commits b930000, 23ecdf9. pytest 145.
- Keymap: History tab opens again (Undo was unreachable), edits only touch files the scope registry lists, no sideways scroll at 760 px. Commits 0924208, b8a9496. pytest 19.
- Study Companion: question bank no longer doubles its first page, names escaped, plot parser refuses unknown names, Jan re-checked instead of trusted. Commits e790144, 5604388. pytest 19 (new).
- Not verified: a real Power mode apply, a real edit to Emerson's Hyprland config, a real chat with Jan.
- Critic: 7 findings, 6 fixed. Open: shared `errText` shows "[object Object]" for FastAPI's list `detail` (shared).

### G18 Codec Lab, Codec Player (Relay task 92)
- Codec Lab: upload names stay inside `clips/uploads/`, run requests checked against the strategy schema (422, nothing queued), comparison videos actually play (an old seek loop kept them at 0 s), poll rests and backs off, 760 px layout.
- Codec Player: a 1.3 kB `.acv` could ask for 250 GiB; header and in-stream sizes now checked against the memory budget; malformed files a 422.
- Commits: in `~/Forge` only the stubs: Codec Lab fbace83, 5ebb411; Codec Player b8a6bf6, 98f2936. **The code in `~/anime-codec-lab` is uncommitted** (repo has no first commit).
- Tests: pytest 77 (anime-codec-lab venv), check_ui 29/29.
- Not verified: the lossless H.264 4:4:4 output video in WebKitGTK; no real encode run.
- Critic: 12 findings, all fixed (two suspected ones by design, not raced/run).

## Measure this (every item the workers listed; none measured in the sweep)

- Browser: wakeups of a hidden Browser frame over 5 min (only the 25 s long-poll expected); WebKitWebProcess CPU of a video page in a hidden background tab.
- Board: paint cost of the old box-shadow pulse vs the new opacity ring; CPU of the 3 s full-board poll with 150+ notes.
- Files, Comix: wakeups per minute in a hidden Forge tab; requests per minute with the backend stopped (expect 2/min after a minute).
- Crew Room: page CPU with the room on screen (rAF 60 Hz with a 30 fps draw gate). Terminal: xterm DOM renderer vs WebGL with htop in 3 panes.
- Code: code-server child CPU while Code is hidden (`pidstat -p <pid> 5`). Settings, Logins: confirm zero cost while hidden in the real hub.
- Emberfield: hidden CPU with the AudioContext suspended; frame cost at 1920 vs 760 px.
- Arcade: menu ambient page CPU; rAF still running on pause/intro/over screens. Drift Peaks: title screen page and GPU time vs a ride.
- Janhollow: hidden CPU with Sound on before/after the suspend; backend CPU with the 200 ms world poll on screen (would 300-400 ms look the same?); atmosphere.js frame cost at 1920 px.
- Cosmos: menu power and frame rate after the 30 fps cap (2026-09-16 numbers in its WIP: 12.0 W flying, 10.5 W idle); hidden behind another app should equal Forge idle. Eighty Six: while a test run goes with the tile in front.
- Jan Tune: requests per minute idle in front (20 down to about 2). Acchan: one request per 30 s with its backend stopped; smoothness of a chat with hundreds of tool cards in WebKitGTK.
- AI Studio: GPU/CPU with a preview video while another app is shown; first-paint memory with lazy thumbs. PixelForge: wakeups with the frame preview hidden.
- Dossier: WebKit CPU with a long bulk queue hidden over 5 min. Foresight: requests per hour to 8438 while hidden (450/h before, 0 expected).
- InkForge: webtoon scroll smoothness at 1920 px in WebKitGTK; time and disk of a 300-page PDF import. NovelForge: one request per 30 s with its backend stopped.
- PrintForge: fps and CPU while the turntable spins on a 36 MB STL; idle CPU with a model loaded. PanelForge: CPU of a render job shown vs hidden.
- PulseForge: hidden CPU with a Scenery preview loop; paint cost of the Autopilot shimmer.
- Media: CPU while a video plays hidden. MediaForge: CPU while a long encode streams its log hidden.
- Power: wakeups of its hidden WebKit process over 10 min; the backend sampler's own CPU share.
- Codec Player: peak memory decoding a real `.acv` near the 4 GiB budget; a big real vector_art encode to confirm the inflate ceiling.

## shared/ and hub changes the workers recommend (none made; they need their own task)

1. One thin, themed scrollbar rule in `shared/forge.css` (copied into nearly every app now: G2, G10, G12, G13, G14, G16, G17).
2. `[hidden] { display: none !important; }` in `shared/forge.css` (the Jan Tune Advanced bug).
3. `shared/forge_idle.js`: an `onChange(fn)` hook (G8, G11, G15), `whenShown()` (G4), `onDown`/`onUp` or `onRecover` (G2, G4), `watch(fn, ms, on)` (G12), and stretch `hiddenMs` by the backoff after failures (G2).
4. `shared/forge.js` `pollJob`: pause while hidden and back off on errors (G3, G16).
5. `shared/forge.js` `errText`: join FastAPI's list `detail` into one line (G16, G17).
6. Shared helpers in `shared/forge.js`: a "backend not reachable yet" boot card (G5), a one-press-one-request `onClickOnce` (G15, G16); `initTabs` should wire `.mode-switch` too (G17); `toast()` kinds `good`/`bad`/`warn` aliased or documented (G17).
7. A shared Python helper (`forge_errors.install(app)` or `forge_api.py`): 422 without echoing the value, NaN/Infinity bodies refused, ENAMETOOLONG as 404, `.`/`..` path segments refused (G14, G15, G17).
8. `Cache-Control: no-cache` or a `?v=` stamp for static JS in every app (G6: a stale cached script never booted).
9. The power tier (`forge_power.js`) reaching app iframes and games (G4, G6, G8).
10. `shared/forge_chrome.js`: place the Close app chip beside a fixed `#go-fullscreen` (G9), reserve space for the floating buttons at narrow widths (G14), hub buttons wrap with 15 tabs (G4).
11. `shared/forge_theme.py`: send `wallpaper_name` relative to the folder, validate and cap the `wallpaper` setting (G5).
12. `shared/forge_content.py`: a module-level `delete()` (G7).
13. Hub: forge_views.py reloads a view on `web-process-terminated`; forge.py passes Ctrl+T/W/L/D/Shift+T to the Browser while a page has focus (G1).
14. Tests and tooling: a per-app `pyrightconfig.json` with `extraPaths: ["../../tests"]` (G9); a check that no `<script src=` sits inside an inline script in `apps/*/static/*.html` (G13); one decision on Starlette 1.6's `httpx2` test-client dependency (G11).

## Still open from final-breaker.md (hub and Claude app, outside the sweep)

Breaks 1-5 of `sessions/2026-10-07-overhaul/critics/final-breaker.md` were not part of U1 and are still open:
1. Medium: the covered-window threshold has no hysteresis; a share around 0.35 flips the tier, every app's theme and the particles on each sample (`shared/forge_power.js`).
2. Low: the battery-saver edge has no hysteresis; a reading bouncing 20/21 % toasts each time.
3. Low (older): Alt+Space overview: a second press or Esc inside the 220 ms snapshot wait is lost.
4. Medium: Claude run controls: Ultracode then Normal clicked quickly ends on Ultracode (`apps/claude/static/run_controls.js`).
5. Low: Claude `POST /api/everyone/{id}/message` is a 500 when the crew module is missing.
Each has a written fix in that file.

## Questions for Emerson

1. After your next Forge restart: does the Browser show a page at once, and does it take typing and clicks inside a page? (G1)
2. In Forge, open Codec Lab, click a finished run: does the right-hand lossless 4:4:4 "output" video play in WebKitGTK? (G18)
3. `~/anime-codec-lab` has no commits, so the Codec Lab/Player sweep is only on disk. Make its first commit?
4. A Forge restart is needed for every backend fix above (and the Browser fix in forge.py). Restart when it suits you.
5. The shared/ list above: queue it as one task?
6. The idle-CPU before/after numbers were not taken (the laptop crashed during the first try, see the last section). Run them with you at the laptop? Part B also needs about 10 minutes off the charger.
7. `~/ram-culler/gui_daemon.py` segfaulted three times at login after the 06:00 reboot (GTK). Worth a look outside Forge.

## Idle-CPU before/after

**Not measured. Left as a written run plan.** No before/after number in this wave is a measurement yet; every power claim above is reasoning.

What happened (2026-10-08): the first session of this task found the machine quiet (load 0.2, only task 93 running, usage 3 %) and started Part A of the numbers plan in the headless GNOME rig. The laptop went down at about 05:58-06:00 AWST (`last -x`: session "crash", reboot 06:00). The journal from that boot is not kept, so the cause is unknown: the rig may have caused it or it may be a coincidence. Right after the reboot, gnome-shell segfaulted once (06:00:48, restarted itself) and `~/ram-culler/gui_daemon.py` segfaulted three times in GTK (06:00:24-06:00:55); Emerson's Forge was not running. `/tmp/t63/numbers` was lost with the reboot, so no raw lines survive.

Decision (Noa, relay-93-work, second session): I did not run the rig again unattended, because a second GPU-heavy run on a desktop that had just crashed could take Emerson's session down again. The done-when line allows a written plan instead.

**Run plan (as is, nothing to change):** `docs/library/power/2026-10-07-overhaul-numbers.md`, sections "The two trees", "Part A" and "Part B". In short:
1. Commit everything first, then unpack two trees with `git archive`: before = tag `snapshot-2026-10-07-pre-overhaul` (54cc2f9), after = HEAD, into `/tmp/t63/numbers/{before,after}`; copy the live `hub/theme.js` and `hub/status.js` (Board pointed at 8901 / 8902).
2. Start scratch Board backends on 8901 (before) and 8902 (after), stop them by saved PID.
3. Part A, rig on AC: `tests/browser/headless_gnome.sh start`, then `tools/web_gpu_bench.py` 3 runs per tree interleaved (B A B A B A) for each row: home; app in front; app in front + `forgeShare(0.2)`; battery 60 % simulated; battery 40 % simulated; plus `tools/cover_bench.py` maximised/minimised per tree. Quiet window (`tools/quiet_window.py run --seconds 140`) only for "home" and "app in front" (about 280 s of the 600 s grant). Then the frame-time pass. `headless_gnome.sh stop`.
4. Part B, real laptop, read only: `tools/gpu_use.py 15 --json` on his running Forge, home / app / minimised x 3, on AC then about 10 minutes unplugged. Needs Emerson.
5. Fill the two tables in that file and copy the raw JSON lines under "Raw".

Before the next try: run Part A **with Emerson at the laptop** (or at least after a clean boot with nothing crashing), first a single 20 s cell (`run.sh` once per tree) to see the rig stays up, and only then the full set. If the machine goes down again during the rig, the rig itself is the suspect and `headless_gnome.sh` needs looking at before any number is taken.
