# Logins: work in progress

## U1 sweep (2026-10-08, Relay task 74)
Worker Itsuki (relay-80-work), Relay task 80. Static files only; they reach
Forge on the next page reload. Nothing removed.

- **First load**: if the backend is not up yet or `accounts.json` has a
  mistake, the start card says which and tries again by itself through
  `ForgeIdle.poll` (2 s growing to 30 s, resting while hidden), with Try now.
  It used to show "Pick an account above" with no tabs and a one-line
  status, and never retried. An empty registry says "No accounts yet".
- **Sign in in Firefox** is locked while its request runs (a double click
  could open two windows). **Bring login in** stays locked until forge.py
  confirms the cookies, or 20 s at most, then says Forge did not confirm.
- Tabs are buttons now (keyboard focus and Enter work), with a focus ring
  and short hover transitions; the tab strip's scrollbar is hidden in
  WebKitGTK too (`::-webkit-scrollbar`), other scrollbars thin and themed.
- A cookie confirmation for an account that is gone no longer throws.

Verified (headless Chrome, scratch server on 8952 with a sandbox
accounts.json and data dir; no real Firefox profile or cookie was read):
0 callbacks in 10 s visible, hub-hidden and document-hidden; server killed:
calm card, 2 then 2 `/api/accounts` asks (0-10 s, 10-30 s), tabs back by
themselves after the restart; Sign in triple click sent one request; with a
simulated hub parent, Bring login in triple click read the cookies once and
sent them once, unlocked on the confirmation (navigate sent) and after 21 s
with no answer. pytest 7 passed. Not verified inside the real Forge window
or with a real signed-in account.

Critic follow-up (same day): Bring login in waits per account (another
account's button is free, and a timeout names the account); a plain mouse
wheel scrolls the tab strip sideways, and the chosen tab scrolls into view;
the retry card puts a full stop after an accounts.json error. Verified with
`/tmp/u1/G5/fixcheck.py` (`fixcheck.out`): A locked, B free, back on A
locked, A unlocks on its confirmation; 30 tabs at 760 px, wheel moves the
strip 400 px, tab 25 in view (`/tmp/u1/G5/shots/fix-logins-many30-760.png`);
g5check re-run all pass, pytest 7 passed.

## 2026-09-25: new app, not yet seen inside Forge

Built and tested (7 backend tests, standalone page screenshot, per-session
cookie stores in tests/test_views.py). Not verified: the views inside the
real Forge window (Forge needs a restart for forge_views.py and to discover
this app), and Bring login in with a real signed-in account. See
../../docs/DESKTOP-REACH.md.
