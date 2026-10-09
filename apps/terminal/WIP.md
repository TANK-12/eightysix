# Terminal: WIP

## U1 sweep (2026-10-08, Relay task 74)
Tomo (relay-79-work, Relay task 79), group G4. Changed:
- Reconnects back off: a pane that loses its socket writes one dim line
  "[lost the Terminal backend; reconnecting]" and retries 1.5 s doubling to
  30 s (was every 1.5 s forever), not at all while out of sight, and at once
  when the info poll reaches the backend again.
- After a backend restart the page used to retry forever with its old token
  (a close before accept reaches a browser only as 1006, so the 4404 "shell
  gone" code never arrived). The backend now accepts a same-origin socket and
  closes it with 4403 (stale token: the page fetches a new one) or 4404 (the
  shell is gone: the pane says so and Enter closes it). Foreign origins are
  still refused before accept.
- Another window attaching to the same shell now closes the old page's socket
  with 4409: that pane says "open in another window; press a key to bring it
  here" instead of taking the shell straight back (two windows used to swap
  it every 1.5 s).
- Malformed socket messages (not JSON, not an object, bad resize numbers, a
  non-string "in") are ignored; they used to crash the handler with a
  traceback and drop the socket. A token with non-ASCII characters is refused
  instead of raising.
- `refreshInfo` returns false on failure; poll `{ backoff: 2, maxMs: 30000 }`
  (break 6).
- Booting while the backend does not answer shows a calm card ("Can't reach
  the Terminal backend ... Retrying by itself", Try now) and retries 1.5 s
  doubling to 30 s; it used to toast once and stay blank for good.
- Looks: menu, find bar and the card fade in (150-200 ms, reduced motion
  honoured); tab colour transitions; the tab strip hides its scrollbar in
  WebKitGTK too (`::-webkit-scrollbar`), the mouse wheel scrolls many tabs
  sideways and the active tab scrolls into view.
**Verified:** pytest 14 passed (3 new: close codes, malformed messages,
takeover 4409); black, pyright 0 errors; `tests/check_ui.py` 40/40 PASS;
`/tmp/u1/G4/check/termcheck.py` (headless Chrome, scratch 8940): hidden 10 s
0 fetch/ws/timer (hub signal and document hidden); server killed: 1 fetch +
3 socket tries in 0-10 s, 2 + 1 in 10-30 s, 0 while hidden; restarted: the
pane marked gone in 3.6 s, new tab works; takeover note and key-to-return
work; boot card shows and recovers by itself; no page errors. Screenshots at
760/1100/1500/1920 looked at (`/tmp/u1/G4/shots/term-*`).
**Not verified:** inside Emerson's Forge window (WebKitGTK). The page changes
arrive on the next reload of the app; the `web_app.py` close codes only after
his next Forge restart (until then the new page behaves as before on a
restart, with the slower retry).
- Critic follow-up (u1-G4-critic.md): a binary frame or a lone surrogate
  (`"\ud800"`) in an "in" message used to crash the socket handler (the page
  then said the backend was lost); both are now ignored or written as "?"
  (test_malformed_messages_are_ignored covers them, red before the fix). The
  page's `api()` calls give up after 15 s, so a backend that takes the
  connection but never answers lands on the retry card instead of a blank
  page (reasoned, not reproduced: AbortSignal.timeout).
  Not fixed: with many tabs at 760/1100 px the hub's "Full screen" and
  "Close app" buttons (shared `forge_chrome.js`) wrap to two lines; each lost
  pane retries on its own schedule (31 attempts in 10 s with 15 panes).

## State (2026-09-26, Tools / S9 ejb-ea)
Built this session. Verified: 10 pytest pass; `tests/check_ui.py` 16/16 PASS in headless
Chrome; htop screenshot looked at (colours, layout, tab named "htop"). Not yet seen inside
the Forge window itself (needs a Forge restart, Emerson's call). Claude Code image paste
(Ctrl+V) is checked only as "the 0x16 byte reaches a raw-mode program"; a real
`claude` run with an image on the clipboard is still to try.

## Improve next
1. DONE (ejb-83, 2026-09-27): find in scrollback. `@xterm/addon-search` 0.16.0 (MIT, the
   release matching xterm 6.0) vendored as `static/vendor/addon-search.js`. Ctrl+Shift+F or
   right-click > Find… opens a bar top-right: live "n of m" count, every match highlighted,
   Enter / Shift+Enter or the arrows step, toggles for match case, whole word and regular
   expression, Escape closes and hands the keyboard back. Switching tabs re-runs the search
   on the new tab. Verified: `tests/check_ui.py` 23/23 PASS (7 new find checks) and the
   find-bar screenshot looked at; 11 pytest pass. Not yet seen inside the Forge window.
2. DONE (Nagi, ejb-6b, 2026-09-27): split panes. Each tab holds a tree of panes, each its
   own shell (a split is {dir row|col, ratio, a, b}; `panesOf`, `layout`, `split`,
   `closePane`, `moveFocus` in static/app.js). Ctrl+Shift+D splits right, Ctrl+Shift+E
   splits down, Ctrl+Shift+arrows move focus (Alt+arrows are Forge's app keys),
   Ctrl+Shift+W closes the focused pane (its neighbour takes the space; the last one
   closes the tab), the tab's x closes the whole tab. Split buttons in the bar and
   Split right/down/Close pane in the right-click menu; a divider drags to resize; the
   focused pane gets a thin accent outline and the tab shows a pane count. The layout
   (tree, ratios, focus) is saved in localStorage by shell id, so a reload puts the
   panes back. Nothing changed server-side: a pane opens its shell like a tab did.
   Verified: tests/check_ui.py 40/40 PASS (17 new: 2 and 3 live shells each echoing
   their own input, right/below placement, own screens, focus left/right with typing
   landing in the focused pane, a real mouse drag of the divider refits the terminal,
   reload keeps panes, shells and divider, close frees the space and hands the keyboard
   over); pytest 11 pass; split screenshot looked at. Not yet seen inside the Forge
   window (needs a Forge restart).
3. Shells survive a Forge restart (would need a small detached host process; today
   closing Forge ends every shell, like closing any terminal).
4. DONE (S17, 2026-09-27): the WebSocket token is masked in `outputs/terminal.log`
   (`HideToken` log filter; unit test plus a live socket check: the log shows `t=…`).
