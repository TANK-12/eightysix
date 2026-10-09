# Crew Room: current state


## Attach files to a background task (2026-10-08, Koharu, Relay task 118)

The "In the background" box has Attach files, paste and drop (`wireAttach` in
`static/app.js`, chips in `#task-files`). Uploads go to `/api/attach` and
`/api/attach/paste-image` (`shared/forge_attach_api.py`, guarded by
`_same_site`), into `<CREWROOM_DATA_DIR or ~/.local/share/forge/crewroom>/attachments/`;
`/api/launch/task` takes `files` and the prompt on stdin ends with an
`Attached files:` list. Verified: `tests/test_launch.py::test_a_task_names_its_attached_files`
(saves, refuses another Origin with 403, prompt on stdin carries the path,
`/etc/passwd` refused with 400); crewroom suite 39 pass, pyright 0; headless
Chrome on a spare server: drop + paste made two chips and both files landed
in the sandbox data dir (screenshot looked at). Not verified: a real task
started with a file.
Second critic (session 3) fixed: a send while a file is still uploading
now waits (`ForgeAttach.wire(...).busy()`, "A file is still uploading")
and a file that lands during a send stays for the next message instead of
being wiped; copied text that also carries a picture pastes as text; a
failed desktop paste says why; a file over 50 MB is refused before the page
reads it; the same path twice is named once. Tests: `shared/forge_attach.test.js` 6 pass. The 403 now reads "Only the Crew Room page can do that".

## Ultracode helpers show up (2026-10-08, Izumi/ejb-ac)

Emerson: Riku (ejb-6a, an ultracode Eighty Six job) showed no helpers in
Mission Control or the Crew Room. Ultracode keeps its workflow helpers one
folder deeper, in `<session>/subagents/workflows/wf_<id>/agent-*.jsonl`, and
Board, Crew Room, Mission and the Claude app each globbed only
`subagents/agent-*`. All four now ask `shared/forge_helper_files.py`
(PLACES lists the folders; a new layout is one entry there). Test:
`~/Forge/tests/test_forge_helper_files.py`, plus a workflow case in this
app's tests. Verified live: Riku showed 8 working helpers in Crew Room and
12 in Mission (screenshots looked at).

## U1 sweep (2026-10-08, Relay task 74)
Tomo (relay-79-work, Relay task 79), group G4. Page only (`static/app.js`,
`index.html`, `room.css`); no Python touched. Changed:
- Break 6: the room poll is now `ForgeIdle.poll(pollOnce, S.poll s,
  { backoff: 2, maxMs: 30000 })` (`shared/forge_idle.js` loaded): it rests
  while hidden as before, `pollOnce` returns false when the backend does not
  answer (15 s timeout, so a hung backend cannot stall it) and the page says
  "Lost the Crew Room backend, retrying by itself" instead of a raw fetch
  error. It picks up by itself when the backend is back.
- The draw loop runs through `ForgeIdle.loop`, so it also stops while another
  app is in front in Forge (it only checked `document.hidden`).
- No stacked poll chains: the settings poll slider or demo box used to start
  a second chain when changed while a fetch was in flight, and dragging the
  slider fired a fetch per step; now one restart, 300 ms after it settles.
- "Open terminal" ignores a second click while the first is opening (a
  double click opened two GNOME Terminals); "Start task" the same.
- Rapid room tab clicks: the newest room wins (an older answer arriving last
  used to show the wrong room).
- Boot shows "Setting up the room…" and, when the backend cannot be reached,
  retries (1.5 s doubling to 30 s, waiting while hidden) instead of a dead
  page with one error line.
- Looks: details/settings/launch panels and the status line ease in (180 ms,
  opacity/transform, reduced motion honoured), thin themed scrollbars on the
  side panel and conversation blocks (incl. `::-webkit-scrollbar`), room tab
  colour transitions; under 900 px the session counts get their own line
  instead of wrapping into three.
**Verified:** pytest 37 passed (backend unchanged by this sweep);
`node --check`; `/tmp/u1/G4/check/crewcheck.py` (headless Chrome, scratch
8941, real read-only ~/.claude data, launch faked in the page so nothing
started): visible 10 s 5 fetches (2 s poll); hidden 10 s (hub signal and
document hidden) 0 fetch, 0 rAF, 0 timers; shown again: 1 fetch at once;
server killed: 2 fetches in 0-10 s, 2 in 10-30 s; restarted: recovered by
itself in 28.5 s (inside the 30 s back-off cap); triple click on Open
terminal: 1 post; 10-step slider drag: 1 fetch; rapid room clicks: last room
shown; no page errors. Screenshots before/after at 760/1100/1500/1920 looked
at (`/tmp/u1/G4/shots/crew-*`). Bad-input curl sweep of the API (traversal,
5000-char ids, NUL, wrong types, 2 MB prompt with a missing folder,
cross-origin post): all 4xx, no tracebacks; no change needed.
**Not verified:** inside Emerson's Forge window (WebKitGTK); arrives on the
next reload of the app. A real launch (terminal or task) was not fired.

Updated 2026-09-16, end of the part 2 build (`~/Forge/apps/crewroom/docs/PLAN-crew-room-2.md`).
Read `MANIFEST.md` first, `README.md` for formats.
- Critic follow-up (u1-G4-critic.md): the counts get their own line up to
  1240 px wide (was 900, so at 1100 they wrapped in three; screenshot
  checked). Boot fetches (`/api/rooms`, a room, and the shared
  `forge_art.js` library load) give up after 15-20 s, so a backend that
  never answers ends in the boot retry instead of "Setting up the room…"
  forever (reasoned, not reproduced).

## 2026-10-07: sessions show their human names (Haru, ejb-26)

Emerson wanted the names in the room to match the Claude app's tabs, the
Board and Relay ("Hotaru", not "ejb-a9").

- New shared `~/Forge/shared/forge_session_names.py`: `labels(crew_home,
  apps_dir)` gives session id -> name, the Claude app's tab name first
  (its `/api/sessions`, cached 10 s), else the crew board's `persona` for
  that session (newest `last_seen` across every board). Relay's sessions
  (`relay-59-work`) get their board name (Mika) this way.
- `sources/sessions.py` adds `label` to each session; `Context` gains
  `forge_apps_dir` (env `CREWROOM_FORGE_APPS_DIR`, "" in tests = no app call).
- `static/app.js`: `nameOf()` shows the label on name tags, the board list,
  crew task owners and the details title; the hover title keeps `(ejb-a9)`
  and the Where section still lists the raw name. Claims stay keyed by the raw
  name.
- **Verified:** `pytest` 37 passed (2 new tests: board name, and the Claude
  app's name winning over it; no name gives ""). black and pyright (0 errors)
  on the touched Python files, `node --check static/app.js`. A scratch server
  on port 18555 returned ejb-00 -> Sora, relay-59-work -> Mika, ejb-a9 ->
  Hotaru, relay-60-work -> Momo, relay-61-work -> Rin, ejb-26 -> Haru, and a
  headless screenshot showed those names on the tags.
- **Not done:** the Board still has its own copy of the same rule
  (`board/web_app.py` `live_sessions`), and Relay's own page does not show
  these names yet. Old idle chats already sit on the couch and are not counted
  busy (5-minute rule); nothing changed there.

## What exists

- Backend with four discovered sources (sessions, helpers, crews, jan),
  `/api/room`, `/api/rooms`, `/api/rooms/{id}`, `/api/art/library`.
- **Part 2:** starting sessions and reading them.
  - `launch.py`, the only writer. It opens a terminal session
    (`gnome-terminal --working-directory=<folder> -- claude`) or starts a
    headless background task (`claude -p`, always auto mode, prompt on stdin,
    fixed `--session-id`, files in `~/.local/share/forge/crewroom/tasks/<id>/`).
    It also gives the form its folder list (recent session folders, then the
    Forge apps) and a list of recent tasks with their status, result, cost and
    last stderr line.
  - `conversation.py`: the backwards pager (about 256 KB a page, whole lines
    only, a line still being written is skipped, a line over 8 MB is only a
    size). It turns entries into prompts, replies, tool calls in plain words
    with a detail line, and results collapsed with their size. Results over
    16 KB, images and huge lines appear only as a size.
  - `where.py`: folder, `/proc/<pid>/fd/0` terminal device, terminal program
    found through the parent processes, name, start time, process, task
    prompt, and for ended sessions a `cd <folder> && claude --resume <id>`
    command.
  - `sources/sessions.py` marks `entrypoint: "sdk-cli"` sessions as
    `background`, and treats one with no status as busy.
  - Frontend: a **New session** button and panel (folder picker plus a typed
    path, "Open in a terminal", a background task box with a model menu, a
    line about Claude usage, and a live task list). The details panel gains
    **Where**, **Read the conversation** (the panel widens, "Load earlier",
    "Show newest") and a copyable resume command. The panel stays open when a
    session ends. Background sessions get a "background" chip on their name
    tag.
- Art, rooms, renderer and settings from part 1, unchanged: 184 sprites, four
  rooms, walking, idle chat, helpers, Jan spirits, name tags, bubbles, board,
  simple and advanced settings, full screen.

## Verified

- `pytest`: **34 passed** (18 from part 1, 16 new). The new tests cover:
  - the backwards pager across every chunk size from 8 to 400 bytes, a line
    starting exactly at the boundary, a line still being written, and a huge
    line;
  - conversation items;
  - the terminal command and the background command (auto mode, stdin,
    session id, output files), with Popen replaced so nothing is spawned;
  - refused bad folders, prompts and models;
  - task status from a fake /proc;
  - a post with a foreign `Origin` getting 403, and a `text/plain` post being
    refused;
  - "where" from a fake /proc: tty, GNOME Terminal, a shells-only chain,
    ended-session resume quoting, and a background task;
  - background sessions counted as busy, and API 404 and 400 answers.
- `pyright --pythonpath ./.venv/bin/python` on every touched Python file: 0
  errors. `black` on those files. `node --check static/app.js`.
- **Real background task** through `POST /api/launch/task` on a scratch server:
  Haiku, "Reply with the single word ok.". It appeared in `/api/room` as busy
  and background, with where = "Crew Room background task" and no tty. It
  finished `done` with result "ok" for $0.018. Afterwards "where" gave the
  resume command and the conversation showed the prompt and the reply.
- **Real terminal session** through `POST /api/launch/terminal`: a GNOME
  Terminal window opened with claude inside (`fd/0 -> /dev/pts/4`, parent
  `gnome-terminal-server`). It was then stopped by its PID.
- "Where" for a live terminal session from the real /proc: `/dev/pts/1` in
  GNOME Terminal.
- Conversation of a real 1.7 MB transcript: the newest 245 KB in one request,
  about 11 ms.
- Headless Chrome screenshots, looked at: the New session panel with the
  finished task listed; an ended background task's panel (Where, resume
  command, conversation); a live session's conversation scrolled to the
  newest entries. Two real Jan models (Qwen3.5 4B and 2B) were loaded at the
  time and drew as spirits with CPU percentages.

## Not verified

- **The permission mode is disputed.** In this session Emerson answered
  "Always auto mode". A second session building the same plan at the same
  time (ejb-34) says he told it "Always bypass". The code uses auto
  (`launch.MODE`). Ask him which one he wants; it is one constant to change.
- **Whether auto mode really applies under `claude -p`.** The stream-json
  init event reported `permissionMode: "default"` although the command had
  `--permission-mode auto`. The test prompt needed no tools, so it did not
  show which mode was in force.
- In a brand-new folder, the terminal session wrote **no session file within
  30 s**. The likely reason is the folder-trust question waiting for an
  answer, but the window itself was not looked at. The character should walk
  in once that question is answered.
- Clicking through the forms in a browser. The posts were sent with curl
  using the same Origin a browser sends. "Load earlier", the Copy button in
  WebKitGTK, and the panel switching from live to ended were not clicked.
- The "background" name-tag chip on screen (the test task finished before a
  screenshot).
- Inside the Forge window itself (Forge needs a restart to pick up the app).
- Part 1 leftovers: a real crew helper walking in, full-screen toggling,
  sprites opened in Pixel Forge, animation.

## Improve next, most useful first

1. **Settle the permission mode with Emerson** (see above), then run one
   background task that has to edit a file, to see which mode actually
   applies.
2. **Say "answer the trust question in the new terminal"** in the launch
   message when the folder has no transcripts yet, so a missing character is
   not a surprise.
3. **Keep open result toggles** and the "result of …" label when "Load
   earlier" re-renders. Today every toggle closes, and results whose tool call
   is on an older page lose their label.
4. **Helpers crowd their commander's desk.** Three or more helpers plus
   bubbles overlap; spread them along a row or a bench.
5. **Token averages are thin.** A per-session running average kept in memory
   between polls would be steadier than the 64 KB tail.
6. **Art polish, more than six busy sessions, palettes per time of day**, as
   before.

## 2026-09-30: 5-minute rule

A session counts as busy only if its session file (startedAt/updatedAt) or
its transcript changed in the last 5 minutes (`sources/sessions.py`,
`ACTIVE_SECONDS`), the same rule as the Board. Verified: pytest 35 pass
(new `test_a_busy_session_quiet_for_five_minutes_is_not_busy`). Needs a Forge
restart to show live.
