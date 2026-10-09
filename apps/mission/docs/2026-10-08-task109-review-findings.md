# Task 109 review findings (Mission Control chat rebuild)
date: 2026-10-08 · for: both

Three Opus reviewers (critic, creative art director, "Emerson lens") on the
rebuilt Conversations view, session 8. Status per item: open / fixed / kept
(decided not to change, with why). Updated as fixes land.

Session 13 (2026-10-08): every item below was fixed in sessions 9, 11 and 12;
how each was checked is in brackets ("code read" means no test covers it).

## Critic (tried to break it)
- C1 fixed: FastAPI's bare "Not Found" from /api/claude/ or /api/relay-chat now reads "Mission's server is older than this page: close Mission in Forge's top bar and open it again" (browser test test_reading_extras). The live server still needs that one Close + reopen. Was: live Mission server on :8465 runs code from 06:03, so /api/claude/* and /api/relay-chat answer 404 in Forge (Emerson: Close Mission in Forge's top bar, open it again).
- C2 fixed: a send that finishes after a chat switch only updates its own chat (live guard; code read, not browser-tested). Was: a send finishing after a chat switch paints the new chat (applyMeta without live()).
- C3 fixed: drafts are kept per chat (browser test test_reading_extras). Was: the unsent draft is lost on every chat switch (open/openRelay clear the box).
- C4 fixed: a chat that cannot open retries in place with backoff and leaves the box alone (code read). Was: a Claude chat that cannot open wipes the box every 8 s (retry goes through open()).
- C5 fixed: ForgeConvo.filesBase (default "/api", Mission sets "/api/claude") + GET /api/claude/conversations/{id}/files/{name} image proxy, image types only, 40 MB cap (pytest test_claude_proxy). Was: pictures in Claude-app chats 404 (renderer points at /api/conversations/{id}/files/..., Mission has no such route).
- C6 fixed: a link click asks the Claude app to open it (POST /api/claude/open-link, http and https only), window.open as fallback (pytest + browser test). Was: links in replies do nothing (a[data-url] without href; Mission has no click handler).
- C7 fixed: sending state and pending lines are kept per chat for up to 10 min, so Send in one chat cannot resend another's line (code read + node test sameLine). Was: the "sending..." line goes after 60 s or on a chat switch; Send is shared across chats, so a pending WhatsApp line can be sent twice.
- C8 fixed: Chats panel keeps the calm order, has sections and a folded Archived group (node chatSections/chatOrder + browser test). Was: Chats panel and Alt+Up/Down re-sort by live activity (ignores the calm order of note 1316), no Archived section.
- C9 fixed: the popover is only repainted when its HTML changes (code read). Was: the popover is rebuilt on every overview change, so a click can be lost.
- C10 fixed: the name sits in .fx-who-txt with an ellipsis; tag and pill stay (CSS, code read). Was: at 1100 px and below the header name has no ellipsis; persona tag and state pill pushed out.
- C11 fixed: `relay as-whatsapp` finds its own line by sequence overlap, not by counting (relay test, red first). Was: `relay as-whatsapp` can log a plain line twice when the 40-line window is full and the dropped line had the same text.
- C12 fixed: the pending line matches Relay's copy with whitespace collapsed (node test sameLine). Was: a multi-line WhatsApp line shows twice for up to 60 s (Relay collapses blank lines; the ghost match fails).
- C13 fixed: chat.reply logs the answer even with WhatsApp off (relay test, red first). Was: with WhatsApp off, chat answers never reach Messages (Relay chat.py reply returns before logging).
- C14 fixed: empty, negative or non-number sizes are ignored and the size is clamped (node test sizeFrom). Was: an empty or negative text-size number drops the text to 14 px.
- C15 fixed: a failed send shows a toast; Esc closing a panel puts focus back in the box (code read). Was: a failed Claude send only flashes a status line; after Esc closes a panel the composer loses focus.
- C16 fixed: drops are refused (prevented) on chats that take no files (code read). Was: dropping a file on a WhatsApp, terminal or Jan chat may open the file in the window.
- C17 fixed: day chips use real dates: Today, Yesterday, weekday within the week, then the date (node test waRuns + browser test). Was: WhatsApp day chips only know weekdays, so a line from last week reads as today.

## Emerson lens (how he will see it)
- L1 fixed: same as C1. Was: (same as C1) "it says not found".
- L2 fixed: short in-between lines (up to ASIDE_MAX characters) fold into the turn's steps bar; his message and the final answer stay out (browser test test_reading_extras). Was: his messages drown: 230 of 239 Claude bubbles in one chat are short status lines; fold each turn's in-between lines into its steps bar, keep his message and the final answer.
- L3 fixed in part: round 52 px busts with a speech tail (K3) and the session's chibi standing beside the composer (K9); the stars stay static on purpose (Mission is low power). Was: not anime enough: faint stars and small 46 px sprites.
- L4 fixed: on Relay runs the popover says in one line why model and effort are fixed (code read). Was: on Relay runs model/effort are greyed out with no plain reason.
- L5 fixed: shortTitle turns file paths into words (shared/forge_session_title.js, node test logic 9/9). Was: names that are file paths ("~/Forge/sessions/2026-10-08-ai-studio-new-m...").
- L6 fixed: small print follows the size (--fx-s/--fx-m) and the header has A- and A+ (browser test). Was: only the message text follows the size slider; chip, times, tags, buttons stay 12-15 px; no quick A-/A+.
- L7 fixed: sections, Archived fold, names with an ellipsis. Kept: no New chat button (new chats start in the Claude app; Mission opens existing ones). Was: Chats panel not calm, no Archived, names cut at about 25 characters, no New chat.
- L8 fixed: twin Sonnet cards get different blurbs, Default effort comes first, turn ends read "took 18 min" with no dollars (node test modelCards/tookWords). Was: two Sonnet cards with the same words; "Default" after Max looks like a sixth level; turn ends show "1070.5s · $17.34".
- L9 fixed in part: the row shows the last line, WhatsApp bubbles have their own tint. Kept: only the last 40 lines and no pictures (Relay keeps 40 lines). Was: WhatsApp mirror only the last 40 lines, no pictures, same boxes as the Claude chat, row shows no last line.
- L10 fixed: a log chat loads up to 3 earlier pages until the column fills; Relay runs get a Stop that needs two presses (POST /api/relay/tasks/{n}/stop; pytest + browser test). Was: Relay chats open nearly empty (one page); no Stop for Relay runs.

## Creative (art director, CSS tested in the real page)
- K1 fixed: short chats sit on the composer (session 9 CSS). Was: short chats float at the top with 360 px of sky above the composer: sit them on the composer.
- K2 fixed: steps bars are quiet pills (CSS). Was: steps bars as quiet pills.
- K3 fixed: round 52 px bust portrait with a speech tail (CSS). Was: MomoTalk-style round bust portrait and speech tail.
- K4 fixed: popover is a two-column grid at 980 px and wider (CSS). Was: popover as a two-column grid at 980 px and wider (fits 1100x657 without scrolling).
- K5 fixed: same as L5. Was: plain titles from paths (same as L5).
- K6 fixed: bubbles stop at 36em (CSS). Was: line length about 36em (75 characters).
- K7 fixed: same as L6. Was: small print follows the size slider (same as L6).
- K8 fixed: quieter header, borderless buttons (CSS). Was: quieter header (borderless buttons, pastel underline).
- K9 fixed: #fxStage chibi beside the composer (still frame). Was: the session's chibi standing beside the composer (still frame, 8x).
- K10 fixed: the gap is set on .view, where the messages sit (CSS). Was: `.fx .fc.fx-log { gap }` never reaches the messages (they sit inside `.view`).
