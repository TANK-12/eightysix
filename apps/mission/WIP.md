# Mission Control: work in progress
date: 2026-10-08 · for: both

## Attach files and pictures in Conversations (2026-10-08, Koharu, Relay task 118)

The composer's paperclip, paste and drop now work in the WhatsApp (Relay)
chat and in transcript chats, not only Claude app chats. Those upload to
Mission's own `/api/attach` (or `/api/attach/paste-image`, through
`borrow.clipboard()`, for a WebKit screenshot paste), into
`~/.local/share/forge/mission/attachments/YYYY-MM-DD/`; `/api/relay-chat/say`
and `/api/sessions/{id}/say` take `files` (only paths inside that folder)
and add an `Attached files:` list (`MissionChat.withFiles`). Jan chats still
take none. Verified: `tests/test_attach.py` 6 pass, `chat_logic.test.js` 21
pass, and in headless Chrome the WhatsApp composer showed the paperclip and
made two chips from a drop and a paste (screenshot looked at). Not verified:
a real send from Mission with a file (it would post to WhatsApp).
Later (sessions 2-3): the drawer's reply box (`static/chat.js`, `.cx-*` in
`app.css`) has the same attach, paste and drop (headless check: two chips,
screenshot looked at); the routes now come from `shared/forge_attach_api.py`
(`web_app.ATTACH`); the text length limit no longer counts the file list.
`tests/test_attach.py` 7 pass with `test_claude_proxy.py` (45 together).
Session 3: the drawer refuses files in Jan mode with a message (a paste
there goes in as text), and Send waits while a file uploads. **Not
committed:** Mission's task-118 hunks share files with the uncommitted
task-109 work (`web_app.py`, `chat_logic.js`, `convos.js`, tests), so they
were left in the working tree for whoever commits those files.

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
Also in Mission: `context_window(model, used)` treats a session past 200k
as a 1M window (Opus 5.5 runs 1M under a plain id; Riku read 337k/200k),
and `MissionLogic.helperName` names a workflow helper by its label
("build:golden") instead of "workflow-subagent" (cards, drawer, Swarm).

## Go to it opens a headless session's chat here (2026-10-08, Izumi/ejb-ac)

Emerson hit "that session is not in a terminal or in the Claude app" on Go to
it for Relay task 113. Relay sessions run headless, so there is no window.
Now the Board answers `nowhere: true` and `MissionLogic.goResult` turns that
into: select the session in Conversations, switch there, toast "It runs in no
window, so its chat opened here". Real errors still show red. Verified:
`tests/logic.test.js` (goResult), new `tests/test_go_to_browser.py` (real
click in headless Chrome, fake data) pass; live click on relay-113-work
opened its real chat (screenshot looked at). The live server (port 8465) was
restarted by hand with the same uvicorn command to load the change.

## Conversations rebuilt as a full-window chat (Relay task 109, 2026-10-08)

Emerson (WhatsApp, 15:07): the conversation view "still sucks". He wants the
Claude app's chat but better and anime styled, model (Opus / Sonnet / Haiku)
and effort (to max and ultrathink) picked inside the chat, and above all the
back-and-forth on its own: no side bars and dropdown rows, big text (his eyes
are not the best), controls tucked away but reachable.

What was weak (before shots `docs/2026-10-08-task109-before-*.png`, 1600x1000,
real data): Mission's top bar, needs band, nav, list and plan column left the
chat about 640x350 px; four rows of chrome above the first message; 13-15 px
text; every tool call a full card with empty "Thought" cards between them; two
different chat UIs (an Enjoy copy and chat.js); a plain dark look.

Built (commits 4e2af9c, a9c9142 and the task 109 finish commit):
- **Focus layout**: opening Conversations sets `body.focus-chat`; Mission's
  top bar, nav and needs band step aside and the chat fills the window. Slim
  header: Chats (needs-you badge), portrait, plain name + persona tag, state
  pill, what it is doing, plan chip, Stop, Session, WhatsApp, back to Mission.
- **One chat UI** (`static/convos.js`, styles `static/convos.css`, DOM-free
  logic `static/chat_logic.js`) for three sources: a Claude app chat (live
  through `/api/claude`), a transcript (terminal, Relay run, ended session:
  reply via `/say`, Jan via `/ask-jan`, load earlier) and the WhatsApp mirror.
  `chat.js` stays for the drawer's Chat tab.
- **Reading**: centred column, 19 px default (slider 14 to 28 px, times
  Forge's text scale), anime night look: Claude on the left with its sprite
  portrait and name tag, Emerson on the right in a pink-lilac bubble. Each
  run's tool calls and kept reasoning fold into one "N steps" bar (opt-in
  hooks `step` / `stepDone` / `turnEnd` in `shared/forge_convo.js`; the Claude
  app passes none, so it is unchanged). Steps folded / open / hidden.
- **Controls tucked away**: the composer chip ("Opus · High") opens model
  cards (the Claude app's own list via `/api/claude/options`), an effort gauge
  Low to Max and ultrathink Off / Next message / Every message (Next turns
  off after a send). Everything else is in the Session sheet (right
  slide-over): title, may-do, Normal / Ultracode + Limits, reasoning, steps,
  text size, Claude or Jan, facts, Open in Claude / Go to it / Details /
  Resume here. Terminal sessions show their model read-only.
- **Chats panel** (left slide-over, Ctrl+K; Alt+Up / Alt+Down next and
  previous; Esc closes): find box, needs-you first then newest, WhatsApp
  pinned on top, Mission's other views at the bottom.
- **Note 1316**: sessions newest activity first, re-sorted at most once a
  minute (needs you on top), an Archived section (ended or idle 30+ minutes),
  plain names "#109 Mission Control conversation view" with the persona as a
  small tag, everywhere (cards, drawer, map, swarm, chat).
- **Note 1295, WhatsApp mirror**: the Relay thread live (`mc/relay_chat.py`,
  `GET /api/relay-chat`), typing goes through the new Relay session command
  `relay as-whatsapp` (Relay's `cli.py`): handled exactly like a WhatsApp
  line (commands too), echoed to WhatsApp as "From Mission Control: ...";
  the chip switches between To Relay and To the boss.

- **Review fix pass** (sessions 9 to 13): three Opus reviewers (critic, art
  director, "Emerson lens") listed 37 findings in
  `docs/2026-10-08-task109-review-findings.md`; each is now fixed or kept with
  a reason there, with how it was checked. The main ones: plain words when
  Mission's server is older than the page; drafts, sending state and pending
  lines kept per chat; pictures in Claude-app chats through a new image proxy
  (`GET /api/claude/conversations/{id}/files/{name}`, images only, 40 MB cap);
  link clicks opened by the Claude app (`POST /api/claude/open-link`, http and
  https only); a Stop for Relay runs that needs two presses
  (`POST /api/relay/tasks/{n}/stop`); short in-between status lines folded
  into the run's steps bar (his message and the final answer always stay out);
  A- / A+ in the header with all small print following the size; Chats in calm
  order with sections and a folded Archived group; real dates on WhatsApp day
  chips; plain words for path-like names; turn ends "took 18 min" without
  dollars; round busts with a speech tail and the chibi by the composer;
  helper task notifications shown as one grey line, not as Emerson's bubble;
  Relay's `as-whatsapp` no longer logs a line twice and chat answers are
  logged with WhatsApp off; Relay's "reviewing" status counts as open (note
  1337). Left on purpose: no New chat button (new chats start in the Claude
  app), the WhatsApp mirror keeps Relay's last 40 lines and shows no pictures.

Verified: see the "Checks" list at the end of this section (updated when the
task closes). Not verified: a real send from the new view into a real chat
(real-data runs block every POST; sending is checked against fakes in the
browser tests), and `relay as-whatsapp` against the live WhatsApp (tested on
fake Relay data end to end).

## Conversations view of its own (2026-10-08, helper of ejb-f7 Rin)

Emerson (2026-10-08): "mission control still doesnt have its own
conversations thing", then "make a copy of the enjoy conversations
interface and put it in the mission control, it has selectors for model and
effort and ultracode and ultrathink".

First checked: the drawer Chat tab from task 67 works end to end (real data,
scratch port, headless Chrome: Rin's chat drew 18 messages and 19 tool
cards, no page errors). So the complaint was the missing top-level view, not
a broken tab.

Built:
- **Conversations** in the left nav (second, after Sessions;
  `static/convos.js`, `#view-convos`). Left: every session in the overview,
  newest activity first, with a find box. Right, by session:
  - runs in a Claude app tab (`claude_tab`): a copy of the Claude app's Enjoy
    task view (enjoy.js "one task"): editable title, running pill and stop,
    model / effort / may pickers, the Normal / Ultracode switch and Limits
    fold (the Claude app's own `run_controls.js`), an ultrathink switch (adds
    the keyword to the next message, then turns off), a reasoning switch, a
    Claude / Jan switch (Jan answers about the chat locally through
    `/ask-jan`), the chat drawn by `shared/forge_convo.js` with tool calls
    folded and live through the Claude app's long poll (`wait=25`), the
    composer with attach, paste and drop, and plan & progress read by the
    Claude app's `enjoy_logic.js`. The Claude app's colours inside the pane.
  - anything else (terminal, Relay run, ended without a tab): the transcript
    chat from `chat.js` with Mission's reply box (board note, or resume and
    send). Ended ones get **Resume here**: `POST /api/sessions/{id}/open`
    with `show: false` resumes it in the Claude app without switching Forge
    away, and the pane becomes the Enjoy view.
  - header: Open in Claude (unchanged), Go to it, Details (the drawer).
- **Sharing, not copying**: `mc/claude_proxy.py` forwards an allowlist of
  the Claude app's routes (options, conversation events, send / settings /
  stop / seen / files / paste-image) with its `X-Forge` header; POSTs still
  need `X-Mission: 1`. `/claude-ui/<name>` serves four named Claude app
  static files read-only. apps/claude itself is untouched.
- The drawer keeps its Chat / Details tabs everywhere else. In the
  Conversations view the drawer shows Details only (the chat is the view),
  and anything that opens a session there (needs band, Details) also picks
  it in the list.
- `chat.js` `hide()` now empties its box: its ids are page-wide, and a
  stopped chat left behind in the drawer or the view would shadow the next.

Verified (output seen, 2026-10-08):
- `.venv/bin/python -m pytest -q tests`: 99 passed (was 69 + map tests).
  New: `test_claude_proxy.py` (fake Claude app on a free port: the header
  is forwarded, every allowed action reaches it, everything else, bad ids,
  bad bodies and missing X-Mission are refused before it, its errors pass
  through, down is a plain 503, the four UI files are byte-identical and
  nothing else is served, Open with `show: false` does not switch Forge) and
  `test_convos_browser.py` (headless Chrome, 3 seeded random sets of 4-9
  sessions against a fake Claude app: list newest first, newest picked,
  each session opens the right pane, never two copies of a chat, the plan
  read from TodoWrite, send carries `ultrathink. ` and the knob and
  ultracode changes reach settings, ultrathink turns off after sending, no
  page errors). A mutation run (sort reversed, ultrathink dropped) made it
  fail on exactly those checks.
- black clean and pyright 0 errors on every touched .py.
- Screenshots on a scratch port with real data (POSTs to the real Claude
  app blocked in the page): `docs/2026-10-08-conversations-claude-app.png`
  (1600x1000), `docs/2026-10-08-conversations-transcript.png`,
  `docs/2026-10-08-conversations-1100px.png` (plan column folds away).

Not verified: sending for real into one of Emerson's chats from this view
(the test sends into a fake Claude app); attachments end to end (the route
is forwarded and tested, the picker was not clicked); how it looks inside
the Forge WebKit window (Chrome only).

## Map redone as lanes (Relay task 73, 2026-10-07, Ami + Kana)

Emerson after task 67: "map just look really bad". Before shots showed dead
space right and bottom, board-note arcs across cards, every Relay session
twice (crew card + raw "Bash: ..." run card), loud green halos, empty lead
boxes, cut text, boxes inside boxes.

- **HTML lanes, no SVG.** `mc/graph.py` only groups (crews with commander,
  Relay runs, shared boards, solo sessions, Jan); no pixel layout, so the
  page no longer sends `mapw`/`maph`/`zoom`. Each agent appears once; a
  Relay run whose session sits in a crew is a "task N" badge. A run with no
  session yet is titled by its Relay task title; `plain()` strips tool
  names, `VAR=...` shell prefixes and the home path from action lines.
- `static/app.js` packs lanes into columns (two orders tried, a lane with
  free columns beside it widens), sizes in em of `--mz`; fit tries 180%
  down to 100%, - / + set a fixed zoom. Notes per card are a count chip.
  Lanes do not animate (a width animation made heights be read mid-way,
  which clipped the bottom lane); a lane ResizeObserver re-places lanes that grow
  late (sprites, fonts).
- Top bar wraps instead of scrolling sideways; under 1440 px the helper
  count and the "live" word hide (account meters stay).
- Tab switch: the 220 ms fade-in on every view switch is gone.

Verified (output seen, 2026-10-07):
- `.venv/bin/python -m pytest -q tests`: 70 passed. New
  `tests/test_map_browser.py` (headless Chrome via `tests/cdp_driver.py`,
  fake overviews): 1, 6, 15 and 40 sessions at 900, 1300 and 1536 px: no
  card or lane overlap, cards inside lanes, lanes inside the map, no
  sideways scroll (page, main, map), text at least 13 px, names not cut,
  lanes use the width; drawer open at 1300 px; 200% zoom at 900 px. It fails
  when cards are pushed into each other or the old top bar is put back.
- Tab switch, 16 Map/Sessions switches at 1300x840: frames with the view
  dimmed 165 before (ae962d1) and 0 after; no long tasks either way.
- Screens: before `/tmp/t73/before/`, after `/tmp/t73/after4/` (live data).

Result critic (opus), round 1 = CHANGES, all fixed and re-tested:
the browser test reloaded the same `/#map` URL so it only ever saw the
1-session wave (now `/?w=<case>#map` + a cards-drawn guard; the old URL
fails it); map helper cards took the Sessions view's `.helper` style (12 px
text, -5 px margins), so card kind classes are now `k-<kind>`; long lane
titles ran out of their lane (ellipsis now, tested); new lanes slid in from
the top-left (first placement has no transition); `plain()` cut quoted
values and ate "Error: " (known tool names only now, tested); "task 63"
title and badge twice; zoom could go to 90% (floor 100% now).
Round 2 = CHANGES: the browser test flaked 2 in 5 (the vertical scrollbar
narrowed the map after placing; fixed with `scrollbar-gutter: stable` on
`.mc-main` and an at-once re-place when the map width changes; 6/6 passes
after), `plain()` blanked a line cut inside its variables (keeps them now),
and lanes slid through each other for about 200 ms after a change (lanes
no longer animate; they snap into place).
Left as is: one session uses about 66% of a 1536 px map (one card is not
stretched); several solo lanes can all be titled "home folder"; the top bar
may wrap to two rows at 1300 px with many chips (wrap, never sideways).

Result critic round 3: APPROVE (browser test 6/6, stress harness clean
twice, no overlap even sampled every 100 ms through a live change).

Also (board #1105 from Nene): Sessions cards repeated the crew chip
("forge forge forge overhaul · lead") when one session joined a board
under several names; `mc/sessions.py` `one_per_crew()` now keeps one per
crew (the lead's entry if any), tested; seen live with one "forge" chip.

Not verified: on his real screen in the Forge window (headless Chrome at
1300x840 and 1536x864 stood in for it).

## Conversations, Messages, Swarm and the card map (Relay task 67, 2026-10-07)

What was built (three sessions: Ren, Nagi, Kiko):

- **Chat tab** in the session drawer (Chat / Details). It renders the
  session's own Claude Code transcript with the Claude app's renderer, moved
  to `shared/forge_convo.js` + `shared/forge_convo.css` (scoped `.fc`);
  `apps/claude/static/claude_common.js` is now a thin wrapper around it, and
  the Claude app's html files load the shared file first. Backend:
  `mc/convo.py` turns transcript lines into the Claude app's event shapes
  (Emerson's board notes from hook attachments included, signature-only
  thinking dropped); `GET /api/sessions/{id}/events` gives the tail page,
  `before=` older pages, `after=<byte offset>` the live tail. Reasoning
  blocks show only with the "reasoning" switch on.
- **Reply box** with pickers (Claude or Jan, model, effort, ultrathink).
  `POST /api/sessions/{id}/say`: a session open in the Claude app gets it
  through the app's `/send`; an ended one is resumed in the Claude app
  first; a terminal session gets a forge board note. "Ask Jan about this
  chat" (`/ask-jan`, `mc/jan_ask.py`) is local and free, with Mission's own
  Jan model setting, loaded on demand. Open-in-Claude and the quick message
  are unchanged.
- **Messages view**: "Ask everyone" / note to everyone goes through
  `POST /api/broadcast`, recorded by `mc/replies.py` in
  `~/.local/share/forge/mission/messages.json` (`MISSION_DATA_DIR` moves it
  for tests). Replies are board notes acking it (`crew ack --note`) plus
  answers found in each session's transcript after the hook handed the note
  over. One thread per broadcast, a line per session; nav badge for new
  replies.
- **Swarm view** (`static/swarm.js`): every live agent at once, lanes per
  commander, Relay and own sessions.
- **Map rebuilt** (Emerson: too small, small text, sideways scroll,
  overlapping boxes). `mc/graph.py` now lays out panels of fixed-size cards
  (lead 260x88, members 230x70 in a grid) with a skyline packer, for the
  page's own width: the page sends `mapw`, `maph` and `zoom` on every
  `/api/overview` poll. "Fit" picks the biggest scale (up to 150%) whose
  layout fits the window height; - and + set a fixed zoom (kept in
  localStorage). The SVG is 100% wide, so it never scrolls sideways; lines
  go to the first column only. The `breathe` animation for "needs you" was
  referenced but never defined; it is now.

Verified (output seen, 2026-10-07):
- `.venv/bin/python -m pytest -q tests`: 69 passed. Map tests are rectangle
  overlap checks: panels never overlap, every card sits inside its panel
  and the map, no two cards overlap, with 1, 6, 15 and 40 members at widths
  600/1200/1800, a 400-case random sweep, a 200-case packer sweep, and the
  fit/zoom scale rules.
- Claude app after the renderer move: `apps/claude` pytest 194 passed,
  `node tests/markdown.test.js` 4 passed.
- black clean on every touched .py; pyright 0 errors on them.
- Headless Chrome (1600x1000) on real data, scratch port 18465: map before
  (`/tmp/mc67/map-before.png`) and after (`map-after.png`, fit 110%, no
  sideways scroll: scrollWidth = clientWidth), plus injected 15- and
  40-helper graphs (`map-big15b.png`, `map-big40.png`), chat, messages and
  swarm shots. No page errors.

Critics (two Opus agents, 2026-10-07: one tried to break the code, one
judged the look from fresh screenshots). Fixed, each with a test or a
re-shot screenshot:
- live chat froze for good after one transcript line over 2 MB (now steps
  over it with "a N KB entry is not shown");
- compaction summaries showed as a 20,000-character message from Emerson;
- "Ask Jan" on a helper's chat read the commander's chat;
- a chat whose first load failed never retried;
- a broadcast counted the next narration line ("Now let me run the tests")
  as the answer; now only the text that ends a turn (`stop_reason
  end_turn`) counts;
- `mapw=nan` gave a 500; the zoom label showed the asked scale, not the
  drawn one (now `scale` = what is really drawn);
- rapid zoom clicks left the map at an older zoom (a poll asked for while
  one is on its way now runs right after it);
- opening the drawer from the map squashed the map (a ResizeObserver
  re-lays it out for the narrower width; checked: true 100% with the drawer
  open);
- board-note lines ran over panel titles (now drawn under the panels);
- the two Claude browser tests (`tests/browser` claude_stream,
  claude_pic_tag) broke because their harness copied only claude_common.js;
  it now copies shared/forge_convo.js too (13/13 PASS, run directly).
Left as is: a wide table in the chat scrolls sideways inside its own box
(same as the Claude app); a broadcast to a board other than forge could in
theory match a forge note with the same number (notes are numbered per
board; every broadcast so far goes to forge); a tool result whose tool call
is on an older page shows its card as done without output; the commander
card leaves empty space under it in a very tall panel.

Not verified (reasoned only):
- Sending through `/say` and `/broadcast` against the live sessions: never
  posted from a test (they reach real sessions); the routing is unit-tested
  with fakes.
- Inside the running Forge window (the hub was not restarted).

## Looks pass (H7, helper-7 Haru, 2026-10-07)

Goal (Emerson): "i want the mission control to look pretty", "animated as
well and a cool interface", Enjoy-level polish without a copy of Enjoy, and
no power cost while idle or hidden. Only `static/` changed (index.html,
app.css rewritten, app.js patched); the backend, logic.js and tests did not.
Pre-pass copy: `~/Forge/backups/2026-10-07-overhaul/mission-looks/static/`
(helper-1's unfinished parallel restyle is beside it in `unclaimed-edit-2011/`).

What changed:
- Design system in app.css: one status colour set (`--st-needs`, `--st-working`,
  `--st-idle`, `--st-ended`, each with a soft and a line variant) used by
  cards, pills, dots, top-bar stats, map rings and edges; periwinkle accent;
  type scale 11/12/13.5/15/17/20; 4-8-12-16 spacing; thin scrollbars
  (incl. `::-webkit-scrollbar` for WebKitGTK); focus rings; reduced-motion.
- Top bar: logo, "live / resting / offline" line, stat tiles (needs you,
  working, idle, helpers busy, notes) that filter or switch view and count
  up when a number changes; Relay as one button; icon settings button.
- Sidebar: icon nav with an accent bar, filters with status dots and count
  badges; collapses to an icon rail under 900 px.
- Cards: whole card opens details (Enter too); one primary action (Open or
  Resume in Claude when it has a Claude tab, else Go to it), the others
  quiet ghosts that brighten on hover (icon-only under 900 px); "now" line
  tinted by state; context meter with percent; mono feed times.
- Grid fills the width: columns = the biggest group's size (at least 2,
  at most what fits at about 380 px), set as `--cols` in `gridCols()`.
- No jumps on polls: `patchList()` keeps every card whose HTML is unchanged,
  swaps changed ones in place, glides moved ones (FLIP, transform only) and
  fades new ones in. Times fill in after the patch so they do not count as
  changes.
- Sprites: Crew Room frames baked into one strip per sprite with its own
  `@keyframes` (`strip()`); working sessions type, a session waiting on
  Emerson talks, Jan models get busy; idle and ended stand still; small
  avatars never animate. All sprites step on one shared beat
  (`syncSprites()`), 1.6x the Crew Room pace.
- Map: nodes kept between polls (state colours fade, new nodes pop in, gone
  ones fade out); Relay, forge board, Jan and Relay-task nodes have real
  icons; speech bubbles with the current action; working edges green;
  dotted arcs for board notes of the last hour (who talks to whom); a
  one-off spark flies along a line when a note is posted or a helper reports
  a new step; a slow breathing halo on "needs you".
- Empty, no-match (with "Show everything"), offline and loading (static
  skeleton) states; view switch, drawer and dialogs fade/slide in once.
- Fix: shared forge.css hides `.adv` unless `body.advanced`; setMode now sets
  it, so Advanced mode shows its extra lines again.
- Polling and sparks honour the hub's "another app is in front" signal
  (`forge-visible`, via shared/forge_idle.js) as well as visibilitychange.

Motion and power rules: loops only where something is live (typing sprite,
needs-you halo); everything else is a one-shot 150-280 ms transform/opacity
animation. Hidden pages pause all CSS animation (`page-hidden`,
`forge-idle`); `body.calm` (prefers-reduced-motion) drops loops and sparks.
The shared power tier has no app-page API yet (asked helper-3 on the board);
when it has, set `body.calm` from it.

Verified (output seen, 2026-10-07, helper-7):
- `.venv/bin/python -m pytest -q tests`: 41 passed, 1 warning in 0.62s. No Python changed, so
  black and pyright were not needed; `node --check static/app.js` passes.
- Headless Chrome screenshots looked at, on a scratch fixture server
  (real data copy, 0 sessions, 40 sessions with very long names, all idle):
  sessions at 760 / 1100 / 1500 / 1920, map at 760 / 1500, crews, relay,
  drawer. Before: /tmp/mission-shots/final-*.png and /tmp/h7/shots/before-*.png;
  after: /tmp/h7/shots/f-*.png, g-*.png, e-*.png (scratch, not kept).
- Driven over CDP (scratch script /tmp/h7/live.py): no page errors; cards
  are the same DOM nodes across polls with unchanged data; a card click opens
  the drawer, Escape closes it; Advanced shows `.adv`; 3 -> 40 sessions
  renders 40 cards; idle cards run 0 looping animations; reduced motion sets
  `calm`: 0 looping CSS animations and the map's SMIL paused; hidden inside
  the hub (forge-visible false): 0 fetches and 0 requestAnimationFrame calls
  in 10 s, map SMIL paused, one poll straight after showing again; map
  sprites step (image x seen at 0 and -16).
- Page CPU (Chrome process tree, 30 s visible, headless software rendering,
  busy machine, single runs: rough): idle data about the same before and
  after (map 2.5 vs 3.3 %, sessions 4.9 vs 1.2 %, noise about 2 points);
  with 2 sessions and 5 helpers working, about 2.8 -> 8 % on the map and
  2.5 -> 4.4 % on sessions, the price of the typing sprites. Long
  measuring stopped on the commander's instruction (board note 17).
- A critic agent (Opus) compared screenshots with enjoy.dev and tried to
  break it. Fixed: map sprites blank while animated (now SMIL x steps,
  paused when hidden or calm), map shrinking labels at narrow widths
  (min width, scrolls), "~" titles, top-bar counts disagreeing with the
  sidebar, context and usage meters reusing the needs-you pink, "taken"
  chips in working green, three or more waiting rows flooding the page
  (folded into one row with Show them), crews notes box losing its scroll on
  each poll, drawer title without state and buttons of equal weight,
  uppercase labels, sidebar rebuilt every poll, live dot hidden under
  1240 px, header overflowing at 1500 with many counts, helpers per card
  default 5 -> 3 (shorter cards, smaller row gaps).

Not done (critic, open):
- Map at scale: every lone session gets its own cluster circle; with dozens
  of sessions the map gets large. A shared "Solo" cluster laid out as a grid
  is a graph.py change (mc/graph.py, backend), not made here.
- Cards in one row still differ in height when one has many helpers
  (masonry would break the grouped order).
- Several needs-you halos breathe out of step; the Crews view still
  rebuilds per poll (scroll is kept); members list is long on the forge
  board.
- The shared power tier (reduced on battery) has no app-page API yet;
  `body.calm` is the hook to set from it.

## State

Built and working on a scratch port against real data. Not yet seen inside
the running Forge window (that needs Forge to pick up the new manifest; port
8465 is free in every other forge_app.json).

## Verified (output seen)

- `.venv/bin/python -m pytest -q tests`: 41 passed (readers on a fake
  laptop, API incl. bad inputs and the X-Mission guard, note validation, a
  400-case layout sweep: no clusters or ring nodes overlap, labels clear
  the centre, a crew's live leader is always its centre (mutation-checked:
  the test fails with the fix removed), node tests of logic.js).
- black clean; `pyright --pythonpath ./.venv/bin/python web_app.py mc tests/*.py`: 0 errors.
- Real data on scratch port 8765: `/api/overview` 200, 74 KB, 20 to 50 ms;
  an unchanged poll answers 63 bytes; an unguarded POST gets 403.
- Headless Chrome screenshots looked at: sessions (simple and advanced),
  map (1500 and 2560 px), crews, relay, the drawer, 400 and 600 px windows.
- A critic agent (Opus) reviewed screenshots and code and tried to break it
  (2026-10-07). Fixed from its list: a poll wiping a half-typed crew note,
  the drawer rebuilding (and jumping) every poll, an older conversation
  answer overwriting a newer one, no request timeout, see-through drawer on
  small windows, Pause/Resume pointing at the real Relay from scratch copies
  (env overrides), notes to nobody / to Emerson / answering missing notes,
  failed sends losing the text, ended limit applied before filters, stale
  folder filter, unread state lost after one bad poll, unescaped ids and
  classes, map-node memory growth, 198 forge members in the payload and
  dropdown, Relay wording ("5809 min old", "Waiting: paused"), narrow
  layout, unbounded claims/log lists, negative `before`.
  Also found by looking: a commander drawn twice on the map when the forge
  board lists it too.

## Not verified (reasoned only)

- Go to it / Open in Claude / Relay pause against the live apps: these call
  the Board's, Claude app's and Relay's own code or API; only their
  "app is down" paths are tested. They were not clicked live, so the real
  Claude app (8445) and Relay were never touched.
- Whether a note to a crew helper (a subagent inside another session) reaches
  it: that depends on the notes hook running inside subagents.
- Helper to crew-task matching is by task title (the board does not record
  agent ids): an Agent description that does not start with the task title or
  its short code (H1, S2) stays unmatched.
- Fullscreen inside Forge (shared forge_chrome.js, same as other apps).

## Open from the critique (not done)

- While sessions work the data changes nearly every poll, so refresh stays
  at the fastest setting (4 s, 10 s out of focus). Each changed answer is
  about 74 KB and the server runs the full read (about 20 ms) even for an
  unchanged answer. Next step: send only the open view's part, or an
  inotify-driven "changed" signal (item 2 below).
- On a 2560 px screen the session grid leaves empty columns when there are
  few sessions (auto-fill); a matter of taste, left as is.
- Acking a note that does not exist answers 400 (the Board's own error), not 404.

## Improve next (ranked)

1. Ask the crew skill to record the agent id or session id of a helper when
   it joins (`crew join ... --session`), so helper matching stops guessing.
2. Server-sent "something changed" (inotify on ~/.claude/sessions and the
   boards) instead of polling, if the backoff ever feels slow.
3. Per-session token history (sparkline) kept in memory between polls.
4. Drag a session onto a crew in the map to post it a note.
5. Unread counts in the Forge sidebar badge (needs a hub manifest field).

- 2026-10-08 (task 114): shortTitle/displayName/personaTag moved to
  `shared/forge_session_title.js`; `static/logic.js` re-exports them (same
  API, same tests). index.html loads the shared file before logic.js.
