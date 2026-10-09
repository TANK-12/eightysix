# Board: current state (2026-09-27, S17 pass by ejb-94)


## Attach files and pictures to a note (2026-10-08, Koharu, Relay task 118)

The send box has a paperclip, paste and drop. Files go to `POST /api/attach`
(base64 JSON) or `/api/attach/paste-image` (desktop clipboard), both from
`shared/forge_attach_api.py`, saved under
`~/.local/share/forge/board/attachments/YYYY-MM-DD/`; `/api/post` takes
`files` (only paths inside that folder) and appends an `Attached files:` list
to the note. Verified: `tests/test_attach.py` new, board suite 22 pass,
pyright 0; headless Chrome drop + paste made two chips (screenshot looked at).
Not verified: a real post with a file to the live board. Note: Board has no
same-site (Origin) check on any POST, attach included; same as before.
Second critic (session 3) fixed: a send while a file is still uploading
now waits (`ForgeAttach.wire(...).busy()`, "A file is still uploading")
and a file that lands during a send stays for the next message instead of
being wiped; copied text that also carries a picture pastes as text; a
failed desktop paste says why; a file over 50 MB is refused before the page
reads it; the same path twice is named once. Tests: `shared/forge_attach.test.js` 6 pass.

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

## Go to it for a session in no window (2026-10-08, Izumi/ejb-ac)

`POST /api/session/{name}/go` now adds `"nowhere": true` when the session is
in no terminal and no Claude-app tab (Relay runs its sessions headless), so a
caller can show the chat itself. Mission Control does. Verified: board tests
20 pass (`test_go_opens_a_claude_app_session_when_it_has_no_terminal` checks
the flag); live call on relay-113-work returns it.

## U1 sweep (2026-10-08, Relay task 74)

Done by the G2 worker (Relay task 76) on top of edits left by stopped workers.
- **Server down:** a failed refresh returns false, so `ForgeIdle.poll` backs
  off 3 s -> 6 -> 12 -> 24 -> 30 s instead of knocking every 3 s; the live dot
  says "offline, retrying", a never-loaded page shows a calm "not answering"
  card with a Try now button, and the first answer brings it all back.
- **Robustness:** `post` and `ack` pass options as `--opt=value` and the
  names and text after `--`, so a note, name or answer starting with a dash
  ("--help", "-x") is kept as typed instead of crashing crew.py's argparse
  (500). Send and Done / Close / Go ignore a second click or Enter while the
  first is on its way. Send errors read as a sentence, not "Failed to fetch".
- **Looks:** loading text instead of an empty pane, newly arrived notes slide
  in once (220 ms, opacity/transform), a "New notes below" chip when notes
  arrive while you read further up, thin themed scrollbars (incl.
  `::-webkit-scrollbar` for WebKitGTK), the needs-you pulse is now an
  opacity-only ring (no box-shadow repaint each frame); reduced motion honoured.
- **Critic follow-up:** notes are capped at 20 000 characters, recipient
  names at 80 and answers at 4 000 (422 beyond; a 200 kB name used to push
  the whole page off screen and every note is re-sent each 3 s); long names
  in the filter chips end in "…" and meta lines wrap. Kept on purpose: on a
  first visit (nothing in `board.seen`) no note gets the "unseen" ring, so a
  new browser profile is not a wall of 150 rings; later visits ring as before.
  Checked in headless Chrome with a 200 kB name: page stays 760 / 1100 px
  wide, the "New notes below" chip sits in view (`shots/board-longname-*`).
- **Verified:** pytest 19 passed (2 new: dash-led notes/names/answers, size caps);
  black + pyright 0 errors on web_app.py and tests/test_board.py; headless
  Chrome on scratch port 8920 with a temp `CREW_HOME`
  (`/tmp/u1/G2/check/g2check.py`): 0 fetches/timers in 10 s while hidden
  (hub signal and document hidden; the slow tick for desktop alerts is one
  refresh every 15 s, also while the backend is down), one refresh on
  coming back; server
  killed: 2 fetches in 0-10 s, 1 in 10-30 s; restarted: back to "live" by
  itself in 13.5 s; triple submit posted 1 note; no page errors. Screenshots
  at 760/1100/1500/1920 looked at (`/tmp/u1/G2/shots/board-final-*`).
- **Not verified:** inside Emerson's real Forge window. The static changes
  arrive on the next Board reload; the `web_app.py` change only after his
  next Forge restart.

## Jump to Claude-app sessions (2026-09-27, ejb-34, #227)

"Go to it" used to say "not in a terminal Forge can switch" for sessions
running in the Claude app. Now, when no terminal tab is found, the Board asks
the Claude app (found by `"role": "claude"` in its forge_app.json, never by
name) to open that session's conversation and asks Forge to show the app
(shared/forge_open.py). Session cards show the conversation's human name and
topic (GET /api/sessions on the Claude app, cached 10 s, nothing while it is
closed). Verified: tests 15 passed (3 new), pyright 0; the Claude side was
checked live in headless Chrome. Not verified: a click in the real Board
inside Forge (needs a Forge restart to load both backends).

## S17 pass (B32: "much better, don't lose functionality")
Added, nothing removed:
- **FYI notes.** A tick under the send box posts an FYI note (`crew post --fyi`),
  which gets an FYI label and never counts as waiting on anyone. It has no Done
  button, isn't counted in the Me badge, and sessions drop it once delivered.
- **Group replies** (on by default, a toggle): each answer sits under the
  first note of its chain, and the chain moves to where its newest note is. The
  last three answers show, and "Show N earlier answers" opens the rest. Off
  gives the old flat list.
- **Search** over note text, names and `#number`.
- **Desktop alerts** (on by default, a toggle): a note to Emerson, or an
  answer to one of his, that arrives while the Board is out of sight (another
  tab, another app, or Forge unfocused) becomes a `notify-send` notification
  through `POST /api/notify`. The first load of a board only sets the baseline.
- **Its own Full screen button** in the header, so run standalone the floating
  Close/Full screen pair no longer covers Send. Inside Forge the hub's bar
  already carries them.

Verified 2026-09-27: `pytest tests` 12 passed (2 new: fyi post, notify).
`tests/check_ui.py` (headless Chrome, throwaway board, fake notify-send) 6/6
PASS: grouping, show-earlier, FYI label and badge, search, FYI tick, and one
alert out of sight with no replay of old notes. Screenshots at 1400px and
390px looked at. black and pyright clean. Not verified: a real notification on
Emerson's desktop inside the running Forge (the Board needs a Forge restart or
reopening to load the new page and backend).

# Earlier: 2026-09-25, S1 session "Unfinished jobs list"

Rebuilt for the 2026-09-25 wave of five sessions (brief:
`~/Forge/sessions/2026-09-25-S1-sessions-board-claude-app.md`). See README.md
for what the page does.

## What was broken, and the fix
- A note to everyone had one shared "answered" flag, so the first session to
  ack it closed it for every other session: broadcasts reached one session.
  Now each session is tracked on its own (`done_by`, `delivered`); a direct
  note still closes when its addressee acks; the author or `--close` ends it
  for all.
- Sessions only saw notes when they remembered to run `crew notes`. Now the
  notes hook hands them over on the next tool call.
- The page opened on the `jan` board and the Jan panel read claims from
  whichever board was open. It now opens on `forge` (remembered per browser)
  and always reads Jan claims from `jan`.
- Answering used a browser `prompt()`; now Reply uses the send box, and the
  3-second refresh never wipes what is being typed.

## Verified (2026-09-25)
- `pytest tests`: 8 passed (3 new: forge default, Emerson answering without
  closing for others, Sessions list with slot + brief State, dead sessions
  left out).
- crew.py `test_crew.py`: 16 passed (7 new: per-session broadcast, close,
  reply to author, --re, slot addressing, inbox once, inbox writes nothing when
  empty). `test_notes_hook.py`: 3 passed.
- black and pyright: clean on web_app.py, tests, crew.py, notes_hook.py.
- The hook live: registered in `~/.claude/settings.json`; it delivered notes to
  this session and to S4/S5 within their next tool call (S5 replied through it).
  Runs in about 21 ms.
- Headless screenshots at 1400px and 390px of Everyone and Sessions against
  the live `forge` board; Forge's own Board backend (restarted by Emerson
  opening it) serves the new API.

## Not verified
- Clicking Reply / Done / Close for all inside the Forge window (the API
  behind each is tested).
- Whether a session that is idle (not running tools) notices a note: the hook
  fires on its next tool call or prompt only. An idle session needs Emerson to
  press Enter or type in it.

## Improve next
1. A Forge sidebar badge for notes waiting on Emerson (the desktop alert is
   done; the badge would need a hub hook).
2. Wake an idle session when a note arrives for it (the hook can't; Claude
   Code's cross-session messaging might).
3. Mark a whole thread done in one click.

## B27 persona names (ejb-55, 2026-09-27)
Every session on a crew board now has a persona name as well as its id,
drawn from the one list in `apps/claude/names.py` (the same list the Claude
app's tabs use). `~/.claude/skills/crew/crew.py` (outside git) picks it
once, on the member's first touch, skipping names held by members seen in
the last 24 h, and keeps it. A session the Claude app started takes its tab
name instead (the notes hook asks the Claude app once, at auto-join, 0.5 s
wait). The hook's header now reads "Crew board 'forge' (you are Hina
(ejb-55)):", note lines read "#12 Hina (ejb-55) -> everyone", and `crew
status` lists "ejb-55 (Hina, solo)". The Board page's chips, labels,
avatars' initials and desktop alerts use it, and the Sessions tab falls back
to it when the Claude app has no tab for that session.
Verified: crew tests 22 OK, notes hook 7 OK, board pytest 16 pass,
tests/check_ui.py 7/7 PASS (a new check that the page shows "<persona>
(ejb-55)"). Not seen: the live Board shows it after a Forge restart; live
sessions pick their names on their next crew call.

## 2026-09-30: names match the tabs, 5-minute rule, launched agents

Emerson: "names in Forge Claude don't match what you see", "assume sessions
not active for the past 5 minutes aren't active", and "when they launch an
agent I want to see it".

- Names. The picked persona used to stick forever, so ejb-83 read "Sora" on
  the Board while its Claude-app tab said "Nagi", and a session that joined
  as "Kenji" read "Nao (Kenji)". Now (`~/.claude/skills/crew/crew.py`,
  outside git): a Claude-app tab name always replaces the stored persona;
  a member already called by a name from `names.py` keeps it and shows bare
  ("Kenji"); a new session id under a reused ejb-XX name drops the old
  pick (the member remembers its `session`). The notes hook refreshes the
  persona when a tab is renamed. The Board's `/api/board/<crew>` also
  overwrites each live session's persona with its tab name before sending,
  so notes and chips match the tabs even before the session runs a hook.
- Active. `web_app.ACTIVE_SECONDS = 300`: last activity is the newest of the
  session file's startedAt/updatedAt, its transcript's mtime and its agents'
  transcripts. Older than that: `active: false` and a "busy" status shows as
  "idle"; the card says "quiet since Xm ago". Crew Room's
  `sources/sessions.py` uses the same rule for `busy`.
- Agents. Each session card lists the agents (Claude Code subagents) from
  `projects/*/<session>/subagents/*.meta.json`: description, type, model,
  started, "running" when written in the last 5 minutes, else "finished";
  finished ones drop off after an hour. The Sessions tab badge counts
  running agents ("1 agent").

Verified: board pytest 17 pass, `tests/check_ui.py` 8/8 PASS (new check: the
card shows "active" and the agent, badge "1 agent"; screenshot looked at),
crewroom pytest 35 pass, crew tests 26 OK, black + pyright clean.
Not seen live: the Board and Crew Room backends run inside Forge, so they
need a Forge restart; the crew-tool name fix is live now.

## 2026-10-08 (Daichi, Relay task 94): one naming rule with Crew Room and Relay

`live_sessions` no longer has its own "tab name, else this board's persona"
rule: it calls `shared/forge_session_names.labels`, passing the Claude app
answer it already fetched (`app_names=`, new on `labels`, so the app is asked
once). So a session named on any crew board (a Relay session that joined
`forge` as Mika) shows that name on every board, the same as Crew Room and
Relay's page. The member's own persona stays the fallback. The 2026-09-30
work above (agents, 5-minute rule) was still uncommitted; it is committed now.

**Verified:** board pytest 20 pass (new
`test_a_session_named_on_another_board_shows_that_name`),
`tests/check_ui.py` 8/8 PASS (screenshot looked at; `websockets` installed in
the board venv for it), crewroom pytest 37 pass, black, pyright 0. A copy on a
spare port over the real boards listed relay-94-work as Daichi and
relay-95-work as Takumi. Critic (opus) found a malformed board.json could
crash every page using the shared namer; `board_names` now skips bad members
(tested), and the test fixture no longer reads real sessions or the real
Claude app. **Not live yet:** needs a Forge restart.
