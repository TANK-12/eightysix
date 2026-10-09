# U1 critic, group G10: Acchan and Jan Tune
date: 2026-10-08 · for: Claude · written by the G10 critic (scratch ports 9005-9006)

Commits checked: fe828a1 (Jan Tune), 9cb582f (Acchan). Scratch copies ran on
9005 (Acchan; ACCHAN_DATA, JAN_MODELS_DIR, FORGE_JAN_SETTINGS_DIR all temp
dirs) and 9006 (Jan Tune; JAN_TUNE_DATA temp dir). Scratch files are in
`/tmp/u1/G10-critic/`. No tuning run was started, Jan was never asked to
generate, and Apply was only clicked with fetch stubbed.

## Breaks

1. **medium, verified.** Acchan's chat list is blank when the page opens on a
   `#c=<id>` link whose chat no longer exists (deleted, or a stale link).
   Where: `apps/acchan/static/app.js:247` (`if (!res.ok) return;` returns
   before `loadChats()`; the startup path at about line 472 calls `openChat`
   and does not call `loadChats`). Repro: open `http://127.0.0.1:9005/#c=nope`
   with 60 chats on disk. Saw: 0 `.chat-item`s and an empty sidebar, with no
   empty-state text (`shots/ac-linked-missing-1100.png`). This was already
   there before the commit, but it is the blank pane the brief rules out. Fix:
   in `openChat`, call `loadChats()` (and `newChat()` for a 404) before
   returning on `!res.ok` or a network error, and set `chatsFailed = true` in
   the catch so the poll reloads the list.
2. **medium, verified.** One odd file in `conversations/` gives
   `GET /api/conversations` a 500, which takes down the whole chat list.
   Where: `apps/acchan/acchan/conversation.py:112` (`data["id"]` in
   `list_all`; it fails with TypeError when the file holds a list and with
   KeyError on `{}`). Repro: `echo '[]' > conversations/zz.json` and
   `echo '{}' > conversations/zz.json` each gave a 500. The report says
   "corrupt conversation file 404 not 500", but that only covers the
   single-chat GET. The page then shows "Chats will show here when Acchan's
   server answers" while the status line says everything is up, and it retries
   on every 15 s poll. Fix: skip any row that is not a dict with a str `id`
   that passes `valid_id`, and catch KeyError/TypeError there too.
3. **low, verified.** The stored `id` inside a chat file is trusted over its
   file name. If a file's content says `"id": "../evil"`, then
   `Conversation.load("mism").path` resolves to `ACCHAN_DATA/evil.json`
   (checked in Python on the scratch copy), so the next save writes outside
   `conversations/`. `"../settings"` would overwrite settings.json, which is
   the very hole the commit closed for request ids. Where:
   `acchan/conversation.py:92`. Getting there needs a hand-written or corrupt
   file. Fix: `cls(cid, ...)` (the file name), or refuse when
   `not valid_id(data["id"])`.
4. **low, verified.** In Jan Tune, the "Written to model.yml ..." line after
   Apply is wiped by the next status poll, because `render()` rebuilds
   `#winner`. Where: `apps/jan-tune/static/index.html:287`. Repro, with fetch
   stubbed: click Apply, and the message is there; call `poller.now()`, and
   the message is `""`. This was already there before the commit, but the new
   backoff makes when it vanishes look random (3-30 s). Fix: keep the last
   apply message in a variable and render it into `#applyMsg` on each
   rebuild, or move `#applyMsg` outside `#winner`.
5. **low, verified.** The Acchan `voice` setting is not checked against
   `voice.VOICES`. `POST /api/settings {"voice":"nonexistent_voice"}` returns
   200 and the value is stored, while the report says "unknown choices"
   are refused. Where: `acchan/settings.py` `_ok` (voice falls through to the
   generic string check). Fix: accept only ids in `voice.VOICES` or with the
   `piper:` prefix.
6. **low, suspected.** Jan Tune `/api/run` now treats `{"knobs": {"x": []}}`
   as "tune every knob" (`_checked_knobs` returns None). The old code read it
   as "only knob x, all values". The page strips empty lists itself, so only
   direct API callers see the difference. Where: `apps/jan-tune/web_app.py`
   `_checked_knobs` (`out or None`). Duplicate values also pass, for example
   `[24]*100000` makes `planned` huge; the tests are cached, so it is only
   cosmetic. Not run, because a valid body starts a real run.

## Checked and fine
- Tests: Jan Tune 31 passed; Acchan 218 of 218 passed in a full run, the
  `test_shells` timing test included. `black --check` and pyright gave 0
  errors on every touched .py in both apps.
- Commit hygiene: each commit holds only its own app's files. `qwen.py` is
  still untracked and was left out. No debug prints or commented-out code.
  Both WIP.md files have the U1 section.
- Hidden 10 s, with a counter on fetch, setTimeout, setInterval and rAF:
  Jan Tune and Acchan both 0 of everything; 1 fetch when shown again.
- Server killed: Jan Tune 2 fetches in 0-10 s and 1 in 10-30 s, the offline
  line shows (`hidden=false`) and clears after restart. Acchan 0 and 1, says
  "Server not answering, retrying", and recovers with 61 chats. No JS errors.
- Jan Tune API: repeats 0 and 11, interval -1, an empty model, a 201-char
  model and `../x` are refused (422 or 404). An unknown knob, a string, float,
  bool or nested value, and an off-list value (513) all get a 400, and the
  status stays not running. Status and apply with a traversal id are safe;
  apply with no result gives a 400.
- Acchan API: wrong-typed or 200 kB settings get a 400; a list body gets a
  422; conversation traversal, unicode and 20 kB ids get a 404; the v1 route
  gives a 400 for messages as a string, an empty or int content, non-dict
  messages, or an empty /api/chat text.
- UI: the Advanced panel is display none, then grid, then none; three clicks
  on Run (stubbed) send 1 POST; two clicks on Apply send 1 POST; three clicks
  on a chat's ✕ send 1 DELETE. A 300-tool-card chat with a 200 kB reply
  opens without errors. Screenshots at 760, 1100, 1500 and 1920 looked fine
  (`/tmp/u1/G10-critic/shots/`).

## Not covered
A real tuning run, any Jan reply, voice, the page inside the WebKitGTK Forge
window, and Acchan opening a chat while the server is down at page load.
