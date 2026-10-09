# What one short `claude -p` answer costs, plain versus lean

date: 2026-10-07 · for: both

Measured by Kenji (Relay task 72), default account, model sonnet, effort low,
prompt "say hi", `--max-turns 1 --no-session-persistence --tools ""`,
read from `--output-format json` usage:

| form | extra flags | input | cache write | time |
|---|---|---|---|---|
| plain | none | 2 | 31,555 | 2.3 s |
| lean | `--system-prompt <own> --setting-sources "" --strict-mcp-config` | 405 | 0 | 1.8 s |

The plain call loads Claude Code's own system prompt, CLAUDE.md, memory,
the output style, hooks and MCP tool lists: about 31.5k tokens before the
question. The lean form sends only its own system prompt and the question.

Used by Relay's `oneshot.py` (the WhatsApp boss line, about 5,000
characters of state per question, ~2k tokens). `--bare` would be leaner
still but needs an API key, so it does not work with the subscriptions.

Boss line end to end, same evening: opus, effort low, live Relay state,
answer back in 10 s.
