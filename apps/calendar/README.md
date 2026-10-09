# Calendar

A life log of what happens on this laptop, as a calendar. Emerson asked for it
on 2026-09-24: "logs of things that happen or said or app opened and times and
stuff", written by him, Claude, Jan, Nyarch and scripts.

- **Views:** month (a coloured dot and a count per source per day, plus your
  own events), week, and day (an hourly timeline with "Sum up this day with
  Jan"). There's also search across everything.
- **Your events:** notes, tasks, milestones and reminders. A reminder pops up
  on the desktop at its time with notify-send. Click any event to edit it.
- **Feeders** (`sources/`, one file each, switchable in the side panel):

| Feeder | Reads | Backfills history? |
|---|---|---|
| claude | ~/.claude/projects/*/*.jsonl: your messages and session starts | yes |
| jan | Jan's threads/*/messages.jsonl | yes |
| nyarch | Nyarch's datachats.pkl (read with a locked-down unpickler) | no; it has no times, so new messages are logged when seen |
| apps | launcher apps running (/proc and `flatpak ps`), any desktop | no; opens and closes from now on |
| forge | Forge app ports listening | no |
| hyprland | `hyprctl clients` window titles, in Hyprland only | no |

- **Scripts:** run `forge-log "text"` (on PATH through ~/.local/bin), or
  `POST /api/events` with `X-Forge: 1`. The source is recorded as
  `script:<name>`.
- **Privacy:** everything stays local. Numbers typed next to "sudo" or
  "password" are masked before they are stored. You can pause all logging,
  and activity is pruned after N days (default 365; your own events are never
  pruned).

Data: `~/.local/share/forge/calendar/` (events.db, feeders.json with the read
positions, settings.json). Port 8453.

To add a feeder, add one file in `sources/` with NAME, LABEL, DESCRIPTION,
DEFAULT_ON, INTERVAL and `collect(state)`.

Tests: `.venv/bin/python -m pytest -q` (19).
