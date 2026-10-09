# Mission Control manifest
date: 2026-10-08 · for: both

Start here in a fresh session. `README.md` explains how it works and where
each piece of data comes from; `WIP.md` holds the current state, what is
verified, and the ranked list of what to improve next.

## What it is

A Forge app (port 8465, `apps/mission`) that shows every Claude session on
the laptop, its helper agents, the crew boards and Relay in one place, in the
style of Enjoy (https://enjoy.dev/): filters All / Needs you / Working /
Unread / Idle / Ended, every session side by side with what it is doing right
now, a map of the whole wave, crew boards with posting, and Relay's queue and
meters. Built 2026-10-07 by helper-1 (Izumi) in crew `overhaul`
(plan: `~/Forge/sessions/2026-10-07-overhaul/PLAN.md`).

## His words

> "make a new interface so that huge sessions like these can be better
> communicated with and watched over and visualised maybe, and upgrade and
> combine board, forge claude app and crew room"

> "i want new features and optimization please dont remove features i like
> what i have"

So the Board, the Claude app and the Crew Room are untouched and keep working;
Mission Control imports their readers instead of copying them.

## Views

| View | Shows | Can do |
|---|---|---|
| Sessions | Cards in sections Needs you / Working / Idle / Archived (ended, or idle for 30+ minutes; still readable), newest activity first in each, re-sorted at most once a minute so cards do not jump: name = task number and a short plain description (Relay task title or chat title, `logic.js displayName`) with the persona as a small tag, model, effort, folder, crews, Relay, context bar, last activity, current action, recent actions with times, helper agents (crew member, task, state) | Details drawer, Message (a note on the forge board), Go to it (terminal tab or Claude-app tab), Open or Resume in Claude |
| Conversations | The chat fills the window: Mission's top bar, side nav and needs band step aside (`body.focus-chat`). Slim header: Chats (needs-you badge), portrait, plain name + persona tag, state, what it is doing, plan chip (done of total), Stop, Session, Mission. One chat UI (`convos.js`) for every session: a Claude app chat live through `/api/claude`, or the transcript of a terminal, Relay or ended session. Centred column in big type (19 px default, 14 to 28 px), anime night look: Claude on the left with its sprite portrait and name tag, Emerson on the right in a pink-lilac bubble, each run's tool calls and kept reasoning folded into one "N steps" bar | Send (attachments, paste, drop), Stop; the composer chip ("Opus · High") opens model cards, an effort gauge Low to Max and ultrathink Off / Next message / Every message; Session sheet: title, what it may do, Normal / Ultracode and Limits, text size, reasoning, steps folded / open / hidden, Claude or Jan, facts, Open in Claude, Go to it, Details, Resume here; Chats panel (Ctrl+K; Alt+Up / Alt+Down next chat; Esc closes) |
| WhatsApp (in Conversations) | The WhatsApp chat with Relay, live: pinned on top of the Chats panel, a Mission nav entry and a header button (press again to go back). Same anime look: Emerson on the right, Relay / Boss / Jan / Local on the left with portraits, day chips, times, his last line marked sent or read, typing dots while Relay answers. `GET /api/relay-chat?seen=` every 2.5 s (15 s when hidden, backs off on errors) | Type to Relay, or to the boss with the composer chip: `POST /api/relay-chat/say` runs `relay as-whatsapp`, handled exactly like a WhatsApp line (commands too) and echoed to WhatsApp as "From Mission Control: ..."; Session sheet: text size, facts, Open Relay |
| Map | The wave as lanes of big cards: each crew (commander on top), Relay runs, shared boards, lone sessions with their helpers, Jan models. Every agent shows once; a Relay run inside a crew is a "task N" badge. Fills the width, never scrolls sideways, fit zoom 100-180% or - / + | Click or Enter on any card opens its details |
| Crews | Each active crew: goal, commander and members tree with tasks and states, claims and log (advanced), notes newest first | Post to everyone on a board or one member, Answer a note, mark Seen |
| Relay | Boss state, paused, wait reason, task counts, account meters (5-hour and week), running sessions, queue and recent tasks, goals and events (advanced) | Pause / Resume through the Relay page's API |
| Drawer | One session or helper: facts, helpers, the conversation newest first (prompts, replies, tool calls in plain words; results in advanced) | Message, Go to it, Open in Claude, Note to a crew helper |

Top bar: counts, Relay strip (meters), Simple / Advanced, Settings (sliders
with number fields: fastest and slowest refresh, feed lines, ended shown,
helpers per card), Full screen (the shared `{forge:"chrome"}` message; Alt+F
and F11 too). Needs you band: sessions waiting on Emerson, notes to Emerson
from the last 24 hours (summarised when more than two), blocked Relay tasks.

## Files

- `web_app.py`: routes; every POST needs `X-Mission: 1`.
- `mc/borrow.py`: imports the other apps' readers (Crew Room sources,
  transcripts, conversation, where, art; Relay store, items, runs; Claude
  everyone.py; Board web_app.py) read-only.
- `mc/sessions.py`, `mc/crews.py`, `mc/relay_view.py`, `mc/graph.py`: one
  source each into plain JSON. `mc/overview.py` puts them together with a
  signature. `mc/actions.py`: every write, through the owning app.
- `static/`: `index.html`, `app.css`, `app.js` (DOM), `logic.js` (no DOM,
  tested under node), `chat.js` (drawer Chat tab), `convos.js`
  + `convos.css` (Conversations: the full-window chat), `chat_logic.js` (its
  DOM-free logic, node-tested), `messages.js`, `swarm.js`.
- `mc/claude_proxy.py`: the Conversations view's door to the Claude app:
  `/api/claude/options`, `/api/claude/conversations/{id}/events` and POST
  `.../{send,settings,stop,seen,files,paste-image}` only, plus
  `/claude-ui/{run_controls.js,run_controls.css,enjoy_logic.js,enjoy.css}`
  served read-only from `apps/claude/static` (shared, not copied).
- `mc/relay_chat.py`: the WhatsApp mirror: reads Relay's chat task
  `## Messages` through Relay's `chat` module (borrowed read-only) and
  says through `relay as-whatsapp` (Relay's `cli.py`, 90 s timeout).
- `tests/`: pytest with a fake `~/.claude`, `/proc`, crew boards and Relay
  folder (`conftest.py`), plus `logic.test.js` run by `test_logic_js.py`.

## Run

`cd ~/Forge/apps/mission && FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8465`
(Forge starts it from `forge_app.json`). Tests:
`.venv/bin/python -m pytest -q tests`.
