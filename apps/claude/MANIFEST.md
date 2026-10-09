# Claude: manifest

The long form of the `manifest` block in `forge_app.json`.

## Summary

A chat panel over the local Claude Code CLI. Each conversation is a streaming `claude -p` process that can open, search and read pages in the Forge Browser through an MCP server, takes attached files and images, opens links from its answers in the Browser, and resumes after a stop or restart.

## Features

| feature | detail |
|---|---|
| Conversations | Listed, renamed, deleted; history kept on disk and resumed with the Claude Code session id. Live streaming text, tool calls as cards with results, cost per turn and per conversation. |
| Tabs | The side list is the history, the tab bar is the live set. Clicking a conversation opens it as a tab; + or Ctrl+T starts a new one on the default account. Each tab is locked to one account (shown on the tab when there is more than one) and keeps running while another is shown; a pulsing dot marks a busy tab. Ctrl+Tab and Ctrl+PageUp/PageDown switch, Ctrl+W or middle-click closes (the conversation stays). Open tabs and unsent drafts come back after a reload (localStorage forge.claude.tabs). |
| Send while Claude works | Messages sent during a turn go straight to the running Claude Code process, which folds them into that turn; Send stays next to Stop and such messages are marked "added while Claude was working". |
| Command menu | Typing / or . at the start of a message opens the commands and skills, filtered on every keystroke (name first, then description), each with its one-line description. The list is Claude Code's own from its last init event plus a scan of the skills and commands on disk (~/.claude/skills, synced skills, plugin skills and commands, ~/.claude/commands), shared by every account (/api/commands). Arrows move, Tab or Enter picks, Esc closes; a pick is written as /name. Built-ins such as /context, /model and /config answer in the panel as they do with claude -p; they have no description. |
| Slash commands and self-run commands | A message starting with / goes to Claude Code with no persona tag in front, so /compact, /context, /usage and the rest run as commands (checked live with 2.1.289: /compact compacts and the page draws a "conversation compacted" divider; /context's tables render). Claude can run commands on its own session with the panel_command MCP tool (in the forge-browser server, per-conversation config data/mcp/<id>.json): it queues the command (data/commands/<id>.jsonl), the runner sends it as the next message once the turn ends, and the page shows "Claude asked to run /compact". Allowed commands are one registry, panel_commands.COMMANDS (compact, context, usage, recap, rename). |
| Folders | Conversations can be filed into folders: + folder, drag a chat onto a folder or use its folder button, rename, collapse, delete (the chats are kept). folders.json in the data folder; each conversation's meta has folder. |
| Forge Browser tools | browser_mcp.py exposes open, search, read, tabs, back, forward, reload, switch and close, each one command to the Browser app's queue, so Claude uses the Browser the user sees, logins included. |
| Attachments and images | Paperclip, drag and drop, or paste (Ctrl+V or right-click Paste; a copied screenshot WebKit does not hand over is read from the desktop clipboard with wl-paste). Images go to Claude inline and show as thumbnails; every file is saved under the conversation's attachment folder and listed by path for the Read tool. Images in messages and tool results have a Copy image button (wl-copy). The globe button attaches the page open in the Browser as a text file. |
| Links open in the Browser | Clicking a link in an answer opens it as a new tab in the Forge Browser and brings the Browser forward. |
| Accounts | Two or more Claude accounts, one Claude Code config directory each (the default is ~/.claude, the others are CLAUDE_CONFIG_DIR profiles under the data folder). The list shows who is signed in and each account's 5-hour usage bar; one click makes it the default for new tabs; a conversation stays on the account it was created on. Signing in relays claude auth login: the address, the pasted code. |
| Per-conversation settings | Working folder, model, effort (claude --effort: low to max, or the default), and what Claude can do: read and browse only (default), plan, edit files, auto mode, or everything. Nothing can prompt for permission; anything that would is refused. |
| Normal / Ultracode | A switch per conversation (both layouts). Ultracode is Claude Code's standing dynamic-workflow orchestration for the session: passed as `--settings {"ultracode":true,"enableWorkflows":true}`; at start the panel asks Claude Code (get_settings control request) whether it really took effect and shows a warning when not. Haiku cannot run it, so the switch is greyed out there. Carries over to a new tab like model and effort. |
| Agent limits | A "Limits" fold beside the switch: helpers at once (CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS, default 20), helper nesting depth (CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH) and helper model (CLAUDE_CODE_SUBAGENT_MODEL), each a slider plus number field or a picker; empty is Claude Code's default. Declared once in runner.AGENT_LIMITS and drawn from /api/options by static/run_controls.js, so a new limit is one entry. |
| Avatar stage and personas | Off at every page load (Emerson, 2026-10-07); 🎭 or "Turn on the avatar" turns it on until the page reloads (not saved): while off nothing animated loads. A live anime avatar beside the conversation: the persona for each message is picked by mood (Tetsu by default, Kira for builds, Shizu for fixes, Arch-chan for status, Yui or Ren for downtime) or pinned. It reacts to Claude's status, lip-moves, follows the mouse and can speak replies with a Kokoro voice. Personas are files in personas/; the roster goes into the system prompt once and each message carries a short persona tag. |
| Layouts | Two layouts on one backend, switched with "enjoy ↗" (classic) and "classic layout ↗" (Enjoy); the last one used opens next time (localStorage claude.layout). The Enjoy layout (enjoy.html/css/js, enjoy_logic.js): projects (a project is a conversation folder with a working folder, notes and workflows; projects.py), tasks per project each opening as the chat with plan and progress beside it (read from Claude Code's ExitPlanMode and TodoWrite calls), running / needs you across every project, notes with a markdown preview, workflows that start a task, and the roadmap: every session brief in ~/Forge/sessions as a constellation, each ask a star lit when done, click for Emerson's words, meaning and state; open forge board notes below (roadmap.py, GET /api/roadmap; #roadmap/<brief>|<id> opens a star). Markdown and event drawing are shared in claude_common.js. |
| Docs | docs.html (the docs button in both layouts): every important text document for Emerson and Claude as a folder tree, newest first, read-only, with search over titles and text and a Copy path button. Sources are declared in doc_sources.json (library, sessions, Forge docs, app docs, ~/.claude self/memory/skills, ~/Models, codec lab, Desktop); new docs go in ~/Forge/docs/library/<topic>/YYYY-MM-DD-name.md. A doc is dated by its file name, else a date: line near the top, else its last change (shown in italics). docs_library.py, GET /api/docs?q= and /api/docs/read?path= (only listed paths). |
| Avatar Studio | avatars.html: 8 working Live2D models (Arch-chan from Nyarch plus Live2D's free samples), each with its own motions plus 24 generated ones; new motions improvised or described to Jan and saved to the shared library; a puppet generator and editor with save, delete, undo and redo; each persona's avatar and voice. |

## Data

~/.local/share/forge/claude/personas.json (persona choices), voice/ (last 20 spoken clips); shared avatars in ~/Forge/shared/avatars (Live2D models, motion recipes, puppets). ~/.local/share/forge/claude (conversations, attachments, mcp.json, profiles.json, profiles/<name>/ for extra accounts); Claude Code's own session files in ~/.claude

## Dependencies

- Required: fastapi, uvicorn, claude (Claude Code CLI, logged in)
- Optional: the Browser app, for the browser tools and links

## Standalone

```sh
cd ~/Forge/apps/claude && FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8445
```

## Known gaps

- Cost: Claude Code's total_cost_usd is the session's running total, so meta.cost_usd is the sum of the newest total per session (meta.session_costs). Conversations from before 2026-10-07 summed running totals; that too-high figure is kept as "earlier".
- Event numbers (seq) are per backend run; a page that read events before a backend restart is told reset=true by /events (boot id) and redraws.

- Permission prompts cannot be answered from the panel; pick a level that allows the work.
- Browser tools only work while the Browser app is open inside Forge.
- Every message is real Claude Code usage and costs what a terminal session would.
- The second account (`second`) was created 2026-09-25; its sign-in waits for Emerson's code. Headless Chrome needs `--timeout=25000` instead of `--virtual-time-budget` on this page (the long polls never let virtual time end).

See README.md for how a message flows and WIP.md for what is verified.
