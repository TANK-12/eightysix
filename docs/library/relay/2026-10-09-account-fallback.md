# Relay: account fallback (hey runs out, work goes to default)

date: 2026-10-09 · for: both

Decision (Emerson, WhatsApp, Relay task 128): when hey runs out, every task
on it carries on on default by itself.

- Setting `account_fallback` in Relay's settings, default `{"hey": "default"}`.
  One name or a list per account; chains are followed, so
  `{"hey": "default", "default": "second"}` adds a third account in one line.
- "Out" = past the account's new-launch line on the 5-hour meter (hey: 95%),
  past the weekly line (99%), or a usage-limit error (counts as 100% for
  30 minutes) or no meter reading at all. The 3-minute launch spacing is not
  "out": a fallback that only waits for spacing is waited for.
- A task pinned with `account: hey` then launches on default instead of
  waiting. A running session still hands over at hey's 98% line (or moves at
  80% while default has room) and the fresh session lands on default; a
  session that hits the limit mid-run is retried there, not counted as a fail,
  and every other session on that account moves too.
- The pin is kept: once hey has room again, work pinned to it goes back there.
- Both full: the task waits and the status says "waits for hey or default".

Checked: 16 new tests (10 picker, 6 whole-loop boss tests with the fake
Claude), full Relay suite 451 pass, one opus critic (findings fixed or
listed in apps/relay/WIP.md). Goes live when relay-boss restarts.
