# Crew Room manifest

Start here in a fresh session. `README.md` explains the formats; `WIP.md`
holds the current state and the ranked list of what to improve next.

## What it is

A Forge app (port 8447, `apps/crewroom`) that draws the Claude sessions,
crew helpers and Jan models running on this laptop as characters in a
switchable anime pixel-art room: Office, Spaceship bridge, Beach, Relaxed room.
Asked for by Emerson on 2026-09-16, designed in one session
(`~/Forge/apps/crewroom/docs/PLAN-crew-room.md`) and built in the next.

## His words and decisions

> "it would be cool to have an app in forge, maybe a tab, that shows like a
> cool spaceship or beach or office or relaxed room, all anime style or retro,
> of people working and talking together and coordination or stuff, and a
> representation of the jan models"

> "have all the claude things in the background and not all running the same
> model or effort"

| Question (2026-09-16) | Answer |
|---|---|
| Rooms | Spaceship bridge, Beach, Office, Relaxed room |
| Art style | Anime pixel art, editable in PixelForge |
| What characters show | Claude sessions working; crew teamwork; Jan models; click for details |
| How to build | Fresh session, solo |

Build instruction: "go do that, dont ask questions ill fix it all after i
wake up". No questions were asked during the build.

### Part 2 (2026-09-16, `~/Forge/apps/crewroom/docs/PLAN-crew-room-2.md`)

> "it runs fine woudl liek to be able to intecat with them through there and
> start new claude seesion"

| Question | Answer |
|---|---|
| Clicking a character should let you... | "Jump to its terminal, whaever seemas smart" |
| New session: terminal, background, or both | "Both" |
| GNOME cannot raise one terminal tab, so instead | "Full conversation + where (Recommended)" |
| Background task permission mode | "Always auto mode" (a second session reports he told it "Always bypass"; see WIP.md) |
| Usage reminder line in the form | "Yes, one quiet line (Recommended)" |

Mid-build: "no more questions". Messaging, interrupting and stopping running
sessions were left out on purpose.

## Map

| Piece | File |
|---|---|
| API and static serving | `web_app.py` |
| Data sources (discovered) | `sources/sessions.py`, `helpers.py`, `crew.py`, `jan.py` |
| Transcript tail and head, plain-words actions | `transcripts.py` |
| Full conversation, paged backwards | `conversation.py` |
| Where a session runs, resume command | `where.py` |
| Starting terminal sessions and background tasks (the only writer) | `launch.py` |
| Paths and /proc parsing | `context.py` |
| Rooms and art seeding | `art.py`, `seed/` |
| Default art generator | `tools/make_art.py` |
| Renderer, characters, overlay, panels | `static/app.js` |
| Sample crew | `static/demo.js` |
| Tests | `tests/` (pytest, fixture trees) |

Live art: `~/ForgeArtData/packs/crewroom-{characters,props,tiles}.json`,
`~/ForgeArtData/palettes/crewroom.json`,
`~/ForgeArtData/packs/crewroom/rooms/*.json`.

## Rules this app keeps

- Reading is read-only. Nothing is written to `~/.claude`; Jan is never
  contacted. Launching (`launch.py`) is the only thing that starts processes
  or writes files, only into its own data folder, and only for posts from the
  Crew Room's own page.
- Transcripts are read from the end: a tail, or backwards pages. Never whole.
- No messaging, interrupting or stopping of sessions.
- Rooms, sprites and data sources are each one new file, never a list edit.
- Seeding never overwrites an existing art or room file.
