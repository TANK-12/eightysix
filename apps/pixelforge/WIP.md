# PixelForge — work in progress

## U1 sweep (2026-10-08, Relay task 74)
Done by Kaito (relay-86-work, Relay task 86, group G11). Static changes reach
Emerson's Forge on the next page reload; the `web_app.py` guards only after
his next Forge restart (not restarted by this session).

### What changed
- Looks: links `/shared/forge.css` (the frontend contract) and keeps only its
  own accent; the page's neutrals are now the shared theme's (they were a
  purple-tinted copy). `color-scheme: dark` from forge.css also gives native
  selects and number spinners their dark variants in WebKitGTK. The middle
  column keeps its glow, mixed from the accent. Thin themed scrollbars
  (incl. `::-webkit-scrollbar`), a 180 ms fade when switching Sprites /
  Sounds / Ask Jan (off under reduced motion), narrower side columns under
  900 px, ellipsis on the long library path in the header. The waveform is
  drawn at its shown width (it was a 720 px picture stretched at 1500+ px).
  Ask Jan shows a short "describe something" note instead of an empty dark box.
- Rest when hidden: the frame preview (▶ play) runs on `ForgeIdle.poll`, so
  it stops outright when hidden (before: a timer kept firing and skipping).
  The audio context is suspended when the page goes out of view and resumed
  by the next ▶ play. The 1 s "drawing… Ns" counter also pauses hidden.
- Robustness (page): first load that fails shows a calm card ("The art
  library is not answering yet", Try now) and retries by itself, 2 s
  doubling to 30 s, only while shown (before: blank editor, uncaught error,
  no retry). Save pack / Save palette / Save sound / Keep: one request per
  press, a calm toast when the server is down. Sounds that fail to load show
  Try again (before: stuck empty for the session). Ask Jan opened twice fast
  no longer lists every size twice. A pack with no sprites shows a note and
  the frame buttons say "Pick or make a sprite first" (before: exceptions).
  New sprite / sound names that clean to nothing are refused; new sprite size
  is clamped to 1-128 (a typo of 16000 used to freeze the tab). A bad hex
  colour says so instead of doing nothing.
- Robustness (backend): `POST /api/art/packs` with a null or number sprite
  was a 500, now 422 with a reason. `keep-sprite` checks palette and pack
  before writing either (it used to save the merged palette first, then 500
  on a bad sprite, leaving colours merged in). `keep-structure` refuses a
  plan outside 1-64 a side, wrong row count or width, keys with no tile
  (it saved width -1 made of numbers). `POST /api/sounds` refuses a wrong
  type or non-finite number for any known field and names over 200 chars
  (a 300 kB name and `"freq": "high"` both went to disk). All 36 real sounds
  in ~/ForgeGameData pass the new check.

### Verified
- `tests/`: 43 passed (26 old + 17 new in `tests/test_u1_robustness.py`,
  temp data dirs, no Jan calls). black clean, pyright 0 errors on
  `web_app.py` and the new test.
- Headless Chrome on a scratch copy (port 9010, copies of the art and game
  data, Jan URL pointed at a dead port), scripts in `/tmp/u1/G11/`:
  `pfcheck.py rest`: playing preview, hub-hidden 10 s and document-hidden
  10 s: 0 fetch / 0 timer / 0 interval / 0 rAF (before: 4 interval ticks);
  audio context goes running → suspended when hidden.
  `pfcheck.py bootdown`: API failing: card shown, 2 requests in 0-10 s and 2
  in 10-30 s, recovered by itself 28.6 s after the API came back.
  `pfcheck.py ui`: triple-click Save pack / Save palette → 1 request each;
  Ask Jan double-open → 7 size options; save with the server killed → calm
  toast; sounds with the server down → Try again. `pfempty.py`: empty pack →
  note + toast, no errors. Screenshots looked at, 760/1100/1500/1920 px:
  `/tmp/u1/G11/shots/before-sheet-*.png`, `after-sheet-*.png`.

### Critic follow-up (G11 critic, 2026-10-08)
Report: `sessions/2026-10-07-overhaul/critics/u1-G11-critic.md`. Fixed:
- A pack sprite with `tags` that is not a list of words (e.g. `5`) is a 422;
  it used to save and then make `/api/jan/art/ready` a 500 (Ask Jan dead).
  `janart.tile_choices` also skips a hand-edited file's bad tags.
- Ids over 64 characters (pack, sprite, palette, structure, world, sound)
  are a 422 instead of an OSError 500; sprite names, pack and palette labels
  capped at 200, structure source and world description at 4000, world
  label at 200; palette roles must be text; a refused sound id is no longer
  echoed back in full.
- Sounds that failed while the library was down reload by themselves when it
  comes back. The "not answering" card title is no longer in capitals.
- Painting while a pack save is in flight keeps the pack marked unsaved.
Verified: 62 tests passed (19 new); live on scratch 9010 the critic's pack
repro is a 422 and `/api/jan/art/ready` stays 200; headless Chrome: card
title `text-transform: none`, sounds listed after the API came back. The
"edits during save" fix is reasoned from the code only (no test surface).

### Not verified
- Not looked at inside the real Forge window (WebKitGTK); `color-mix()` in
  the middle-column glow needs WebKitGTK 2.40+ (older falls back to no glow).
- No real Jan drawing was made (by rule); the Keep paths were driven with
  hand-made drawings only.
