# Relay: state

## 2026-10-09 (Hayato, task 128): hey runs out, work goes to default

**Asked (Emerson, WhatsApp):** when hey runs out (5-hour or weekly), any task
running or queued on hey switches to default by itself and carries on; kept
in settings so other pairs can follow.

**Found:** most of it existed (unpinned tasks take the account with room,
hand-over at 98 / move at 80 on hey, a limit hit requeues and marks the
account full for 30 min). The gap: a task pinned with `account: hey` waited
while hey was out, and moves picked "most headroom", not a named partner.

**Done:** setting `account_fallback` (store.DEFAULTS `{"hey": "default"}`,
name or list, chains followed, loops and junk skipped). `picker.fallbacks`,
`out_of_usage` (a usage line, a limit hit or no reading,
since the fallback has a real one; spacing does not), `fallback_in`;
`pick_account` sends a pinned task whose account is
out to its nearest fallback with room ("hey is out (...), so its fallback
default"), the move-line path and `move_to` prefer the fallback, and a task
last run on an out account prefers its fallback. The pin is kept, so work
goes back to hey once it has room (assumption: that is what a pin means).
The boss wait note says "waits for hey or default" when both are out.

**Verified:** 9 new picker tests and 5 new boss tests (whole loop with the
fake Claude: pinned task on a full and on a weekly-full account runs on the
fallback, a running pinned task hands over to it, a limit hit mid-run
retries there, both full waits with the note); red before the change.
Full suite 449 pass (451 after the critic fixes), black, pyright: only the 2 old `channels.whatsapp`
errors in test_boss.py.

**Critic (opus):** no wrong-account case. Fixed: a fallback that only
waited for spacing was skipped for the next in the chain (now waited for);
the wait note named the fallback even when only spacing held the task; the
fallback reason text was never shown (removed); a pinned task waited forever
on a missing hey reading (now falls back); a second session still running on
an account that hit its limit kept going (watch now reads the limit mark, it
moves fresh, no hand-over turn on a limited account; test red first). Left:
a stale low meter after the 30-minute limit mark can relaunch once on hey
and bounce back; reviews and the WhatsApp chat are not handed over (they
end on the limit error and relaunch through the same picker).
Suite after fixes: 451 pass.

**Not live yet:** the relay-boss service reads the code on its next restart
(not restarted: sessions were running).

## 2026-10-08 (Koharu, task 118): pictures and files over WhatsApp and the Relay page

**Asked (Emerson, WhatsApp 21:37):** pictures, screenshots and files sent to
Relay over WhatsApp must reach the chat and work sessions as real files;
paste, drop and an attach button in Forge's chat boxes.

**Done:** `channels/whatsapp.py` READ reports a row's media kind and file
name and whether it is ours; `pick_new` lets media rows through (not
Relay's own `sent_files`); `receive()` fetches each with `grab()` (a hook
catches the blob of WhatsApp's Download link; a video through the viewer,
then Close) and saves it with `shared/forge_attach.py` into
`attachments/YYYY-MM-DD/`, then appends `Attached files:\n- <path>` to the
message (a failure note when it cannot). `Incoming.files`; `chat.route`
sends file messages to Claude, not the local desk; `prompts.py` tells
sessions to open attached paths. Relay page: `/api/attach`,
`/api/attach/paste-image` (the Claude app's clipboard.py), `files` on
`/api/tasks`; Attach button, chips, paste and drop on the request box.

**Verified:** `tests/test_attach.py` (16) and the full suite (432 pass);
live on Relay's Whatsie (session 1): a .md document came back
byte-identical, a WhatsApp JPEG at full size, a 2 s video (ffprobe ok,
viewer closed). Page: drop + paste in headless Chrome made two chips,
screenshot looked at.

**Not verified:** a voice note; a picture sent from the phone end to end
(the test files were sent by Relay itself); the intake goes live only
when relay-boss restarts.

**Later (sessions 2-3):** a critic pass fixed a failed page read losing
messages, a still-loading picture (state `wa_wait`, up to 10 looks), 120-byte
safe names, 415 for a non-JSON paste-image and 507 for a full disk. The two
attach routes moved to `shared/forge_attach_api.py` (`Attachments(root,
what=)` with `.paths`, `.save`, `.router`), now shared by Relay, Mission,
Board and Crew Room. Full suite 435 pass, pyright 0. Open from the critic:
a WhatsApp album keeps only one picture per row; `send_tray` has an 8 s
race; there is no request size cap before the JSON is parsed (the decoded
file is capped). The Add task button now ignores a second click while the
first is on its way.
Second critic (session 3) fixed: a send while a file is still uploading
now waits (`ForgeAttach.wire(...).busy()`, "A file is still uploading")
and a file that lands during a send stays for the next message instead of
being wiped; copied text that also carries a picture pastes as text; a
failed desktop paste says why; a file over 50 MB is refused before the page
reads it; the same path twice is named once. Tests: `shared/forge_attach.test.js` 6 pass.

## 2026-10-08 (Chihiro + Nao, task 112): a review instead of a session cap

**Asked (Emerson, WhatsApp 15:37, notes #1302 and #1306):** task 102 was
parked at 13 sessions while it made real progress. No hard cap at all: at
25 sessions without finishing a short review session decides continue or
park (park reason to his phone), then the same check every 10 sessions
(35, 45, 55...). Limits are settings. A session close to finishing may pass
the context hand-over and finish in the same session.

**Done:**
- `store.DEFAULTS`: `review_after_rounds` 25, `review_every_rounds` 10,
  `review_model` opus, `review_effort` medium, `finishing_minutes` 45;
  `max_rounds` is gone. `picker.should_park` only parks on failures;
  `picker.review_due(task, settings)` says when; `requeue()` never parks.
- `review.py` (new): `evidence()` lists the task's work sessions since the
  last retry (when, minutes, account, outcome, whether State moved between
  one session's start and the next, commits naming the task in that time,
  last words, hand-over note) and the commits ending `(Relay task N)`;
  `verdict()` reads the last `verdict: continue|park - why` line.
- `boss.py`: `launch()` starts kind `review` instead of a work session when
  due (task status `reviewing`, `review_run`; `last_run` untouched so the
  work session can still resume). `finish_review()`: continue sets
  `reviewed_at`, park sends "Parked: title" with the one-line reason, no
  verdict or an error tries again, and after `max_fails` tries the task
  carries on (`reviewed_at` set, board note): a failed review never parks.
  A review past the context line is cut off (counts as a try). A usage
  limit only requeues. Work runs record `state_before` (State fingerprint).
- `relay finishing` (cli + `actions.finishing`, `RELAY_RUN_ID` set by
  `runs.start`): the boss's context hand-over waits `finishing_minutes`
  for that run (`picker.finishing`, `Boss.let_finish`), and the move-line
  hand-over skips it; `finishing_minutes` 0 turns it off. RULES tell
  sessions when to use it and to end commits with `(Relay task N)`.
- `relay tell` (and a WhatsApp follow-up) during a review adds the note to
  the task's request (`chat.add_to_task(queue=False)`).
- `reviewing` counts as active (items, chat, page groups and Stop button);
  `retry` resets `reviewed_at`, `review_fails`, `review_note`.

**Critic (opus, session 2), 10 findings, all handled:**
1. (medium) evidence missed commits outside the launch folder's repo (the
   default folder, the home folder, is no repo): it now also searches the
   repos every Relay task and run used, marked `[in <repo>]`. Fixed.
2. (medium) "Final verdict:" or "Verdict for task 102:" read as no verdict,
   and two failed reviews parked a working task; some prose read backwards.
   Fixed: prefix words allowed, only exact word forms count, template and
   "park or continue" lines skipped, failed reviews carry on.
3. A hand-edited `reviewed_at: n/a` or `review_after_rounds: null` stopped
   every launch. Fixed: `picker._number/_whole/_setting` fall back.
4. The commit grep counted "subtask 1" and "task 1 of 3" and missed
   "(Relay task #1)". Fixed: `relay task #?N`.
5. The 80% move line still handed over a finishing session. Fixed.
6. "failed twice" was hardcoded. Gone with finding 2 (no park).
7. `finishing_minutes` 0 told a session "your time ran out". Fixed.
8. README said "Parked:" always reaches WhatsApp (not when quiet). Fixed.
9. Notes sent during a review went to a session that is not running, and
   reviews had no size cap. Fixed (request, context cut-off).
10. Pre-existing flaky `test_chat_health::test_sessions_know_their_kind`:
    not from this change, left alone.
Session 3 found one more: the template skip never worked (the parser ate
the `<`), so a reply ending with the prompt's template read as
`('park', 'why>')`. Fixed, with a test.

**Second critic (opus, session 3), 7 findings, 6 confirmed by its probes:**
1. (medium) Replies meaning continue still read as park ("Next verdict:
   park if...", "park is not warranted", "Park would be premature", an
   early "A tempting verdict: park" when the last line did not parse).
   Fixed: allowed words before "verdict" are a short list, the word must
   end the line or have a separator after it, only the last 5 lines count.
2. Real verdicts read as none ("Verdict for Relay task 102:", "(Relay task
   102)", "My verdict is:", a curly apostrophe, "3. Verdict:", any `<...>`
   reason). Fixed; only the literal `<why>` is the template.
3. A long task still parked on its second failure ever (fails never reset).
   Fixed: a clean session (continue, or a hand-over that wrote State)
   resets `fails`, so failures park only in a row.
4. A note during a review could save a stale copy over the verdict and
   leave the task `reviewing` with no run for good. Fixed twice:
   `add_to_task` reads the file again first, and `Boss.heal_reviews()`
   requeues a reviewing task whose review run is gone.
5. Stop or a note during the evidence step was lost (`start_review` saved
   the copy read at the start of the tick). Fixed: it reads the task again
   after the notes and starts nothing if it is no longer queued.
6. After a retry the reviewer read "Last review, after 0 sessions". Fixed.
7. Mission Control (`apps/mission/mc/relay_view.py` OPEN_STATES) does not
   know `reviewing`. Not mine to edit (claimed by relay-109-work): board
   note sent asking them to add it.
Design points it raised, handled: his answer to a blocked task now counts
as a review (no review right after he unblocks it), and the review prompt
says a wait on him is over once he has answered. A WhatsApp note during a
review goes into the request; if the review parks the task, retry runs it
with the note.

**Verified:** full pytest 414 passed (24 s); `tests/test_review.py` 79
passed, and its 18 new or changed tests fail on the pre-fix code (checked
on a copy). It covers: trigger points (25, 35, 45, no cap past 50 and 60), hand-edited
values, verdict wording (prefixes, prose, template), the commit tag grep
on a real git repo, evidence (State moves, commits, another task's repo),
the boss flow with fake_claude `REVIEW:continue|park|none|error|limit|sleep`
(continue, park mail, no verdict twice carries on, usage limit, cut off
past the context line, a note during the review), retry, and the
finishing grace (context line, move line, 0 turns it off). The page's
Settings boxes were checked in headless Chrome (session 2). black clean;
pyright no new errors (2 old ones in test_boss.py).

**Not verified live:** no real task has reached 25 sessions on the new
code, so no real review has run; no real session has used
`relay finishing` yet. Old sessions already running keep the old RULES
text until their next launch.

## 2026-10-08 (Mirai, task 105, 4th session): a finished task came back

**What happened:** the 3rd session finished task 105, but at 171k context the
boss handed it over (12:34). The hand-over turn wrote `- status: done`, and
`finish()` requeued every hand-over turn anyway, so a 4th session started at
12:46 for nothing. The hand-over prompt also said "nearly out of usage" for
context hand-overs.

Fixed (**verified by tests**, 329 passed; the old boss.py fails the two
new done and blocked tests, so they catch the bug):
- `hand_over()` saves `state_mark` (crc of the State section,
  `items.state_mark`) on the hand-over run, read after the work session is
  stopped.
- `finish()` for a hand-over run: if the turn succeeded, changed State and
  ended it with done or blocked, the task takes the normal done or blocked
  path (mail with the turn's report, board, goal check); otherwise it is
  requeued as before. A stale done from before a retry with a hand-over
  turn that writes nothing is requeued (test).
- `prompts.handoff(task, why)` names the reason and asks for the phone report
  when the task is finished.
- Tests: three in `tests/test_boss.py`; `tests/fake_claude.py` takes
  `HANDOFF:done|blocked|quiet`.

**Not verified live:** no real hand-over has run on the new code yet. The
"Done" mail for a task finished in a hand-over says effort low (the hand-over
turn's effort), cosmetic. Also seen and left as designed: work launches waited
12:35 to 12:46 on the machine-busy guard (the chat launches before that guard).

## 2026-10-08 (Asuka and Kohaku, task 105): the chat never goes quiet

**What broke (11:34 to 11:52):** a critic's scratch test from task 99
(`/tmp/critic99/t/test_critic.py`) imported `test_boss.py`'s `world` fixture
from outside `tests/`, so no `conftest.py` set `RELAY_DATA_DIR`, and the
fixture wrote the real `settings.json`: `default_folder` = its pytest tmp
folder, `poll_minutes` 0, `launch_gap_minutes` 0, `digest_time` 23:59. Once
pytest deleted that folder every chat launch failed with "No such file or
directory", the error was only logged, and the chat sat queued in silence.
Task 102 put `default_folder` back to /home/ejb.

Fixed (all **verified by tests**, 312 passed, plus the live check below):
- `store.data_dir()` raises under pytest when `RELAY_DATA_DIR` is unset
  (`test_tests_never_reach_the_real_data_folder`).
- `Boss.home_folder()`: `default_folder`, else the home folder, logged once
  per missing path. `folder_for`, the chat launch and plan launches use it;
  a missing task folder is logged. `runs.start` refuses a missing folder
  before it makes a run folder.
- Chat health in `boss.py`: `launch_chat` wraps `start_chat`; a failure
  calls `chat_failed` (state `chat_fail`), `chat_to_boss` hands his unread
  messages to the boss line (`bossline.ask_later`) and sends `down_text()`
  once per outage (state `chat_down_told`); retries wait `CHAT_RETRY` (30 s);
  `chat_guard` catches a chat queued over `CHAT_STUCK` (60 s) with no run
  and no `chat_wait`; `chat_ok` sends `BACK_TEXT` once it starts again.
  `finish_chat` on the second failure in a row now goes to the boss line
  too (before: "write again", and his message sat unread).
- Faster pickup: `quick()` (every few seconds) calls `chat_now` right after
  a message, so the chat no longer waits for the one-minute tick.
- Boss line (`bossline.py`): it refused his real asks on 2026-10-08
  ("Please email a task...", "make taks to fix this", "tell it when it gets
  to 80 percent", "do it yourself"). Now: wider task words, `let me know` is
  not a tell, `recent()` (his boss questions of the last 15 minutes) counts
  for all but stop and pause, numbers with units ("80 percent", "13:00") are
  not task numbers (`BARE_NUMBER`), and with no number the only running work
  task counts (`_only_work`). Answers are remembered up to 2000 characters
  (was 900); the summary labels the chat run as the chat, not a work task.
- `move_at` in `account_limits` (hey 80): past it an account takes no new
  launches while another has room (even a task pinned to it) and its running
  work hands over (`picker.moving`, `picker.move_to`, `Boss.watch`). His ask
  at 11:47 that the boss line refused to pass on.
- One message per answer: `whatsapp_part_chars` 900 -> 4000 and CHAT_RULES
  says one relay reply per answer (he asked 2026-10-07 09:23); a side-by-side
  job goes in with `task:` instead of `new:` (he asked 09:16 for parallel
  rather than queued work).
- The board hears "task N started" only on a task's first launch, not on
  every hand-over or retry.
- Real settings repaired: `digest_time` 13:00 (from `state.digest_at`),
  `poll_minutes` dropped (back to the default 2). `launch_gap_minutes` left
  at 0: its value before the test wrote it is unknown (assumption). Copies:
  `/tmp/relay-settings-before-102.json`, `/tmp/relay-settings-before-105.json`.

Critic (Opus, fresh context) found 8, all fixed with a test each (326 pass):
1. high: the move hand-over looped when default had usage room but could
   not launch yet (spacing or a recent limit hit): `move_to` now takes
   `last_launch`/`now` and uses `blocked_reason` and `Boss.readings()` (the
   limit-adjusted meters), and no move while paused.
2. high: "stop sending me so many messages" could stop the only running work
   task: that fallback is for tell only, and "tell me", "remind me", "my
   message" are no longer tells.
3. task words matched questions ("how many open tasks"): plurals dropped,
   send/email need "a task", session/helper need start/spawn + "a".
4. earlier questions overrode "don't ..." now: a "don't" in this message
   wins (`_refuses`), and only tell/say/task lean on earlier ones (`LEANS`).
5. a persistent session error flip-flopped down/back each message: "back"
   is now sent when a chat session ends well (`chat_ok` in `finish_chat`),
   and after two failures the chat rests `CHAT_REST` (300 s) while the boss
   line answers.
6. `relay 'task: ...'` from the chat came in as a terminal task (no Done on
   WhatsApp): `runs.start` sets `RELAY_RUN_KIND`, and `cli.main` queues a
   chat session's `task:` with source whatsapp (not the work task).
7. an earlier task number blocked this message's: this message's numbers
   decide first. Left: "tell it to hand off at 80" without "percent" still
   reads 80 as a task number, so that one is refused (safe side).
8. a failure after the session started also sent his message to the boss
   line: when a chat run is active it only logs. Also `missing_folder` now
   clears when the folder is back.

Live check (**verified**, boss restarted 12:31, pid 185436): two real test
messages typed into Indeed. 1) With `default_folder` pointed at a missing
folder on purpose (the 11:34 failure): seen 15.4 s after typing (quiet poll),
chat started 0.1 s later in /home/ejb with "default folder ... is missing"
logged, reply 20.6 s after typing; default_folder put back at once.
2) Inside the fast window: seen 1.8 s, started 1.9 s, "ok" in WhatsApp at
9.5 s. Numbers in docs/library/relay/2026-10-08-whatsapp-chat-outage-and-
pickup-times.md. **Not verified live**: the outage notice and the boss-line
hand-off (unit-tested only: breaking the real chat on purpose would have
sent him a false alarm), and the hey move at 80 (hey was not past 80).

Not changed: `/tmp/critic99` (another session's scratch) is left in place;
it can no longer touch real data. Gmail polling still fails with
AUTHENTICATIONFAILED (since 2026-09-29): the app password needs renewing.

## 2026-10-08 (Riku, task 99): fast WhatsApp polling, Haiku 5.5 chat

- **Fast poll.** `boss.read_mail` stamps `state["last_heard_<channel>"]`
  when a poll brings in a message from Emerson (only his: `pick_new` skips
  Relay's own); `channels/whatsapp.poll_seconds(settings, quiet_for)` then
  gives `whatsapp_fast_seconds` (2, never under 2) for
  `whatsapp_fast_minutes` (5; 0 = off), else `whatsapp_poll_seconds` (15).
  Each new message restarts the 5 minutes; an empty poll does not.
- **Haiku 5.5 exists.** Live probe: `claude -p --model claude-haiku-5-5`
  answered "ok" and `modelUsage` names claude-haiku-5-5; Claude Code 2.1.289
  only prints a stderr warning `unrecognized_model` (its table predates it).
  The `haiku` alias still resolves to claude-haiku-4-5-20251001, so
  `store.MODEL_IDS` / `store.model_id()` maps Relay's "haiku" to the 5.5 id
  in `runs.start` and `oneshot.ask` (every Relay launch, task `model: haiku`
  too). When Claude Code's alias moves to 5.5 the entry can go.
- **The chat's light model is now Haiku 5.5 low** (`chat.LIGHT`, default
  `whatsapp_chat_model: haiku`), a deliberate change of task 52's "never
  haiku" (that was Haiku 4.5). `relay chat-model haiku|light|down` steps
  down to it; `sonnet low` stays available by name.
- **Bug found by the probe, fixed:** the chat rule said to put the
  `effort:` line "on top" of `new:`, but `commands.parse` only read options
  under the `new:` line. Sonnet wrote them above (the task lost the work
  slot: a plain terminal task titled "new: ..."); Haiku wrote
  `new: effort: medium` (title "effort: medium", effort ignored). Parse now
  takes option lines above a command or straight after its colon, and
  CHAT_RULES shows the exact form.
- Quality probe (real chat prompt on a copy of Relay's data in /tmp, so
  nothing reached WhatsApp or the real queue): full write-up in
  `~/Forge/docs/library/models/2026-10-08-haiku-5-5-relay-chat-probe.md`.

**Verified:** pytest 283 pass (new: two fast-poll tests in test_boss, the
options test in test_commands, the Haiku 5.5 chat test in test_whatsapp;
the chat launch test now sees `--model claude-haiku-5-5`); black; pyright 0.
Real-clock run of `boss.wait` + `Boss.quick` on a fake channel: 2.0 s
between looks for 20 s after a message, 16 s once the 5 minutes were over.
**Not live yet:** the relay-boss service was not restarted (sessions were
running); the fast poll, the parse fix and the Haiku launch id start on its
next restart. The live chat setting was left alone: Emerson set the chat to
opus medium himself at 09:25 ("stay on Opus"), so Haiku 5.5 is the default
and the step-down target, not forced on. **Reasoned, not measured:** a real
WhatsApp poll (DevTools read of the page) usually adds well under a second,
so the live gap should be 2 to 3 s (more when "Read more" or blank-row
retries kick in).

Critic (opus, fresh context) on the diff, fixed and each now a test:
(1) "new: Check: why ..." / "new: Priority: ..." / "new: Model: <question>"
lost the request or set a nonsense model: only *clear* options (known
effort or model, a path, important) move out of the head or count above a
command (`commands._clear_option`); (2) "Priority: <words>\nTask: ..." from
WhatsApp turned into a task: now chat again; (3) a dead page logged
mail-error every 2 s in the fast window: now at the normal 15 s pace;
(7) `relay chat-model haiku medium` ran at low: haiku keeps a chosen effort.
Not changed: a clock jump backwards stops polling until it catches up
(was so before); a photo or voice note with no text does not start the fast
window (pick_new needs text); `meters.py` usage ping still uses the bare
`haiku` alias (4.5, harmless); `chatlog.py` Claude fallback summary still on
sonnet low (could move to Haiku 5.5; not tested, so not done).

## 2026-10-08 (Takumi, task 98): subagent context no longer triggers a hand-over

- Bug (found by task 97): `runs.summary()` took `context_tokens` from every
  "assistant" event in `output.jsonl`, including a subagent's (those carry
  `parent_tool_use_id = "toolu_..."`; the session's own have it null). A
  critic at 170k made the boss hand the task over and kill the critic while
  the session itself sat at 43k to 48k.
- Decision: `context_tokens`, `last_action` and `last_text` are main-session
  only (while a subagent works, last_action stays "Agent: ...", which is the
  truth; a subagent's words must not go to WhatsApp as "Said:").
  `output_tokens` counts every event, subagents included: it is all spend.
- If a busy subagent fills the whole 256 kB tail with its own events, so no
  main event with usage is in it, `summary()` reads the whole file once to
  find the session's last context (otherwise 0 would mean "cheap to resume").

**Verified:** new `tests/test_runs_summary.py` (3 tests: mixed events,
latest main event wins, tail flooded by a subagent); pytest 280 pass; black,
pyright 0. On task 97's real runs: 0d7ac811 old 173k, new 48k; aac8a697
reads 208k both ways (its main session really did grow that far by its last
step). **Not live yet:** the Relay boss picks it up on its next restart (not
restarted, tasks were running).

## 2026-10-08 (Daichi, task 94): session names match the other pages

- Each task (its last session) and each running session now shows the name
  the Claude app, Crew Room and the Board use: "Mika (relay-59-work)".
  `web_app.session_labels()` calls `shared/forge_session_names.labels`
  (Claude-app tab name, else the name any crew board gave the session id);
  `_session_of(run)` gives a run's session id (a resumed chat keeps its old
  one) and its `--name`; `_run_session(run_id)` reads each `run.json` once
  and caches it. Fields `session_name`, `session_label` on `/api/state`
  tasks and running runs; `app.js` `sessionText()` shows them.
- Also committed from an earlier session: a task's State box stays open
  across the 4-second refresh (`openStates` in `app.js`).
- Tests isolate names: `conftest.py` points `CREW_HOME` and
  `FORGE_APPS_DIR` at the tmp folder (no real boards, no real Claude app).

**Verified:** pytest 277 pass (new
`test_tasks_and_runs_carry_the_session_name_the_other_pages_show`), black,
pyright 0. A copy of the page on a spare port over the real Relay data
showed "Daichi (relay-94-work)" and "Takumi (relay-95-work)" on the running
cards and "last session Noa (relay-93-work)" etc. on tasks (screenshot
looked at); 91 of 95 tasks have a name, the 4 without are early tasks no
board ever named. **Not live yet:** the Relay page backend in Forge picks it
up on its next restart.

## 2026-10-07 23:00 (Kenji, task 72): the boss line on WhatsApp, calm meters

- **Boss line** (`bossline.py`, `bossline_prompt.md`, `oneshot.py`):
  WhatsApp `boss <question>` (or the word `boss` = boss mode for every plain
  message; `claude`/`desk`/`local` back) goes to Relay's boss. The boss
  process answers with one lean Claude turn (no tools/settings/CLAUDE.md/MCP;
  405 tokens overhead measured vs 31,555 plain) over a ~5,000-character
  State summary + last 6 boss exchanges; reply starts "Boss:". ACTION lines
  (stop, retry, pause, resume, tell, say, task:) run through Relay's own
  commands behind a guard (his words must ask for that kind; task number
  said by him or known to Relay). No account with room = plain state, no
  model. `relay boss <q>` in the terminal. Settings boss_line_model (opus),
  boss_line_effort (low). **Verified**: 22 new tests; live end to end
  (WhatsApp-shaped message -> real parser -> queue -> Line -> real opus turn
  on default -> outbox -> WhatsApp composer) answered in 10 s with ETAs and
  calm usage; outbox redirected so nothing was typed into WhatsApp.
- **Calm meters**: picker.usage_reason/has_room split usage limits from
  launch spacing; wait_reason says "spacing launches (...)" when only
  spacing holds launches, "no account has room" only when none has usage.
  meters.describe (used by status, usage, local chat, boss line) shows both
  meters, a full one "resting, back HH:MM", then "Room to launch on X" or
  "No account can launch now". Page bar grey "resting" (red only when none
  can launch; headless screenshot checked). A task pinned to a full account
  no longer holds back the rest of the queue. "Running (N):"/"Queued (N):"
  headers untouched (tested).
- **Not live yet**: the relay-boss service was NOT restarted (sessions were
  running; the laptop powers off when Relay is idle and the new code starts
  on the next boot). Until then WhatsApp "boss ..." goes to the old chat.

Critic (opus, fresh context) on the 72 diff, all fixed and each now a test
(tests/test_bossline.py "Critic findings", tests/test_boss.py pinned tests):
(1) the action guard let a plain question run an action ("when will 1 end?"
could stop 1): now the kind word must be asked for, not under a "don't", and
a task number must be one he marked (#5, task 5) or named by a title word or
bare number ("60fps" is not task 60); (2) a task pinned to a full account
held the only slot and starved the rest: the pinned loop now counts slots
and only notes "task N waits for X (asked for by name)" calmly; (3) one
failing ACTION threw away the answer: run_actions catches per action; (4)
meter readings taken after take() lost the question on a meter error: now
before; (5) "boss level 3" or "Boss fight in emberfield" became boss
questions: the prefix needs boss + ":"/newline/space and a non-sentence
start; (6) "#12 boss" replies route to the task thread; (7) a "task build x"
action without a colon kept the word "task"; the typical-time estimate now
sorts by finish time. Added after: a reply that fails to write (disk) is
logged, not retried (its actions may already have run).
Verified 2026-10-07 ~23:25: 276 tests green, black + pyright clean, live end
to end (/tmp/t72/e2e.py, outbox redirected) answered in 14 s.
Not done: the real WhatsApp typing/reading for a boss reply was not run
(same plumbing as every other reply); relay-boss not restarted (new code on
next boot).

## 2026-10-07 20:00 (Tetsu, ejb-55): tasks 59 and 61 finished inline (hey was out)

Both accounts were out (hey 5-hour 100%, default had no fresh reading), so
Relay was paused and the two tasks were finished in a plain session.
Task 59: the last patch had not landed; redone by hand (shut down only as
the whole message, "it"-messages pull in his earlier chat line, history
budget test). Thinking now off by default (176 s per thinking answer).
Task 61 (chat log, tidy-up, high effort default, hey limits, critic rule,
Whatsie after boot, 401 refresh): docs in README "Chat log and tidy-up" and
"How it decides". New: a blank-row read no longer marks a message seen
(`RENDER_TRIES` in channels/whatsapp.py), over-long summaries keep their
first whole lines (`chatlog.fit`).

Critic (opus, fresh context) on the 61 diff, fixed: (1) the 401 login
refresh and (2) the Claude summary fallback ran a bare `claude` the boss's
PATH cannot find (now `claude_launch.find_claude`); (3) a message he wrote
offline (stamped before the newest seen) was dropped as history (the time
guard now only applies when no seen row is in view, 10 min); (4) "keep the
last 30" counted all rows, now also his own last 30; (5) a stretch could be
summarised twice while its deletes were still going out (`<chat>.summarised.json`);
rows with a photo, video, voice note or file are never deleted; the blank-row
wait only waits on the newest row; "stale reading (401 min old)" no longer
reads as a 401; any wayland-N socket; relay-whatsie.log trimmed past 1 MB.
Not fixed (noted): rows that scroll past unrendered are not logged; the log
job runs only while the boss runs; a leftover .oauth_refresh.lock would make
the refresh fail quietly; while the usage server answers 429 for good an
account gets no reading and nothing launches on it (default tonight).

Verified: suite 242 passed; black on touched files; pyright 0 new errors (the
one in tests/test_whatsapp.py send_tray fake is older).
Live: restarted boss wrote both visible messages to
`chatlog/Indeed-2026-10-07.txt` within a second; a test message (84) sent
and deleted for me through the outbox, 82/83 untouched; Jan summaries of two
real stretches (107 s, 81 s), in the bench doc.
Not verified live: an automatic hourly tidy of a real 45+ message chat
(Relay's Whatsie was relinked and only holds 2 messages), and a 401 login
refresh (no account read 401 tonight). Gmail polling fails with
AUTHENTICATIONFAILED: the app password needs renewing by Emerson.

## 2026-10-07 (Hotaru): State box fix

- The task list's State box closed itself within 4 s because the refresh rebuilt the list. Open boxes now live in `openStates` (app.js) like `openTails`. Checked in headless Chrome: open after 9 s, closes on a second click.

## 2026-10-07 (relay task 59): local chat, quick commands, file send

Built: `localchat.py` + `localchat_prompt.md` (mode `local`, auto stand-in
while the Claude chat has no usage), `quick.py` (command list, stats, top
cpu/gpu with kill by number, kill task / kill all, modes, local model, jan
start, find + send files), Read more expansion in `channels/whatsapp.py`,
`shared/forge_jan.py` ensure_router / chat_messages, `shared/forge_sysinfo.py`
temperatures / top_cpu, `shared/forge_gpuload.py` top_gpu. Default local
model is the 2B (12/14 right, 15 s average on a contended CPU; 0.8B 9/14 at
4 s; 4B 45 s, too slow): numbers in
`docs/library/models/2026-10-07-relay-local-chat-bench.md`.

Verified: full suite 181 passed (tests/test_localchat.py, the Read more
test in tests/test_whatsapp.py); the Read more script run in real headless
Chrome on a fake WhatsApp row opened the full text; ensure_router started
Jan's router live in session 1. Tests now point Jan's per-app settings at a
temp folder (conftest) so they never change the real relay.json again.
Not verified: a real cut-off WhatsApp message from his phone (the class
name WhatsApp uses could differ; the script also matches any role=button
reading "Read more").


## 2026-10-07 (relay task 49)

`relay --help` / `relay -h` now print the CLI usage (cli.py docstring)
instead of being queued as a task. Verified: new test in tests/test_cli.py,
full suite 113 passed, and a real `relay --help` queued nothing.

## State on 2026-09-29 (end of the build session, ejb-12)

Built and running: the boss service is enabled and active, Relay's data
folder is empty and ready, mail is off until Emerson sets up the spare Gmail.
Forge needs a restart to show the Relay tile (apps are found at start).

### Verified

- 67 pytest tests pass (`.venv/bin/python -m pytest -q tests`): picker at
  50/70/92/95/99 %, warm-cache preference, parked after two fails, file
  round trips, the mail parser (commands, long requests, option lines,
  Outlook signatures and quoted replies), the sender + DMARC/DKIM check
  (forged From, header from another server, fake header below the real one),
  the whole boss loop against a fake `claude` (done, continue with
  `--resume`, blocked, errors, usage-limit switch, hand-over at 95 %, stall,
  pause, full accounts, mail threads, stop by thread reply, follow-ups, goal
  plan -> task -> check -> done, digest once a day), the web API, the CLI.
- Real sessions (2026-09-29, about $0.11 of usage each):
  - one tiny task on each account (default and hey) finished, State set to
    done by the session, report text as meant for the phone;
  - hand-over: a task running on hey was stopped when its limit was set to
    60 %, a low-effort `--resume` turn on hey wrote its State, and it
    finished fresh on default;
  - a session survived `systemctl --user restart relay-boss` and the new boss
    finished it (boss PIDs 69793 -> 70286).
- Found live: headless Claude Code refuses a bare `sleep`, and a session
  that ends its turn to wait for a background job simply exits. The prompt
  now says so; the next session finished cleanly.
- Crew board posts from Relay work (name `relay`).
- The page: headless Chrome screenshot checked (running, tasks, goals, log,
  meters; mail-sourced `<b>` shows as text).

### Not verified

- Live mail. Needs Emerson's spare Gmail + app password (README "Set up
  mail"). Then: send `status` from Outlook, and one mail from another address,
  and check the first is answered and the second ignored (`relay status` log
  shows "ignored").
- That Gmail's Authentication-Results for Outlook.com mail looks as the tests
  assume (`dmarc=pass ... header.from=outlook.com`). If mail is ignored with
  "no dmarc=pass", read the event log reason and the raw header.
- Keep-awake (`systemd-inhibit`) is only unit-skipped in tests; not watched live.
- A real planning session for a goal (only the fake planner ran).

## Improve next (ranked)

1. Live mail test once the Gmail exists (the only unproven path he asked for).
2. Renders block launches (`wait_for_renders`): with the Juggernaut crews
   rendering a lot, Relay may wait for hours. Consider letting light tasks
   through, or a per-task "ok during renders" flag.
3. `stall_minutes` (20) treats one long silent command as stuck; a per-task
   override for long test runs.
4. Per-goal budget (tokens per day) so a goal cannot eat a whole window.
5. An ntfy/Telegram channel (one file in `channels/`) for instant pings.
6. The page: show a task's full report text, not just State.

## 2026-10-06 (Tetsu, ejb-b1)
Context cap (hand over at 170k, fresh start instead of resume past 80k), 3-minute launch gap per account, `relay tell N text` (crew note to relay-N-work), rules on context and on Emerson's notes; max_rounds 4 -> 6. Tests 71/71 (new: picker gap/context, tell parse, tell action; boss fixture turns off the gap and the daily digest, which made mail tests fail after 17:00). Boss restarted (KillMode=process, task 39 kept running). Not yet seen live: a context hand-over firing (next session past 170k). Gmail polling fails: AUTHENTICATIONFAILED, app password needs renewing.

## 2026-10-06 WhatsApp channel (Tetsu, ejb-44; stopped at 98% usage)
Emerson's ask: the WhatsApp chat "Indeed" (his choice; it is a real business
account with a bot that answers, told him) as a message board to Relay, quiet
unless asked, headless from login. Built:
- `cdp.py`: stdlib DevTools client (websocket, js, typing, keys, screenshot).
- `channels/whatsapp.py`: Relay's own hidden Whatsie (`flatpak run
  --env=QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:9333 com.ktechpit.whatsie
  --profile relay --minimized`, its own linked device, already QR-linked).
  The boss starts it when the port is down (at most every 2 min), so it comes
  up at login with relay-boss. Hidden, the page is 0x0: every connection sets
  a 1280x900 virtual screen. Reads only Emerson's own messages (aria "You:" /
  tail-out); Relay's messages start with 🔨 and are skipped. Polled every 15 s
  between ticks (`Boss.quick`), a message wakes a tick at once.
- Commands (all channels): `progress [N]` (State notes + last step),
  `usage`, `say [@name] text` (crew board), `notify quiet|mine|all`,
  WhatsApp `#N text` (tell N if running, else follow-up). `check:` refused
  from WhatsApp like mail. Default notify `mine`: replies, results of tasks
  sent from WhatsApp, and blocked/parked only.
- Settings: whatsapp_enabled (on), whatsapp_chat "Indeed", port, profile,
  poll seconds, notify, autostart.
### Verified
- 80/80 tests (9 new in tests/test_whatsapp.py). black run. pyright NOT run.
- Live: boss restarted Whatsie hidden by itself; test() opened Indeed in the
  hidden instance; typing a message into the chat works (shows "Delivered").
### Not verified (next session, first thing)
- The inbound round trip after the "You:" fix: send `usage` from the phone,
  expect a 🔨 reply within ~20 s. If none: `relay status` events log
  (whatsapp poll errors) and check `me` in whatsapp.READ against the DOM.
- Emerson asked mid-build (not started): send files/pictures (copy into
  ~/Downloads/relay-outbox, which the flatpak can read, then attach with
  DOM.setFileInputFiles on the attach menu's file input) and delete
  messages (message menu > Delete); a `relay send-file <path>` for sessions.
- Main Whatsie: its flatpak override env was set then unset (now has an
  empty `unset-environment` entry; harmless).

## 2026-10-06 WhatsApp chat mode (relay task 46, three sessions; Yuzu, then Sora)
Emerson's ask (tasks 41-45 each became a task per message): one chat, not a
task per message; a cheap model for chatting, Opus for work; short
phone-friendly replies; answer straight away; files, pictures, deleting.
Built:
- `chat.py` (new): the standing chat task (setting whatsapp_chat_task; a
  "## Messages" section, last 40), `relay inbox`, the outbox (`relay reply`,
  `send-file`, `unsend`) that the boss flushes on its fast poll (failed entries
  retried, then moved to outbox/failed), the work slot (whatsapp_work_task:
  `new:` makes it, more work is told/appended while it is open),
  `relay chat-model` (switch model, next run starts fresh).
- boss: chat runs outside the work slots, launch gap, pause and render waits
  (still obeys the usage meters); a finished chat run goes `idle`, not done;
  resumed while under whatsapp_chat_context_k (40k), fresh after a switch.
- prompts: the chat rules (answer with relay reply, a few short lines, no
  commands or code; plain requests become relay commands; step up on ask).
- channels/whatsapp.py: phone filter, split at paragraphs (max 4 parts, no
  "…"); commands._title cuts at a word without dots and acks don't quote it.
- Files: attach menu > "Photos & videos" (png/jpg/gif/webp/mp4/mov) or
  "Document"; the menu's hidden file input is caught by patching
  HTMLInputElement.click, then DOM.setFileInputFiles. The footer's own file
  input is the sticker maker (a test picture went out as a sticker once).
  Captions go as their own text. Sent file ids are kept in
  whatsapp_sent_files.json (not in outbox/: every .json there gets sent).
- Delete: a contextmenu event on the text span / picture img / document card
  opens the message menu (the hover button never shows; CDP mouse clicks on
  menu items do nothing, JS .click() works; Escape with no menu open closes
  the chat). Menu Delete > selection bar Delete (retried until the dialog
  shows) > "Delete for everyone", else "Delete for me". unsend only deletes
  🔨 texts and remembered file ids; it stops at the first failure once some
  went, so an outbox retry never deletes older messages.
### Verified
- 101/101 tests (tests/test_whatsapp.py covers each part, incl. the step-up
  path, idle/resume, the work slot, outbox order/retry, partial delete).
  black on the touched files; pyright 0 errors on chat, boss, actions,
  commands, cli, prompts, store, cdp, channels/whatsapp, tests/test_whatsapp.
- Live, boss restarted (pid 111331): a plain message typed into Indeed made
  chat task 47 (haiku low) and its reply was in the chat 35 s later ("Hey!
  Boss is pure Python, doesn't touch your usage..."). A second message resumed
  the same session (event "haiku low (resumed)") and got a one-line answer.
- Live: a picture went as a photo and a .txt as a document; delete worked on
  a sticker, pictures and documents (all test messages removed again).
### Not verified
- `relay unsend` through the boss's outbox end to end (delete_last was run
  directly). "Delete for everyone" was never offered for the test files
  (only "for me"); texts were said to offer it in session 2, unconfirmed.
- The step-up path and the work slot live (unit-tested only).
- Gmail polling still fails (AUTHENTICATIONFAILED), unrelated and older.

## 2026-10-07 (Tomo, Relay task 50): Jan front desk on WhatsApp
Emerson's ask: Jan answers WhatsApp first with a strong system prompt, hands
off to Claude for real work or deeper thinking; and Relay should say when it
is waiting for usage instead of going silent. Built: `frontdesk.py` (Desk
thread, parse of `HANDOFF chat|work:` lines, fallback to the Claude chat,
10-minute skip after a Jan failure), `frontdesk_prompt.md` (editable), chat
status `desk`, `waiting_text` in boss.py (once per wait, with reset time),
setting `whatsapp_frontdesk` (jan|off), Jan role `frontdesk` (default
Qwen3_5-4B-IQ4_XS). Verified: 112/112 pytest (11 new in test_frontdesk.py,
fake Jan), pyright 0 errors, boss restarted cleanly (pid 140451) with
running sessions kept. Not verified: live Jan (Jan was not running on
2026-10-07, so `frontdesk.py --samples` could not score the prompt) and a
real WhatsApp round trip through Jan. Next: open Jan, run `--samples`, tune
the prompt or step the model up/down from the score.

## 2026-10-07 06:15 (Tetsu, ejb-4c): WhatsApp silent since 2026-10-06 18:01
Cause: Relay's Whatsie hung with its DevTools port open but never answering
(545 "timed out" polls); `start_whatsie` only launches a second copy, which
does nothing. Fix: `channels/whatsapp.py` stops Relay's own Whatsie
(`pgrep -f "^whatsie --profile relay"`, never Emerson's) after HUNG_AFTER=300 s
of failed connects, then starts it again. Emerson asked for Claude first, Jan
later: `whatsapp_frontdesk` default and live setting now "off". Verified:
114/114 pytest (new test_hung_whatsie_is_stopped_after_a_while), pyright 0,
boss restarted (pid 169866), his "Hello" reached chat 47 and a reply went out
6 s later (outbox/last_reply). Not verified: the auto-stop firing live.

## 2026-10-07 06:50 (relay task 52): the chat never runs on Haiku
The WhatsApp chat's light model is now Sonnet at low effort. `chat.LIGHT`
and `chat.chat_model(settings)` in chat.py: the default (store.py now
"sonnet"), `relay chat-model haiku` (or light/down/default) and a setting
still saved as haiku all come out as sonnet low; the step-ups (sonnet
medium, opus high) are unchanged. The boss reads the model through
`chat.chat_model`, the chat prompt (prompts.CHAT_RULES) steps down with
`relay chat-model sonnet low`, and README, cli help and forge_app.json say
the same. Verified: 115/115 pytest (new test_chat_never_runs_on_haiku), pyright
0 on the touched files, and a real `relay chat-model haiku` set the live
setting to sonnet low (it was opus low before; reset as the new default).
Not done: the running boss (pid 169866) still holds the old prompt text and
model read until its next restart; the live settings already say sonnet low,
so its next chat session runs on sonnet low either way.

## 2026-10-07 09:30 (relay task 53): numbered messages with a day sign
Emerson asked that every Relay WhatsApp message start with a running number
and a sign for the weekday. `channels/whatsapp.py` `numbered()` puts
"🔨 <n> <sign>" in front of every text part `send()` types and every file
caption (the 🔨 stays first, so own-message detection and unsend still work).
Signs Monday first: ● ▲ ◆ ■ ★ ✚ ○ (`DAY_SIGNS`). The count is
`whatsapp_count.json` in the data folder, so it carries on across restarts; a
message that fails mid-typing uses up its number. Chat and work sessions both
reach Emerson through `send()`, so the numbering is automatic for both. Chat
prompt nudged a touch tighter (prompts.py: answer first, no padding;
frontdesk_prompt.md: one to three lines). Verified: 117/117 pytest (new
test_numbered_counts_up_with_a_day_sign_and_survives_restart,
test_send_numbers_every_part), pyright 0 on the touched files, black.

## 2026-10-07 (relay task 55): files go as one lot

`relay send-file <path>... [caption]` takes several paths (the first word is
always a path, so is every following word that names a file; the rest is the
caption). `chat.send_files` copies them and queues one outbox entry
(`paths`, `names`, `caption`; old entries with only `path` still work).
`channels/whatsapp.py` `send_files` sends pictures/videos in one attachment
tray (`send_tray`: one DOM.setFileInputFiles with all files, one send) and
other files in a second tray (WhatsApp has two separate inputs), then one
numbered message with the caption and, for several files, a numbered name list.
Single file, no caption: unchanged, no extra message.
**Verified:** pytest (120 pass) incl. three new tests with fake pages; black and
pyright clean. **Not verified live:** that WhatsApp Web accepts several files
on one input and shows "Send N selected" (it does by its own `multiple`
attribute, but no live run was made). Prompts and README updated.

Emerson's follow-up (2026-10-07, task 55): the prefix is now one symbol, the
number plus the day sign (`12 ◆ text`); the 🔨 is dropped. Own-message
detection (`whatsapp.is_own`, and the regex in `OWN_LAST` for unsend) matches
`^\d+ <day sign> ` and still the old 🔨 prefix. **Verified:** unit tests
(121 pass). **Not verified live:** unsend/echo-skip against real WhatsApp text.

## 2026-10-08 (task 114): plain session names on the running list
- The running-sessions list shows "#<task> <short description>" (the task
  title cut at the first colon/comma, 44 characters) with the persona (Mika)
  as the small tag. The rule is `shared/forge_session_title.js`
  (`ForgeSessionTitle.displayName/personaTag`), the same file Mission Control
  (`apps/mission/static/logic.js`, which now delegates to it) and the Claude
  app's "everyone" list use. The full title is the tooltip.
- Verified: pytest 414 pass; `node --test shared/forge_session_title.test.js
  apps/mission/tests/logic.test.js` pass. Browser check:
  `tests/check_names_ui.py` (see the task report for its result).
