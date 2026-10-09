> **Built 2026-09-24.** See `apps/calendar/README.md` and `WIP.md`. The week view is not an hour grid; it lists each day in columns.

# Plan: Calendar, the Forge life log

Asked for by Emerson on 2026-09-24: "a calendar app that is locally generated
or updated by you and me and jan and nyarch and python scripts, basically logs
of things that happen or said or app opened and times and stuff". To be
**built in a fresh session**. Start it with: *"build ~/Forge/apps/calendar/docs/PLAN-calendar.md"*.

## What it is

A new Forge app, `apps/calendar`, with a calendar and timeline of everything
that happens on the laptop and in Forge, plus Emerson's own events and notes.
Anyone can write to it: Emerson, Claude, Jan, Nyarch or any script.

## Design

- **One event log.** SQLite at `~/.local/share/forge/calendar/events.db`.
  Each event has a time, an end time (optional), a source (`emerson`,
  `claude`, `jan`, `nyarch`, `script:<name>`, `forge:<app>`), a kind (`said`,
  `app_open`, `app_close`, `task`, `note`, `reminder`, `milestone`), a title,
  a body and tags.
- **Sources as a registry.** `apps/calendar/sources/<name>.py`, one file per
  feeder, with an enable toggle in settings. Adding a feeder is one file.
  - `forge`: the hub already starts and stops app servers, so it logs app
    open and close.
  - `hyprland`: listens on Hyprland's event socket for window open and focus
    changes (lightweight, with no polling).
  - `claude`: reads new user prompts and session start and end from
    `~/.claude/projects/*/*.jsonl` (titles only by default, full text as an
    option).
  - `nyarch` and `jan`: what was said to and by the assistant, if its history
    is readable. Otherwise a small HTTP endpoint they can post to.
  - `scripts`: `POST /api/events` and a tiny `forge-log "text"` command, so any
    script can log.
- **The Emerson side.** Add, edit and delete events. Reminders (reuse Acchan's
  `remind_me` notifications if possible). The maths test and university dates
  go in by hand.
- **Views.** Month, week and day, a timeline scroll, search, and filter by
  source. A "what did I do on …" daily summary that Jan writes on demand
  (loaded only when asked, then unloaded).
- **Privacy.** Everything stays local. There's a pause-logging switch, and old
  events are pruned after N days (a setting).

## Checks

- Tests: the event store (add, query by range and source), each feeder's
  parser on a fixture, and the API round trip.
- A headless screenshot of the month and day views, dark theme, readable text.
- A registry entry in `forge_app.json`, plus a manifest, README and WIP.
