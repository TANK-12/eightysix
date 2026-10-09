# Emberfield — work in progress

The long-form record is `MANIFEST.json` plus `manifests/session-NN.json`; this
file holds the short notes from sweeps that were not full sessions.

## U1 sweep (2026-10-08, Relay task 74)
date: 2026-10-08 · for: both · Noa (relay-81-work, Relay task 81, group G6)

What changed:
- **One frame loop, always.** Every start of play goes through `kickLoop()`
  (index.html), which keeps one pending frame. Before: a double click on
  Begin, or a quick pause then resume, started a second (or fourth) loop, so
  the game ran at double speed or more until reload.
- **No double submits.** Begin and Continue wait for the valley they already
  asked for (`S.starting`); the cave mouth and house doors ignore a second press
  while the map is on its way (`S.travelling`). Before: two quick presses at the
  cave mouth parked the first cavern as if it were the valley, losing the valley
  (crops, worked ground) for the session.
- **Calm errors and recovery.** New `api()` helper (throws with the server's
  reason on a failed request). Boot failure shows "could not start yet" and
  retries by itself (2, 4, 8 … 30 s, not while hidden) plus a Try now button.
  Begin, Continue, the wilds, doors and Settings say what went wrong in a toast
  instead of an unhandled error. Save & leave stays on the pause screen if the
  save failed (before: it left anyway and the day was lost). Any failed save is
  announced, even a quiet one; a 500 no longer counts as "saved".
- **Rest when hidden or paused.** Pausing (also by the hub hiding the app or the
  tab going hidden) suspends the audio clock (`Sound.rest()`; the next key or
  click wakes it) and stops the 400 ms tutorial check; resume restarts both.
  Waking from sleep while off screen opens the pause screen instead of running
  the game behind other apps.
- **Layout.** Below 1700 px the tutorial box sits above the hotbar; below
  1250 px the key hint moves to the top right, the tutorial under it and toasts
  to the bottom. Before, tutorial, hint and hotbar overlapped at 760-1500 px.
  Thin styled scrollbars on the menu veil (incl. `::-webkit-scrollbar`), menu
  cards ease in (opacity/transform, 180 ms), the hotbar's lifted slot slides,
  `prefers-reduced-motion` honoured. Save names and server messages are escaped.
- **Settings are type-checked** (`config.clean_settings`): a wrong type is a 422
  and changes nothing, numbers are clamped (cores 1-64, day 20-86400 s, volume
  0-100, zoom 1-8), a bad value already in `~/EmberfieldData/settings.json`
  falls back to its default on load. Before: `{"heavy_cores": "abc"}` was
  stored and `/api/capabilities` then failed forever, so the game never booted.
- **Caching.** Script tags carry `?v=2026-10-08` (bump it when a script
  changes) and the backend sends `Cache-Control: no-cache`. Found when a
  browser profile kept the old `ui.js` and the new page never booted.
- Typed seeds too long to hold exactly are hashed (`seedFrom`).

Verified:
- `pytest -q tests`: 130 passed (new `tests/test_api.py`, 7 tests: settings
  types, clamping, refused patch changes nothing, poisoned file heals, the
  page's own settings accepted, save slots, no-cache header).
- `tests/check_ui.py` (headless Chrome, new): 15/15 pass on the new code; the
  same script against the old code failed boot retry, double Begin (2 requests,
  60 doubled frames), pause/resume (240 doubled frames) and crashed on the
  double wilds press (valley lost).
- In-game selftest `/?seed=777&selftest=1`: PASS 64/64.
- Server stopped mid-game: toasts, 0 background requests, recovers by itself
  when back. 10 s hidden: 0 fetches, 0 frames, 0 timers, audio suspended.
- Screenshots at 760/1100/1500/1920 before and after (/tmp/u1/G6/shots/).
- black and pyright clean on the touched .py files.

Critic follow-up (critic report `sessions/2026-10-07-overhaul/critics/u1-G6-critic.md`,
all five verified breaks predate the sweep, all fixed):
- Escape on a death screen used to resume play (0 hp, no day passed) and could
  undo a full permadeath; it now does nothing there or during the sleep fade
  (`S.dead`, `S.sleeping`). Full permadeath clears `S.world`, so no later save
  (including the one sent on closing the page) writes the deleted valley back;
  the frame loop stops cleanly when a death inside a frame closed the valley.
- Settings ranges now match the sliders (zoom 2-5, day 60-1800 s) and unknown
  keys are refused (422), so nothing unbounded lands in settings.json.
- A damaged save says "that save is damaged" instead of a raw JS error.
- Long save names wrap inside the title card.
- The selftest script is added once even if a `?seed=` boot retries.
- Script stamp bumped to `?v=2026-10-08b`.
- Checks after the fix: pytest 130 passed (test_api extended), check_ui 18/18
  (new: escape on death, death inside a frame, full permadeath stays dead after
  escape and a reload; the in-frame death check fails with the loop guard
  removed), selftest PASS 64/64, black and pyright clean.

Not verified:
- Inside the real Forge window (WebKitGTK). Static changes reach it on the next
  reload of the Emberfield page; the settings check and no-cache header only
  after Emerson's next Forge restart.
- Nobody has played the changed build by hand.
