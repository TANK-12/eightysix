# Acchan

A local assistant that runs on Jan's small models and can act on the whole
computer: code and files, the shell, apps, windows and keystrokes, Firefox /
Forge Browser / terminal tabs, any media player (Qobuz included), video
transcripts and frames, whole-document questions over PDFs and web pages, and
the screen through OCR and vision. One backend serves four front ends:

| front end | how |
|---|---|
| Forge app (port 8451) | `static/` page; Claude and Study Companion embedded as tabs |
| terminal | `acchan` (full-screen Textual app) or `acchan "one message"` |
| Nyarch Assistant | its OpenAI provider points at `http://127.0.0.1:8451/v1`, model `acchan` |
| Claude Code / any MCP client | `mcp_server.py` (stdio), the same tools |

The backend is an always-on user service (`~/.config/systemd/user/acchan.service`),
so the terminal and Nyarch work without Forge open. Forge adopts the running
service instead of launching a second copy (the generic "already running"
check in `forge.py`'s `Backend.start`).

## Layout

| file | what it is |
|---|---|
| `acchan/registry.py` | `@tool` decorator, schema from the signature, argument repair, fuzzy names, discovery of `acchan/tools/*.py` |
| `acchan/tools/*.py` | one module per toolset; each declares `TOOLSET`, `TOOLSET_SUMMARY`, `TOOLSET_KEYWORDS`, `TOOLSET_EXAMPLES`, optional `TOOLSET_COMPANIONS` |
| `acchan/desktop.py` | Hyprland (hyprctl, wtype, grim) or GNOME (AT-SPI, ydotool, portal screenshots via `~/Forge/nyarch/screenview.py`) behind one interface |
| `acchan/atspi_helper.py` | runs under **system** python (PyGObject); lists windows, reads and presses controls in any accessible app |
| `acchan/spelling.py` | typo fixing before routing ("firfox" -> firefox), towards registry keywords, app and site names; dictionary words untouched |
| `acchan/memory.py`, `acchan/tools/memory.py` | long-term facts (remember/recall/forget) in `memory.json`, newest 15 in every prompt |
| `acchan/router.py` | fast path (plain commands, no model), chat/story/model-question detection, toolset choice from keywords |
| `acchan/prompts.py` | system prompt per tier: persona, environment, numbered rules, few-shot examples from the toolsets |
| `acchan/agent.py` | the loop: events out, one tool call per step, refusal nudge, loop guard, escalation, wrap-up |
| `acchan/llm.py` | Jan streaming client, tiers, per-request sampling |
| `acchan/conversation.py` | chats on disk: sticky `tier`, rolling `summary` of folded-out older turns, trimmed view |
| `acchan/client.py`, `acchan/tui.py` | terminal client (backend if up, else in-process) |
| `web_app.py` | FastAPI: `/api/chat` (SSE), conversations, status, tools, tabs, Jan settings, `/v1/*` OpenAI API |
| `mcp_server.py` | MCP stdio server over the registry |
| `tests/test_core.py`, `tests/test_tui.py` | deterministic tests (no Jan, no desktop) |
| `tests/eval_prompts.py` | prompt evaluation against the real models with stubbed tools |

## Adding things

- **A tool:** a function with `@tool(TOOLSET, example={...})` in the right
  module, `Annotated[type, "meaning"]` parameters, and a docstring whose first
  paragraph tells the model when to use it. Nothing else.
- **A toolset:** a new module in `acchan/tools/` with the five module constants.
- **A fast-path command:** a pattern in `router._one`. Only unambiguous
  phrasings; anything uncertain must return None and go to a model.
- **A tab:** the app name in `forge_app.json` `"tabs"`.

## Which model answers

Default ("Auto (one model)"): every chat starts on the 0.8B (`llm.START_TIER`,
env `ACCHAN_START_TIER`) with tools on, and stays there, so Jan keeps one model
loaded. Two failures step it up one size, and the chat stays on that size
(`Conversation.tier`). "Switch per message" is the old per-message ladder;
picking a size in the menu pins that size. "What model is this" is answered
from the settings, never by a model.

## How it copes with small models

Measured facts drive these (see WIP.md for the numbers):

1. Plain commands skip the model entirely (fast path, about 0.3 s).
2. Only the toolsets a message needs are offered (2 for the 2B, 3 for the 4B),
   plus companions such as `find_files` for documents.
3. Tool calls are repaired: fuzzy names, coerced types, a lone wrong argument
   name mapped to the missing one, calls written as text parsed.
4. Tool errors say how to fix the call; the model usually fixes itself.
5. Apologising instead of acting gets one nudge ("You do have tools").
6. The same call twice is refused; two failures move up a tier (and stay up).
6b. Typos are fixed before routing; Qwen's XML tool-call text is parsed; a
   reply that copies an earlier one is asked for again once.
6c. Chats longer than the budget are summarised by the loaded model (the
   summary rides at the end of the system prompt), not silently dropped.
7. Tools do multi-step work themselves where small models lose the thread:
   `whats_on_screen` returns the page text, `ask_document` retrieves the right
   passages of a long document, folder names like "my Forge folder" resolve.
8. The prompt prefix is stable per conversation, so llama.cpp's cache makes a
   follow-up cost only its new tokens (measured: 15 new tokens, 0.36 s).
9. Sampling is per request (thinking off, presence penalty 0, low
   temperature), so the user's own Jan model settings are never touched.

## Run

```
systemctl --user restart acchan      # after code changes
tail -f ~/Forge/outputs/acchan.log   # backend log (the service appends here)
acchan                               # terminal
.venv/bin/python -m pytest -q tests  # tests
.venv/bin/python tests/eval_prompts.py small medium   # prompt eval (needs Jan, minutes)
```
