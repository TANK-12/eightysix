# Claude

Claude Code inside Forge (port 8445, role `claude`). A chat panel over the
local `claude` CLI that can use the **Forge Browser**, takes **attached files**,
and opens links from its answers in the Browser.

## Layout

| file | what it is |
|---|---|
| `runner.py` | One `claude -p` process per conversation in stream-json mode; history on disk; resume by session id; the `MODES` and `MODELS` tables. |
| `browser_mcp.py` | MCP server (stdio, stdlib only) giving Claude the Forge Browser tools. |
| `web_app.py` | FastAPI: conversations, long-poll events, uploads, attach the Browser's page, open links. |
| `static/` | The chat page. |
| `tests/` | `test_claude_panel.py` against `fake_claude.py`, which speaks the real CLI's stream-json. |

## How a message flows

```
page --POST send--> web_app --stdin {"type":"user",...}--> claude -p (stream-json)
claude --stdout events--> runner (records, disk) --long poll--> page draws them
claude --MCP tools/call--> browser_mcp.py --POST /api/agent/do--> Browser app
Browser page (in Forge) --long poll /api/agent/next--> runs it on real pages --> result
```

The command line is built in `runner.command()`: `--input-format stream-json
--output-format stream-json --verbose --include-partial-messages`, the MCP
config, `--permission-mode <level>`, `--permission-prompts none`,
`--allowedTools Read,Glob,Grep,WebSearch,WebFetch,mcp__forge-browser`, the
conversation's attachment folder via `--add-dir`, a short system note, and
`--resume <session id>` after the first run.

## What Claude can do

Set per conversation in the header ("Can"): read and browse (default), plan,
edit files, Claude Code's auto mode, or everything. There is nobody to answer a
permission prompt, so anything that would prompt is refused.

## Accounts

Two Claude subscriptions, one panel. The list under the conversations shows
each account: its sign-in (email), a bar for its 5-hour window (from the
`rate_limit_event` the CLI streams with every answer; the tooltip has the
reset times and the 7-day window; there is no other machine-readable usage
in the CLI, so the bar appears after the first answer on that account), and
the active one. Clicking an account makes it the active one for new
conversations **and carries the open conversation over**: Claude Code only
resumes a session under the config directory that wrote it, so the transcript
(`<config>/projects/<folder>/<session>.jsonl`) is copied across, never
removed. Without one to copy, the next message starts a fresh session and the
page keeps the history.

"default" is Claude Code's own `~/.claude`; the panel never signs it out or
writes to it beyond that transcript copy. Every other account is its own
`~/.local/share/forge/claude/profiles/<name>/`, passed as `CLAUDE_CONFIG_DIR`,
so it starts empty (no global CLAUDE.md, skills or settings) and gets its own
sign-in. **To add the second account:** "+ add", give it a name, then sign in
as that account in the browser window the CLI opens (sign out of the other
account there first, or use a private window); if nothing opens, the box shows
the address and takes the code the page displays. Remove (×) deletes that
profile directory and its sign-in; the default cannot be removed.

Routes: `GET /api/profiles`, `POST /api/profiles {name}`,
`DELETE /api/profiles/<name>`, `POST /api/profiles/<name>/activate
{conversation?}`, `POST/GET /api/profiles/<name>/login`,
`POST .../login/code {code}`, `POST .../login/cancel`; a conversation's
`settings` also take `profile`.

## Data

`~/.local/share/forge/claude/`: `conversations/<id>.json` (settings, session id,
profile, cost), `conversations/<id>.jsonl` (events, without live text deltas),
`attachments/<id>/`, `mcp.json`, `profiles.json` (active account, last usage
per account), `profiles/<name>/` (a second account's Claude Code config dir).

## Run and test

```sh
cd ~/Forge/apps/claude
FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8445
.venv/bin/python -m pytest tests -q      # 20, free: uses tests/fake_claude.py
```

`FORGE_CLAUDE_BIN` replaces the `claude` command (the tests use it);
`FORGE_CLAUDE_DATA` moves the data folder; `FORGE_BROWSER_URL` points at the
Browser backend.

## Avatars, personas and voice

The right pane shows the persona answering this turn as a live avatar. Its
parts are `personas.py` (the registry, mood picking, the system prompt and
tags), `voice.py` and `tts_worker.py` (Kokoro), `static/stage.js`, and the
Avatar Studio (`static/avatars.html` and `avatars.js`). The avatar engine and
the storage are shared: `~/Forge/shared/forge_avatar.js`,
`~/Forge/shared/forge_avatars.py` and `~/Forge/shared/avatars/`.

- To add a persona, add one file in `personas/`.
- To add a motion, add one entry in `shared/avatars/motion_recipes.json`, or
  save one from the Studio.
- To add a Live2D model, drop its folder in `shared/avatars/live2d/`.
