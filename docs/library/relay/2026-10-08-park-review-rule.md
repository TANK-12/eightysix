# Relay: long tasks get a review, not a session cap

date: 2026-10-08 · for: both

## The rule (Emerson, 2026-10-08, Relay task 112)
- Before: a task was parked after a fixed number of sessions without
  finishing (`max_rounds`). Task 102 (Exo Lab) hit it at 13 while making
  real progress every session.
- Now there is no hard cap. After 25 sessions without finishing, the next
  launch is a short review session that reads the task file, the list of
  its sessions (State moved or not, commits naming the task, last words)
  and its commits, and answers continue or park.
- Continue: the task keeps going; the same review comes again every 10
  sessions (35, 45, 55 and on).
- Park: the one-line reason goes to his phone on WhatsApp (and mail).
  `retry N` runs it again and starts the count from zero.
- The reviewer must end with `verdict: continue - why` or
  `verdict: park - why` ("Final verdict:" or "Verdict for task N:" in front
  is fine). A review that gives no verdict twice (an error, no verdict
  line, or cut off past the context line) does not park the task: it
  carries on and the next review comes 10 sessions later (a wrong park
  costs more than a few sessions). A usage limit only makes it wait.
- Only the last 5 lines of the reply are read, and the word must end the
  line or have a dash, colon or comma after it, so "park is not warranted"
  or "next verdict: park if nothing lands" never parks a task.
- Failures park a task only twice in a row: a session that ends cleanly
  resets the count (without a session cap, two stray errors in a long
  working task would otherwise stop it).
- Emerson's answer to a blocked task counts as a review.
- A session whose task is close to finished runs `relay finishing`; for 45
  minutes the boss does not hand it over for its context size, so it
  finishes in the same session. It is not moved off an account past its
  move line either; the 95% usage hand-over still applies.

## Settings (`~/.local/share/forge/relay/settings.json`)
| Setting | Default | Meaning |
|---|---|---|
| `review_after_rounds` | 25 | sessions before the first review; 0 turns reviews off |
| `review_every_rounds` | 10 | sessions between later reviews; 0 means one review only |
| `review_model` | opus | model of the review session |
| `review_effort` | medium | effort of the review session |
| `finishing_minutes` | 45 | how long `relay finishing` holds off the context hand-over |
| `max_fails` | 2 | failures in a row before a task parks; tries a review gets before the task carries on |

## Where it lives
`apps/relay/review.py`, `picker.review_due`, `Boss.start_review` /
`finish_review` in `boss.py`, `prompts.review`; tests in
`apps/relay/tests/test_review.py`. Details and what is verified:
`apps/relay/WIP.md` (2026-10-08 task 112 entry).
