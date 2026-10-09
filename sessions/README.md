# Forge sessions: where every Claude session's manifest lives

Emerson's rule (2026-09-25): every Claude session working on Forge has a
manifest here, so he (not only Claude) can find what each session is doing,
what it finished, and what is left. One file per session, named
`<date>-<slot>-<topic>.md`. The session keeps its own file current.

## Wave of 2026-09-25: five terminal sessions

Written on 2026-09-25 by the planning session, from one long message of Emerson's.
Each brief below is a whole job for one terminal session. Emerson opens a
terminal per brief and pastes its start line. Sessions are started by him in
real terminals, not spawned as agents: he found terminal sessions do far
better work than self-spawned helpers.

| Slot | Brief | Covers | Suggested model |
|---|---|---|---|
| S1 | [S1-sessions-board-claude-app.md](2026-09-25-S1-sessions-board-claude-app.md) | Board fixes, talk-to-all-sessions, session manifests, Claude app (mid-stream send, avatars, usage bars) | Opus, medium |
| S2 | [S2-hub-shell.md](2026-09-25-S2-hub-shell.md) | Forge hub: scale/text/scroll, close button, Alt switching, overview key, open-app markers, zen mode, home declutter, smoothness | Opus, medium |
| S3 | [S3-driftpeaks-audio-media.md](2026-09-25-S3-driftpeaks-audio-media.md) | Drift Peaks polish + music, visualiser for any audio, background music, Media YouTube downloader | Opus, medium |
| S4 | [S4-blender-godot-acchan.md](2026-09-25-S4-blender-godot-acchan.md) | Blender/Godot tooling upgrade finished + polished, Acchan app launching and slow replies | Opus, medium or low (Emerson's ask) |
| S5 | [S5-app-fixes.md](2026-09-25-S5-app-fixes.md) | Comix, AI Studio, Calendar, Dossier, Power | Opus, medium |

Start line to paste into a fresh terminal (swap the slot):

```
Read ~/Forge/sessions/README.md, then do your brief: ~/Forge/sessions/2026-09-25-S2-hub-shell.md
```

## Rules for every session in this wave

1. **Read first**: this README, your brief, `~/Forge/README.md` "start here",
   and the `WIP.md` of each app you own. Load the `forge-session`, `verify`
   and `lean` skills. Build the `ask-checklist` ledger from your brief's
   ledger lines (they are already numbered; keep the IDs).
2. **Join the board**: `python3 ~/.claude/skills/crew/crew.py join forge <you> --role solo`
   where `<you>` is the name ListAgents gives this session. Then post
   `crew post forge <you> "S<n> started: <topic>"`.
3. **Talk on the board**, not through side files. Between tasks run
   `crew notes forge --for <you>` and answer anything addressed to you
   (`crew ack forge <you> <id> --note "reply"`). Emerson posts from the Board
   app (port 8452, board `forge`). A note with no `--to` is for everyone.
   S1 is improving this (broadcast, tabs, notes arriving without polling);
   switch to the new way once S1 posts that it is live.
4. **Claim before editing** (`crew claim forge <you> <paths>`), release when
   done. You own the paths your brief lists. Hub-wide files (`hub/`,
   `forge.py`, `shared/`, `PROGRESS.json`) are claimed only for the edit
   and released straight after. Exit code 2 = someone holds it: post to them.
5. **One usage meter for all five.** Every session draws on the same 5-hour
   window. Run `python3 ~/.claude/tools/usage.py` between tasks: under 70%
   keep going; from 70% one task every 15 minutes; from 92% stop working;
   at about 95% stop the task, update your brief's "State" section and
   post a handoff note. The 7-day window matters too; say on the board
   when it passes 80%.
6. **No live renders or model evals** (Emerson, 2026-09-25: "dont run renders
   or tests"; read as: no Blender or Godot renders, no Jan/LLM eval runs, no
   GPU-heavy jobs; he looks at those himself). Still allowed and required:
   pytest, black, pyright, headless Chrome screenshots of web pages. Leave
   him the exact command for anything heavy.
7. **No subagents.** Do the work in your own session.
8. **Jan is shared**: check the `jan` board before loading, unloading or
   restarting anything (crew skill, "Jan board").
9. **Disk is short**: no big downloads without saying so on the board; use
   models, voices and binaries already in `~/Forge` before fetching new
   ones. Nothing gets installed (pip into an app's venv excepted) without
   Emerson picking it from a list with real sources.
10. **Handoff**: keep the "State" section at the bottom of your brief
    current after every finished item (done+checked / done not checked /
    not done / blocked), plus the owning app's `WIP.md`. Add a
    `session_N_work` entry to `~/Forge/PROGRESS.json` at the end (claim
    it for that edit only).
11. **Restarts**: Forge finds apps when it starts. Say on the board before
    restarting Forge or an app Emerson may be using, and never kill his
    open Forge window without asking.

## 2026-09-29: Relay (boss, goals, Gmail)

| Brief | Covers | Suggested model |
|---|---|---|
| [relay-app.md](2026-09-29-relay-app.md) | New app `apps/relay`: a zero-token boss process that queues goals and tasks, launches headless sessions on whichever account has room, hands over at 95 percent, and reports by Gmail | Opus, high |

Start line: `Read ~/Forge/sessions/README.md, then do your brief: ~/Forge/sessions/2026-09-29-relay-app.md`
