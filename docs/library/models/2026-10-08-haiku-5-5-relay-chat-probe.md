# Haiku 5.5 on Relay's WhatsApp chat: a reply-quality probe

date: 2026-10-08 · for: both · Relay task 99 (Riku)

## Does it exist?

- `claude -p --model claude-haiku-5-5` (Claude Code 2.1.289): answered "ok",
  `modelUsage` key `claude-haiku-5-5`, `is_error` false. Stderr warns
  `[claude-code:unrecognized_model]`: the CLI's own table predates it, so its
  cost estimate for this model is not trustworthy.
- `--model haiku` (the alias) still ran **claude-haiku-4-5-20251001**.
- `claude-haiku-5-5-20261001` (a guessed dated id) did not answer.

## The probe

Real `prompts.chat()` prompt for the chat task (47) on a copy of Relay's tasks,
goals, settings and state under /tmp (RELAY_DATA_DIR and CREW_HOME pointed
there, so no message reached WhatsApp and no task reached the real queue),
working folder ~/Forge as live. One fresh session per message, `--effort low`.

| message | Haiku 5.5 low | Sonnet 5.5 low |
|---|---|---|
| hows it going? anything need me? | 10 s, 3 short replies: nothing running, parked 5 and 63, usage per account | 10 s, one reply, same facts, offers to restart 5/63 |
| show how long each task took (round 1, old prompt) | 9 s, made the work task but with options in the wrong place, no number given | 12 s, options above `new:`: became a plain task outside the work slot; number given |
| what did task 97 produce? | 10 s, 3 replies, accurate (spec, M0 to M12, 13 decisions, 30 fixes, commit) | 9 s, 3 replies, accurate, also mentions it found the task 98 bug |
| show task times (round 2, fixed prompt) | 24 s, correct work task (title, effort high, folder); reply promised the number later instead of giving it | not run |
| wallpapers app remembers the last pick | 12 s, correct work task, number 100 given, plan in one line | 21 s, correct work task (effort medium), number given |
| pause everything, im gaming | 8 s, `relay pause`, one-line reply | not run |
| think harder: boss on a systemd timer? | 10 s, stepped up to opus high as the rules say, one line | 12 s, answered itself after reading boss.py (rules say no exploring) |

Verdict: Haiku 5.5 is as accurate as Sonnet low on chat, status and summaries,
faster, and follows the action rules (pause, step up, work hand-off). One miss
in three hand-offs: it did not say the task number. Made the chat's light
model (default and step-down target; the live chat stayed on the Opus medium Emerson chose that morning). Sonnet low stays one command away (`relay chat-model sonnet low`).
Sample is small (7 Haiku runs, 6 Sonnet), so it is a sanity check, not a
benchmark.
