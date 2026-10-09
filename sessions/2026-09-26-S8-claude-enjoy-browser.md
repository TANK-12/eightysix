# S8: Enjoy-style Claude app + Browser loading — session "Chat"

Split off from S7 (`2026-09-26-S7-forge-polish.md`, session ejb-47) on
2026-09-26 at Emerson's request: "split the tasks and give it to the new
claude terminal session". S7 keeps the hub (full screen, background start,
hide/archive apps, Settings, media popup, zen mode, polish). This brief is the
part that lives inside two apps and does not touch hub files.

Suggested model: Opus. The rules in `~/Forge/sessions/README.md` "Rules for
every session in this wave" apply (board, claims, no subagents, Jan is shared,
no Forge restart without asking, handoff). Join the board with slot S8:
`python3 ~/.claude/skills/crew/crew.py join forge <you> --role solo --slot S8`.
Emerson wants this polished enough to show his dad.

## Owns
- `apps/claude/` (the Claude app; read its `MANIFEST.md`, then the top and
  newest section of `WIP.md`, 523 lines, grep the headings first)
- `apps/browser/` (read `MANIFEST.md`, `WIP.md`, 35 lines)
- `forge_views.py` (the native web views the Browser app sits in) is hub-side
  and S7 may touch it for the full-screen fix: `crew claim` it per edit and
  post on the board before changing it.
- Pre-edit copies of `apps/browser/static` and its `*.py` are already in
  `~/Forge/backups/2026-09-26-forge-polish/`; back up `apps/claude/` yourself.

## Ledger
- **A15** "make a version of the claude app to work and act and look like"
  Enjoy. Emerson pasted the landing page of Enjoy, a desktop app for building
  software with coding agents. What it says it does:
  - "one person, infinite engineers": the team of one; you set the
    direction, the agents do the programming.
  - "Give each task its own conversation, with plans and progress together.
    See what's running and what needs you, so you can move several ideas
    forward without keeping every detail in your head."
  - "Keep ideas, plans, and customer insights together in notes and
    documents. Build a knowledge base you can return to, and save repeatable
    work as workflows."
  - "Describe the app you wish existed ... without learning the command
    line."
  - unlimited projects; phone/browser access (skip that part).
  Look: lowercase headings with a full stop ("enjoy.", "less juggling. more
  building."), calm and roomy, playful ↗ / ↓ / ∞ marks on links and buttons,
  short friendly copy, "+ more ↗" chips.
  -> a second layout of `apps/claude` in that style, on the same backend and
  runner, that he can switch to and back from (the current layout stays and
  keeps working). Minimum: projects list; a task list per project where each
  task is its own conversation showing its plan and progress beside the chat;
  a "running / needs you" view across tasks; notes and documents per project;
  saved workflows (a named prompt or step list you can run again).
  assumed (S7): a switchable version, not a replacement. [core]
- **A8** "make the browser load better, it's a bit finicky" -> find what is
  finicky about the Browser app loading (first open, page loads, the native
  view appearing late or in the wrong place, blank pages, tabs) by measuring
  and reproducing it, fix the worst, report before/after. Ask Emerson on the
  board for the exact symptom if you cannot reproduce one. [core]
- **A21** (2026-09-26, from S7) "i dont want the live 2d to be active by
  default" -> the Claude app's Live2D avatar stage (static/stage.js ->
  ForgeAvatar) stays off, and does not load pixi/Live2D at all, until he
  turns it on with a clear toggle; the choice is remembered. [core]
- **A24** (Emerson via S7, note 49) "make copy and paste images work in
  claude terminal and claude forge app" -> the Forge Claude app part: pasting
  (Ctrl+V / right-click Paste) or dropping an image into the chat box attaches
  it (thumbnail chip, removable) and Claude receives it as an image; copying
  an image out of a reply works too. (The terminal part is S7's.) [core]
- **A28** (Emerson via S7, note 56) "make a tab in the claude app to show
  like roadmaps interactive and tasks and looks cool with good ui and space
  themed or brainstorm themed" -> a tab in apps/claude reading
  ~/Forge/sessions/*.md (ledger items with [core]/[detail], the State
  lines) and the forge board notes; sessions (Hub/Chat/Tools...) as
  constellations, items as stars that light up when done, click for detail.
  Fits A15's "running / needs you" view. [core]
- **A29** (Emerson via S7, note 61) "the update went away because you sent
  another thing before I could read it, please fix that" -> every assistant
  text block stays in the transcript, never replaced by the next chunk or tool
  call; scroll stays put when scrolled up. [core]
- **A32** (Emerson via S7, note 68) "the claude usage bars in the app don't
  update till I actually start using them, I don't like that" -> real numbers
  as soon as the app opens, refreshed on a timer for every account, a visible
  last-updated time; on HTTP 429 back off and show the last good reading. [core]
- Constraints: nothing that works today removed; do the work yourself (no
  subagents); headless screenshots for anything visible; the real Forge
  window is not restarted without asking.

## State
- A8 done+checked off screen: old pages stayed alive and visible after closing, reopening or reloading the Browser (1 -> 2 -> 3 stacked views). Fixed in hub/index.html (dropViews, cleared with S7) and apps/browser/static/app.js; tests/browser/run.sh ALL PASS incl. new hub_views, tests/smoke_browser_reopen.py PASS, pytest 22 passed. Not seen in the real window yet (needs a Forge restart). Details in apps/browser/WIP.md.
- A21 done+checked (headless + tests): avatar off by default (prefs.avatar in personas.json, false), 🎭 toggle in the stage header and a "Turn on the avatar" button; while off no pixi/Live2D request is made (server log), voice and avatar chat keep working through a stand-in. Stage header no longer overflows. Not clicked in the Forge window.
- A24 done+checked (tests + headless), Forge-app part: paste reads files/items, and when WebKitGTK brings no file the backend reads the desktop clipboard (wl-paste) -> attachment; chips and sent messages show image thumbnails (GET /api/conversations/{id}/files/{name}, images only); tool-result images now show; every image has a Copy image button (wl-copy via POST /api/clipboard/image) plus WebKit's own right-click Copy Image. Not checked: a real Ctrl+V of a screenshot and the Copy button click in the Forge window (would touch Emerson's clipboard). Tests 76 passed.
- A29 done+checked (off-screen WebKit probe, before/after + live split stream; pytest 76): each reply block keeps its own slot, a tool call no longer wipes the update before it. Cause and check in apps/claude/WIP.md.
- A32 done+checked (pytest 90 incl. 2 new backoff tests; page probe shows "5h 97% · just now" under each account): a 429 keeps the last good numbers, records why ("check busy"), backs off (Retry-After, else doubling, max 15 min); the page re-reads 5 s after opening and shows each account's reading and its age. Not seen in the Forge window.
- A15 + A28 done + checked (Finisher S10, 2026-09-26; details in apps/claude/WIP.md): the Enjoy layout (projects, tasks with plan and progress beside the chat, running / needs you, notes, workflows) and the roadmap tab (constellations from the briefs, star cards, board notes), switchable both ways and remembered. Checks: pytest 108 passed incl. test_roadmap 17 and node tests 9; every view probed in off-screen WebKit on a scratch copy; screenshots looked at. Not seen in the real Forge window yet (needs the Claude app reopened / Forge restart).
  1. [done+checked] backend: projects.py, note_turn, seen, project/notes/workflow routes (tests/test_projects.py 12).
  2. [done+checked] roadmap.py + GET /api/roadmap (tests/test_roadmap.py 17).
  3. [done+checked] static/enjoy.html + enjoy.css + enjoy.js + enjoy_logic.js; shared claude_common.js (classic re-checked after the move).
  4. [done+checked] switch: "enjoy ↗" / "classic layout ↗", localStorage claude.layout, index.html redirect.
  5. [done+checked] checks and docs (WIP.md top section, MANIFEST.md Layouts row).
