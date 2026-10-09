# Plan: Crew Room

> **Built 2026-09-16** in `~/Forge/apps/crewroom` (port 8447). Current state,
> what was verified and what to improve next: `apps/crewroom/WIP.md`. This
> plan is kept as the design record. Two deliberate differences from it: the
> port is 8447 (Cosmos took 8446), and the Jan source reads router child
> processes, because Jan runs llama-server as a router without `--alias`.

A new Forge app that shows, as a living anime pixel-art room, the Claude
sessions and crew helpers at work and the Jan models running. Asked for by
Emerson on 2026-09-16; designed in that session and meant to be **built in a
fresh session, solo** (his choice). Start that session with: *"build the crew
room from ~/Forge/apps/crewroom/docs/PLAN-crew-room.md"*.

## His words

> "it would be cool to have an app in forge, maybe a tab, that shows like a
> cool spaceship or beach or office or relaxed room, all anime style or retro,
> of people working and talking together and coordination or stuff, and a
> representation of the jan models"

Later in the same conversation: "have all the claude things in the background
and not all running the same model or effort".

## Decisions (asked 2026-09-16, answered verbatim)

| Question | Answer |
|---|---|
| Rooms (switchable) | Spaceship bridge, Beach, Office, Relaxed room |
| Art style | Anime pixel art, editable in PixelForge |
| What characters show | Claude sessions working; crew teamwork; Jan models; click for details |
| How to build | Fresh session, solo |

## What it shows

- **Each Claude session is a character.** It types at a station when `busy`
  and relaxes when idle. A speech bubble shows its current action in plain
  words ("running tests", "editing web_app.py"). A name tag shows its name,
  its **model** and, where known, its effort.
- **Crew helpers** are smaller characters beside their commander, colour-coded
  by type: `crew-light` (Haiku), `crew-worker` (Sonnet, medium) and `crew-deep`
  (Opus, high). A helper walks to the commander to report, the room's board
  (whiteboard, bridge display, beach sign or lounge corkboard) lists crew tasks
  and their status, and a claimed file appears as an item on the owner's desk.
- **Jan models are characters too.** One per loaded model, glowing and busier
  as its CPU use rises, leaving when it is unloaded.
- **Click any character** for a details panel: task, claimed files, recent
  actions, token use (average context and output for the session).
- The room choice and a simple/advanced settings split, fullscreen (`forge`
  chrome postMessage plus F11) and a reduced-motion toggle follow the usual Forge
  expectations.

## Data sources (all local and read-only, checked 2026-09-16)

| What | Where | Fields |
|---|---|---|
| Live Claude sessions | `~/.claude/sessions/<pid>.json` | `name`, `status` (busy/idle), `cwd`, `sessionId`, `kind`, `updatedAt`; `pid` confirms it is alive |
| What a session is doing, its model and tokens | `~/.claude/projects/*/<sessionId>.jsonl`, tail only | latest `tool_use` name and input; `message.model`; `message.usage` |
| Background helpers | `~/.claude/projects/*/<sessionId>/subagents/*.jsonl` | same fields; the file name gives the agent id |
| Helper types | `~/.claude/agents/crew-*.md` frontmatter | `model`, `effort` |
| Crew teamwork | `~/.claude/crew/*/board.json` | members, tasks, claims, log |
| Jan models | `pgrep -a -x llama-server` args (`--alias`), `/proc/<pid>/stat` for CPU | alias, CPU share |

Rules: read transcripts from the end (seek to the last ~64 KB), never whole.
Never restart or query-load Jan; reading process info only. Show tool names and
file names, not message bodies, in bubbles; the details panel may show the last
few user-visible actions. Check whether effort is recorded anywhere per session
before displaying it; if not, show it only for crew helpers from their type.

## Shape

- `~/Forge/apps/crewroom/` with `forge_app.json`, `.venv`, FastAPI
  `web_app.py`, `static/`. Port: the next free one after the highest in
  `apps/*/forge_app.json` (8446 on 2026-09-16).
- `crewroom/sources/`: one module per data source, discovered by a registry,
  each returning plain dicts. `GET /api/room` merges them; the page polls it
  every 2 s.
- **Rooms and sprites are data**, not code. Rooms are
  `~/ForgeArtData/packs/crewroom/rooms/<room>.json`: tile layout, stations,
  board position and walk paths. Characters are palette-indexed sprites in the
  same pack format PixelForge already edits (read `apps/pixelforge/README.md`
  first). Adding a room means one JSON file.
- Canvas renderer with integer scaling, so the pixel art stays crisp and runs
  lightly on the Iris Xe.

## Build chunks (about 150 tool calls each, per the lean skill)

1. **Data backend**: source modules, `/api/room`, unit tests over fixture
   session, transcript, board and process files, and a live check against the
   real `~/.claude`.
2. **Renderer and the Office**: sprite and room loading, character state
   animation (typing, idle, walking, talking), speech bubbles, details panel,
   and a headless screenshot.
3. **Spaceship, Beach and Relaxed room**, crew animations (walk to report,
   board tasks, desk items) and Jan characters. Screenshot every room, then
   write `MANIFEST.md`, `WIP.md` and a ranked improvement list.

Done when all four rooms render live data and pass the app's tests, each room
has a screenshot that has been looked at, and the handoff docs exist.
