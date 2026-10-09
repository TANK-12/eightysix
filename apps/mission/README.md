# Mission Control

Every Claude session, helper agent, crew and Relay task on this laptop in one
page. See `MANIFEST.md` for what each view shows, `WIP.md` for state.

## Where the data comes from (all read-only)

| What | Source | Through |
|---|---|---|
| Live sessions, model, effort, context, recent actions | `~/.claude/sessions/<pid>.json` + transcript tail | Crew Room `sources/sessions.py`, `transcripts.py` |
| Helper agents | `projects/*/<session>/subagents/agent-*.jsonl` + `.meta.json`, `~/.claude/agents/*.md` | Crew Room `sources/helpers.py`; Claude app `everyone.py` for older ones |
| Ended sessions (3 days) | session files whose pid is gone | Claude app `everyone.sessions`; their transcript summary is cached by (path, mtime, size) |
| Crews | `~/.claude/crew/<crew>/board.json` | Crew Room `sources/crew.py` + `crew.peek` (no lock) for notes and personas |
| Claude-app tab names | Claude app `GET /api/sessions` (port from its manifest) | Board's `claude_names` (10 s cache, 1.5 s timeout) |
| Relay | `~/.local/share/forge/relay` | Relay `store`, `items`, `runs` |
| Jan models | `/proc` llama-server processes | Crew Room `sources/jan.py` |
| Sprites | `~/ForgeArtData` crewroom packs | Crew Room `art.library()` + `shared/forge_art.js` |
| WhatsApp thread with Relay | Relay's chat task, `## Messages` | Relay `chat` module (`mc/relay_chat.py`) |

Groups: needs you = the session file says `status: waiting`; working = busy
and wrote something in the last 5 minutes (the Board's rule); idle = alive;
ended = pid gone. Unread (page-side, localStorage) = a session that stopped
working after Emerson last opened it.

## Writes (each through the app that owns it)

| Action | Goes to |
|---|---|
| Message a session | Claude app `everyone.message` (a note on the forge board to its board name) |
| Note on a crew board, Answer, Seen | Board `post` / `ack` (crew.py under its lock) |
| Go to it | Board `go_to_session` (terminal tab, else the Claude app tab) |
| Open / Resume in Claude | Claude app `POST /api/everyone/<id>/open` + `/focus`, then `forge_open` |
| Relay Pause / Resume | Relay page `POST /api/pause` / `/api/resume` (503 with a plain message when the Relay page is closed) |
| A line in the WhatsApp mirror | `relay as-whatsapp` (Relay's `cli.py`): handled like a WhatsApp line, echoed to WhatsApp as "From Mission Control: ..." |
| Attach a file or picture (Relay chat, transcript chats) | Saved by Mission `POST /api/attach` (or `/api/attach/paste-image`, the desktop clipboard) into `~/.local/share/forge/mission/attachments/YYYY-MM-DD/`; `say` sends the paths as an `Attached files:` list. Only paths inside that folder are accepted. Claude app chats keep using the Claude app's own upload. |

A note must go to a member (or slot) on that board, not to Emerson himself,
and an answer must name a note that exists. `MISSION_PORT_RELAY` and
`MISSION_PORT_CLAUDE` point a scratch copy away from the real apps.

## Low power

- One endpoint, `/api/overview?sig=<last>`; when nothing changed it answers
  `{same, sig, now}` (about 70 bytes) and the page re-renders nothing.
- Refresh starts at the fastest setting (4 s) after a change and stretches
  by 1.6x per quiet poll to the slowest (30 s). While the window does not
  have focus the fastest is 2.5x slower (10 s). Errors double the wait; a
  request that hangs is dropped after 10 s.
- The forge board remembers every session that ever joined (198 members on
  2026-10-07); only members seen in the last 6 hours, running, holding a
  task or leading are sent, which took the answer from 98 KB to 74 KB.
- `visibilitychange`: hidden stops the timer and pauses CSS animations;
  visible polls at once.
- No animation loop, no canvas redraws: the map is plain HTML lanes. The
  server (`mc/graph.py`) only groups agents into lanes; the page packs the
  lanes into columns (`placeLanes` in `static/app.js`). The only keyframes
  are one-shot pings when a session's action or state changes.
- Sprites are baked once into data URLs and cached.
