# Cost line and Ctrl+Z: handoff (Relay task 69)

date: 2026-10-07 · for: both

Two small fixes Emerson asked for at about 21:40. Both are committed. They
go live when Forge reloads the pages; the cost recount also needs the Claude
app's backend restarted (Emerson restarts Forge himself). **forge.py was not
touched.**

## 1. Claude panel cost line

**Problem.** The Kaito chat (conversation `03f4781c43d1`) showed "Spent in this
conversation: $2276.72". `meta.session_costs` was
`{"earlier": 2201.83, "ea15de3f…": 75.4}`. The "earlier" figure came from the
old bug: Claude Code's `total_cost_usd` is a running total for the session, and
the runner added it up turn by turn.

**Fix** (`apps/claude/runner.py`):
- A new `Conversation._recount_cost()` runs on load and after each result. When
  `session_costs` holds "earlier", it rebuilds each session's figure from the
  conversation's own event log (`<id>.jsonl`), taking the largest
  `total_cost_usd` per `session_id`. The log keeps every result event, so this
  is an exact recount.
- "earlier" (`runner.EARLIER_COST`) is kept in meta and never deleted, but it
  is never added to `cost_usd` again. A session with no result in the log is
  left out.
- Why not Claude Code's transcripts (`~/.claude/projects/…/<session>.jsonl`)?
  They hold token counts but no cost, so the conversation log is the better
  source. This is an assumption I made; Emerson was not asked.
- For the Kaito chat, every one of its 92+ result events belongs to one
  session (`ea15de3f…`), so the honest figure is that session's latest total:
  **$75.64** at check time, down from $2277.47.

**Label.** In the classic page (`static/app.js`) it now reads "This conversation
at API list prices: $75.64 (not billed: your plan covers it)". In the Enjoy
page (`static/enjoy.js`) the row is "worth  $75.64 at API list prices (not
billed)". It shows two decimals, not four.

**Verified:**
- `apps/claude/.venv/bin/python -m pytest -q tests`: 194 passed. There are new tests in `tests/test_lost_messages.py`: the
  recount from a log (several sessions, a result with no session id, a bad
  value), "earlier" kept but not counted, and a conversation with no "earlier"
  left as it was.
- A scratch server with a copy of the Kaito chat's meta and result lines, in
  real headless Chrome. The status line read exactly "This conversation at API
  list prices: $75.64 (not billed: your plan covers it)", and I looked at the
  screenshot. The live data was not changed.

## 2. Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y in text boxes

**Cause.** Nothing in Forge swallows these keys. forge.py's key handler passes
them to the page, and neither the hub nor the Claude app binds them.
WebKitGTK itself binds no key to undo. I checked this with real key presses
in an off-screen WebKitGTK view: typing works, but Ctrl+Z, Ctrl+Shift+Z and
Ctrl+Y left a plain textarea unchanged. The box still keeps its undo history,
and `document.execCommand("undo")` reaches it.

**Fix** (shared level):
- New `shared/forge_undo.js`, about 40 lines. It binds Ctrl+Z to undo, and
  Ctrl+Shift+Z and Ctrl+Y to redo, in text inputs, textareas and
  contenteditable elements (Cmd works too). It leaves alone a key a page
  already handled (`defaultPrevented`, for example the avatar maker's own
  Ctrl+Z), IME composition, read-only or disabled boxes, and non-text
  targets.
- `shared/forge_chrome.js` loads it, so every page that loads forge_chrome
  gets it: 38 of the 40 app and hub pages, the hub included. Not covered:
  `apps/emberfield/static/index.html` and `apps/claude/static/docs.html`,
  which don't load forge_chrome.
- In the Claude panel, picking a slash command from the menu now goes in
  through `execCommand("insertText")`, so Ctrl+Z can take it back. Setting
  `.value` from a script still wipes a box's undo history. That is a WebKit
  rule, and the comment in forge_undo.js says so.

**Verified:**
- `tests/test_forge_undo.py`, run with `apps/acchan/.venv/bin/python -m pytest
  -q tests/test_forge_undo.py`: 3 passed.
  - Node unit tests (`tests/forge_undo.test.js`): which keys count, which
    boxes count, and a page's own handling left alone.
  - A real WebKitGTK test (`tests/forge_undo_webkit.py`, run in a child
    process with system Python because PyGObject is needed). Real key
    presses in a textarea on the page and in one inside an iframe (apps run
    in the hub's iframes) gave "ab" → Ctrl+Z "" → Ctrl+Shift+Z "ab" → Ctrl+Z
    "" → Ctrl+Y "ab". Without the script, the same presses leave "ab", which
    reproduces the bug.
- The real Claude panel page on a scratch server:
  - In real WebKitGTK, the `#input` box gave the same sequence.
  - In headless Chrome, "hello world" → Ctrl+Z "hello" → Ctrl+Shift+Z
    "hello world". There was no double undo where the engine already has
    native undo.

**Not checked:** the live Forge window. It needs a page reload: Ctrl+R on an
app, or a Forge restart.

## Files
`apps/claude/runner.py`, `apps/claude/static/app.js`, `apps/claude/static/enjoy.js`,
`apps/claude/tests/test_lost_messages.py`, `apps/claude/WIP.md`,
`shared/forge_undo.js` (new), `shared/forge_chrome.js` (one hunk only; the
rest of its uncommitted diff belongs to another session), `tests/forge_undo.test.js`,
`tests/forge_undo_webkit.py`, `tests/test_forge_undo.py`.

pyright: no new errors. `tests/forge_undo_webkit.py` reports the same
"unknown import symbol" for `gi.repository` that every gi file here gets,
because PyGObject has no stubs.
