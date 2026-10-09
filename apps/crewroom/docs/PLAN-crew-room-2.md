# Plan: Crew Room, part 2 (start sessions, read conversations)

Build in a **fresh session**, first of three (then `~/Forge/docs/plans/PLAN-pixel-games-tab.md`,
then `~/Forge/apps/janhollow/docs/PLAN-jan-world.md`). Start with: *"build ~/Forge/apps/crewroom/docs/PLAN-crew-room-2.md"*.
Read `apps/crewroom/MANIFEST.md`, `README.md` and `WIP.md` first.

## His words (2026-09-16, after using the finished Crew Room)

> "it runs fine woudl liek to be able to intecat with them through there and
> start new claude seesion"

## Questions asked, answers verbatim

| Question | Options offered | Answer |
|---|---|---|
| Clicking a Claude character should let you... | Send it a message / Jump to its terminal / Interrupt or stop it / Read its full conversation | "Jump to its terminal, whaever seemas smart" |
| Starting a new Claude session should... | Open a terminal / Background task / Both | "Both" |
| On GNOME an app can't raise a specific terminal window. 'Jump to its terminal' becomes... | Full conversation + where / Install a GNOME extension / Skip it | "Full conversation + where (Recommended)" |
| Order of the three pieces | Crew Room first / Jan world first / Games tab, world, Crew Room | "Crew Room first (Recommended)" |

Not chosen, on purpose: sending messages into a running session (the peer
messaging socket is undocumented), interrupt/stop (a misclick cuts off work),
the GNOME extension (install needs review, and it still cannot pick a tab).

## Asked at the start of the build (2026-09-16, session ejb-34), answers verbatim

| Question | Answer |
|---|---|
| Permission mode for background tasks | "Always bypass" (`--permission-mode bypassPermissions`, no per-task picker) |
| Show a note that each task uses Claude usage? | "Yes, one quiet line (Recommended)" |

Session ejb-34 builds all three plans in order in one session: this one, then
the Pixel games tab, then Janhollow (the Jan world) as far as it gets. Emerson,
mid-session: "jan is being used alot an dmy gpu is already at max so dont do
tetsing expecting fast result at all". Model checks run in the background with
long timeouts, or against a fake Jan.

## Facts checked 2026-09-16

- The desktop is **GNOME on Wayland**, not Hyprland (`XDG_CURRENT_DESKTOP=GNOME`,
  no `hyprctl`). Sessions run in **gnome-terminal**: each `claude` pid's parent
  is a `bash` whose parent is the single `gnome-terminal-server`, so one pid
  cannot be matched to one window.
- `apps/claude/runner.py` already runs `claude -p` with stream-json both ways
  and resumes with `--resume`; reuse its approach rather than inventing one.

## What to build

### 1. Start a session, two kinds

- **In a terminal**: a "New session" button opens a small form (folder picker:
  recent session folders, `~/Forge/apps/*`, or a typed path) and runs
  `gnome-terminal --working-directory=<dir> -- claude`. Confirm the flags on
  this machine first. The character walks in by itself when its
  `~/.claude/sessions/<pid>.json` appears; no extra wiring.
- **In the background**: a task box (prompt, folder, model) that starts a
  headless `claude -p` process owned by the Crew Room backend, with a PID file
  and its output stored under the app's data folder. Check whether a headless
  run writes `~/.claude/sessions/<pid>.json`. If it does not, add
  `sources/tasks.py` (one new file; the registry picks it up) so these
  sessions still appear as characters, marked "background".
- Ask Emerson once, at the start of that session: which permission mode
  background tasks run with, and whether to show a line reminding that each
  one uses Claude usage.
- Launching is the only thing that writes. Reading stays read-only, so update
  the README's "Everything is read-only" section to say exactly that.

### 2. Full conversation and "where" in the details panel

- A "Conversation" view: `GET /api/sessions/{id}/conversation?before=<offset>`
  pages the transcript **backwards** in chunks of about 256 KB and never loads
  the whole file. Show user prompts, assistant text, tool calls in plain words,
  tool results collapsed with their size. Images and huge results appear only
  as a size.
- "Where": folder, terminal device (`/proc/<pid>/fd/0` -> `/dev/pts/N`), the
  terminal program, the session name (shown in the terminal tab), when it
  started, and for an **ended** session only, a copyable
  `claude --resume <id>` command.
- Speech bubbles keep showing no message text; only the panel does.

## Checks

- Tests: backwards pager across chunk boundaries, including a line split
  exactly at a boundary; the launch command is built correctly (subprocess
  mocked, nothing spawned); "where" read from a fake `/proc`.
- Real checks: open one real terminal session and one background task with a
  trivial prompt on the cheapest model; screenshot the conversation view and
  the new-session form.
- Keep `MANIFEST.md`, `WIP.md` and the `manifest` block of `forge_app.json`
  current as each part lands, not at the end.
