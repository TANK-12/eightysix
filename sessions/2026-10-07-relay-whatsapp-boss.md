# Relay: the WhatsApp boss line and calm usage meters (task 72)

date: 2026-10-07 · for: both · by Kenji (relay-72-work), Opus 5.5

## What Emerson asked

1. A direct line from WhatsApp to Relay's boss (what runs, ETAs, usage,
   steering: stop or queue a task, pass a note to a running task), answered
   within a minute or two, cheap, and obvious which messages go there.
2. Stop warning about one full account: there are two subscriptions. Warn
   only when no account can launch; show both meters calmly.

## What was built

- `apps/relay/bossline.py` + `bossline_prompt.md` (instructions, plain
  text) + `oneshot.py` (one lean Claude turn). WhatsApp `boss <question>`,
  `boss: ...` or `@boss ...` goes to the boss; the word `boss` alone turns
  on boss mode (every plain message goes there; `claude`, `desk`, `local`
  switch back). Mail and the terminal are unchanged; `relay boss <q>`
  prints an answer in the terminal.
- The boss process (`boss.py`, `Boss.boss_line`) answers one queued
  question at a time in a thread: compact State summary (running tasks with
  their last State lines, queue, recently ended, typical task time, both
  meters, last crew board notes, ~5,000 chars) + last 6 boss exchanges
  (`<data>/bossline.json`). Reply starts "Boss:". ACTION lines (stop, retry,
  pause, resume, tell, say, task:) run through Relay's own commands behind
  a guard. No account with room: the plain state, no model.
- Calm meters: `picker.usage_reason` / `has_room`, `meters.describe` (used by
  status, usage, local chat, the boss line), page bar grey "resting".
  "no account has room" only when none has; spacing says "spacing
  launches". A task pinned to a full account no longer holds the queue.
- Docs: `apps/relay/README.md` ("The boss line", "How it decides"),
  `WIP.md`, manifest feature "Boss line", measurement in
  `docs/library/tokens/2026-10-07-lean-oneshot-claude-cost.md`.

## Verified

- Tests: `cd ~/Forge/apps/relay && .venv/bin/python -m pytest -q`, all green
  (22 new in tests/test_bossline.py, one new in test_boss.py).
- Live end to end (script /tmp/t72/e2e.py, outbox redirected so nothing went
  to WhatsApp at night): a WhatsApp-shaped "boss what's running ..." went
  through the real parser, queue and Line worker to a real opus turn on the
  default account and back as a "Boss:" message in 10 s, with an ETA per
  running task and "hey is resting at 100% ... normal with two accounts".
- Lean turn cost: 405 tokens overhead vs 31,555 for a plain `claude -p`.
- Relay page: headless Chrome screenshot on a private server, default bar
  green, hey bar grey with "resting".
- black and pyright (project venv): no errors on the touched files.
- `relay status` header lines "Running (N):" / "Queued (N):" unchanged
  (a test checks them).

## Not done / reasoned only

- The relay-boss service was **not restarted** (sessions were running). It
  uses KillMode=process and sessions are their own process groups writing to
  files, so a restart would very likely be safe, but it was not tried. The
  new code starts on the next boot (the laptop powers off when Relay is
  idle). If it did not reboot: `systemctl --user restart relay-boss`.
  Until then "boss ..." on WhatsApp goes to the old chat.
- The real WhatsApp typing and reading (Whatsie) were not exercised for a
  boss message; that plumbing is unchanged and used by every other reply.

## Critic

An opus critic found 7 problems (actions run from plain questions, a pinned
task blocking the only slot, one failing action losing the answer, a meter
error losing the question, "boss level 3" read as a boss question, "#12 boss"
replies, "task build x" keeping the word task). All 7 are fixed and covered
by tests; the details are in apps/relay/WIP.md under task 72.

Verified 2026-10-07 ~23:25: 276 tests green in apps/relay/tests, black and
pyright clean on the touched files, live end to end through the real parser,
queue, boss-line worker and a real lean Claude turn into a redirected outbox:
answered in 14 s, split into two WhatsApp parts by the channel's own composer.
