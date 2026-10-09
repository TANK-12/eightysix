# U1 sweep, group G6 (Emberfield): critic and breaker report
date: 2026-10-08 · for: Claude · critic for Noa (relay-81-work), Relay task 81, commit d68f95d

Scratch copy on port 8965, temp HOME `/tmp/u1/G6-critic/home` (copies of
~/ForgeArtData and ~/ForgeGameData; ~/EmberfieldData never touched), fresh
Chrome profile per run under `/tmp/u1/G6-critic/sb-*`. Probe scripts:
`/tmp/u1/G6-critic/{api_probe,probe,probe2}.py`; shots and contact sheets in
`/tmp/u1/G6-critic/shots/`. Server stopped by PID; no Chrome of mine left
(`pgrep` on my profile path = 0; the 7 headless Chromes already running belong
to another session's arcade check).

None of the breaks below was introduced by the sweep. Break 1 is an older game
rule bug that the robustness pass did not catch.

## Breaks

1. **Escape on a death screen keeps playing, and full permadeath can be
   undone.** Severity medium. **Verified.** This was there before the sweep.
   - Where: `apps/emberfield/static/index.html:335`
     (`if (k === "escape") { S.world && (S.running ? pauseScreen() : resume()); ... }`).
     `die()` (`static/play.js:713`) leaves `S.world` set and `S.running` false,
     so Escape calls `resume()`.
   - Repro and what I saw:
     - Full rule: `/?seed=4242&rule=full`, then `autosave(true)` and `die()`.
       The save is deleted and "The valley closes" shows. Press Escape: the
       game runs again (`S.running` true, veil hidden). The next autosave (sleep,
       leaving the wilds, Save, or `beforeunload`) writes the deleted slot back:
       `/api/saves` lists it again.
     - Character rule: `die()`, then Escape on "You fell". Play goes on with
       `hp 0`, the day does not advance, and Wake up is skipped.
   - Fix: let Escape toggle only the pause screen. For example, set a
     `S.screen = "pause"` (or `S.paused`) flag in `pauseScreen()`, clear it in
     `resume()`, and have the Escape handler call `resume()` only when that flag
     is set. Death, permadeath, shop, craft and settings screens then ignore
     Escape, or map it to their own Back/Leave. Add a check_ui case: `die()`,
     Escape, expect `S.running === false`.

2. **The settings API ranges are wider than the UI's.** Severity low.
   **Verified.**
   - Where: `apps/emberfield/emberfield/config.py:73,75`. RANGES allows zoom
     1-8 and day_seconds 20-86400. The UI sliders allow zoom 2-5 and a day of
     1-30 minutes (`static/ui.js:355` and the zoom slider just below it).
   - Repro: `POST /api/settings {"values":{"zoom":1e300}}` is accepted and
     clamped to 8. The game then boots at zoom 8, a huge close-up. The Settings
     screen reads "zoom — 8x" with the slider stuck at 5, and pressing Save
     quietly changes it to 5.
   - Fix: clamp to the ranges the UI offers (zoom 2-5, day_seconds 60-1800), or
     widen the sliders to match. Keep one source of truth.

3. **Unknown settings keys are stored without a size limit.** Severity low.
   **Verified.**
   - Where: `config.py:93-95`. Unknown keys take any str, int, float, bool or
     None, of any length and in any number. Known text keys are capped at 500
     characters.
   - Repro: `POST /api/settings {"values":{"unknown_big":"x"*200000}}` returns
     200. `settings.json` grows to 200 kB, and every `GET /api/settings` and
     page boot then carries it.
   - Fix: refuse unknown keys with a 422 (the page only sends known ones), or at
     least apply the same 500-character limit and a key-count cap.

4. **A broken save shows a raw JavaScript error in the toast.** Severity low.
   **Verified.**
   - Where: `static/world.js:389` (continueSave).
   - Repro: a save without `world` (`POST /api/saves/broken {"name":"x"}`),
     then click it on the title screen.
   - Saw: "could not open that valley: Cannot read properties of undefined
     (reading 'seed')". It is calm, with no page error and nothing lost, but the
     wording is not user-facing.
   - Fix: check `save && save.world && save.world.seed != null` before using
     it, and throw `new Error("that save is damaged")`.

5. **A long unbroken save name pushes every save card past the title card.**
   Severity low. **Verified** at 760, 1100, 1500 and 1920 px
   (`shots/sheet-title-saves.png`).
   - Where: the `.choices` / `.choice` CSS in `static/index.html`, rendered from
     `static/ui.js:258-261`.
   - Repro: a save whose name is 200 kB of "x". Only a crafted save can do
     this, because the game always names saves "Emberfield".
   - Saw: all four save rows overflow the card to the right edge of the window.
   - Fix: `.choice b{overflow-wrap:anywhere}` (or
     `text-overflow:ellipsis; white-space:nowrap; overflow:hidden`) and
     `min-width:0` on the choice.

6. **The selftest script is appended twice when a `?seed=` boot retries.**
   Severity low. **Suspected** (read from the code, not run).
   - Where: `static/index.html:493`. `selftest.js` is appended before the
     `?seed` world fetch. If `/api/world/new` fails, `retryBootSoon()` calls
     `boot()` again, which appends `selftest.js` a second time, so two selftest
     runs post to `/api/selftest`.
   - Fix: guard it with a flag (`if (!window.__selftestLoaded)`), or move the
     append after `startWorld` succeeds.

## Checked and fine

- `pytest -q tests`: 130 passed. `black --check` is clean on `web_app.py`,
  `config.py`, `tests/test_api.py` and `tests/check_ui.py`. `pyright
  --pythonpath ./.venv/bin/python` on the same files: 0 errors. `node --check`
  passes on every `static/*.js`.
- The worker's `tests/check_ui.py --port 8965`: 15/15 ok. In-game selftest
  `/?seed=777&selftest=1`: PASS 64/64 (read from `/api/selftest`).
- Commit hygiene: d68f95d touches only `apps/emberfield` (11 files).
  `git status apps/emberfield` is clean. No stray `console.log`, `print` or
  `debugger`; the one `print` is check_ui's own output line. No temp files and
  no commented-out code.
- Rest when hidden:
  - Title screen hidden 10 s: 0 fetches, 0 frames, 0 timers.
  - Game hidden by the hub (worker check): 0/0/0, audio suspended.
  - Sleep, then hidden during the fade: it wakes to the pause screen, with
    0 frames, 0 fetches and 1 one-shot toast timer over 5 s.
  - Boot failing while hidden for 35 s: 0 fetches. The pending retry fires once
    and waits, and the game boots by itself when shown.
- Boot backoff with the API blocked while visible: 4 tries in 40 s (2, 4, 8,
  16 s, then 30 s). The calm card with "Try now" reads well at 760 and 1920 px.
- Server killed mid-game: 0 fetches over 0-10 s and over 10-30 s.
  - The wilds toast "the way down is blocked: the Emberfield server is not
    answering"; `travelling` is reset.
  - Save shows "could not save" and the button is enabled again.
  - After a restart the wilds work again with no reload.
- Double submits:
  - A double click on Continue: 1 save GET, 1 world/new, 0 doubled frames.
  - A triple click on Settings Save: 1 POST.
  - Double Begin and double wilds: covered by the worker's check, re-run here.
- Escape while Save & leave is in flight (1.5 s latency): ends on the title
  screen with the game stopped and no page errors.
- Bad and huge input:
  - Settings: a wrong type, `[]`, invalid JSON, NaN, Infinity, 2.5, `true` for
    a number, null for text, or a 200 kB known text value: all 422, nothing
    stored. 1e300 is clamped (see break 2).
  - World, wilds and interior take 2^80 seeds, negative days, and unicode or
    200 kB building ids without error.
  - Save slots with unicode work (`ü.json`). `..%2F` path traversal returns 404.
  - A save named `<img onerror>` is escaped on the title screen; the XSS flag
    stayed unset.
  - `Cache-Control: no-cache` is present on static files.
- Looks: game, pause and settings at 760, 1100, 1500 and 1920 px (half scale).
  No overlap of HUD, hint, tutorial or hotbar. The thin veil scrollbar shows
  on Settings. Contrast is readable.

## Not covered

- The real Forge window (WebKitGTK): `-webkit-scrollbar` and the hub's
  `forge:visible` message coming from a real parent frame. I posted the message
  from the page itself.
- Audio: whether the ambience really resumes on the next key after `rest()`. I
  read that `unlock()` calls `ctx.resume()` but did not listen.
- Shop, craft and storage screens at the four widths, and a title list with
  dozens of saves.
- No fps, CPU or power measurement (by rule).
