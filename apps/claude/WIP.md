# Claude: work in progress

## Shiori, Claude's own persona (2026-10-09, Umi, Relay task 123)

QUICKSTART 2026-10-02 item 8: Emerson said yes to Claude designing a persona
of its own, as one more mood beside the six. `personas/shiori.json` (avatar
Izumi, Kokoro voice bf_alice) owns the new `check` mood; `personas.py` picks
it for "are you sure", "is that true", "double check", "look it up",
"you sure", "is that accurate", "confirm this", "give me sources",
"research", "how do you know" (after fix/status/build/downtime, before plan).
Critic fix: "source code", "sources/helpers.py", "source of truth", "open
source" and "researcher" no longer count (tests 33 pass). Avatar Studio greets with her own hello line. Verified:
`tests/test_personas.py` 23 pass (5 new, red first, incl. a for_message case
that gets Shiori and the roster prompt naming her), full app suite 211 pass,
headless shot of avatars.html on the running app shows the Izumi card tagged
Shiori. The running server reads the registry per call, but `pick_mood`
only picks the `check` mood after the app restarts. Write-up in
~/.claude/self/PERSONALITY.md and the Tetsu output style.

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
The Claude app's running server was not restarted (it hosts live chats);
everyone.py's change takes effect at its next restart.

## 2026-10-08 voice: ask Claude by voice, dictation, spoken replies (Relay task 113, crew voice helper-5, Mio)

- **`POST /api/voice/ask {text, source}` -> `{id}`** and **`GET /api/voice/reply?id=&wait=`**
  (long-poll, wait capped at 30 s) -> `{done, text, error, conversation}`. Both need
  `X-Forge: 1`. `voice_ask.py` (`VoiceDesk`): the turn runs in one visible
  conversation titled "Voice", made on first use (default account, `dontAsk` = read
  and browse, normal mode) and reused; its id is kept in
  `<data>/voice_conversation.json`, and a deleted one is made again. One voice turn
  at a time; a turn typed in the panel ends first. The reply is the result's
  `result` text, else the last assistant text; an error result or a dead process
  gives `error`. 10-minute cap per turn.
- **Avatar speech (`POST /api/voice`)** tries the Forge voice service first
  (`voice.service_tts`: `POST http://127.0.0.1:8467/api/tts {text, app: "claude",
  voice, speed}`, `FORGE_VOICE_URL` overrides) and falls back to the Kokoro worker
  when the service is down or fails.
- **Page:** `shared/forge_voice.js` (new, every app can use it) gives the composer a
  mic button (press to record, press again to stop, words go in at the cursor) and a
  speak-replies toggle (`localStorage forge.voice.speak.claude`). When on, each
  finished reply of the shown conversation is spoken through the service; skipped
  when the avatar's own speaker is on (`Stage.speaks()`), so it never talks twice.
- `forge_app.json` has `"voice": {"listens": true, "speaks": true}`.

**Verified:** pytest 207 passed (whole suite, after black; the 15 voice tests use
the fake Claude binary, no real turn: header guard, 400/404, reply in one reused Voice conversation
with mode dontAsk, deleted conversation made again, wait cap, a sweep over reply
shapes, service-first then Kokoro fallback). `node --test shared/forge_voice.test.js`
7 passed (mic state sweep, text insertion cases, the mic, speak and toggle with a
fake browser). pyright 0 errors on the touched Python. Live: the running voice
service (8467) answered a CORS preflight from origin 127.0.0.1:8445 allowing
X-Forge, and `voice.service_tts` got a 73 KB wav from it (10.5 s, first load).
**Not verified:** no screenshot (relay-110 had not posted done on its headless
Chrome hold); the mic and toggle were not seen in a real page, MediaRecorder in
WebKitGTK and its mic permission were not tried, and the reply-speaking hook in
app.js (`voiceReply`) has no test. The live app on 8445 was not restarted, so the
new routes are not live until it is.

## 2026-10-08 final-critic fixes: header wraps, side pane, sidebar (Relay task 63, Nene)

From `sessions/2026-10-07-overhaul/critics/final-critic.md` (items 1, 3, 4; item 5 is the hub):
- **Header settings wrap instead of scrolling sideways.** The one-row
  `.head-controls` hid Normal/Ultracode, Limits and Can below about 1900 px
  (a scroll with no scrollbar). Now `flex-wrap: wrap`; the `.more` fade and its
  scroll JS in app.js are gone.
- **Avatar pane starts shut below 900 px** when nobody chose yet
  (`stage.js`: no saved `claude.stage.open` -> open only if `innerWidth >= 900`,
  and that start does not save a choice). At 760 the message box went from
  about 150 px to 322 px wide.
- **Enjoy task title** ends in an ellipsis when it is cut.
- **Sidebar at App 1.5 + Text 1.5** (`check_sizes_ui.py` was failing there at
  HEAD too): the `.new-row` buttons' column minimum grows with Text size, and
  `.list` scrolls when the buttons, list and accounts cannot all fit.

**Verified:** pytest 194 passed; `check_sizes_ui.py` all passed (18/18; HEAD
failed 1, checked on a `git archive` copy); `check_run_controls_ui.py` and
`check_enjoy_ui.py` all passed; headless Chrome at 760/1100/1500: no header
control outside the window, settings row scroll 0, pane 38 px at 760. Not seen
in the real Forge WebKit window. Not done: the critic's shorter placeholder
under 900 px (the box is wide enough now).

## 2026-10-07 honest cost line (Relay task 69, Sakura)
- The old summed figure ("earlier" in `meta.session_costs`) is kept but no longer counted. On load, `Conversation._recount_cost()` rebuilds each session's total from the conversation's own log: the largest `total_cost_usd` per `session_id`. Kaito's chat goes from $2277.47 to $75.64.
- The label is now "This conversation at API list prices: $X (not billed: your plan covers it)"; Enjoy shows a "worth" row.
- A slash-command pick goes in through `execCommand("insertText")`, so Ctrl+Z can undo it. Ctrl+Z itself is handled by the shared `shared/forge_undo.js`, loaded by forge_chrome.js.
- Verified: new tests in tests/test_lost_messages.py, the full suite (194 passed), and a scratch server in headless Chrome showing the line. Handoff: ~/Forge/sessions/2026-10-07-cost-and-undo.md. Goes live after the Claude app restarts.

## 2026-10-07 critic fixes, slash commands, self-run commands (Rei, helper-2 continued)
Work list: ~/Forge/sessions/2026-10-07-overhaul/critics/claude-behaviour-breaker.md (B1-B13) and claude-look-feel.md (L1-L15), plus two asks from the commander. **Everything here needs the Claude app restarted in Forge to go live** (8445 still runs the old code; never restart it from a session inside it). Backups: ~/Forge/backups/2026-10-07-overhaul/claude-2/.

Verified by tests (`.venv/bin/python -m pytest -q tests`: 192 passed, three runs in a row; new: tests/test_lost_messages.py, tests/test_panel_commands.py, tests/markdown.test.js run from test_enjoy_js.py):
- B2 (likely the "message gets lost" report): seq numbers restart with the backend, so a page polling `after=109` waited forever. /events now returns `boot` and `reset`; reset (every event from 0) when the page's boot id differs or its seq is past the end. app.js (catchUp/follow/resetView) and enjoy.js (followTask) redraw on reset.
- B1/B13: stop(), close() and send() share one lock, so a message never lands in a process being ended; a forge_stopped process counts as not running.
- B3: send() writes first and records after; a broken pipe stops the dead process, starts a fresh one and writes once more; a failed send records nothing and leaves no `working` mark.
- B5: a mid-turn settings change is no longer forgotten when a message is sent in the same turn (send does not clear the close-after-turn flag; the settle timer checks it too, via `_after_turn`).
- B4: a long poll that wakes on a new event gathers for 90 ms more (`runner.BATCH_SECONDS`): 30 events over 0.3 s arrive in <= 8 polls (was 30).
- B7-B9: /settings refuses wrong types with 400 before changing anything; limits ignore nan/inf/1e999; `archived` and `ultracode` must be real booleans; /send needs text as a string and files as a list of strings.
- B12: `Conversation.snapshot()` copies meta in one C-encoder step; saves and /events use it (hammer test with two savers and a mutating thread).
- L2: `claude --version` runs on a thread at start and is cached 10 min (`web_app.ClaudeVersion`); /api/options answers at once; the classic page loads the list in parallel with the options.
- L12: a crash sets `last_turn.ok = false, crashed: true` (so Enjoy's needs-you lists it) and draws as a card (`.crash-card`).
- L5: Markdown tables render (claude_common.js; node test).
- Commander ask 1: a message starting with "/" goes untagged with no persona event, so /compact etc run as commands. Live check, real Claude Code 2.1.289 on a scratch server (haiku): /compact gave status "compacting", a `compact_boundary` event (pre 28428 -> post 4405 tokens) and a result; the page draws a "conversation compacted (from 28k tokens)" divider; the summary and `<local-command-stdout>` user events are not drawn; /context answers as an assistant message whose tables now render (screenshot looked at).
- Commander ask 2: `panel_commands.py` (registry: compact, context, usage, recap, rename) and the `panel_command` MCP tool in browser_mcp.py, offered when `FORGE_PANEL_QUEUE` is set; each conversation gets its own MCP config (data/mcp/<id>.json) naming its queue (data/commands/<id>.jsonl). At turn end `_after_turn` sends the oldest queued command as the next message and records `forge_asked` ("Claude asked to run /context"). SYSTEM_NOTE has one line about it. Live check with the real CLI (haiku): Claude found the tool through tool search, queued /context, ended its turn, and the panel ran /context next.
- Found on the live check: `total_cost_usd` is the session's running total (the /context result repeated the /compact result's figure; a resumed process carried on from it), but the runner summed it per turn. Now `meta.session_costs` keeps the newest total per session and `cost_usd` is their sum; older conversations keep their summed (too high) figure as "earlier".

Verified by headless screenshots (scratch server, real conversation; both layouts at 760/1100/1500 looked at): L3 thin scrollbars (Chrome/WebKit via ::-webkit-scrollbar; standard properties only where that is unsupported, because Chrome ignores the webkit rules once scrollbar-color is set); L4 tab row has no vertical bar and + is sticky; L7 classic header is now title row + one settings row that scrolls sideways (`.head-controls`, fades at the edge), 300 -> 118 px at 760, 178 -> 84 px at 1100; the Limits panel is pinned position:fixed while open there so the row cannot clip it (screenshot at 760, row scrolled); L10 web logins start folded (opened once, they stay open: localStorage forge.claude.webLoginsOpen), chat list min 30%, list buttons in a grid; L11 the avatar pane is clamp(200px,18vw,260px) while the avatar is off (:has(.stage-off)); L1 Enjoy rail turns into a top strip under 900 px; L8 non-task Enjoy views have 92 px bottom room for the Close app / Full screen pills (the task view keeps its fit-the-window height); L13 no second full stop after a name ending in punctuation, 2-line clamp; L14 knobs min 128 px; L15 an unset limit slider shows no thumb until hover.

By code only, not measured (Emerson's 2026-10-07 power rule: best practice now, numbers in one test later): B10/L6 refreshTabs runs through ForgeIdle.poll (shared/forge_idle.js now loaded by both pages, which also pauses CSS animations while hidden); B11 pulsing dots get will-change: opacity and stop under body.no-anim and reduced motion. The open conversation's long poll still runs while hidden on purpose: the avatar's voice reads replies aloud. B6 double send: a sending flag, Send disabled until the POST returns, input cleared first and put back on failure (both layouts). L9 the Enjoy limits panel closes on any route change.

Second breaker pass (critic subagent, fake CLI, scratch server; repro scripts in /tmp/critic2/), all fixed with tests:
- A message could be dropped: after a turn with a mid-turn message, 1 s of quiet cleared busy and then ran the pending restart, ending a turn that had not spoken yet. The quiet timer no longer closes or sends queued commands; they wait for the next real end of a turn. Trade-off: when a mid-turn message was folded into the turn, a mid-turn setting applies one message later (never a lost message). Busy can still read false while a new turn is silent for over 1 s (old behaviour; the real CLI sends status events at once).
- A lone UTF-16 half (emoji cut in two) in a message, title or Claude's output gave 500 on /events and the list for good: responses now go out ASCII-escaped (`web_app.SafeJSON`), and message text, titles and names pass `runner.clean_text`.
- The command queue lost or doubled commands under concurrent append/take: `panel_commands` now takes an flock for both; any bad line (even one that raises RecursionError) is dropped, and `_after_turn` reaches the pending close in a `finally`.
- A reply could be numbered before its user bubble (instant /context, /compact): the reader waits (at most 2 s) while a send is between its write and its record.
- " /compact" with spaces is sent stripped; a crash no longer leaves a close mark that ends the next process after its first turn (`_start` clears it).
- Polls at app.js loadAccounts/loadEveryone and enjoy.js roadmap/listing use `ForgeIdle.shown()` (pause inside the hub when another app is in front); a failed Claude Code start on /send is 503, not 500; the classic title ellipsises.
- Left as is: the classic settings row scrolls sideways by design (fades at its edge); Enjoy's loose-task link sits under Forge's pills only before scrolling to the end (92 px room there).

Not done / open: not checked in the real WebKitGTK window. Not verified in the real WebKitGTK window (scrollbars, :has, mask-image are supported there since WebKitGTK 2.40, not checked on screen).

## 2026-10-07 handoff state (Rei, helper-2; task 2 left open for the next helper)
- Done and verified: Live2D off at load (classic), Normal / Ultracode switch, agent limits registry and fold in both layouts, the usage "98 hours ago" flip-flop (sections below). `.venv/bin/python -m pytest -q tests`: 156 passed. `tests/check_run_controls_ui.py`: 18/18 ok; screenshots looked at (classic, Enjoy, 760 px narrow). black run on touched Python; pyright 0 errors on runner.py, web_app.py and the touched tests.
- Live ultracode check (real Claude Code 2.1.289, opus, scratch server on a free port): `ultracode_state: {'active': True, 'available': True, 'model': 'claude-opus-5-5'}`, limits `{'max_helpers': 2}` stored. Before that, raw `claude -p --settings '{"ultracode":true}'` with the get_settings control request gave `"ultracode":false,"ultracodeRequested":true,"ultracodeAvailable":false` until enableWorkflows was added.
- Not done: Part B fixes. Critic reports are in ~/Forge/sessions/2026-10-07-overhaul/critics/ (claude-behaviour-breaker.md, claude-look-feel.md). Nothing from them is fixed yet.
- Not verified: ultracode on a real multi-step task (cost, speed); the live panel on 8445 runs the old code until Forge is restarted (never restart it from a session inside it).
- Backups of every edited file: ~/Forge/backups/2026-10-07-overhaul/claude/.

## 2026-10-07 usage bar went back to "98 hours ago" (Rei, helper-2)
Emerson: "the usage bar keeps showing the actual usage and then changing back to 98 hours ago". Cause: the main account's usage endpoint answers 429, so usage.py's fetch() returns its cached reading with `_age` about 96 h; `poll_usage` merged it over the fresher numbers a conversation's rate_limit_event had stored, every 120 s. Fix: `runner.merge_usage()` keeps whichever reading is newer, per window (windows now carry their own `seen`), and only moves `seen`/`source` when the live one is newer; otherwise it records a check note ("usage server is rate-limiting; showing the newer numbers from this panel"). Tests: `test_an_older_live_reading_never_replaces_newer_stream_numbers`, `test_each_window_keeps_its_newest_reading` (12/12 in test_usage_poll.py). Live panel needs a Forge restart to pick it up.

## 2026-10-07 overhaul: avatar off at load, Normal / Ultracode, agent limits (Rei, helper-2 of crew overhaul)
Emerson: "i dont want the live 2d to happen automatically in the normal forge claude app"; "make an ultracode and normal toggle and like limits on agents and effort levels".
- Avatar: `static/stage.js` no longer reads the saved `prefs.avatar`; `S.sitting` (false at every load) decides. 🎭 / "Turn on the avatar" turns it on until a reload and saves nothing. Avatar Studio untouched. Verified in headless Chrome with prefs saying avatar: true (no pixi, no canvas at load; 🎭 on/off; off again after reload; saved prefs unchanged).
- Ultracode: `meta["ultracode"]` adds `--settings {"ultracode":true,"enableWorkflows":true}` (runner.command). Found live with Claude Code 2.1.289 through the `get_settings` control request: `{"ultracode":true}` alone gives `ultracode:false, ultracodeAvailable:false` (dynamic workflows off on this machine); with enableWorkflows (or env CLAUDE_CODE_WORKFLOWS=1) it is `true/true` on opus, fable, sonnet, claude-sonnet-5-5 and the default; haiku stays unavailable (`ULTRACODE_UNSUPPORTED`). At start the runner sends that probe and keeps the answer in `meta["ultracode_state"]` {active, available, model}; the page warns when it did not take effect. Verified with the real CLI through a scratch server: `{'active': True, 'available': True, 'model': 'claude-opus-5-5'}`. Not verified: how ultracode changes real work (cost, speed) on a non-trivial task.
- Agent limits: one registry `runner.AGENT_LIMITS` (key -> env, kind int|choice, min/max or choices, default, label, help), `clean_limits()` and `apply_limits()` (unset = env var removed, so an inherited value never leaks). Served in `/api/options` as `agent_limits`; `POST .../settings {"limits": {key: value|""}}` merges per key. The page control is `static/run_controls.js` + `.css`, shared by both layouts (classic header after Effort, Enjoy task knobs); new tabs/tasks carry ultracode and limits over like model and effort.
- Tests: 5 new in `tests/test_claude_panel.py` (flag, registry completeness, a value sweep across every limit kind, env building, API end to end with the fake's control_response); `tests/fake_claude.py` answers control requests and logs the limit env vars. UI: `../files/.venv/bin/python tests/check_run_controls_ui.py [shots dir]`, 18/18 ok.

## 2026-10-01 effort/model change mid-turn (Mei, ejb-c6)
A settings change while a turn ran used to keep the old process, so the next message ignored it. `change_settings` now calls `conv.close()` (ends it after the turn). Test: `test_a_setting_changed_mid_turn_applies_to_the_next_message`; 149 tests pass. Needs a Forge restart to take effect.

## Account box drags to size; Web logins fold (2026-10-01, Aiko / ejb-7b)
- Done and verified: a drag bar above the sidebar's account box
  (`#split-accounts`, `data-side="top"` in `splitters()` drags height, saved as
  `forge.claude.height.accounts`, double-click resets, folding still shrinks it
  to the header). "Web logins" is now a fold button of its own (remembered in
  `forge.claude.webLoginsFolded`).
- Check: `../files/.venv/bin/python tests/check_accounts_drag_ui.py [shot.png]`
  (real mouse drags in headless Chrome) gave 10/10 ok; screenshot looked at.
  pytest 148 passed. Classic layout only; Enjoy has no account box.

## Docs section (2026-09-29)
- Done and verified: `docs_library.py` + `doc_sources.json` + `static/docs.*`,
  routes `/api/docs` and `/api/docs/read`, links from both layouts.
  `tests/test_docs_library.py` passes (dates, folders, order, search, refusal
  of unlisted paths); screenshot checked on a test server.
- Live on port 8445 since the app's restart (checked 2026-09-30: `/api/docs` answers).
- Hard-wrapped docs read as flowing paragraphs: `static/docs_text.js` unwrap()
  joins continuation lines before the shared markdown renderer
  (`tests/docs_text.test.js`, run by `tests/test_docs_js.py`).
- Improve next: 202 of about 258 docs have no date in name or header and
  show their last-change date in italics; adding `date:` lines would fix
  that (never done automatically, files are left as they are).

## #185 Claude page speed: paused (2026-09-27, Umi / ejb-3f)
Stopped by Emerson mid-measurement; nothing about the page itself changed.
- Uncommitted: `tests/fake_claude.py` gained a "pace N" message (N words
  streamed at 40 a second) and `tests/bench_stream_ui.py` measures the page
  in headless Chrome. Baseline with the 100 ms batching: 9.0% of a core while
  streaming (script 0.3, layout 1.3, style 0.7, the rest paint), 0.1% busy
  but silent.
- Next step (not started): measure in a real on-screen WebKitGTK window,
  since the 87% came from Forge's WebKit, then fix what that shows.

## Closed tabs end their process; sidebar overlap (2026-09-27, Umi / ejb-3f)
Emerson: closed Claude tabs still showed up as live sessions to the other
sessions, and the Archived folder drew over the other conversations.
- Cause 1: `closeTab()` in `static/app.js` only dropped the tab on screen,
  so its `claude -p` process kept running (ListAgents and the Board saw it).
  Now it posts `/api/conversations/{id}/close` (`web_app.py`), which calls
  `Conversation.close()` in `runner.py`: an idle process ends at once
  (quietly, and `working` is dropped so a restart does not carry it on); a
  busy one sets `_close_after_turn` and ends when its turn's result lands.
  Sending a message clears the flag, and the next message resumes the
  session as before. Tests: `test_closing_an_idle_tab_...`,
  `test_closing_a_busy_tab_...`, `test_the_close_endpoint` (133 pass).
- The 4 orphan processes already running were stopped through the live
  server's `/stop` endpoint; 3 remain (the open tabs).
- Cause 2: `.folder-body.loose { min-height: 24px }` let the loose list
  shrink as a flex item to 24 px while its rows spilled under Archived.
  `.chats > * { flex-shrink: 0; }` in `static/app.css` keeps every group at
  full height and the list scrolls. Verified in headless Chrome with 26
  rows per group: loose 186-1142 px, Archived starts at 1144 px.
- Verified in tests and headless Chrome only; the live panel needs a Forge
  restart (Ctrl+Shift+R) to pick up the new server code and CSS.


## Auto-archive of quiet conversations (2026-09-27, Sakura / ejb-55)
Emerson: "auto archive/hide conversations that aren't in a folder ... if the
conversation is 2 hours old". Read as: quiet for 2 hours (no message sent,
no turn finished), so a long-running chat he is still using never vanishes.
- `runner.py` `Registry._archive_quiet()` runs inside `list()`: a
  conversation with no folder, not busy, whose newest of updated / created /
  restored is at least `archive_hours()` old gets `meta["archived"]` (a
  time stamp), written to its file and to its open copy (`_store`, now also
  used by the name back-fill). `set_archived()` archives by hand or brings
  one back (`restored` then gives it a fresh 2-hour window). Sending a
  message clears it; filing it into a folder clears it too.
- The hours are a Forge setting, `claude_archive_hours` in
  `shared/forge_theme.py` (group Apps, default 2, 0 = never, max 168);
  `web_app.py` reads it on every listing. API: `POST
  /api/conversations/{id}/settings {"archived": true|false}`.
- Page (`static/app.js`): an "Archived (n)" group under the loose list,
  shut by default, click to open; each row has a ↩ button. An archived
  conversation's tab closes unless it is on screen or holds a draft (in
  `loadChats` and in `restoreTabs` at start). The Enjoy layout's loose tasks
  leave archived ones out (`projects.listing`).
- Verified: `tests/test_archive.py` 6 pass, whole app 123 pass,
  `tests/check_archive_ui.py` 6/6 in headless Chrome (screenshot looked at),
  `check_names_ui.py` still passes (its seeded chat is now archived but on
  screen). Not verified live: needs the Claude app restarted inside Forge.
- Fixed after (same day): `check_enjoy_ui.py` "a new task starts with the
  last picks" failed on and off. Cause: the Enjoy task's three pickers post
  at once, FastAPI runs them on parallel threads, and `save_meta` shared one
  temp file, so a save hit FileNotFoundError, that request failed, and the
  page never stored its pick as the default. `save_meta` now holds a
  per-conversation lock. `tests/test_save_race.py` (6 threads x 60 saves)
  had 151 errors before, 0 after; app 124 pass; check_enjoy_ui all passed
  twice.
- Improve next: an "Archive" button on loose rows (the API has it), and
  showing the hours in the Archived header.

## Human names on tabs (2026-09-27, ejb-34)

Emerson: the tabs should carry human names, not "New conversation". Every
conversation now has a `name` from `names.py` (the list of 50 names is the
whole registry). A new one gets the name its id points at, skipping names
already in use. Older conversations are named once, oldest first, the first
time the list is read, and the name is saved. Tabs and list rows show the name
in bold with the topic in grey. Double-click a tab or row to rename it
(POST /api/conversations/<id>/settings {"name"}; a blank name is ignored).

Verified: tests/test_names.py 6 passed, suite 115 passed, pyright 0 errors;
tests/check_names_ui.py (headless Chrome) shows the API's names on all three
tabs and list rows, screenshot looked at. Not verified: the double-click
rename in a real browser (the API behind it is tested); Enjoy layout still
shows titles only.

Board jump (#227): the Board's "Go to it" now reaches sessions that run in this
app, not only terminal ones. `POST /api/sessions/<session id>/focus?pid=` marks
the conversation (matched by stored session_id, or the live claude pid); the
next `GET /api/conversations` carries `focus` once (a minute at most) and the
page opens that tab, also right away when the page becomes visible.
`GET /api/sessions` gives session id -> name/title, which the Board shows.
Verified: tests/test_names.py 8 passed; check_names_ui.py sends the Board's
exact request to a sandbox app and the open page switched to that tab by
itself. Needs a Forge restart to load (restarting the app ends the sessions
running in it, so do it when none are working).

## S14 (ejb-d3) 2026-09-27: layout at other App and Text sizes (B14)

CSS only (`static/app.css`, `static/enjoy.css`); shows the next time the page
opens. Causes found and fixed:
- **Enjoy rail footer jumped into a second column** on short windows: shared
  `forge.css` gives every `<nav>` `flex-wrap: wrap`, and the rail is a `<nav>`.
  Now `nowrap`, the rail scrolls, and its project list keeps at least 5em.
- **Fixed-width sidebars** (classic 250px, Enjoy 236px) with text that grows:
  both now `clamp()` to `base * var(--forge-text)`, the classic one also capped
  at 28vw. The avatar stage is `clamp(240px, 26vw, 340px)` and its top bar
  wraps. The "+ New conversation / + folder / enjoy" row wraps.
- **Account picker** in the Enjoy rail spilled out: now full width, may shrink.
- **Task view scrolled by 22px**: `#v-task` was `100vh` inside `main`'s 22px
  padding; now `calc(100vh - 44px)`. Plan panel `clamp(220px, 30%, 320px)`.
- **Web logins list** had no scroll and pushed the classic page 189px past
  the window at Text 1.5; capped at half the sidebar with its own scroll.

**Verified:** new `tests/check_sizes_ui.py` (headless Chrome via cdp_driver,
scratch data, fake Claude): classic, Enjoy and a task at App 0.8/1/1.5 x
Text 0.8/1.5, no sideways scroll, no spilled box, no page past the window:
18/18, three runs in a row. `check_enjoy_ui.py` all passed; pytest 108 passed;
no headless Chrome left. **Not seen** in the real Forge WebKit window (App
size there is WebKit zoom; the check emulates it with a window / zoom viewport).

## S13 (Suzu) 2026-09-27: Enjoy finished off (B15)

Loads the next time the Claude app page opens; no backend change.

**What exists now** (`static/enjoy.html`, `enjoy.js`, `enjoy.css`)
- **Task pickers:** under a task's title, three pill pickers: model, effort,
  and "may" (the permission level, short words such as "read & browse",
  "edit files"; the backend's full sentence is the tooltip). The choices come
  from `/api/options` (runner.MODELS, EFFORTS, MODES). A change saves at once
  through `/settings`, a note says so, and the pick is remembered
  (`localStorage claude.enjoy.defaults`); new tasks are created with the last
  picks. A race where quick changes to several pickers undid each other was
  found by the check and fixed (value read before the request; redraw only
  after the last reply).
- **Drag to file:** any task row can be dragged onto a project card or a
  project in the rail (files it into that project) or onto the loose tasks
  section (unfiles it). Drop targets show a dashed outline while dragging and
  light up underneath; a toast says where it went.
- **Files:** dropping files on the chat attaches them, next to paste and the
  attach button (paste was already there; chips already showed thumbnails).
- **Motion:** views drift in, rows and cards rise in one after another when a
  view opens (not on the 8-second refresh), toasts slide, pickers pulse when
  saved, rows nudge on hover. All of it is off under `body.no-anim` and
  `prefers-reduced-motion`.
- The "Task tools instead of TodoWrite" worry (old improve-next 1) is not
  real yet: every to-do call in the app's own logs (52) is TodoWrite.

**Verified:** `tests/check_enjoy_ui.py` in real headless Chrome against a
scratch copy (own data folder, fake Claude): 11/11 on four runs after the
race fix (lists, pickers save, note, new task inherits picks, drag onto a
project files it, drag back unfiles it, file drop makes a chip, no page
errors). Run it with `../files/.venv/bin/python tests/check_enjoy_ui.py`
(this venv has no websockets). Suite 108 passed. Screenshots of the task and
projects views looked at.
**Not checked:** inside the real Forge window (WebKitGTK drag and drop of a
task row, and files dragged in from the desktop); the drag tests use
synthetic drag events.

**Improve next** (ranked)
1. A "move to…" menu on each task row for keyboard users and touchpads
   (drag is the only way to file in Enjoy now).
2. Roadmap: a date strip to jump between waves ("all sessions" grows long).
3. Show effort and permission in the task's side panel too, not only in the
   pickers.

## Finisher (S10) 2026-09-26: the Enjoy layout and the roadmap tab (A15, A28)

Brief: `~/Forge/sessions/2026-09-26-S8-claude-enjoy-browser.md` (chunks 2-5
done by Finisher, `2026-09-26-S10-finish-wave.md`). Loads the next time the
Claude app page opens; the new /api/roadmap route needs the app's backend
restarted (Forge does that when it restarts the app).

**What exists now**
- `static/enjoy.html`, `enjoy.css`, `enjoy.js`: the second layout. Views by
  hash: `#projects`, `#project/<id>/<tasks|notes|workflows>`, `#task/<id>`,
  `#now`, `#roadmap[/<brief>|<id>]`. New tasks run on the account picked in
  the rail (remembered, `claude.enjoy.profile`).
- `static/enjoy_logic.js`: page-free logic (plan and progress from
  ExitPlanMode/TodoWrite, running / needs you grouping, the star layout with
  nearest-star lines, "ago"). Node tests: `tests/enjoy_logic.test.js` (9),
  also run by pytest through `tests/test_enjoy_js.py`.
- `static/claude_common.js`: markdown, API helpers, event drawing and image
  helpers moved out of `app.js` so both layouts share one copy; `app.js` passes
  hooks (scroll, command list, Browser opening). The classic page was checked
  after the move with a real split reply (text, tool card, text, cost).
- `roadmap.py` + `GET /api/roadmap` (tests/test_roadmap.py, 17): every dated
  brief in ~/Forge/sessions (slot, name, topic, ledger items with quote,
  meaning, tag; state per item from the ## State lines, including bold,
  comma, sub-item and range forms; handed-on items follow the session they
  went to) plus the open forge board notes, newest first.
- Switch: "enjoy ↗" next to "+ folder" in the classic list; "classic layout ↗"
  at the foot of the Enjoy rail; index.html redirects to enjoy.html when
  `claude.layout` is "enjoy".
- `tests/fake_claude.py`: a message containing PLAN makes the fake send an
  ExitPlanMode plan and a TodoWrite list (one done, one in progress, one to
  do).

**Verified**: full suite 108 passed; pyright clean on roadmap.py, web_app.py,
tests; every view probed in off-screen WebKit against a scratch copy (port
18445, fake Claude): projects (card, badge, loose list), task (3 todos with
the right states, "1 of 3 done", current step, plan, chat, stop hidden when
idle, "needs you" becomes "quiet" once opened), notes, workflows, now,
roadmap (3 constellations, 41 stars, 22 lit, star card with quote, meaning,
state, latest word). Screenshots looked at.

**Not checked**: inside the real Forge window; a real (not fake) Claude
turn with TodoWrite; the Enjoy composer's paste of a real screenshot (would
touch Emerson's clipboard).

**Improve next** (ranked)
1. Newer Claude Code versions may track work with Task* tools instead of
   TodoWrite; planStep reads only TodoWrite and ExitPlanMode. Check a real
   transcript and add the Task tools if they appear.
2. The Enjoy task view has no model/effort/permission pickers yet (the classic
   header has them); new tasks use the defaults. Add a small settings
   popover.
3. Roadmap: the "all sessions ∞" view grows long; a date strip to jump
   between waves would help.
4. Drag a loose task onto a project in the Enjoy layout (today: the classic
   layout's folders).

## Chat (S8) session 2026-09-26: avatar off, images in and out, updates that stay

Brief: `~/Forge/sessions/2026-09-26-S8-claude-enjoy-browser.md`. All of this
loads the next time the Claude app page is opened (the backend changes need the
app's backend restarted, which Forge does when it restarts the app).

- **A29 updates vanished mid-turn (fixed, the worst of the three).** Claude
  Code sends one reply as several `assistant` events with the same id, one per
  block (thinking, text, tool call). The page cleared the reply's box on every
  such event and drew only that event's block, so a text update was wiped the
  moment a tool call followed it, live and when history reloads. In Emerson's
  own newest conversation 95 of 114 replies arrive split. Now each block keeps
  its own slot by its position in the reply (`claudeMessage` / `textSlot` in
  app.js) and nothing is cleared. Scrolling was already fine: the log only
  follows when you are within 160 px of the bottom.
  Checked with `tests/page_probe.py` (off-screen WebKit) on a planted
  conversation shaped like the real file: before, `first: false, second: true`;
  after, both true, the tool card in place. Live: `tests/fake_claude.py` now
  streams a real-shaped split reply when the message contains SPLIT; the
  update and its tool card both stay.
- **A21 avatar off by default.** `prefs.avatar` in personas.json (false unless
  turned on). While off, the stage builds nothing animated (no pixi or Live2D
  request at all, seen in the server log) and a stand-in keeps the voice and
  the avatar chat working. 🎭 in the stage header and a "Turn on the avatar"
  button switch it; the choice is saved with the persona settings. The stage
  header's dropdowns now shrink so its buttons stay on screen.
- **A24 images.** Paste reads `clipboardData.files` and `items`; when WebKitGTK
  hands the page no file and no text (a copied screenshot), the backend reads
  the desktop clipboard itself (`clipboard.py`, wl-paste) and attaches it
  (`POST /api/conversations/{id}/paste-image`). Chips and sent messages show
  image thumbnails (`GET /api/conversations/{id}/files/{name}`: images only,
  only from that conversation's attachment folder, unguarded because an img
  cannot send headers). Images in tool results now show instead of "[image]".
  Every image has a Copy image button (`POST /api/clipboard/image`, wl-copy)
  and WebKit's own right-click Copy Image.
- **Verified:** pytest 76 passed (new: tests/test_clipboard.py 9 with fake
  wl-paste/wl-copy, the avatar pref test); black, pyright 0 errors on touched
  Python; headless screenshots of the off stage, the on stage (libraries
  load; the model itself does not draw headless, no GPU), and a sent image.
- **Not verified:** clicks in the Forge window; a real Ctrl+V of a screenshot
  and the Copy button (both would touch Emerson's live clipboard; the paste
  route was checked read-only against it and correctly found only text).
- **Improve next:** (1) A15 Enjoy-style layout and A28 roadmap tab (next
  session, plan in the brief). (2) Markdown images in replies are still not
  drawn. (3) Composer thumbnails for a pasted image use the served file, so a
  paste into a conversation not yet saved would show a broken thumbnail
  (newChat saves first today, so not seen).

## S1 session 2026-09-25 ("Unfinished jobs list"): usage bars, avatars, browser, MCP

Brief: `~/Forge/sessions/2026-09-25-S1-sessions-board-claude-app.md`.
Everything below goes live the next time the Claude app is opened (it was
closed when this was written, so no restart was needed and no chat was cut).
That includes the earlier "send while Claude works" work (ejb-79 handoff).

- **Usage bars follow the real account** (A37). They only moved when a panel
  conversation streamed a rate-limit event, so terminal sessions on the same
  account never showed. Now `Profiles.poll_usage` asks the account's usage
  endpoint (through `~/.claude/tools/usage.py`'s `fetch`, not a copy) at most
  every 2 minutes per signed-in account, in a thread; the page re-reads
  accounts every minute; the bar's tooltip says when and from where
  ("checked with the account" or "from this panel's last answer"). A failed
  check keeps the last numbers. Tests: `tests/test_usage_poll.py` (3). Seen
  live on a scratch copy: 61% from the account while the panel had no chats.
- **Avatars switch** (A23). Emerson's persona overrides file was empty: the
  Studio's tile chooser only previewed, and the real control was a dropdown on
  each persona card. Now: a **Look** dropdown beside the persona picker on the
  chat stage (every model and puppet; saves and changes the avatar at once);
  **Use for [persona] / Use this avatar** under the Studio preview; the stage
  re-reads personas when the page becomes visible; Studio saves report errors
  instead of failing silently; the Studio draws its tiles before the first
  model loads (a model that fails no longer hides the chooser). Checked with
  headless screenshots (chat stage shows "Kira [Kira] [Haruto]"; Studio shows
  the Use for bar and all tiles). Not clicked in the Forge window.
- **Forge Browser message gone** (A40). The permanent "The Forge Browser is
  not running" notice is removed. When Claude calls a forge-browser tool and
  the Browser is closed, the page asks the hub to open it (only for a call
  still waiting after 400 ms, so replaying history opens nothing), and
  `browser_mcp.call_browser` waits up to 25 s for it before giving up with
  "did not open". Tests: 2 new + the old failure test updated. Not checked in
  the Forge window. Note: opening switches the view to the Browser (the hub's
  `open` message focuses it; a background start would need hub support).
- **Acchan tools in every account** (A39). `mcp_config()` now merges the
  user's `mcpServers` from `~/.claude.json` (acchan) with forge-browser, which
  always wins its own name. Test: `test_every_account_gets_the_users_own_mcp_servers_too`.
- Full suite: 65 passed; black and pyright clean on the touched Python.

### Still open
- (Fixed later the same session) A2 edge: a message landing as a turn ends.
  After a `result`, if a message was sent mid-turn, the panel stays busy for
  1 s; any event in that time (a second turn) keeps it busy until that turn's
  own result, and events of a new turn re-mark it busy. Folded messages clear
  after the 1 s grace. Test: `test_a_message_landing_as_the_turn_ends_keeps_the_panel_busy`
  (fake CLI mode `wait`). Full suite 66 passed.
- Headless screenshots of this app: use `--timeout=9000`, not
  `--virtual-time-budget` (the open event stream means the budget never runs
  out and Chrome hangs), and `--disable-gpu`.


## Queued (2026-09-25, Emerson): usage for every account in Settings
Emerson asked for "the claude app to show usage for both accounts in settings
or something". Not started (the session hit 99% of its 5-hour window).
What exists: account buttons already carry each profile's usage in a tooltip
(static/app.js usageTitle(), the p.usage field) plus a five-hour number.
Build: a Usage section in the app's settings with, per account (default,
second, ...), a bar for the 5-hour and the weekly window, the percentage and
"resets in", refreshed on open and every few minutes. The same numbers come
from ~/.claude/tools/usage.py --all (reads every Forge profile) if the
backend needs a fresh read rather than the last-answer value.

## Handoff 2026-09-25 (ejb-79): send while Claude works, and what's left

**Built, tested, not live.** None of today's panel work (tabs, the / and .
menu, effort, sending mid-turn) is live until the Claude app's backend
restarts. That means closing the Claude app in Forge and opening it again.
It cuts every running panel chat. Their history stays on disk and they
resume by session id. Emerson asked for it to be done without him; it was
not done, because the session was stopped first.

**Sending while Claude works** (asked: "let me inject messages without
having to stop and start the stream").
- The real CLI was checked with Haiku, about $0.02. A second stream-json
  user message written to stdin mid-turn is folded into the running turn,
  and one result answers both ("ONE TWO").
- `/send` no longer refuses with 409 while busy. `Conversation.send`
  writes straight to stdin and marks the `forge_user` event `during_turn`.
  The page keeps Send visible next to Stop, the status says a message sent
  now joins the turn, and such messages show "added while Claude was
  working".
- tests/fake_claude.py: a message starting with "busy" works for a second
  and folds anything that arrives meanwhile into one reply, like the real CLI.
- Verified: `test_a_message_sent_while_claude_works_joins_the_turn`. In
  headless Chrome on a scratch server, pressing Enter twice gave the reply
  "busy three + and four" with the mid-turn note. A final screenshot was
  taken but not looked at before the stop.
- Known edge, not handled: a message that lands just as the turn ends may
  start a second turn. `busy` then clears at the first result while the
  second turn streams. Events still draw; only the Stop button and status
  lag.

**Checks at stop:** 59 tests pass. pyright shows 0 errors on runner.py,
web_app.py, tests/test_claude_panel.py and tests/fake_claude.py. black
was run, and `node --check` passes on app.js. The scratch servers (ports
8498 and 8499, Chrome on 9333 to 9335) are stopped and their /tmp folders
deleted.

**For Emerson to confirm:** the account-lock work (relayed by ejb-a9/ejb-d1
as his ask) removed "move this conversation to another account"
(`Conversation.move_to`). His standing rule is never to lose a feature
without agreement. If he wants it back, the handoff banner planned below is
where it would return.

**Next:** restart the Claude app, then check the live panel: tabs, the menu,
effort, and sending mid-turn. After that comes the handoff banner (see
"Room for the handoff" below).

## Tabs and the / or . command menu (2026-09-25): built, tested, not yet live

Built by ejb-79, alongside ejb-a9/ejb-d1, which made the accounts share one
config (Profiles.link_shared, section at the end).

- **Tabs** (static/app.js, index.html, app.css). The side list is the history,
  the tab bar is the live set. A tab is `{id, profile}`: one conversation,
  locked to the account it was created on. Kept in localStorage
  `forge.claude.tabs` with the current tab and unsent drafts. Clicking an
  account now only sets the default for new tabs (`/activate` takes no
  conversation). `Conversation.move_to`, the `profile` key in `/settings`
  and the `forge_account` event are gone. With projects/ shared between
  accounts, the transcript copy they did is no longer needed.
- **Command menu.** `/` or `.` at the start of the message box lists the
  slash commands and skills from the newest init event
  (`Registry.commands()`, `GET /api/commands`, refreshed live from each init).
  A pick writes `/name `. Checked against the real CLI: `/config`, `/model`,
  `/context`, `/color` and `/clear` all answer under `claude -p` at $0, so
  none are hidden.
- **Asks relayed by ejb-d1, same day.** The menu shows descriptions and
  filters on each keystroke. `runner.scan_commands()` reads ~/.claude/skills
  (plus synced buckets as `anthropic-skills:*`), plugin skills (the
  `skills` list in `.claude-plugin/plugin.json`, else `skills/*/SKILL.md`),
  plugin commands and ~/.claude/commands. It always reads `runner.MAIN_CONFIG`,
  since every profile links there. `Registry.commands()` merges that with the
  init list. On the real config: 46 skills or commands found, all with a
  description, and 96 menu entries in total. The 50 undescribed ones are
  built-ins. **Effort**: `runner.EFFORTS`, `meta["effort"]`
  ("" = CLI default), `--effort` in `command()`, `/settings`, new tabs
  inherit it, and a picker in the header. The model picker was already per
  conversation (so per tab) and applies from the next message.
- **Room for the handoff** (not built). The banner can open a new tab
  `{id, profile: other}` on the same session_id, or a fresh tab.

Verified: 58 tests pass (new: the command scan, commands from init plus disk,
effort in the command line and /settings; the account tests rewritten for
locked conversations). black and pyright
(0 errors) on runner.py, web_app.py and the two test files; `node --check`
on app.js. Headless Chrome drove a scratch server (fake Claude, three seeded
chats): three tabs with account badges, `.co` listed /code-review, /compact,
/context, /config and /mattpocock-skills:tdd, ArrowDown+Enter wrote
`/compact ` without sending, and tabs came back after a reload. Closing the
current tab moved to its neighbour. A second run showed the Effort picker
(High, from meta) and `/gri` or `.gril` listing the grill skills with
their descriptions.
The page also boots against a backend from before this work (it hides the
Effort picker when /api/options has no efforts, and the menu stays empty
while /api/commands is missing). Checked in headless Chrome against the live
old backend on 8445: no exceptions, one tab, the chat drawn, the picker hidden.
Not verified: the live panel. It needs the Claude app closed and reopened,
which Emerson does himself because it cuts running chats.

## Folders and web logins (2026-09-25): built, tested

Conversations can live in folders (`+ folder`, drag onto a folder, 📁 button,
rename, collapse, delete keeps the chats). Registry.folders / add_folder /
update_folder / delete_folder / file_into in runner.py, /api/folders routes in
web_app.py, test_folders_file_rename_collapse_and_delete. The Accounts panel
also lists the web logins from shared/accounts.json and opens the Logins app.
The chat highlight now matches by id (it used list position, wrong once
folders reorder the list). A second Claude Code account `second` was created
and its sign-in started 2026-09-25, waiting for Emerson's code. Verified:
52 tests, headless Chrome screenshot. Full story: ../../docs/DESKTOP-REACH.md.


## Fix 2026-09-24 22:15: "Claude Code is not installed" inside Forge

Forge started from the desktop launcher had no ~/.local/bin on PATH, so
`shutil.which("claude")` failed. `runner.claude_command()` now falls back to
~/.local/bin/claude and the other standard install locations. A test covers
it, and with `env -i PATH=/usr/bin:/bin` it finds the binary. It takes effect
once the Claude app's backend restarts (Close app, then open it again).

## Avatars round 2 (2026-09-25): built, tested (~/Forge/apps/claude/docs/PLAN-avatars-2.md)

Emerson asked for more Live2D models, more Live2D features, and avatars that
are interactive and chattable. What exists now:

- **19 usable Live2D models** in `~/Forge/shared/avatars/live2d/` (43 MB for
  all avatars, his cap is 200 MB). New: 11 **Cubism 2** models from the npm
  packages `live2d-widget-model-<name>@1.0.5` on jsDelivr: Live2D Inc's
  official samples (Haruto, Shizuku, Koharu, Hijiki, Tororo, Epsilon, Hibiki,
  Izumi, Tsumiki, Chitose) and Unity-chan (Unity-Chan License, credit
  needed). Skipped on purpose: game or anime rips (z16, rem, asuna, umaru,
  gf and so on) and packages with no clear licence (miku, nico, nipsilon,
  ni-j). All of them are hard-linked into Nyarch Assistant's models folder
  (`~/.var/app/moe.nyarchlinux.assistant/config/avatars/live2d/web/models`),
  whose handler lists `.model.json` too.
- **Cubism 2 support**: `forge_avatars.list_models` records `cubism` (2 or
  4) and `hit_areas`; Cubism 2 parameter ids are read from the `PARAM_*`
  names in the `.moc`; `mtn()` writes recipes as `.mtn` (one value per
  frame at 30 fps). `forge_avatar.js` puts them in `settings.motions.Forge`
  and uses `setParamFloat` and the related calls in `push()`.
- **Live2D features**: reactions can name the model's own motions as
  `own:Name` (a motion or a group; Arch-chan now uses her Happy, Wink, Nod,
  Thinking, Sad, Surprised and Shy). A face with the same name as one of the
  model's own expressions uses the real one (Arch-chan's Smirk).
- **Interactive** (stage and Studio): click the head for a shy reaction and
  the body for a surprised one (the model's HitAreas, or the top third
  counts as the head); `reactions.head` and `reactions.body` in a persona
  override that, and models with `tap_body` or `flick_head` groups (Shizuku)
  use them. Drag to move and scroll to zoom; the place is saved in
  localStorage per page and persona. Double-click still plays a reaction.
- **Chattable**: a chat box under the stage (`avatar_chat.py`,
  `POST/GET/DELETE /api/avatars/chat/{persona}`). It uses Jan with this
  app's role `chat` (settable per app) and falls back to the model Jan
  already holds, so it never loads a second model onto the iGPU. The reply
  is 1 to 3 sentences plus a tag (happy, think, shy, sad, surprised, wink)
  that the avatar plays; it is spoken when 🔊 is on. The last 30 exchanges
  per persona are kept in `<data>/avatar_chat/<id>.json`.
- **Kira now wears Haruto** (a boy); Rice is his `alt_avatar`. The Studio
  groups tiles as Cubism 4, then Cubism 2, then generated puppets, and the
  persona dropdowns use the same order.

### Verified (real output, 2026-09-25)

- 51 app tests (7 new in `tests/test_avatar_chat.py`: the tag parser,
  history trimming, the request sent to Jan, and the endpoint with a stand-in
  Jan) and 19 shared tests (5 new for Cubism 2: discovery, `.mtn` format,
  `.mtn` writing, the real samples). black run, pyright 0 errors.
- Param probe (a temporary page, now deleted) that drove frames by hand:
  `headbang_lite` swung PARAM_ANGLE_Y from about -16 to +23 on Haruto,
  Shizuku, Unity-chan, Hijiki, Koharu, Tsumiki and Epsilon, the same as
  Arch-chan (Cubism 4). Lip sync reached 0.41 to 0.47, and the models' own
  motions and expressions played. **Cubism 2 motions run on the page clock**,
  so a probe must let real (or virtual) time pass between frames.
- Screenshots: the Studio with Haruto and the grouped tiles; a stage-only
  page with Arch-chan and with Kira as Haruto plus a live chat history.
- Live Jan chat: Kira answered through the already-loaded
  Qwen3_5-4B-IQ4_XS in 4.4 s, and the tag was parsed (happy, then wink).

### Not verified / known gaps

- Not seen in a real Forge window. Drag, zoom and poke were never clicked by
  a person.
- Headless Chrome cannot photograph the full chat page with Live2D: under
  virtual time the long-poll hangs it, and in real time fetches stall. Use a
  stage-only copy of the markup (as done here) or look in Forge.
- The hair physics during a motion were not checked by eye.
- The tag parser also takes a bare tag word at the very end ("... wink"),
  which could clip a reply that happens to end with one of those words.

### Improve next (ranked)

1. Look at it in Forge with Emerson: poke, drag, chat, voice. That is the
   only thing not yet seen.
2. Per-persona `own:` mappings for the other Live2D wearers (Kira/Haruto has
   numbered motions only, so map them after watching them).
3. Ren still needs a newer viewer (Cubism 5.3 `.moc3`).

## Avatars and personas (2026-09-24): built, tested

Emerson asked for a live anime avatar panel in this app with personas (cute
and flirty girls and boys, plus Claude's own made-up persona), Nyarch's
Arch-chan as the first model, more than 8 motions per model, motions
generated when needed, and a generator, editor and saver. The personality
itself is in `~/.claude/self/PERSONALITY.md`; the design was
`~/Forge/apps/claude/docs/PLAN-claude-avatars.md`.

What exists:

- **Stage** (`static/stage.js`, right pane of the chat page): the persona
  for this turn, shown as a Live2D model or a generated puppet, reacting to
  events (thinking, tool, done, error), lip-moving while text streams,
  following the mouse, speaking the reply when 🔇/🔊 is on. It is
  collapsible (⟩) and has a "who answers" picker (by mood, one persona, or off).
- **Personas** (`personas/*.json` plus `personas.py`): Tetsu (default, a
  generated puppet), Kira (build, Mark), Shizu (fix, Natori), Arch-chan
  (status), and Yui and Ren (downtime, Hiyori and a puppet). The mood comes
  from the message (`pick_mood`, tested on Emerson's real typed messages).
  The roster goes into `--append-system-prompt` once; each message gets a
  one-line `[persona: X | mood: Y]` tag on stdin only. That is cache-friendly;
  it is not shown in the log. Emerson's choices are in `<data>/personas.json`.
- **Voice** (`voice.py` plus `tts_worker.py`): Kokoro through PanelForge's
  venv and the shared model files (nothing installed twice), at nice 10 with
  2 threads, started on first use and stopped after 5 idle minutes.
  `POST /api/voice` returns a WAV.
- **Avatar Studio** (`static/avatars.html`, the 🎨 button): a model and puppet
  browser, every motion (the model's own plus generated), new motions
  (Improvise, or "Make with Jan" using this app's own Jan model role
  `motions`), the puppet generator and editor (undo/redo, save, delete), and
  per-persona avatar and voice choice. Deep links look like
  `avatars.html#live2d=arch&play=nod&tab=motions`.
- **Shared parts** (`~/Forge/shared/`): `forge_avatars.py` (catalogue, recipes
  to `.motion3.json`, puppets), `forge_avatar.js` (renderer for both kinds),
  and `avatars/` (Live2D viewer libs from Nyarch, 9 models, 24 recipes,
  puppets). Tests: `~/Forge/tests/test_forge_avatars.py` (system python).

### Verified (real output, 2026-09-24)

- Tests: 14 shared (`tests/test_forge_avatars.py`) and 42 in this app
  (`tests/`: the panel, personas, voice). black done, and pyright shows 0
  errors on every touched file.
- Headless Chrome (swiftshader) screenshots: the chat page with Tetsu in the
  stage; the Studio with Arch-chan, Mao and Wanko (Live2D) and Tetsu (puppet);
  the Generator panel with no sideways overflow.
- Driving the model by hand in a probe page: `headbang_lite` moved ParamAngleY
  from -17 to +24 on Arch-chan, Hiyori and Wanko (`PARAM_ANGLE_Y`, name
  translated), and lip sync moved the mouth from 0.26 to 0.52 on all three.
- `POST /api/voice` gave a 141 KB WAV in 2.0 s warm (9.3 s cold, with a
  PulseForge render using the CPU); without `X-Forge` the answer is 403.

### Not verified / known gaps

- **Ren (Live2D sample) does not load.** Its `.moc3` is format 6 (Cubism 5.3).
  The official core 6.00 (from CubismSdkForWeb-5-r.5) opens it, but under
  Nyarch's pixi-live2d-display build every model went blank, so the old core
  stays. `forge_avatars.MAX_MOC_VERSION = 5` hides Ren. It needs a newer
  pixi-live2d-display (or the official Cubism framework) to fix.
- "Make with Jan" was not run live: Jan was busy with another session's 4B
  model swap. The parsing and validation of a reply are tested.
- The stage has not been seen in a real Forge window with a real Claude
  turn yet. The event path is covered by the fake-CLI tests, but not by eye.
- Headless screenshots need `--virtual-time-budget` for the Studio; the
  chat page long-polls, so use `--timeout=9000` there.
- The Live2D lip sync and expressions go through a wrapper on
  `coreModel.update`, because this viewer never emits `beforeModelUpdate`.

## Check (2026-09-22, Acchan session): works end to end; also a tab in Acchan

Emerson asked to "make the claude code app work" and to show it inside the
new Acchan app. No code change was needed here; it is embedded as an iframe
tab by Acchan (listed in `apps/acchan/forge_app.json` "tabs"), which works
because this page sends its own `X-Forge: 1` header.

Verified on a scratch port (18445, scratch `FORGE_CLAUDE_DATA`, CLI 2.1.278):
`/api/options` answered; a conversation with model `haiku`, mode `dontAsk`
answered "pong" and the result's `modelUsage` was `claude-haiku-4-5`. In
mode `plan` with `haiku`, the CLI's init event said Haiku but the reply was
billed to `claude-sonnet-5`: Claude Code itself uses a stronger model for
planning. That is CLI behaviour, not this app; worth a hint next to the Plan
mode choice if Emerson is surprised by the cost. Round trip 8 s.

## Status (2026-09-17, crew panelforge helper-8): two accounts, switchable

Emerson has two Claude subscriptions and switches when one hits its 5-hour
limit. The panel now holds one **account profile** per Claude Code config
directory: "default" is `~/.claude` (untouched), every other one is
`~/.local/share/forge/claude/profiles/<name>/`, passed to the CLI as
`CLAUDE_CONFIG_DIR`. Each conversation remembers its profile.

### Verified (real output)

- CLI 2.1.274 probes: `claude auth status --json` (email, org, plan,
  configDirectory); an empty `CLAUDE_CONFIG_DIR` reports not signed in;
  `claude auth login` over pipes prints the sign-in address and waits for the
  code on stdin; a wrong code exits 1 with "Login failed"; `BROWSER` is
  honoured; a session transcript copied to another config dir is found by
  `--resume` (without it: "No conversation found").
- Before the change, on a scratch port with the real CLI: the first
  conversation's process took over 2 minutes before its init event (CLI-side,
  seen once; api time 3 s), the second answered in 6 s. The page now says
  "still starting" after 20 s without an event instead of a bare "working".
- After the change, scratch port, real CLI, `FORGE_CLAUDE_DATA` in scratch:
  turn 1 streamed "panel works" in 4.3 s on the default account; the
  rate_limit_event was recorded as usage (5-hour window 85% used, 7-day 10%);
  adding "work" and switching the conversation to it copied the transcript and
  the next send was refused with "The account 'work' is not signed in";
  switching back resumed the same session id and turn 2 recalled the words
  (4.1 s). A real `claude auth login` for "work" reached state "waiting" with
  the real address (BROWSER=/bin/true for the test, so no window opened).
- `pytest -q tests`: 20 passed (5 new: profile directories and names, a
  2000-name sweep, the login relay against the fake CLI, a conversation running
  on its profile and moving with and without a transcript, the HTTP routes).
- black; pyright 0 errors on runner.py, web_app.py, tests; node --check.

### Not verified

- **The page itself was not screenshotted**: headless Chrome hung on this page
  in that session (three tries, also with a private profile dir). The account
  list, the sign-in box and the header badge are written and `node --check`
  passes, but nobody has looked at them. First thing next session: start on a
  scratch port, screenshot, fix contrast or layout.
- The second real sign-in. Emerson does it: "+ add" under the conversation
  list, a name, then sign in as the other account in the browser window that
  opens (sign out of the first account there, or use a private window), or
  paste the code the address shows into the box.
- The one-off multi-minute first start above.


## Status (2026-09-15, session 33)

Built at the user's request for "a Claude Code interface linked to the browser
that can browse, with a link somewhere to attach files".

### Verified

- `pytest tests`: 15 pass against `tests/fake_claude.py` (MCP handshake, tool
  list and tool calls, browser failures as tool errors, command line per
  setting, images inline and files by path, attachment names cannot escape,
  streaming + history + resume with the same session id, Stop on a hung turn,
  a crash reported with its stderr, the header guard, uploads, settings, links
  and the Browser page attachment).
- The stream-json shapes were read from the real CLI (2.1.270) before building:
  one "reply OK" probe, $0.04.
- **Real end to end**, one turn, $0.09: a scratch backend with real Claude Code
  in the default "read and browse" level, the Browser page running in an
  off-screen Forge window. `forge-browser` connected; Claude called `tabs`,
  `open` (new tab) on iana.org and `read`, then answered "Example Domains" in
  7.5 s. The records the Browser kept from it were cleared afterwards.
- Screenshot of the chat page (with the fake CLI): list beside the chat,
  attachment chip, a Browser tool card marked done, Markdown with a link and a
  code block. The first screenshot caught a layout bug (list stacked above the
  chat) and a version line leaking fake output; both fixed and re-shot.
- black; pyright 0 errors on runner, web_app, browser_mcp and tests;
  node --check.

### Not verified

- Inside a real Forge window on screen, including clicking a link to open it in
  the Browser and the paste/drag attachment paths (the upload endpoint behind
  them is tested).
- Long answers, compaction and very large attachments.

## Status (2026-09-25, second-account session): every account shares one brain

Emerson wants both Claude accounts to "act, feel and know the same". Before
this, the `second` profile's config directory was almost empty: no
settings.json, none of his skills, agents or output style, no plugins, and a
memory folder of its own that was empty.

- `runner.Profiles.link_shared(name)` symlinks `CLAUDE.md`, `settings.json`,
  `skills/`, `agents/`, `output-styles/`, `commands/`, `plugins/` and
  `projects/` (memory and transcripts) in a profile's directory to the default
  profile's (`runner.MAIN_CONFIG`, i.e. `~/.claude`). The list is
  `SHARED_FILES` / `SHARED_DIRS`. The login (`.credentials.json`,
  `.claude.json`) and per-process scratch folders stay per profile.
- It runs from `Profiles.add()` and from `Profiles.env()`, so every start and
  every status check keeps the links current, and new profiles get them free.
- A profile's own copies are merged into the shared one first. Anything that
  would overwrite is renamed `<item>.before-shared` beside the link; nothing
  is deleted.
- Because `projects/` is shared, a session id now resumes under any account.
  That is what the planned handoff (below) relies on, and it makes
  `Conversation.move_to`'s transcript copy unnecessary. Session ejb-79 is
  removing move_to as part of its tabs work.
- `tests/test_shared_profiles.py`: 4 tests. `tests/conftest.py` has an autouse
  fixture pointing `runner.MAIN_CONFIG` at tmp, so no test links into the real
  `~/.claude`. Before it existed, one test run created an empty
  `~/.claude/commands`, which was the only leak and is harmless.
- `~/.claude/tools/usage.py` now reads `$CLAUDE_CONFIG_DIR/.credentials.json`
  when set (it used to always read `~/.claude`, so the second account saw the
  default account's numbers), plus `--all` for every profile. Its docstring
  has the real 70% / 15 min / 92% rule.

Applied to the real `second` profile on 2026-09-25 17:21. **Verified:** all 56
tests pass; black clean; pyright 0 errors on runner.py, the two test files and
usage.py. The links exist, and the running second-account session picked up the
shared settings.json on its next turn (the Tetsu output style switched on).
`usage.py`, `--all` and a default-account run each printed the right account's
meters.

Found while applying it: Claude Code under `CLAUDE_CONFIG_DIR` had been writing
part of each transcript into `~/.claude/projects` as well, and the rest into the
profile. The merge therefore found two copies of the two live transcripts and
kept the profile's (the complete ones) aside. They were spliced back into the
shared copies: the full aside copy, then the shared-only entries by uuid. The
resume chain was checked (218 linked entries back to the first message).
`profiles/second/*.before-shared` still hold the originals and can be deleted
once nothing looks wrong.

**Not verified:**
- Whether Claude Code's synced-skills cleanup is happy with two accounts'
  buckets in one `skills/synced` (the second's bucket was kept aside, not merged).
- Whether ListAgents / SendMessage reach across accounts; they did in this
  session (ejb-79 and this session are both on `second`), not yet between
  default and second.

Next (planned with Emerson, not built): tabs locked to one account (ejb-79),
then the handoff. When a tab's account hits its limit or 92%, a banner offers
"resume this session on the other account" (same session id, new tab) or
"fresh tab from a handoff" (first message points at the old transcript and
WIP.md).

## Status (2026-09-25, second-account session): instant tab switching

Emerson: "when I change conversations it blanks out for a second as though
there is nothing, then it loads; I want instant loading". The cause was
`openChat` in `static/app.js`. It wiped `#log` to the empty placeholder, fetched
the whole history (1.4-4.3 MB, 3,400-7,700 events for the big chats), and
redrew all of it. Every user message in that redraw called `scrollDown(true)`,
which forces a layout of the whole log, so a long chat laid out thousands of
times.

Now each conversation draws once into its own **view** (`views` Map: a `.view`
box plus its own `live` / `tools` maps, `seq`, `streaming`, last
`forge_persona`, `meta`, `busy`). Switching swaps boxes and then fetches only
the events after the view's `seq`. The previous chat stays on screen until the
new view is ready, so the screen never goes blank. `warmTabs()` pre-draws the
open tabs at boot. Bulk draws never scroll per event (`scrollFor`). Views for
chats with no open tab are capped at `KEEP_VIEWS` (4), least recent dropped
first. The avatar stage only replays the view's last persona, which is all
`Stage.event(e, false)` ever used. CSS: `.view` takes over the column layout
`.log` gave its children.

**Verified** in headless Chrome (CDP, driven from the venv's `websockets`),
against a scratch backend on port 8499 using a *copy* of the data dir, since
the live 8445 backend still runs pre-tabs code (see below). The same 3 chats
and the same harness were run with the old app.js on 8498. Switching back to a
tab took 140-434 ms before and 42-62 ms after, both including two animation
frames (~33 ms). After a reload with the warm-up it took 21-64 ms, against
38-194 ms. No page errors. A screenshot was looked at: tabs, effort picker and
tool cards lay out as before, and contrast is fine. The 58 Python tests pass
(JS has no unit tests here). **Not verified:** the timings in Forge's own
WebKitGTK window, which is slower than Chrome, so the old blank was longer
there.

**Before using the new page:** the live backend on 8445 is the old code
(`/api/commands` returns 404; `/api/options` has no `efforts`). ejb-79 then made
boot() tolerate that (`o.efforts || {}`), so against the old backend the page
loads with the effort picker hidden and an empty / menu. Restart the Claude app
in Forge to get the full feature set.
Backups of the pre-edit files are in `~/Forge/backups/claude-app.{js,css}.2026-09-25-instant-tabs`.

## Carry on after a restart (ejb-e3, 2026-09-27, commit 6e4f3c6)

- A turn in progress is marked `working` in the conversation's JSON. At start the app resumes each marked one (`Registry.resume_interrupted`, 20 s apart) with a short carry-on message through `--resume`. Setting: Settings > Apps > "Claude: carry on after a restart". The manifest's `start_at_launch` makes Forge start this app at launch even when apps start on demand.
- **Verified:** tests/test_resume_after_restart.py (6), full suite 130 passed, and a real backend run with the fake CLI.
- **Not verified live:** a real reboot, and the real CLI's reply to SIGINT mid-turn.

## 2026-09-30: Sonnet 5.5 in the model picker

`runner.MODELS` gains `claude-sonnet-5-5` ("Sonnet 5.5", released this week);
the old `sonnet` alias stays, relabelled "Sonnet 5", because Claude Code
2.1.283 still resolves that alias to Sonnet 5. **Verified:** a live
`claude -p --model claude-sonnet-5-5` run answered (with a harmless
"not in this version's model catalog" warning; updating Claude Code removes
it); `tests/` pass, including a new MODELS test; `check_enjoy_ui.py` passes.
Once Claude Code knows Sonnet 5.5, the `sonnet` alias will follow it too.

## 2026-09-30 (Daichi / ejb-a8): everyone view, dividers, cold sessions

- **Claude Code updated** 2.1.283 -> 2.1.285 (`claude update`) while Relay was
  paused. Running sessions keep the version they started with; 2.1.283 stays
  in ~/.local/share/claude/versions.
- **Everyone** (`everyone` button, classic layout): every Claude session on the
  laptop from ~/.claude/sessions/<pid>.json, grouped working / idle / ended
  (cold = its pid is gone; shown 3 days), each with its helper agents (from
  projects/*/<session>/subagents/*.meta.json; "working" = transcript written in
  the last 2 min). Buttons: *open tab* (a Forge tab), *resume here* (a cold
  session resumes in a new tab with `--resume`), *message* (a crew-board note
  from Emerson to that session's board name, worded "answer him in your next
  reply, then carry on"; the notes hook hands it over at its next step).
  Running-elsewhere sessions are never resumed (409): two processes on one
  session would split it. Backend: `everyone.py`, routes `/api/everyone*`.
- **Dividers**: drag between the list / chat / avatar panes; width is
  remembered per pane, double-click resets. The Account section folds (▸).
- **Crew** (`~/.claude/skills/crew/crew.py`): a claim is stale at once when its
  holder's session has exited (`session_gone`), not only after 4 h; `status`
  marks such members "session ended, not working".
- **Verified**: 148 app tests + crew unittests pass; `tests/check_everyone_ui.py`
  (headless Chrome) lists the 3 live sessions, the divider drags 250 -> 400 px
  and is remembered, accounts fold, no page errors. Pyright 0 errors.
- **Not done / not verified**: needs a Claude app restart to be live (not
  restarted: 3 sessions run in it). Not in the Enjoy layout yet. The report
  that a message typed in a Forge tab "gets lost" was not reproduced or fixed:
  typing mid-turn already goes into the running turn (runner.send), so the
  cause is still unknown; next step is a repro with the event log.
- Update: with Claude Code 2.1.285 the `sonnet` alias runs claude-sonnet-5-5
  (checked with `claude -p --model sonnet --output-format json`), so that
  option is now labelled "Sonnet (newest)".

## 2026-10-08 (task 114): plain Relay session names in "everyone"
- `/api/everyone` rows now carry `relay` ({task, title}) for sessions named
  relay-<n>-...; the title comes from the task file via
  `shared/forge_session_names.relay_task`. The list shows it through
  `shared/forge_session_title.js` ("#109 Mission Control conversation view");
  the persona/session name stays in the sub line. Forge tabs themselves are
  the app's own conversations and are unchanged.
- Verified: tests/test_everyone.py 4 pass; browser check
  `tests/check_relay_names_ui.py` (needs a Relay session from the last 3 days).
