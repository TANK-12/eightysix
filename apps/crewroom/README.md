# Crew Room

A Forge app that shows what is working on this laptop as a living anime
pixel-art room. Port 8447.

- Every live **Claude Code session** is a character. It types at a station
  while busy and relaxes in the lounge corner while idle. A speech bubble says
  what it is doing in plain words ("editing app.js", "run the tests"), and its
  name tag shows its model and effort.
- **Background helpers** (subagents) are smaller characters beside their
  commander's station, colour-coded by type: mint `crew-light` (Haiku), amber
  `crew-worker` (Sonnet), violet `crew-deep` (Opus), grey for any other agent
  type. A finished helper walks over to its commander to report.
- **Crew boards** from the crew skill fill the room's board (whiteboard,
  bridge display, beach sign, corkboard) with tasks and status. A file claimed
  on the board appears as a paper on the owner's desk.
- **Jan models** are glowing spirits, one per loaded model. They glow brighter
  and bob faster as their CPU use rises, and leave when the model unloads.
- **Click** any character (or its name tag) for details: task, claimed files,
  recent actions, token use.

Rooms: Office, Spaceship bridge, Beach, Relaxed room.

## Reading is read-only; launching is the one thing that writes

Everything the room shows is read, never changed:

| What | Read from |
|---|---|
| Live sessions | `~/.claude/sessions/<pid>.json`; the pid must be alive with the same start time |
| Model, effort, actions, tokens | the last 64 KB of `~/.claude/projects/*/<sessionId>.jsonl` (1 MB once if that tail has no model) |
| Full conversation | the same transcript, paged backwards about 256 KB at a time; the whole file is never loaded |
| Where it runs | the session file, `/proc/<pid>/fd/0` (terminal device) and the parent processes (terminal program) |
| Helpers | `~/.claude/projects/*/<sessionId>/subagents/agent-*.jsonl` and `.meta.json`, written within 10 minutes |
| Helper model and effort | `~/.claude/agents/<type>.md` frontmatter, else the helper's transcript |
| Crew teamwork | `~/.claude/crew/*/board.json` |
| Jan models | `/proc` only: `llama-server` processes that are not the router (`--models-preset`) |

The app never talks to Jan's port, so it cannot load, unload or restart a
model. Bubbles show tool names and file base names, never message text; only
the details panel shows a conversation.

The **only** thing that writes or starts anything is the **New session** panel
(`launch.py`, `POST /api/launch/terminal` and `POST /api/launch/task`). Those
posts are refused when they come from any page other than the Crew Room's own
(the `Origin` header is checked). There is no way to message, interrupt or stop
a running session from here, on purpose.

## Starting sessions

- **In a terminal:** runs `gnome-terminal --working-directory=<folder> --
  claude`. The new session writes its own session file, so its character walks
  in by itself. In a folder Claude Code has not seen before, it waits on the
  folder-trust question first, and the character appears only after you answer
  it. Other terminals are one line in `launch.TERMINALS`.
- **In the background:** runs `claude -p --output-format stream-json --verbose
  --permission-mode auto --session-id <new id> [--model m]` in the folder, with
  the prompt on stdin (so a prompt starting with `-` is never read as a flag).
  It always uses auto mode, which Emerson chose; that is `launch.MODE`. A
  headless run writes a session file with `entrypoint: "sdk-cli"`, so it shows
  as a character with a "background" tag while it runs. Each task keeps
  `task.json`, `pid`, `output.jsonl` and `stderr.log` in
  `~/.local/share/forge/crewroom/tasks/<session id>/` (`CREWROOM_DATA_DIR`
  overrides). Tasks keep running if the Crew Room or Forge closes.
  The task box takes files and pictures (Attach files, paste, or drop on the
  box; Relay task 118): saved in `<data dir>/attachments/YYYY-MM-DD/` and
  added to the prompt as `Attached files:` and one path per line. `/api/attach`
  has the same Origin check as the launch routes.
- The details panel of any session has **Where** (folder, terminal device and
  program, name, start time, process) and **Read the conversation**. An ended
  session keeps its panel and gets a copyable `cd <folder> && claude --resume
  <id>` command. GNOME cannot raise one terminal tab from another app, so
  "Where" replaces "jump to its terminal".

## Layout

```
web_app.py          FastAPI: /api/room, /api/rooms, /api/rooms/{id}, /api/art/library,
                    /api/sessions/{id}/conversation?before=, /api/sessions/{id}/where,
                    /api/launch/options, POST /api/launch/terminal, POST /api/launch/task, /api/tasks
context.py          where to read from (CREWROOM_CLAUDE_DIR, CREWROOM_PROC_DIR override), /proc readers
transcripts.py      tail and head readers and "what is it doing" in plain words
conversation.py     backwards pager and conversation items in plain words
where.py            terminal device, terminal program, resume command
launch.py           the only writer: terminal sessions and background tasks
sources/            one module per data source, discovered (see below)
art.py              rooms and sprites in ~/ForgeArtData, seeded from seed/
seed/               default palette, sprite packs and room files
tools/make_art.py   generates the default sprites into seed/
static/             index.html, room.css, app.js (renderer), demo.js (sample crew)
tests/              pytest over fixture ~/.claude and /proc trees
```

### Adding a data source

Drop a module in `sources/` with `NAME` (its key in `/api/room`), optional
`ORDER` (lower runs first) and `collect(ctx)`. Set `WANTS_ROOM = True` to get
`collect(ctx, room)` with the results gathered so far. A source that raises is
reported under `errors` and the rest of the room still loads.

### Adding a room

One JSON file in `~/ForgeArtData/packs/crewroom/rooms/<id>.json` (copy one of
the four). Fields, all positions in tiles (16 px), decimals allowed:

| Field | Meaning |
|---|---|
| `id`, `label`, `order` | tab name and position |
| `palette`, `background` | palette id; colour behind everything |
| `legend` | tile character -> `{sprite, solid}` |
| `tiles` | rows of legend characters |
| `props` | `{sprite, x, y}` top-left; `solid` blocks walking over the lower half, `block: [x, y, w, h]` blocks exact tiles, `layer: "back"` always draws behind characters (couches, towels) |
| `board` | `{sprite, x, y, text: [x, y, w, h] in sprite pixels, ink}` |
| `stations` | desks: `{sprite, x, y}`; a character sits at `x + seat.dx, y + seat.dy` unless the station has its own `seat` |
| `helper_offsets` | where helpers stand around a station seat |
| `lounge` | `{x, y, pose}` feet points for idle sessions; `pose` is `relax` or `idle` |
| `jan` | `{prop, spots}`: the Jan prop and the spirits' feet points |
| `door` | where characters arrive and leave |
| `ambient` | optional `{type: "stars" or "motes", rect: [x, y, w, h] in pixels}` |

Missing files are copied from `seed/` at startup; files that already exist are
never overwritten, so edits survive. To go back to a default, delete the file
and restart the app.

### Editing the art

Sprites are the `crewroom-characters`, `crewroom-props` and `crewroom-tiles`
packs with the `crewroom` palette, editable in PixelForge. Characters are
named `person<1-8>_<pose>`, `helper_<light|worker|deep|other>_<a|b|c>_<pose>`
and `jan_<a|b|c>_<idle|busy>`. `tools/make_art.py` only makes the first draft
into `seed/`; it does not touch `~/ForgeArtData`.

## Settings

Simple: room, reduced motion (also follows the system setting), name tags, a
sample crew and Jan model for seeing every kind of character. Advanced: poll
interval, pixel scale, speech bubbles, palette, helper name tags. Links can
open things directly: `?room=beach`, `?demo`, `?panel=settings`,
`?panel=launch`, `?select=s:<sessionId>` (works after the session has ended)
and `?select=s:<sessionId>&conversation`.

## Run and test

```bash
cd ~/Forge/apps/crewroom
FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8447
.venv/bin/python -m pytest -q tests
```
