# S1: sessions, the Board, and the Claude app

Part of the 2026-09-25 wave; read `~/Forge/sessions/README.md` first.
Suggested model: Opus, medium effort.

**Do the Board items first.** The other four sessions talk through the board,
so it has to work before anything else here.

## Owns
- `apps/board/`, `~/.claude/skills/crew/` (crew.py, SKILL.md, tests)
- `apps/claude/` (whole app, including `runner.py`)
- `~/Forge/sessions/README.md` (the index; others edit only their own brief)
- Claude Code settings changes for a notes hook (`update-config` skill)

## Ledger (Emerson's words, then what it means)

- **A33** "you chat with each other in the notes board also make that work"
  and **A38** "fix the message board notes thing" -> find what is broken in
  Board notes today (ask Emerson on the board what he saw if it is not
  obvious: posting, showing, answering, the page not updating?). Fix it with
  a test. [core]
- **A34** "cleanly and fast chat to all of you at once or send out a message
  and have a separate tab where all you talk and coordinate" -> in the Board
  app: [core]
  - a **To everyone** box at the top: one line, Enter sends to every
    session on the board (no `--to`);
  - a **Crew talk** tab: session-to-session notes, read-only for skimming;
  - a **Me** tab: notes addressed to Emerson or answers to his notes;
  - optional per-session filter (chips with each session's name and its
    brief slot, S1..S5);
  - the page refreshes on its own (poll every few seconds or server-sent
    events).
- **A34b** notes reach a busy session without it polling -> a small
  Claude Code hook (for example on `PostToolUse` or `UserPromptSubmit`) that
  runs `crew notes forge --for <session> --unread` and prints only new notes
  addressed to that session or to everyone, and prints nothing otherwise.
  It must be quick (under ~100 ms) and never block. This is an information
  hook, not a guardrail hook (those were declined; this is different). Test
  it in this session, then post on the board telling the other four how to
  pick it up (a restart of their session may be needed; say so). [core]
- **A29** "all claude sessions more structured with the manifests and
  handoff so even I can find them" -> make `~/Forge/sessions/` the standard:
  add the rule to the `forge-session` skill (every session writes
  `sessions/<date>-<slot>-<topic>.md` with a State section), link the
  folder from `~/Forge/README.md`, and show each session's brief and state
  line on the Board page (a "Sessions" tab). [core]
- **A2** "claude app keep working on polish; I want to be able to put
  messages mid-stream just like in terminal" -> the mid-turn send is built
  and tested but not live (`apps/claude/WIP.md`, "Handoff 2026-09-25
  (ejb-79)"). Make it live: restarting the Claude app's backend cuts running
  panel chats (their history is kept and they resume by session id). Post on
  the board and wait a couple of minutes before restarting, and never
  restart while Emerson is mid-conversation in the panel. Then handle the
  known edge (a message landing just as the turn ends starting a second
  turn) and check it with a headless screenshot. [core]
- **A23** "I can't switch avatar in the claude app; I can see them and the
  motion in the avatar editor and chooser but the original options don't
  change no matter what" -> picking an avatar in the chooser does not change
  the avatar actually shown in the panel. Find where the choice is stored
  and where the panel reads it; fix; test the round trip. [core]
- **A37** "the bars for usage to update every now and then, it's just
  stuck" -> the usage bars in the Claude app must refresh on a timer (every
  minute or two, and after each finished turn), and show when they were
  last updated. Find why they freeze (cached once at start?). [core]
- **A40** "do something about that error message that never goes away":
  the Claude app shows "The Forge Browser is not running, so Claude's
  browser tools will report that until it is opened."
  (`apps/claude/static/app.js:1041`) the whole time the browser is closed.
  That's normal, not an error. Options: start the Forge Browser on its own
  when Claude first uses a browser tool, or show it once as a quiet,
  dismissible hint (remember the dismissal), or show it only when a
  browser tool actually failed. Pick the least noisy option that still
  tells him why a browser tool failed. [core]
- **A39** Forge Claude app sessions lack the Acchan MCP tools (found
  2026-09-25): `runner.py::mcp_config()` writes only `forge-browser` into
  `~/.local/share/forge/claude/mcp.json`. Also merge the user-level
  `mcpServers` so `blender_*`, `godot_*`, `assets_*` tools exist there. S4
  needs this; tell S4 on the board when done. [detail]
- General polish of the Claude app as time allows: take the top of "Improve
  next (ranked)" in `apps/claude/WIP.md`. [detail]

## Order
1. A38 board fix -> 2. A34 tabs and To everyone -> 3. A34b notes hook ->
4. A29 sessions standard -> 5. A37 usage bars -> 6. A23 avatars ->
7. A40 browser banner -> 8. A39 MCP tools -> 9. A2 go live + edge -> 10. polish.

## Checks
pytest for board, crew.py (`test_crew.py`) and the Claude app; black and
pyright on touched files; headless screenshots of the Board page (1400px and
390px) and the Claude panel.

## State
Session: "Unfinished jobs list" (slot S1). Updated 2026-09-25, all S1 items done.

- A38 board fix: done, checked (broadcasts closed for all on the first ack; now per session. crew tests 16, hook tests 3, board tests 8)
- A34 tabs + To everyone box: done, checked (headless screenshots at 1400 and 390; running in Forge's Board now)
- A34b notes reach sessions by themselves: done, checked (hook live; S2, S4, S5 received notes and replied through it)
- A29 sessions standard: done (forge-session skill rule, Forge README link, Board Sessions tab)
- A37 usage bars follow the real account: done, checked (3 tests; saw 61% live on a scratch copy). Live when the Claude app is next opened
- A23 avatars switch: done, checked by screenshot (Look dropdown on the chat stage, Use this avatar in the Studio). Not clicked in Forge
- A40 Forge Browser banner: done, tested (banner gone; Browser opens itself when Claude needs it). Not checked in Forge
- A39 Acchan tools in every Claude app account: done, tested; S4 told
- A2 send mid-turn: done, tested (edge case fixed: a message landing as the turn ends keeps Stop and the status up; 66 tests). Live when the Claude app is next opened
- Emerson said to ignore the usage pacing (relayed to all as note 32)
- Next: Claude app polish from apps/claude/WIP.md "Improve next"
