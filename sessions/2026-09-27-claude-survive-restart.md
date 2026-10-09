# Claude sessions survive a restart, and a key to restart Forge

Emerson (2026-09-27): "make it so that claude sessions survive even when i
restart my laptop, also give a key bind for restarting forge". Queued by
ejb-e3 (Kiko), which finished Speed and detail (01292cf) first. Not started.

## The job
1. Claude sessions (the Claude app in Forge: apps/claude, and the terminal
   sessions it runs) come back after a reboot: same conversations, resumed
   (Claude Code `--resume <id>` / `--continue`), in the same folders, with
   Forge starting at login (setting start_at_login already exists).
   Find out first what is lost today: the process, the transcript, the
   panel's list of open sessions, or all three.
2. A key bind that restarts Forge cleanly (quit, then start again), added to
   the Forge keys table (shared/forge_theme.py HUB_KEYS + HUB_KEY_LABELS,
   caught in forge.py) so Settings > Forge keys can change it. It must not
   kill running Claude sessions without bringing them back (see 1).

## Rules
- Claim forge.py / hub/index.html on the crew board per edit (Tomo, ejb-6b,
  is editing both for monitors).
- Definition of done in ~/.claude CLAUDE.md: tests first, a real run, black +
  pyright with a venv, handoff in PROGRESS.json.

## State
Done by ejb-e3 in 6e4f3c6; details in PROGRESS.json session_ejb_e3_claude_restart. Terminal tabs are not restored after a reboot (not asked; a possible follow-up).
