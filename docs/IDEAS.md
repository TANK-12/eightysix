# Forge ideas backlog

Ideas Emerson has asked for "some day". None of these are built yet. When one gets
picked up, it moves into its own plan file and this entry links to it.

## Civilisation text sim, run by agents (asked 2026-09-24)

A text-only civilisation game you mostly watch:

- Several agents, each playing a faction with its own goals and personality, take
  turns on a shared world: tiles, resources, and a diplomacy table.
- A detailed chronicle log records every turn: what each faction thought, decided and
  did, plus the consequences. You can read it like a history book.
- A deterministic simulation core decides outcomes (harvests, battles, plague, trade),
  so the agents only make *choices* and can't invent results.
- Possible build: a small Python engine, a world state in JSON, and one
  prompt per faction. The local Jan model plays ordinary turns (free), with Claude
  kept for rare big moments. Remember Jan is shared and loaded per app, on demand.
- The UI is a Forge app with a map, a timeline and the chronicle, with pause, speed and
  "intervene as god" buttons.

## Paper-trading sandbox (asked 2026-09-24, as a safe stand-in)

Emerson asked for an app that trades or mines with a hard-capped "sacrifice" bank
account. It was **deliberately not built with real money**:

- Laptop crypto mining on an Iris Xe costs more in electricity than it earns.
- An auto-trader moving real money most likely loses it.
- Bank credentials in a local app are a security risk.

What could be built instead is a paper-trading sandbox: pretend money, real public price
data, strategies as one file each in a registry, and a leaderboard of which strategy
would have made or lost what. Only if a strategy beat simply holding an index fund
over months of paper trading would it be worth talking about more.

## PulseForge: upload through the YouTube API (opt-in, later)

Autopilot (added 2026-09-24) stops at an upload-ready folder on purpose. A later
opt-in could upload through the YouTube Data API with OAuth, always as a
private or scheduled video that Emerson approves. It would never publish on its own.
