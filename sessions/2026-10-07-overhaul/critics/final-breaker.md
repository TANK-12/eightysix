# Overhaul wave: final breaker
date: 2026-10-08 · for: Claude · reviewer: final-breaker (helper of relay-63-work)

Scope: hub/index.html, desktop/particles.html, shared/forge_idle.js, forge_power.js, forge_framecap.js, forge_particles.js, apps/claude/static, power-sweep poll wrappers. Mission skipped (task 73). Scratch files in /tmp/t63/final-breaker/.

Covered so far: hub keys/overview/tiles/search (area 1), power tier flapping (area 3), forge-visible flapping (area 2), Claude API bad JSON, two tabs, 200 kB send, mode/limits mid-run, header widths (area 4), server killed under Board/Terminal/Claude polls (area 5), fps following the tier (area 3). All areas done.

## Breaks

1. **medium · Covered-window threshold has no hysteresis: tier, every app's theme and the particles re-apply on every share sample around 0.35.** Verified.
   - Where: shared/forge_power.js:42,75-76,79-81 (`COVERED_SHARE = 0.35`, one edge used both ways); fed by hub/index.html:1864 `forgeShare`, which forge.py:1414 calls on every change of the GNOME extension's 0.05-step share (extension.js:163, re-measured 120 ms after each restack/size-changed).
   - Repro: /tmp/t63/final-breaker/hub/power_harness.js (run with `source /tmp/t63/final-breaker/run.sh; cd /tmp/t63/final-breaker/hub; run power power_harness.js status_tool.js`): `forgeShare(0.30)` / `forgeShare(0.35)` alternated 20 times.
   - Seen: `FAIL :: share flapping 0.30/0.35 x20 :: theme posts to app=20, Particles.apply=20, tiers=reduced: mostly covered|full`. Resizing a window whose edge sits over Forge at about a third flips the whole tier (fps 60 to 15 and back, visualiser on/off) on each step.
   - Fix: give the covered state an exit edge. In forge_power.js add `const UNCOVERED_SHARE = 0.45;` and in the hub keep a sticky flag: in `forgeShare`, `covered = covered ? n < UNCOVERED_SHARE : n < COVERED_SHARE; shownShare = covered ? Math.min(n, COVERED_SHARE - 0.01) : Math.max(n, COVERED_SHARE);` (or do the same in forge.py's `on_share` before calling the page), plus a test in tests/test_power_tier.py with 0.30/0.35/0.40 alternation expecting one tier change.

2. **low · Battery-saver edge has no hysteresis: a charge reading bouncing 20/21 % on battery flips the tier and shows the "Saving power" / "Effects back to full" toast each time.** Verified.
   - Where: shared/forge_power.js:73 (`Number(s.battery) <= saver`, same edge both ways); toast at hub/index.html:1925-1936.
   - Repro: same harness, `forgeSetStats({plugged:false, battery: 20|21, gpu:{level:0}})` x20.
   - Seen: `FAIL :: battery 20/21 flapping on battery x20 :: theme posts=20, Particles.apply=20, hud=20`.
   - Fix: leave battery-low only at `saver + 3`: keep a `batteryLow` flag in the hub (`batteryLow = onBattery && pct != null && (batteryLow ? pct <= saver + 3 : pct <= saver)`) and pass it to ForgePower as `state.battery_low`, which `level()`/`tier()` use instead of comparing the raw percent.

3. **low (pre-existing, not this wave) · Alt+Space overview: a second press or Esc inside the 220 ms snapshot wait is lost, so the overview opens anyway.** Verified.
   - Where: hub/index.html:1449 `toggle()` reads `this.open`, which is false until `reveal` runs (1451-1467); `close()` does not cancel the pending `wait` timer or the `forge-snap` listener; Esc goes to `Overview.key` only when already open (1589).
   - Repro: /tmp/t63/final-breaker/hub2/flap_harness.js (hub copy at /tmp/t63/final-breaker/hub2/.h/index.html, dump-dom run), with an app open and `window.webkit.messageHandlers.forge.postMessage` stubbed so the snap is "asked" as in WebKit: `forgeKey("overview")`, 30 ms, `forgeKey("overview")`.
   - Seen: `FAIL :: Alt+Space twice within 30 ms (app open, snap asked): overview closed :: open=true` and `FAIL :: Alt+Space then Esc 20 ms later: overview not left open :: open=true`.
   - Fix: keep the pending reveal on the object: in `show()` store `this.pending = { wait, reveal }`; `toggle() { return this.open || this.pending ? this.close() : this.show(); }`; `close()` starts with `if (this.pending) { clearTimeout(this.pending.wait); window.removeEventListener("forge-snap", this.pending.reveal); this.pending = null; }`, and `reveal` clears `this.pending`. Let the capture keydown at 1589 also call `Overview.close()` on Escape while `Overview.pending`.

4. **medium · Claude run controls: Ultracode then Normal clicked quickly ends on Ultracode; the last click is dropped.** Verified.
   - Where: apps/claude/static/run_controls.js:36-40. `setUltra(on)` returns early when `!!meta.ultracode === on`, and `meta` only changes when the first save's answer comes back (apply via app.js:826), so a second click during the first save compares against the old value and is thrown away.
   - Repro: scratch Claude on 8821 (fake Claude), /tmp/t63/final-breaker/cui/run.py: open one conversation in two pages; send a 200 kB message from page A; in page B click Ultracode then Normal in the same tick (`const [n,u]=document.querySelectorAll('#run-host .run-seg button'); u.click(); n.click();`).
   - Seen: `after Ultracode then Normal quick clicks: server ultracode = True | B pressed: Normal:false Ultracode:true`. A slow backend (a real turn running) widens the window to a normal double click.
   - Fix: track the wanted value and catch up after each save: `let want = null, saving = false; async function setUltra(on) { want = on; if (saving) return; saving = true; seg.classList.add("saving"); try { while (want !== !!meta.ultracode) { const w = want; await save({ ultracode: w }); if (want === w && !!meta.ultracode !== w) break; } } finally { saving = false; seg.classList.remove("saving"); } }`. Also mark the clicked button pressed at once (optimistic `aria-pressed`) so the click shows.

5. **low (outside the wave's files) · Claude `POST /api/everyone/{id}/message` answers 500 when the crew module is missing.** Verified.
   - Where: apps/claude/everyone.py:97 imports `crew`, reached from web_app.py:338; only LookupError is caught.
   - Repro: scratch server with HOME=<scratch>/home: `curl -H 'X-Forge: 1' -H 'Content-Type: application/json' -d '{"text":"hi"}' http://127.0.0.1:8821/api/everyone/x/message`.
   - Seen: `500 Internal Server Error`; log `ModuleNotFoundError: No module named 'crew'`. In the real HOME the crew skill exists, so this only bites when ~/.claude/skills/crew moves.
   - Fix: in everyone._crew catch ImportError and raise `RuntimeError("the crew skill is not installed")`; in web_app.everyone_message add `except RuntimeError as e: raise HTTPException(503, str(e))`.

6. **low · No poll backs off while its server is down: the power sweep wired `ForgeIdle.poll` everywhere but no caller passes `backoff` or returns `false` on failure.** Verified.
   - Where: apps/board/static/index.html:508 (`refresh` catches and returns undefined, 411-421), apps/terminal/static/app.js:703 (`refreshInfo`, 645), apps/claude/static/app.js:1085 (`refreshTabs`) and the Claude long-poll retry at app.js:568-570 (fixed 3 s). Same pattern at calendar/comix (no backoff option).
   - Repro: /tmp/t63/final-breaker/polls/run.py: each app on a scratch port (Board 8830, Terminal 8831, Claude 8821), page open in headless Chrome, `fetch` wrapped to count, server SIGKILLed, counted 0-10 s and 10-30 s, server started again.
   - Seen: `board: up10s=[3,3] | down0-10s=[4,0] | down10-30s=[6,0] (per10s 3.0) | back10s=[4,4] probe='live'`; `terminal: up10s=[5,5] | down0-10s=[5,0] | down10-30s=[10,0] (per10s 5.0)`; `claude: up10s=[2,2] | down0-10s=[5,0] | down10-30s=[12,0] (per10s 6.0) probe='Lost the connection…' | back10s=[7,6]`. The rate never drops; all three recover and Board/Claude say they are offline. Cheap on localhost (connection refused), so low, but it is the "must back off" rule.
   - Fix: return `false` from the catch of each job and pass the option: Board `ForgeIdle.poll(refresh, 3000, { hiddenMs: 15000, backoff: 2, maxMs: 30000 })` with `return false;` in refresh's catch; Terminal `ForgeIdle.poll(refreshInfo, 2000, { backoff: 2, maxMs: 30000 })` with `return false` when `api` throws; Claude `refreshTabs` the same, and in `follow()` keep `let retry = 3000;` before the loop, `retry = 3000` after a good answer and `await new Promise((r) => setTimeout(r, retry)); retry = Math.min(retry * 2, 30000);` in the catch. A test in tests/forge_idle_check.mjs already covers backoff itself.

## Checked and fine
- forge_idle.js under flapping (/tmp/t63/final-breaker/idle_flap.html, 400 forge-visible flips): polls at the same rate after as before (`{"a":10,"b":4,"c":3}` per s both), hidden runs only the hiddenMs job (`b:1` in 1.1 s), never two runs in flight (`maxInflight=1`).
- forge_chrome.js Rest + ForgeIdle.loop inside an iframe, real-time Chrome (/tmp/t63/final-breaker/loop/run.py), 300 fast and 300 slow `{forge:"visible"}` posts: `base [60,60]`, `after 300 flips [60,60]`, `hidden [0,0]`, `after slow flips [60,60]`. No doubled rAF loop.
- Hub: 60 app/home flips end with the app told `visible:true` last; Alt+W/Alt+Q/Alt+1 spam x25 leaves widgets flag and body class in step; Esc x10; tile x12 with Alt+Q between keeps one iframe; search typing then section chips then clear leaves no tile hidden.
- Power: CPU hysteresis (cpu_sweep.py over shared/forge_gpuload.py CpuBusy): 75/65 alternation never flips, 71 for 6 samples then 40 for 11 flips only per sustained run; None readings keep the state. fps follows the tier both ways: busy `cap=25 pfps=25 vis=false`, covered `cap=15 pfps=15`, battery 15 % `cap=25`, and after 50 mixed flips settles at `cap=60 pfps=30 vis=true tier=full`.
- Claude: malformed JSON (`{bad`, `[]`, `"x"`, `null`) gives 4xx on all 19 POST routes tried; two pages on one conversation both draw the 200 kB turn, no page errors, composer emptied; send while the server is down says `Not sent: Failed to fetch` and keeps the text; after SIGKILL the page says `Lost the connection…` and recovers by itself; header at 760/1100/1500 has nothing clipped (`sw == cw`, 3/2/2 rows); the critic's item 1 fix holds.

## Not covered
- desktop/particles.html in a live GNOME session (only its forge_power path, which is the hub's). The Enjoy layout under server-down. Calendar/Comix/Files/Settings server-down (same wrapper pattern as Board, see break 6). Real WebKit (all runs were headless Chrome). No fps or CPU measurements, as the brief asked.
- Note on side effects: the bad-JSON sweep sent `{"text":5,...}` to `/api/avatars/motions/describe` on the scratch server, which asks the shared Jan for a motion; curl gave up after 10 s and the request never logged an answer. Jan was not restarted; no other call reached it. Avoid that route in future sweeps.
- Scratch servers: Claude 8821, Board 8830, Terminal 8831, all stopped by PID (`ss -ltnp | grep :88` empty at the end).
