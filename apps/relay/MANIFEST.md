# Relay manifest

Start here in a fresh session. `README.md` is the user guide; `WIP.md` holds
the current state and the ranked list of what to improve next. The original
brief is `~/Forge/sessions/2026-09-29-relay-app.md`.

## What it is

A Forge app (port 8463, `apps/relay`) plus a boss process (`boss.py`, user
service `relay-boss`) that runs headless Claude sessions unattended, across
Emerson's accounts, fed by mail, the terminal and the page. Built 2026-09-29
by ejb-12.

## His words and decisions

> "when usage gets too high you set an effort and account ... and write a
> handoff and send it to the new session"
> "a boss session that controls what people do ... so that when i get back
> from work things are still running"
> "i want to be able to send emails from my outlook account with details and
> simple command or stupid long command and for the python script to launch a
> new session and the new session to know what to do ... just make it work in
> the most efficient and useful way for my use cases" (2026-09-29, build start)

| Question | Answer |
|---|---|
| Phone channel | Spare Gmail as the Relay mailbox; he writes from his **Outlook** address |
| Permissions | bypassPermissions ("all permission") |
| Boss | Plain Python, zero tokens while waiting |
| Goals | Relay is also the goals app |
| Mail content | Fixed short commands, **and any other mail is a task** (his 2026-09-29 ask, replacing the brief's "anything else gets a help reply") |
| Sessions at once | Default 2 (setting) |
| Digest | Default 17:00 (setting) |
| Long tasks | No session cap (2026-10-08, replacing the park at N sessions): a short review session after 25 sessions without finishing, then every 10 (35, 45, 55...); it says continue or park, and a park reason goes to his phone. All settings. A session close to finishing may pass the context hand-over (`relay finishing`). Failures park only twice in a row |

## Map

| Piece | File |
|---|---|
| Boss loop: watch, hand over, mail in, launch, digest, keep awake | `boss.py` |
| Account / effort / park / review-due rules (pure, tested) | `picker.py` |
| A long task's review: what its sessions did, the verdict line | `review.py` |
| Starting, watching, stopping one session (PID + start time) | `runs.py` |
| Headless command line, shared with Crew Room | `~/Forge/shared/claude_launch.py` |
| Meters via `~/.claude/tools/usage.py` (imported, 3-min cache) | `meters.py` |
| Machine busy check (disk, load, render, Jan CPU) | `machine.py` |
| Goal and task files (front matter + State) | `items.py` |
| Mail / terminal text -> command | `commands.py` |
| What a command does (shared by mail, terminal, page) | `actions.py` |
| Session prompts (work, resume, hand-over, plan, review) | `prompts.py` |
| Channels (discovered; one file each) | `channels/__init__.py`, `channels/gmail.py` |
| Page backend / frontend | `web_app.py`, `static/` |
| Terminal | `cli.py`, `~/.local/bin/relay` |
| Service unit (symlinked into `~/.config/systemd/user/`) | `relay-boss.service` |
| Tests (fake `claude` in `tests/fake_claude.py`) | `tests/` |

## Rules this app keeps

- The boss is the only thing that starts sessions. The page and the terminal
  write files and poke it (`poke` file); it ticks within 2 seconds.
- Every session: its own process group, stopped only by its saved PID (checked
  against its start time). `KillMode=process` so sessions outlive a boss restart.
- Mail is acted on only from `allowed_senders` with the mailbox server's own
  top Authentication-Results showing dmarc=pass (or aligned dkim=pass). Mail
  text is never executed; a goal's `check:` shell command is accepted from the
  page and terminal only.
- Sessions commit only their own files (`git add <paths>`); Relay never does
  `git add -A` in shared trees (deviation from the brief's "commit per task",
  because `~/Forge` holds other sessions' uncommitted work).
- A new channel is one file in `channels/`; no list to edit.
- Never touches Jan, renders or the Power app's CPU caps.
