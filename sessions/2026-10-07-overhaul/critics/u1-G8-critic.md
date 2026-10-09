# U1 sweep critic: G8 Janhollow (commit 3b1ba20)
date: 2026-10-08 · for: Claude · critic for Hikari (relay-83-work)

Scratch setup: `/tmp/u1/G8-critic/` (own copy of ~/ForgeGameData, server on
8985 with `JAN_BASE_URL` at the dead port 8989, temp `FORGE_JAN_SETTINGS_DIR`),
headless Chrome through `tests/cdp_driver.py`. The server and every Chrome were
stopped by PID afterwards. Real saves, real Janhollow (8448) and Jan untouched.

## Breaks

1. **Unhashable settings values are still a 500** (medium, verified).
   `janhollow/sim.py:120` and `:123`: `value in AWAY_MODES` / `value in CHATTER_LEVELS`
   raise `TypeError: unhashable type` for a dict or list.
   Repro: `curl -X POST :8985/api/world/settings -H 'Content-Type: application/json' -d '{"values":{"away_mode":{"a":1}}}'`
   → 500 (same for `{"chatter":["x"]}`, `{"away_mode":[1]}`, and
   `/api/world/new` with `{"settings":{"away_mode":{"a":1}}}`). The WIP says
   wrong-type settings now keep the current value; the new test only covers
   hashable wrong types (`chatter: 5`). Fix: `if isinstance(value, str) and value in AWAY_MODES`
   (same for chatter) and add a dict/list case to `test_a_bad_value_in_an_update_keeps_the_current_setting`.

2. **Huge integers in settings are a 500** (medium, verified).
   `janhollow/sim.py:114` and `:127`: `float(400-digit int)` raises
   `OverflowError`, which the `except (TypeError, ValueError)` misses.
   Repro: `-d "{\"values\":{\"day_minutes\":$(python3 -c "print('1'*400)")}}"` to
   `/api/world/settings` → 500; same with `start_hour`, and with `/api/world/new`.
   Fix: catch `OverflowError` too (both places); add `10**400` to the
   non-finite settings test.

3. **Slot names of 4-byte characters still overflow the file name** (low, verified).
   `janhollow/saves.py:26-31` caps at 64 *characters*, the comment says the limit is
   255 *bytes*, and the temp file adds `.json.tmp`. `𠀀` (CJK Ext B) passes `isalnum()`
   and is 4 bytes in UTF-8, so 63 of them = 252 + 9 bytes.
   Repro: `curl -X POST ":8985/api/saves/$(python3 -c "import urllib.parse;print(urllib.parse.quote('𠀀'*63))")"`
   → 500, log `OSError: [Errno 36] File name too long ... .json.tmp`.
   Fix: trim by encoded length, e.g. `while len(safe.encode()) > 200: safe = safe[:-1]`
   (or cap at 48 chars), and add a 4-byte-char case to the long-slot test.

4. **Step aboard / Step out: no guard against double clicks and no message when the backend is down** (low, verified).
   `static/game.js:869` `joinStation`, `:881` `leaveStation` (wired at `:999`)
   are not wrapped in `once()` and have no catch. Repro in headless Chrome:
   triple click `#join` → 3 `/api/player/join` requests; double click
   `#leave` → 2 requests; with every `/api/` fetch failing, clicking either
   gives no toast and an unhandled rejection "Failed to fetch". The brief asks
   for one request per button and calm errors; the sweep did this for the
   settings-pane buttons only. Fix: `$("#join").onclick = () => once($("#join"), joinStation)`
   and the same for `#leave`.

5. **Day-length slider shows a value that was not applied** (low, verified).
   `static/game.js:472` `push()`: on failure it toasts "the day length was not
   changed", but the slider and its number keep the new value (repro: fail
   the API, set the range to 300 and fire `change`: slider reads 180, `S.settings.day_minutes`
   stays 2). Fix: in the rejection handler call `set(S.settings.day_minutes)`.

6. **A boolean counts as a day length** (low, verified, pre-existing).
   `{"values":{"day_minutes":true}}` → 200 and `day_minutes: 2.0` (`float(True)`).
   Fix: refuse `bool` before `float()` in both numeric branches.

## Checked and fine
- Commit 3b1ba20 touches only `apps/janhollow/` (8 files), no other session's
  hunks, no stray prints or commented-out code; `git status apps/janhollow` clean.
- `pytest -q tests`: 127 passed. `black --check` clean and `pyright` 0 errors on
  player.py, saves.py, sim.py, test_u1_robustness.py. `node --check` on game.js, sound.js.
- NaN hold → 200 and state stays 200; `1e308` hold → state 200; non-dict
  `values` → 422; 200 kB `say` → 200 (server trims to 200 chars).
- The worker's checks, re-run on my port: hub-hidden 10 s = 2 state polls +
  2 heartbeats, 1 rAF (the documented heartbeat for the away modes); server killed:
  7 fetches in 0-10 s, 4 in 10-30 s, calm header and Voices text, recovered
  by itself 9.6 s after restart, no page errors.
- Save triple click = 1 request; Start over needs a second press and resets after
  4 s; typing `n` in the talk box leaves names alone; held key cleared on hide;
  AudioContext running → suspended (hidden) → running, and stays suspended
  when Sound is off.
- Screenshots at 760/1100/1500/1920 (crew, log, settings, aboard), looked at at
  50 %: header wraps to two rows at 760 with every button reachable, no clipping or
  overlap. (`/tmp/u1/G8-critic/shots/`.)

## Not covered
- Real Forge window (WebKitGTK), real Jan, sound by ear.
- A real hidden document (headless only fakes `document.hidden`, so the
  rAF count in that case says nothing).
- Long lists (the crew is a fixed 9; the log was not filled to thousands of lines).
- Note: the worker's own scratch server was still listening on 8980 at the start
  of this review.
