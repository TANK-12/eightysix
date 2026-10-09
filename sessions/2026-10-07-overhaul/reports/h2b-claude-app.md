# H2b Claude app: critic fixes, slash commands, self-run commands
date: 2026-10-07 · for: both · helper-2 (Rei), crew overhaul

**Checks passed.** `.venv/bin/python -m pytest -q tests`: 192 passed, three runs in a row (it was 156). New tests are in tests/test_lost_messages.py, tests/test_panel_commands.py, and tests/markdown.test.js (run from test_enjoy_js.py). black was run on the touched Python, and pyright shows 0 errors on runner.py, web_app.py, browser_mcp.py, panel_commands.py and the new tests. Headless screenshots of both layouts at 760, 1100 and 1500 px were looked at; four of them are beside this file (h2b-*.png). Nothing was committed.

**All of it needs the Claude app restarted in Forge.** Port 8445 still runs the old code; it was not touched.

## Behaviour critic (B1-B13)
- B2 (likely the cause of the "message gets lost" report): fixed. After a backend restart the page's event numbers no longer matched the server's, so it waited forever for new events. /events now returns `boot` and `reset`, and both layouts redraw the conversation when the backend has restarted.
- B1 / B13: fixed. stop, close and send share one lock, so a message can no longer land in a process that is being ended.
- B3: fixed. A message is written before it is recorded; a broken pipe restarts the process and writes once more; a failed send leaves nothing behind (503).
- B4: fixed. A long poll gathers for 90 ms after the first new event, so 30 words take at most 8 round trips instead of 30.
- B5: fixed. A mid-turn setting is no longer forgotten when a message is also sent in that turn. If that message was folded into the running turn, the setting applies one message later; this trade-off means no message can be lost.
- B6: fixed, browser-checked by the critic. Send cannot fire twice; the input is cleared at once and put back if sending fails.
- B7-B9: fixed. Wrong types get a 400; nan, inf and 1e999 limits are ignored; `archived` must be a real true/false; `files` must be a list of strings.
- B10: fixed by code. The tab refresh and the other polls now run through ForgeIdle, so they pause while the page is hidden.
- B11: fixed by code. The pulsing dots stop while hidden, with animations off, or with reduced motion.
- B12: fixed. Conversation settings are copied in one step before they are saved or sent (meta snapshot).

## Look critic (L1-L15)
Fixed and screenshot-checked:
- L1: the Enjoy side menu becomes a strip along the top below 900 px.
- L3: thin, quiet scrollbars.
- L4: the tab bar has no vertical scrollbar and the + button stays in view.
- L5: Markdown tables are drawn.
- L7: the classic header is one title row plus one settings row (300 to 118 px tall at 760 px wide). The Limits panel is pinned so the settings row cannot clip it.
- L8: Enjoy views keep room at the bottom for Forge's Close app and Full screen buttons.
- L10: web logins start folded, and the chat list keeps at least 30% of the height.
- L11: the avatar pane is narrower while the avatar is off.
- L12: a crash shows as a card and is listed under needs you.
- L13: no double full stop after a name, and long names clamp to two lines.
- L14: the Enjoy setting pills have a minimum width.
- L15: an unset limit slider hides its handle.

Fixed but not screenshot-checked:
- L2: /api/options answers in 0.02 s; `claude --version` now runs on a background thread.
- L6: same fix as B10.
- L9: the Enjoy limits panel closes when you move to another page.

## Commander asks
1. **/compact sent as plain text:** fixed. A message starting with / now goes to Claude Code with no persona tag and no extra spaces. Checked live with the real CLI (2.1.289, haiku, scratch server): /compact compacted the conversation (28,428 to 4,405 tokens), and the page shows a "conversation compacted (from 28k tokens)" divider. /context's tables render.
2. **Claude can run commands on itself:** done. The new `panel_command` tool (`panel_commands.py` holds the list: compact, context, usage, recap, rename) queues a command per conversation, and the runner sends it as the next message when the turn ends. The page shows "Claude asked to run /context". Checked live: Claude found the tool, queued /context and ended its turn, and the panel then ran /context.
- **Found on the live check:** the cost figure was too high. Claude Code reports a running total for the session, and the app was adding it up turn by turn. It now keeps the latest total per session; older conversations keep their too-high figure, labelled "earlier".

## Second critic pass (critic subagent)
The critic broke three things and raised several smaller points; each fix below has a test.
- A message could be dropped when the process restarted for a settings change during 1 s of silence. Fixed.
- One broken emoji half (a lone surrogate) caused 500 errors on the event and conversation lists. Fixed: responses are ASCII-escaped and text is cleaned on the way in.
- The command queue lost or doubled commands when written and read at once. Fixed with a file lock.
- One malformed queue line jammed the queue for good. Fixed: bad lines are dropped.
- A reply could appear before the user's own message. Fixed.
- A slash command with spaces in front was sent unstripped. Fixed.
- A stale close flag after a crash ended the next process after its first turn. Fixed.
- More polls now pause while the page is hidden.

## Left open
- Busy can still read false while a new turn stays silent for more than 1 s. This is old behaviour; the real CLI sends status events at once.
- The classic settings row scrolls sideways by design.
- Nothing was checked in the real WebKitGTK window.

## Files
- In ~/Forge/apps/claude: runner.py, web_app.py, browser_mcp.py, panel_commands.py (new), the static/ pages and styles, the tests, WIP.md (newest section) and MANIFEST.md.
- Backups: ~/Forge/backups/2026-10-07-overhaul/claude-2/.
