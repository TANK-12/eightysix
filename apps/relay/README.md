# Relay

Keeps Claude working while you are out. Mail it from your phone (or type in
the terminal, or use the Relay page in Forge); a plain Python boss starts a
fresh Claude session for the job on whichever account has room, watches it,
moves it to the other account when one runs low, and mails you the result.

## Set up mail once (5 minutes)

1. Make a spare Gmail account. Turn on 2-Step Verification (Google Account ›
   Security). Google will not make app passwords without it.
2. Google Account › Security › App passwords: make one called "Relay".
3. In Forge, open Relay › Mail: fill in the spare Gmail address, your own
   Outlook address as the allowed sender, paste the app password, tick
   "Mail on", Save, then "Send test mail". The test mail lands in your
   Outlook inbox.

Only mail **from your allowed address that Gmail has verified as really sent
by Outlook** (DMARC/DKIM pass) is read. Everything else is ignored silently.
Mail text is never run as a command; it only becomes a task file that a
session reads.

## Using it

Write to the spare Gmail from Outlook. The subject or the first line decides:

| You write | Relay does |
|---|---|
| `status` | replies with what is running, queued, waiting on you, and both usage meters |
| `pause` / `resume` | stops / allows new sessions (running ones carry on) |
| `tell 12 <text>` | a note to task 12's running session through the crew board; it sees it after its next step and acts on it first |
| `stop 12` / `retry 12` | stops or re-runs task 12. Inside a task's mail thread just `stop` or `retry` |
| `digest` | the daily summary now (it also comes by itself at 17:00) |
| `goal: <title>` + lines below | a goal: short planning sessions split it into tasks until it is done |
| `task: <goal> <text>` | a task added to that goal |
| `help` | the list |
| **anything else** | a new task. One line or three pages: the whole mail is the brief |

Optional lines at the top of a request:

```
important                       max effort, jumps the queue
folder: ~/Forge/apps/cosmos     where to work (default: your home folder)
effort: high                    low / medium / high / xhigh / max
account: hey                    default / hey / second
done when: the tests pass       how the session knows it is finished
```

You get a "Got it: task 12 queued" reply, then the session's own short report
when it finishes, in the same thread. **Replying in that thread** with more
text makes a follow-up task that first reads what the earlier one did.

From the terminal: `relay status`, `relay "fix the thing"`, `relay < notes.txt`,
`relay 'goal: ...'` (the terminal, unlike mail, may give a goal a
`check: <command>` line). Inside a Relay work session, `relay finishing`
says the task is close to done, so the boss does not hand it over for its
context size for a while (see Context under How it decides).

## WhatsApp (chat mode, 2026-10-06)

The WhatsApp chat "Indeed" is a second way in. Relay runs its own hidden
Whatsie (a WhatsApp Web window, linked as its own device) and the boss reads
and types into it; the boss itself is plain Python and spends no usage while
it watches. Only sessions use usage. It looks at the chat every 15 s
(`whatsapp_poll_seconds`); for 5 minutes after each message from you it
looks every 2 s (`whatsapp_fast_seconds`, `whatsapp_fast_minutes`; 0
minutes turns that off), so a quick back-and-forth is not held up.

- **Just chat.** Anything you write that is not a command goes to one standing
  chat task (Haiku 5.5, low effort by default). Its session answers within about
  half a minute, one message per answer, and remembers the conversation
  (it resumes the same session while its context is under 40k tokens, then
  starts fresh from its notes). Plain requests work: "how is the cosmos job
  going", "stop that", "make it smarter".
- **Work** goes to one separate work task (Opus, high effort): write
  `new: <what to do>`, or ask the chat and it starts one. While a work task is
  open, more work is added to it rather than starting another, so WhatsApp
  never has more than two tasks open (the chat and one job). The chat passes
  your messages on to the work session and tells you its answers.
- **Smarter on request**: "use sonnet", "think harder" or "use opus for
  this" makes the chat switch model (`relay chat-model sonnet medium` or
  `relay chat-model opus high`); the next message starts a fresh session on
  it from the notes. Stepping back down (`relay chat-model haiku`, or
  `light`) goes to Haiku 5.5 at low effort. Relay launches "haiku" as
  `claude-haiku-5-5` (store.MODEL_IDS), never Claude Code's own alias,
  which still meant Haiku 4.5 on 2026-10-08.
- The commands above work here too (`status`, `stop 12`, `#12 more text`).
- Replies are phone-sized: no code, commands or tables, long ones split at a
  paragraph into at most 4 parts, nothing cut off with "…".

**Jan answers first (front desk, 2026-10-07).** With `whatsapp_frontdesk`
set to `jan` (the default), a plain message goes to a local Jan model before
any Claude session: it chats, answers questions and Relay status itself (no
usage), and hands off what it cannot do. A hand-off to the Claude chat
(deeper thinking, his files, unsure) queues the chat session above with
Jan's note; a work request starts the work task, as `new:` does. Its
instructions are `frontdesk_prompt.md` (plain text, edit freely, read on
every message); its model is role `frontdesk` in
`~/.config/forge/jan/relay.json` (default Qwen3_5-4B-IQ4_XS, released when
idle). If Jan is closed or fails, the message goes to the Claude chat and
Jan is skipped for 10 minutes. When a Claude hand-off has no usage to start,
Relay says so once with the time usage comes back, and the chat goes back to
Jan for new messages meanwhile. Score Jan's calls on sample messages with
`.venv/bin/python frontdesk.py --samples` (tests/frontdesk_samples.json).

**Local chat and quick commands (task 59, 2026-10-07).** Three chat modes,
switched by typing one word: `claude` (Claude sessions answer), `desk` (Jan
first, as above) and `local` (a small Jan model answers everything, no
usage at all). With `whatsapp_fallback: auto` (the default) the local model
also stands in by itself whenever the Claude chat has no usage to start,
and Relay says when Claude is back. The local chat is `localchat.py` with
its prompt in `localchat_prompt.md`: every message gets a facts block (time,
Relay tasks, usage, temperatures, CPU, GPU, memory, battery, disks, Jan),
keyword lookups (LOOKUPS registry: progress, cpu, gpu, disks, forge, board,
file, find, read-only shell...) and may end in one guarded ACTION line that
only runs when Emerson's own message asked for it. Its model is role `local`
in `~/.config/forge/jan/relay.json` (default the 2B Qwen as its `-long`
copy with a 131072-token window, picked by
`docs/library/models/2026-10-07-relay-local-chat-bench.md`); `local model
0.8b` / `2b` / `4b` switches it. It sees the last 40 chat lines and knows
itself: the facts name its model, size, context window and the speed it
last measured (`local_speed.json` in the data folder). Lookups include
`web` (DuckDuckGo through `shared/forge_websearch.py`, picked up by words
like weather, news, google, online) and `page` (read one web page).
Thinking is off by default (on the 2B a thinking answer took about 3
minutes against about 10 s without, 2026-10-07): `think auto` lets it reason
first only on harder questions (why, how, compare, plans...), `think on`
always, `think off` never.
It is held to honesty: a message asking for a task queues one in his own
words (never a placeholder) through the WhatsApp work task, a reply that
claims a deed nothing did gets "(That was talk only ...)" added, and bare
command lines in its reply are dropped, never run. If Jan's model server is down Relay starts
it (`forge_jan.ensure_router`, never a restart). Score it on sample chats
with `.venv/bin/python localchat.py --bench`.

Quick commands answer instantly with no model, on any channel (`quick.py`,
one COMMANDS entry each): `command list`, `stats`, `top cpu` / `top gpu`
(numbered, then `kill 3` or `force kill 3`), `kill task 12`, `kill all`
(stop every Relay session and pause), `local` / `claude` / `desk` / `mode`,
`local model`, `jan` / `jan start`, `think on` / `off` / `auto`,
`google <words>` (or `web search <words>`), `shut down` (asks; only `yes
shut down` within two minutes powers the laptop off), `tidy chat` (see
below), `find report` (or `find *.blend`,
numbered, newest first; never hidden folders, key-like names or Relay's
data) then `send 2` to get that file on WhatsApp. Long WhatsApp messages
that arrive cut off with "Read more" are opened before they are read.

For sessions (what the chat session uses):

```
relay reply <text>             send a message to the chat (via the outbox)
relay send-file <path>... [text]  send pictures (as photos) and files (as documents) in one lot:
                               give every path in one call; words after the last file are the caption
relay unsend [N]               delete Relay's own last N messages
relay inbox                    Emerson's new messages for the chat task
relay chat-model <model> [effort]
```

Sessions never touch WhatsApp themselves: they write to an outbox the boss
sends from every few seconds. Settings: `whatsapp_chat_model`,
`whatsapp_chat_effort`, `whatsapp_chat_context_k`, `whatsapp_work_model`,
`whatsapp_work_effort`, `whatsapp_notify` (quiet / mine / all),
`whatsapp_part_chars`, `whatsapp_max_parts`, `whatsapp_files_dir`.

- **It never goes quiet (2026-10-08, task 105).** A message starts the chat
  session straight away, between the boss's one-minute ticks. When the chat
  cannot start (its launch fails, it fails twice in a row, or a message
  waits over a minute with no session and no known usage wait), you get one
  WhatsApp line saying why, your messages go to the boss line so they still
  get an answer, and one more line says when the chat is back. A missing
  folder is no longer fatal: a task or the chat whose folder is gone starts
  in `default_folder`, and when that is gone too, in your home folder (each
  logged as an error).

- **Pictures and files (2026-10-08, task 118).** A picture, video, voice note
  or document you send in the chat is downloaded into
  `~/.local/share/forge/relay/attachments/YYYY-MM-DD/` (never overwriting:
  a second `shot.png` becomes `shot (1).png`), and the message reaching the
  chat or work session ends with `Attached files:` and one path per line;
  the session prompts say to open them (Read shows a picture). A file
  message skips the local desk and goes to Claude (unless Claude is out of
  usage). A file that cannot be fetched still arrives as a line saying so.
  Relay's own sent files are never read back in. The Relay page's New
  request box takes files too: Attach files, paste, or drop on the box
  (`/api/attach`, `/api/attach/paste-image`; a task may be files alone).
  Shared code: `shared/forge_attach.py` (save, safe names, the note) and
  `shared/forge_attach.js` (paste, drop, picker for any Forge text box).

### The boss line (2026-10-07)

A direct line to Relay's boss, the commander that knows what runs, what
waits, the ETAs and both usage meters, and that can steer.

- **`boss <question>`** (or `boss: ...`, `@boss ...`): that one message goes
  to the boss. "boss what's running and when will it finish", "boss stop the
  cosmos job", "boss tell 63 to skip the fps runs", "boss queue a task to fix
  the zoom". The answer comes back on WhatsApp starting with **Boss:**,
  usually within half a minute (10 s measured).
- **`boss`** on its own switches the chat to boss mode: every plain message
  goes to the boss until you write `claude`, `desk` or `local`.
- Everything else is unchanged: no `boss` in front means the chat, `new:`
  means work, commands (`status`, `stop 12`, ...) answer at once as before.
  Only WhatsApp has the prefix; a mail starting "boss" is still a task. From
  the terminal, `relay boss <question>` prints the answer there.

It is cheap on purpose: nothing stays open. Each question is one lean Claude
turn (`oneshot.py`: no tools, no settings, no CLAUDE.md, its own system
prompt; measured 405 tokens of overhead against 31,555 for a plain
`claude -p`) that reads a compact State summary (about 5,000 characters:
running tasks with their latest State lines, queue, what ended lately, the
typical task time, both meters, the last crew board notes) plus the last 6
boss exchanges. Model and effort: settings `boss_line_model` (opus) and
`boss_line_effort` (low). Its instructions are `bossline_prompt.md` (plain
text, edit freely). Steering comes back as `ACTION` lines that run through
Relay's own commands (stop, retry, pause, resume, tell, say on the board,
task: queue a real task), only when your words asked for that kind of thing
and the task number is one you said or one Relay knows. Stop and pause need
your words in that message; the others may lean on what you asked the boss
in the last 15 minutes ("do it yourself" after "tell it to hand off at 80").
With no number given ("tell it ..."), the one running work task counts; with
two or more running you have to say which. With no account able
to launch, the boss answers with the plain state and no model.

### Chat log and tidy-up (2026-10-07)

Nothing in the chat is lost: every message the boss sees goes into a plain
running log, one file per chat and day, `<data>/chatlog/Indeed-YYYY-MM-DD.txt`
(`chatlog.py`), every 10 minutes (`whatsapp_log_minutes`) and always before
anything is deleted. Once an hour (`whatsapp_tidy_minutes`), or when you
write `tidy chat`, an older stretch (at least `whatsapp_tidy_least` = 15
messages above your last `whatsapp_tidy_keep` = 30) becomes ONE new summary
message, written by the local Jan model (Claude, Sonnet low, only when Jan's
is missing or fails the checks), and the summarised messages are deleted
"for me". WhatsApp only lets you edit a message for about 15 minutes, so
the summary is a new message. Only messages already in the log are deleted,
never the last 30, never an earlier summary. `whatsapp_tidy_delete` false
keeps the summary and the log and deletes nothing; `whatsapp_tidy` false
stops the hourly one. Note: Relay's Whatsie only holds what arrived since it
was linked, so the log starts there.

Reading the chat waits for rows to render: a row read blank right after the
chat opens is left out (it used to be marked seen and lost), and old history
scrolled into view is never taken as a new request (only rows below the last
one seen and not older than the newest seen count).

## How it decides

- **Account**: never one at 95% of its 5-hour window (or 99% weekly), no new
  sessions from 92%, one per 15 minutes from 70%. Two subscriptions, so
  one full account is normal: status, usage, the page and every message
  show both meters calmly ("hey: 5-hour 100%, week 43%, resting, back
  00:10 (in 1h15m)" then "Room to launch on default.") and only say "No
  account can launch now" when none can. A launch held only by spacing
  says "spacing launches (...)"; a task pinned to a full account with no
  fallback waits without holding back the rest of the queue. An account can have its own
  lines in `account_limits`: hey (Emerson, 2026-10-07) has no 15-minute
  spacing, new launches up to 95% and hand-over at 98%. Past an account's
  `move_at` (hey: 80%, Emerson 2026-10-08: hey is the Pro plan, default the
  20x one) it steps aside while another account has room: no new launches
  there, even for a task pinned to it, and its running work hands over
  (writes its State, carries on fresh on the other account). With no other
  room it carries on to its hand-over line. A task that just ran keeps
  its account while it is still allowed (its cache is warm), otherwise the
  account with the most room.
- **Fallback** (Emerson, 2026-10-09): `account_fallback` names where an
  account's work goes when it runs out; the default is `{"hey": "default"}`.
  "Out" means past its new-launch line on the 5-hour meter, past the weekly
  line, or a usage-limit hit (counts as full for 30 minutes). Then a task
  pinned to it (`account: hey`) launches on the fallback instead of
  waiting; a running session hands over at its line as usual and the fresh
  session lands on the fallback; a session that hits the limit mid-run is
  retried there (not counted as a failure), and every other session still
  running on that account moves too, fresh (a hand-over turn on an account
  at its limit would only fail). Moves past the move line and
  a task that last ran on the out account prefer the fallback over the
  most headroom. The pin is not rewritten: once hey has room again, work
  pinned to it goes back there. A missing meter reading counts as out
  (the fallback has a real one, so nothing launches blind); launch spacing
  does not, and a fallback that only waits for its spacing is waited for,
  not skipped. A value may be a name or a list, and
  chains are followed, so `{"hey": "default", "default": "second"}` adds a
  third account in one line. With every fallback full too, the task waits
  and the status says "waits for hey or default".
- **Effort**: `important` = max, everything else high (Emerson, 2026-10-07:
  "make all tasks high effort"; the WhatsApp chat keeps its own setting).
  Planning = medium.
- **Critics**: every work session is told (prompts.RULES) that a deep coding,
  game or program task gets at least one critic subagent on its diff before
  it is called done, and lists the findings in its report.
- **Meters**: a reading that is old and whose window has already reset is
  dropped (no reading, so nothing launches on a guess). A meter that reads
  HTTP 401, or a login whose token is past its expiry, gets one tiny Claude
  call on that account (at most every 20 minutes) so Claude Code refreshes
  the login. After a boot the boss reads the display from the user manager
  before it starts Whatsie (it used to die with no display); Whatsie's start
  output goes to `~/Forge/outputs/relay-whatsie.log`.
- **Hand-over**: if a running session's account passes 95%, Relay stops it,
  lets the same session write where it got to (one short turn), and a fresh
  session on the other account carries on from that note. The hand-over
  turn is told why it was stopped. If it finds the task finished (or blocked)
  and writes that into State, the task ends there with its report; a stale
  `done` from before a `retry` does not count, because the boss fingerprints
  State when the hand-over starts (2026-10-08, task 105).
- **Context** (2026-10-06): a session past 170k tokens of context hands over like
  at 95% (writes its State, a fresh session carries on), and one that ends with
  "continue" is only resumed while under 80k (resuming reloads all of it). The
  rules tell sessions to stop themselves at about 150k. Settings
  `hand_over_context_k`, `resume_max_context_k`. The one exception
  (Emerson, 2026-10-08): a session whose whole task is close to finished
  runs `relay finishing` once; for `finishing_minutes` (45) after that the
  boss does not hand it over for its context size, nor move it off an
  account past its move line, so it finishes where it is. The usage
  hand-over (95%) still applies; `finishing_minutes` 0 turns this off. Only a running work session
  can say it (the command reads `RELAY_RUN_ID`, which Relay sets).
- **Long tasks** (Emerson, 2026-10-08): no session cap. After 25 sessions
  without finishing (`review_after_rounds`), the next launch is a short
  review session instead (`review_model` opus, `review_effort` medium). It
  reads the task file, Relay's list of the task's sessions (when, how long,
  whether State moved, how many commits naming the task landed, last words,
  hand-over notes) and the commits ending `(Relay task N)`, and ends with
  `verdict: continue - why` or `verdict: park - why`. Continue: the task
  carries on and is reviewed again every `review_every_rounds` (10)
  sessions, so 35, 45, 55 and on. Park: the one-line reason goes to his
  phone (a "Parked:" message reaches WhatsApp unless `whatsapp_notify` is
  quiet) and mail. Only a verdict line in the last 5 lines of the reply
  counts ("Final verdict:", "My verdict is:" or "Verdict for Relay task N:"
  in front is fine), and the word must end the line or have a dash, colon
  or comma after it: prose such as "park is not warranted" or "next
  verdict: park if nothing lands", and the prompt's own `<why>` template,
  are no verdict. A review
  that gives no verdict `max_fails` times (an error, no verdict line, or
  cut off past the context line) does not park: the task carries on, the
  next review comes 10 sessions later and the crew board gets a note. A
  usage limit only waits. While it runs the task shows as `reviewing`; a
  note sent then (`relay tell` or WhatsApp) goes into its request, so the
  next session reads it. His answer to a blocked task counts as a review
  (the next one comes 10 sessions later). A task left `reviewing` with no
  review running goes back to the queue. `retry` starts the count again. `review_after_rounds` 0 turns reviews off;
  `review_every_rounds` 0 makes the first review the only one. Sessions
  end their commit messages with `(Relay task N)` so the review can count
  them.
- **Spacing**: launches on one account are at least 3 minutes apart
  (`launch_gap_minutes`), so a meter reset never starts the whole queue at once.
- **Stuck**: no output for 20 minutes = stopped and retried. A task that fails
  twice in a row is parked and mailed to you instead of burning usage (a
  session that ends cleanly resets the count, 2026-10-08). The number of
  sessions alone never parks a task (see Long tasks).
- **Machine**: waits while a Blender render or a busy Jan is running, the load
  is high, or the disk is nearly full (all settings).
- **Laptop sleep** is held off while anything is queued or running.

## Where things are

- The boss: `boss.py`, the `relay-boss` user service (starts at login).
  `systemctl --user status relay-boss`, log in `~/Forge/outputs/relay-boss.log`.
- Everything it knows: `~/.local/share/forge/relay/` (tasks, goals, sessions,
  settings; the app password in `secrets/`, mode 600). `RELAY_DATA_DIR`
  points it elsewhere; under pytest without it, `store.data_dir()` raises,
  so no test (not even a scratch copy outside `tests/`) can write the real
  settings again (task 105).
- Each session's full output: `runs/<id>/output.jsonl`; the page's "Live"
  button shows it in plain words.
