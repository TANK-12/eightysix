# Codec Player: work in progress

The code lives in `~/anime-codec-lab` (`web_player.py`, `static/player.html`),
a git repo with no commits yet; its first commit is Emerson's call.

## U1 sweep (2026-10-08, Relay task 74)
By Rin (relay-92-work), Relay task 92. Files changed in `~/anime-codec-lab`
(not committed there; originals in
`~/Forge/backups/2026-10-07-overhaul/sweep/codec-lab/`): `web_player.py`,
`static/player.html`; tests in `tests/test_u1_sweep.py` and `tests/check_ui.py`.

What changed:
- Memory: a `.acv` header asking for a huge frame count or size went straight
  into the decoder, which allocates it all (this machine has no swap, so that
  freezes it). The header is now checked against Codec Lab's memory budget
  (`core/limits.py`) first: too big is a 413 with the size it would need.
- A malformed header (string sizes, zero frames, bad fps, unknown strategy,
  params not an object), a truncated or non-.acv file: all 422 with a reason,
  never a 500. ffmpeg failing is a calm 500 message.
- A failed open leaves no folder behind in `results/player/` (it used to keep
  each bad upload).
- The open route was `async` but decoded synchronously, blocking the server
  for the whole decode; it is now a plain handler, so FastAPI runs it on a
  worker thread as the module docstring always said.
- Page: a second drop or click while decoding is ignored (one request); a file
  that is not a .acv gets a calm message without an upload; a file dropped
  beside the drop zone no longer navigates the page away; meta values are
  escaped; a spinner while decoding; the video pauses while hidden and carries
  on when shown; the drop zone works from the keyboard; thin scrollbars; a
  video that cannot play says so.

Verified: pytest (shared with Codec Lab) 55 passed; `tests/check_ui.py` player
part 9/9 PASS in headless Chrome (open, double open, play, pause while hidden,
resume, server down). black clean, pyright 0 errors. Screenshots:
`/tmp/u1/G18/shots/`.

Not verified: not seen in the real Forge window. `static/player.html` reaches
Emerson's Forge on the next page reload; `web_player.py` only on his next
Forge restart.

## U1 critic follow-up (2026-10-08, Relay task 92)
By Kaito (relay-92-work); critic report
`sessions/2026-10-07-overhaul/critics/u1-G18-critic.md`. Files changed in
`~/anime-codec-lab`: `web_player.py`, `static/player.html`,
`strategies/base.py` and every zlib strategy, `strategies/ffmpeg_baseline.py`.

- The memory guard could be sidestepped: it checked the `.acv` header, but the
  decoders allocate from a second size stored inside the compressed stream. A
  1.3 kB file asked for 250 GiB. Now each strategy refuses a stream whose
  inner size differs from the header (422), inflates zlib data only up to a
  bound from the frame size, checks keyframe PNG sizes before decoding,
  limits palette and block sizes; the ffmpeg strategy caps its output at the
  header's frame count and size.
- A header without `params` opened, decoded, then failed with a 500; it opens.
- A long error message wraps inside the error box at 760 px.

Verified: pytest 77 passed (tests include exactly the critic's 250 GiB file,
now refused with "the stream says ..." before any allocation, and a round trip
of every strategy so real files still open). check_ui player part all PASS,
including no sideways scroll with a 300-character error at 760 px.
