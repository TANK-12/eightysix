# U1 critic: group G7 (Arcade, Drift Peaks)
date: 2026-10-08 · for: Claude

Critic for Rin's commits 59ac54c (Arcade) and f3315e5 (Drift Peaks). Scratch
ports 8975-8977, everything under `/tmp/u1/G7-critic/` (temp HOME, a copy of
the Drift Peaks save, a one-second music file, `JAN_BASE_URL=http://127.0.0.1:9/v1`).
Scripts: `breaker.py` (API fuzz + UI), `dbl.py` (HEAD against the pre-sweep
copy), `intro.py`; output in `breaker.out`, `breaker2.out`, `breaker3.out`,
server logs `arcade.log`, `driftpeaks.log`. Every server stopped by PID, no
headless Chrome of mine left (`pgrep` shows only G8's).

## Breaks

1. **Medium, verified: concurrent Hearsay saves fail with 500, and can corrupt
   the save.** `apps/arcade/web_app.py:206`. The new atomic write uses one temp
   name per process (`hearsay_save.<pid>.tmp`), but FastAPI runs the sync
   endpoint on a thread pool, so two saves at once share it. Repro: 24
   concurrent `POST /api/hearsay/save` (400 kB each): 19 x 200, 5 x 500,
   `FileNotFoundError ... hearsay_save.892053.tmp -> hearsay_save.json` in the
   log. Two threads writing the same temp file can also interleave, and the
   mixed file is then moved into place: the next load reads it as "no save"
   and the case is gone, which is exactly what the change meant to prevent
   (the corruption part is reasoned, not reproduced). Hearsay fires a
   fire-and-forget save after every action, so a quick double action is enough.
   Fix: a unique temp per write (`fd, tmp = tempfile.mkstemp(dir=SAVE_PATH.parent,
   suffix=".tmp")`) or a module `threading.Lock` around write and replace, plus a
   test that posts 20 saves from threads and expects all 200 and a valid file.

2. **Medium, verified, pre-existing (not from the sweep): the Waveguide and
   Lanternfall intro screens throw 60 errors a second.** `apps/arcade/static/index.html:731`
   (`else if(needsPaint){ inst.frame(0,t); needsPaint=false; }`), with the
   throws at `:1626` (Waveguide `trace()` reads `src.c`, `src` is null before
   Begin) and `:3092` (Lanternfall reads `p.x` before Begin). Because the
   throw comes before `needsPaint=false`, the paint is retried on every frame
   for as long as the intro is up. Repro: open either card and wait 3 s: 180
   `TypeError`s; Aphelion 0; after Begin 0. Same on the pre-sweep copy
   (lines 1589 / 3055), so it predates U1, but the worker's "no page errors"
   check never opened those two intros. Fix: clear `needsPaint` before the
   call (`needsPaint=false; inst.frame(0,t);`) and have the two games return
   early from `frame` until their state is built.

3. **Low, verified: Drift Peaks save retries skip the backoff on every show.**
   `apps/driftpeaks/static/js/game.js:103` (`onShown` -> `persist()` at 400 ms).
   Repro: server killed, one settings change, then hide/show every 3 s for 30 s:
   11 `PUT api/save` (one per show); the next 30 s with no flips: 1. Bounded
   by how fast someone switches apps, so not a storm, but the backoff is
   reset on every show. Arcade's status ask has a 15 s floor; Drift Peaks has
   none. Fix: in `onShown`, send at once only if the last try is older than
   `saveWait` (keep a `lastTry` time), otherwise leave the pending retry timer.

4. **Low, verified: Arcade's menu dot stays red while the page stays shown.**
   `apps/arcade/static/index.html:3278-3287`. Repro: wait 16 s, kill the
   backend, hide and show (dot red), restart the backend, stay shown: 20 s
   later the dot is still `dot no`. It recovers only on the next show or on
   opening a Jan game. The report's "recovers by itself" means "on the next
   show". `S.backend=false` also stops Hearsay saving, so a failed ask made
   while a case is open drops every save until the next show. Fix: after a
   failed ask, try once more after 15-30 s while shown (one `setTimeout`,
   cleared when hidden), or let `save()` try anyway and set `S.backend` from
   its result.

5. **Low, verified, pre-existing: the Hearsay save accepts a lone surrogate
   and then cannot be loaded.** `apps/arcade/web_app.py:189-195` and `:199`.
   Repro: `POST /api/hearsay/save` with `{"a":"\ud800"}` gives 200, then
   `GET /api/hearsay/save` gives 500 (`UnicodeEncodeError: surrogates not allowed`
   while rendering the response; the `except` around `json.loads` does not
   cover it). A crafted request is needed, so it is unlikely. Fix: in the save,
   `text.encode("utf-8")` inside a try and answer 400 on failure (this also
   makes the 1 MB cap count real bytes).

6. **Low, verified, pre-existing: reverting a shape the game never shipped
   is a 500.** `apps/driftpeaks/web_app.py:222` calls `forge_content.delete`,
   which does not exist in `shared/forge_content.py` (`AttributeError`).
   Repro: `DELETE /api/shapes/nosuchshape` gives 500. The Art editor answers it
   calmly ("Could not put it back."), so it only shows for a store shape that
   another tool made. Fix: remove the entry file through
   `forge_content.entry_path("shapes", PREFIX + sid)` in the app (missing
   file -> 404), or add `delete()` to `shared/forge_content.py` in a separate,
   shared-owner change.

## Checked and fine
- Tests rerun: Arcade pytest 19 passed, `tests/check_ui.py` 13/13 PASS;
  Drift Peaks pytest 20 passed, node tests pass, `node --check` on the
  changed JS (and on Arcade's inline script), `tests/check_ui.py` 13/13
  PASS. black: 4 + 2 files unchanged; pyright 0 errors on both apps' touched
  .py files.
- Commit hygiene: each commit touches only its own app (`git show --stat`);
  nothing staged or left in `git status` for either app; no debug prints or
  commented-out code in the diffs.
- Rest: Arcade menu 4 s shown: 0 timers (rAF only); in play with the demo tone
  13-14 timer ticks per 4 s, and the same after two rounds of double clicks on
  every card, Begin, Pause and Menu (no stacked sound schedulers); Hearsay intro
  badge correct with Jan off. Drift Peaks: a hidden save retry does not fire;
  the change lands after the server is back and the page is shown.
- API input: Arcade chat with bad JSON 422, list body 422, 200 kB 413, `NaN`
  temperature and `Infinity` max_tokens 400, unicode 503 (Jan off, as meant),
  deep nesting 400; save 200 kB 200, non-object 422. Drift Peaks save list 422,
  300 kB 413, bad JSON 422, deep 400; shape traversal 405, unicode id 400,
  wrong types 422; music traversal 404.
- Looks: Arcade menu at 760/1100/1500/1920 and Hearsay intro at 760/1920; Drift
  Peaks title, settings and Art at 760/1100/1500/1920 (contact sheets
  `/tmp/u1/G7-critic/sheet-*.png`, looked at): no clipping, overlap or contrast
  trouble; the fade keyframes keep each panel's own centring transform.

## Not covered
- The real Forge window (WebKitGTK), sound by ear, a real background tab
  (`document.hidden`) as opposed to the hub signal.
- Whether the Drift Peaks sound-effect context is really suspended while
  hidden (module scope, not reachable from the page; the code was read only).
- Hearsay with Jan on (never asked Jan anything, as the brief says).
