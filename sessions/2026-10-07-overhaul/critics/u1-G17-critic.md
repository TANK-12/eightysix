# U1 sweep critic: group G17 (Power, Keymap, Study Companion)
date: 2026-10-08 · for: Claude · critic for Relay task 91 (U1 sweep of Relay task 74)

I reviewed commits b930000 (power), 0924208 (keymap) and e790144 (study-companion)
against the worker report `reports/u1-G17.md`. Scratch copies ran on 9075 (power),
9076 (keymap) and 9077 (study-companion) under `/tmp/u1/G17-critic/s/`, with a temp
HOME, a copy of `~/.config/hypr` and Jan pointed at a dead port (127.0.0.1:9). I
stopped every server by its PID, closed every Chrome, and left ports 9075-9079 free.
I never applied a Power mode: the one browser test that clicks the mode buttons
answers `POST /api/modes/*` inside the page, and the power log shows 0 such
requests. I sent nothing to the real Jan and edited nothing in `~/Forge`. Scripts
and screenshots are in `/tmp/u1/G17-critic/`.

## Breaks

### 1. Power: clicking a second mode while one is being applied leaves the slider on a mode that was never applied (medium, **verified**)
- **Where:** `apps/power/static/index.html:363` (the `.stop` click handler sets
  `slider.value` before calling `applyMode`) together with `:391` (the new
  `busy` guard returns early without putting the slider back). For the keyboard
  path, `:767` (the `input` handler calls `showMode`) also runs while the guard
  drops the `change`.
- **Repro:** run `/tmp/u1/G17-critic/power_apply2.py` with Power on 9075. The
  script stubs the mode POST with a 3 s delay inside the page. It clicks
  "Battery saver" and then "Auto" 0.5 s later.
- **Seen:** one POST (`saver`), so the double apply is fixed. After that:
  `current saver | slider 2 | on-stop 0 | state Active: Battery saver`. The
  slider thumb stays on Auto while the label and description say Battery saver
  (screenshot `shots/power_second_stop.png`). `syncMode` never corrects this,
  because `data.current === current`. With the keyboard (click Cool, then
  ArrowRight on the focused slider during the apply): slider 2, highlighted
  stop 2 (Auto) and Auto's description are shown, but Cool is applied. Before
  this commit the second click started a second apply, so the slider at least
  matched the outcome. The guard turned that into a silent mismatch.
- **Fix:** while `busy`, disable the stop buttons (`b.disabled = true`; the
  `.stops .stop:disabled` rule at `:120` already exists but nothing sets it) and
  check `busy` in the click handler before touching `slider.value`. In the
  `applyMode` early return, put the slider and `showMode` back to the index
  being applied (keep it in a variable).

### 2. Keymap: a damaged history line can still make History a 500, and Undo of a half-written entry is a 500 (low, **verified**)
- **Where:** `apps/keymap/editor.py:90-92` keeps any dict with `id` and
  `timestamp`, then sorts on `timestamp` with no type check. `apps/keymap/web_app.py:174`
  reads `target["file"]`, `["old_text"]` and `["new_text"]` without checking
  they exist.
- **Repro (scratch copy):** append `{"id":"partial","timestamp":2000000000}` and
  `{"id":"lst","timestamp":"soon"}` to `data/history.jsonl`, then
  `curl http://127.0.0.1:9076/api/history`. Result: 500, `TypeError: '<' not
  supported between instances of 'int' and 'str'`. The History tab shows an
  error and every Undo becomes unreachable. With only the `partial` line:
  `curl -X POST .../api/undo/partial` gives 500 `KeyError: 'file'`, and the
  History tab lists that row with empty or undefined cells and a live Undo
  button.
- **Fix:** in `read_history`, keep only entries where `timestamp` is an int or
  float and `file`, `line`, `old_text` and `new_text` are present with the
  right types. This matches the WIP claim that "damaged history lines skipped".
  Add a test with a string timestamp mixed with real entries.

### 3. Power: with the server away at load, the page still shows raw "Failed to fetch" next to the calm strip (low, **verified**)
- **Where:** `apps/power/static/index.html:806-815`. `firstLoads(false)` writes
  `e.message` into `#mode-state` and toasts it for autostart, priority and fps.
  `loadProcesses` does the same in its table.
- **Repro:** `python3 /tmp/u1/G17-critic/bootdown.py 9075 "<ready js>" 6` (all
  `/api/` fetches fail for 6 s after load). Screenshot `shots/boot_down_9075.png`
  shows the calm strip at the top, red "Failed to fetch" in the Mode card, a red
  "Failed to fetch" toast, empty mode labels and empty auto-switch selects. The
  worker's own `/tmp/u1/G17/shots/boot_down_9070.png` shows the same thing. It
  recovers by itself about 6 s after the API returns, so this is only a looks
  problem. The brief asks for no raw errors, and the report calls the strip
  calm.
- **Fix:** in `firstLoads`, treat a `TypeError` as "server away": call
  `serverDown(true)` and stay quiet. Only show `e.message` for real HTTP
  errors. Do the same in `loadProcesses`.

## Nits and suspected
- **Nit, verified:** `apps/study-companion/web_app.py:188` compares
  `row.get("topic") != topic` without `str()`. The new topics list uses
  `str(r["topic"])`, so a bank row with a numeric topic (`"topic": 5`) gives a
  "5" option that matches 0 rows. Also, `static/index.html:251` says "No
  questions in the bank for this course yet." when only the topic filter is
  empty. It should say "No questions for this topic."
- **Nit:** `apps/keymap/web_app.py:62`. `_refusal` refuses an empty old combo
  but accepts an empty new text. An API edit to `new_text: ""` succeeds, and
  then its Undo is refused with "the old key combo is empty". The UI cannot send
  an empty new text (it always adds quotes), so this only happens through the
  API.
- **Nit, verified:** `.stops .stop:disabled` (`power/static/index.html:120`) is
  dead CSS until break 1 is fixed.
- **Nit, measured:** Keymap's `.src { overflow-wrap: anywhere }` applies at every
  width, not only at 760 px. It narrows the Source column at 1100-1920 px from
  260 to 174 px. With real-length paths (`/home/ejb/...`, swapped in the page)
  the table only grows from 11567 to 11640 px, so it is barely visible. With the
  long scratch paths every row went to two lines
  (`shots/km_beforeafter_1920.png`). It could move into the `max-width: 820px`
  block.
- **Suspected, shared:** `errText` returns `body.detail` as is. The new
  `RequestValidationError` handlers (like FastAPI's default) return `detail` as
  a list, so a 422 would toast "[object Object]". I found no UI path in these
  three apps that sends a 422 (Power clamps fps and nice before sending), so this
  is a shared `forge.js` note only.

## Checked and fine
- **Tests:** power 145 passed, keymap 17 passed (`tests` + `test_parser.py`),
  study-companion 19 passed. The keymap and study tests use tmp_path and
  monkeypatched data dirs and touch no real data. `black --check` and
  `pyright --pythonpath ./.venv/bin/python` on every touched .py: unchanged, 0
  errors.
- **Commit hygiene:** each commit contains only its own app's files. There was
  no foreign hunk, no `console.log`, `print` or `debugger` added, and no
  commented-out code. `git status` is clean for all three apps. Backups exist and
  keymap's `web_app.py` backup equals `0924208^`. Each WIP.md has the U1 section
  and says backend changes need a Forge restart.
- **Rest when hidden** (hub hidden signal, 10 s): power 0 fetch, rAF or timers
  (11 fetches in 5 s shown); keymap 0; study 0. Each recovers on show.
- **Server killed:** Power made API calls at 2.0 s and 12.0 s in 30 s, showed
  the strip, and recovered 1 s after restart. Keymap and Study do not poll once
  loaded (0 requests) and recovered.
- **API abuse:** I sent empty, 200 kB, NaN/1e999, wrong-type, list-instead-of-dict,
  `..`, `%2E%2E` and unicode/NUL inputs to all three. Every one got a 4xx with a
  clear message: course traversal 404, chat over 20,000 characters 413, bad
  count 400, `/etc/passwd` edit refused. Power `limit=-1` returns 1 process. No
  500s outside break 2.
- **Keymap fence:** all 4 files with editable binds (variables.lua,
  caelestia-keybinds.lua, custom/ and hyprland/keybinds.lua) pass the new
  `_editable_files` check, so no real bind is wrongly refused. A UI edit with
  Enter pressed 3 times sent 1 POST. A double-clicked Undo sent 1 POST and left
  the files byte-identical to the start. The History tab opens. A combo
  containing a backslash is refused calmly by luac and the file is unchanged.
  The no-match empty state is fine.
- **Study with a course named `Odd "<b>name' & 100%#?`**, a source named
  `it's "<b>x<b>" & #1` and bank rows with `<img onerror>`, a string `steps`,
  list, string and broken lines: everything is escaped (`window.__xss` stays
  undefined) and URL-encoded. The bank reads 20 of 47. Three fast Load more
  clicks followed by one more reached 47 of 47 with the button disabled. Three
  fast course flips ended on the right course with the right topics and
  sources. Switching course plus picking an old topic at once reset the topic
  correctly. Quiz and chat with Jan offline gave a calm toast and no request. A
  90k-character message was refused with 413, the text went back into the box
  and the history stayed at 0.
- **Looks:** no sideways scroll at 760, 1100, 1500 or 1920 px for any of the
  three (`shots/m_*`), and no clipping or overlap.

## Not covered
- Anything inside the real Forge window (WebKitGTK scrollbars, the
  `forge-visible` path through the real hub). A real Power mode apply (only
  stubbed). A real chat or quiz against Jan. Power's backend sampler CPU share
  while the page is hidden. These are the worker's "measure this" items and were
  not measured, by rule.
