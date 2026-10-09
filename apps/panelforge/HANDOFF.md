# PanelForge: handoff manifest

**Read this first if you are a fresh Claude Code session with no history.**
It may be running under a different Claude account, so there is no shared
memory. Everything you need is in this file, `~/.claude/CLAUDE.md` (the user's
global working rules) and `~/.claude/self/USER-PROFILE.md`.

Last updated: 2026-09-19 17:40, session 4 still running (solo, paced by the usage meter).

## Where things stand (2026-09-20 14:25, final handoff of session 46) -- the short version

- **Read in this order:** this section, then "After the 04:09 window
  reset" below (a timestamped log of the day; the newest bullets are at
  its end, 16:00-20:45), then `WIP.md`, then `CONTRACTS.md`.
- **What the app does now, verified today:** ten WebToon chapters of Bad
  Born Blood fetched; the reader finds panels and balloons, reads them
  (tilted text levelled, screen text and sound words told from speech,
  balloon-edge strokes and I-as-1/T/[ cleaned, a learned series glossary
  keeps names whole, editable on the Chapter tab); the scene analysis
  finds the cast across chapters (20 cast + 15 extras, hand edits in a
  ledger, crop bench in the Cast tab); the Jan model reads each page
  (speakers, expressions, delivery words, word fixes; then looks at the
  panel picture for unsure speakers) in about 9 minutes a chapter;
  **every cast member has a voice** (c01 by hand, 19 cast by the model
  from their pictures, distinct voices, shared with pitch offsets when
  the nine American men run out); Kokoro speaks every line with
  context-driven delivery; the film renders in six styles with an
  intelligent camera and transitions (morph in-betweens where safe);
  just-watch mode, 9:16, subtitles, bulk runs (gather every chapter ->
  cast -> build), render list with style and sound.
- **Session 46 closed 14:25 on 2026-09-20.** Emerson's verdict at 14:20,
  verbatim: "it's fine, just still wrong characters but I'll fix that,
  ok it's great, just finish up." Suite **569** passing at 14:21; the
  scratch server on 8460 is stopped (PID file removed); nothing of this
  session runs any more; the in-session cron is deleted. Start the next
  session with
  `/pace continue PanelForge from ~/Forge/apps/panelforge/HANDOFF.md`.
- **What he will do himself:** fix the wrong speakers -- in the Cast &
  voices tab's Lines card (click a face, hear, Speak changed lines,
  Render scroll film). Everything else he asked for on 2026-09-20 is in.
- **What a next session should do first:** (1) whatever he says after
  fixing speakers; (2) the cast grouping itself (c01 merges two people,
  c03/c07 one person split -- crop bench on the Cast tab) since "the
  auto detector for characters" is the weak part; (3) real music tracks
  once he drops files in `~/PanelForgeData/library/music/`; (4) the
  Open list below.
- **Since 19:13, in one line each (details in the 18:40-20:35 bullets
  at the end of "After the 04:09 window reset"):** the Lines editor now
  does the whole voice loop (Edit words / own voice / expression, hear,
  Speak changed lines, Render scroll film, speaker filter); a render
  re-plans when lines were re-spoken; music is one segment per mood
  stretch (chapter 1: 60 -> 4); the scroll reader rests on each balloon while its line plays (a ring
  round it exists but is off -- "yellow boxes"); the Render tab
  draws each style's knobs; 42 thought balloons moved from the narrator
  to their characters; a junk line silenced; Dossier's idle watcher was
  the one unloading Jan's model (fixed, live when Dossier restarts).
- **Since 21:00:** Emerson said chapter 2's render was "not very good"
  and that it had "yellow boxes around the text": balloons drawn over
  the gutter were being cut at the top (fixed: the balloon wins over the
  panel range) and the ring round the spoken balloon is now off by
  default (style version 2 so no cached clip with it survives). All six
  films of chapters 1-3 are final as of 22:52. A tilted-text scan of
  chapters 2-10 (`tools/tilted.py`) found nothing unread, so the
  downhill page he saw is one where the reader forms no block at all --
  it needs his page. He has not said what else was wrong with chapter 2.
- **Chapters 4-10 built end to end (23:13-01:33, bulk job
  `20260919-231322-49ad91`, all seven done, none failed):** script ->
  model reading (3-13 min a chapter, vision pass took 0-6 speakers from
  the pictures) -> voices -> music (2-3 segments each) -> scroll
  timeline -> `renders/scroll-16x9.mp4` (385-598 s each, with sound,
  2.2 GB in all; disk 45 GB free before). That was Open item 4's build
  phase on real data: the bulk runner works. Not looked at frame by
  frame -- Emerson judges; chapters 1-3 were.
- **Manifest:** `manifests/session-46.json` (final, 14:25) -- the ask in Emerson's words, built, verified,
  fixed after looking, not verified, known limits, files outside the app.
- **Nothing of mine is running (14:25)** except the scratch server on
  port 8460 (PID in `docs/crew/scratch-8460.pid`, current code since
  20:20 -- open http://127.0.0.1:8460/#cast for the Lines editor). The
  final scroll films are on disk: chapters 1-3 `renders/scroll-16x9.mp4`
  and `scroll-9x16.mp4` (588 / 595 / 585 s, sound on, 22:52) with the
  new music plan, the resting scroll and the moved thoughts, no ring. Checked on
  chapter 1: at 223 s the thought balloon is whole in the window with
  the ring (`docs/crew/final-c01.jpg`). Chapter 1's `scroll-9x16.mp4` was
  rendered again too (21:11, 588 s, 1080x1920; same moment checked,
  balloon whole with the ring). Chapters 2-3's 9:16 films render from 21:14
  (`docs/crew/tall-films.sh`, PID in `tall-films.pid`, about 20 min).
- **Pacing is now automatic (19:00):** Emerson said the 15-minute pacing
  "didn't work" (he had to type Resume each time). New skill `/pace` in
  `~/.claude/skills/pace/` with `~/.claude/tools/pace.py`: each tick
  chimes, reads the meter, prints a mode (continuous / one-task /
  hibernate / handoff) and a delay, and the session schedules its own next
  wake-up. Start a clean session with
  `/pace continue PanelForge from ~/Forge/apps/panelforge/HANDOFF.md`
  (add `after HH:MM` for a final-handoff cutoff).
- **To see today's work inside Forge:** the PanelForge backend your Forge
  is running started at 17:46 and predates the Lines editor, the music
  plan and the resting scroll. Click "Close app" on PanelForge in Forge
  and open it again (that restarts just its backend, port 8449, with the
  current code); or use the scratch copy at http://127.0.0.1:8460 until
  then. Forge itself and Jan were never restarted.
- **Emerson's answers, 02:05 on 2026-09-20 (verbatim where it matters):**
  chapter 2's film: the voices and the music/sound -- "the sounds were
  too random and often didn't make sense and the voices had the cool
  echo but in no context also music didn't really happen"; voices:
  wrong speaker, every kind (narrator reads dialogue, two characters
  swapped, one voice for different people, captions read by a
  character) -- "basically the auto detector for characters sucks but
  it is understandably hard to detect faces in such a complex manga as
  well as guess who is saying what without human level intelligence
  reading it"; film shape: both; the unread downhill text: "chapter 1
  somewhere in the first 6 pages"; sound effects: **off by default**;
  echo: make all three behaviours options (none unless set by hand /
  only radio for comms / the scene's guess), none as the default;
  music: **none for now**; he wants **a proper timeline editor** (all
  of: music segments add/move/trim/track/volume, per-line room/echo/
  volume/mute, drag lines in time, sound effects placed by hand);
  scheduling: keep the in-session cron, no systemd timer.
- **Plan to Sunday 18:00 (Emerson, 02:10: "I'm going to stop the
  session Sunday 6pm, be ready by then with handoffs and manifests, pace
  yourself"):** the cron now runs `/pace ... after 17:20`, so from 17:20
  the tick writes the final handoff instead of a task. Chunks, in order:
  1. **Sound policy -- done 02:15.** `panelforge/audio/policy.py`
     (`read`, `write`, `apply_echo`, `plays`), `~/PanelForgeData/sound.json`
     `{echo: none|comms|scene, sfx: false, music: false}`,
     `GET|PUT /api/sound`, a block on the Render tab (screenshot
     checked); echo applied in `_effective_voice_and_emotion` (a delivery
     set by hand, `source: "user"`, keeps its room), sound effects and
     music skipped in `mix_timeline` unless `source: "user"`/edited.
     Tests `tests/test_audio_policy.py` (5); suite 567.
     `docs/crew/revoice-all.sh` spoke every line of chapters 1-10 again
     and rendered all twenty films (02:54-05:50, every voice job done):
     **every film on disk is now dry-voiced, without auto sound effects
     or music, with the picture-checked speakers and the resting
     scroll.**
  2. **Downhill text -- done 02:22.** It was page 8: "THE IMPERIAL
     GUARD'S SOLE REASON FOR BEING IS IN THIS...", 27 degrees downhill,
     never read: `text.group_lines` linked letters by centre height, and
     at that slant the last letters of one line sit level with the first
     of the next, so six lines became one "line" and no text was found.
     Now `_fragments` (tight, 0.35 h) then `_join_along_baseline`: a
     fragment continues another when it starts where the other's fitted
     baseline arrives (`LINE_TOL`, `LINE_GAP`, `SLANT_MAX`). The crop is
     `tests/fixtures/c01-p08-downhill-caption.jpg`, test
     `test_emersons_downhill_caption_is_read` (block of 4-7 lines at
     15-35 degrees, and the words come out). Every other detect test
     still passes; the rest of the series was not re-read (a re-detect
     renumbers balloons and breaks the script's links). The caption was
     added to chapter 1 by hand (bubble b0185, line l0095, narrator,
     edited); `revoice-all.sh` voices it with the rest.
  3. **Timeline editor -- first pass done 02:29** (the Timeline tab
     already had + SFX, + music, track/mood/gain, from/to panel, delete,
     drag lines and sounds in time; Emerson may not have found it). Added:
     per line a **Room (echo)** select (none / small-room / hall /
     outdoor / vehicle / comms / void; sets `emotion.room`, `reverb`,
     `eq`) and a **Mute** tick box (`line.muted`: the mixer leaves it
     out, its slot stays; test in `test_audio_mix.py`); the sliders now
     mark the delivery `source: "user"` so the sound policy keeps a
     hand-set room; **music blocks drag**: left end trims the start,
     right end the stop (snapping to panels), middle moves the whole
     block (`dragMusic`, `shotAtTime`); mood is a select; auto music and
     sound blocks are drawn dimmed with a tooltip when the sound policy
     silences them, and become "by hand" (always played) as soon as they
     are edited. Screenshot checked (line inspector with Room and Mute,
     dimmed music block). 06:30: arrow keys nudge the selected line or sound by 0.1 s
     (Shift 1 s) when no field has the focus (checked in the browser: a
     block moved 62 -> 66 px on ArrowRight). The SFX inspector already
     had a sound picker with audition; the gain slider is the per-line
     volume.
  4. **Speakers -- done 02:50: the picture changed 9 / 9 / 6 speakers in
     chapters 1 / 2 / 3** (24 lines, sound cleared, voiced by
     `revoice-all.sh`). `vision_pass(..., everyone=True)`
     asks the picture about every non-caption line where two or more
     cast stand; the llm route takes `{vision_only, vision_all}`
     (`LlmReq`). `docs/crew/vision-1-3.sh` (PID in `vision-1-3.pid`, log
     `docs/crew/logs/vision-1-3.log`) runs it on chapters 1-3 (Jan,
     about 10 min a chapter); lines whose speaker changes lose their
     sound and `revoice-all.sh` speaks them (it reaches chapter 1 after
     the 9:16 films of 4-10, about 03:00). Test extended
     (`test_vision_pass_asks_only_where_two_stand...`). Suite 569.
  5. **17:20 Sunday:** final handoff, WIP, PROGRESS, manifests; stop
     the scratch server.
- **First things for the next session:** (0) Emerson watches
  `chapters/0001/renders/scroll-16x9.mp4` (final from about 20:47) and
  says what is still wrong with voices and music; he fixes speakers in
  the Lines card (Cast & voices tab) and music moods on the Timeline tab;
  (1) real music tracks per mood from `~/PanelForgeData/library/music/`
  once he drops files there (the library is empty; the Timeline's music
  blocks already take a `track`); (2) the Open list below.
- **Tests:** 562 passing (`.venv/bin/python -m pytest -q`; one
  order-dependent flake in `test_render_depth3d`). `pyright` clean on
  every file touched (one pre-existing error in `detect/bubbles.py`).

## Session 4 (2026-09-19, solo, no helpers) -- the day's log

Started from section 6 below: render the film with the session-3 fixes, then
look at the frames. Everything here is verified unless it says otherwise.

**Checks at the end:** `.venv/bin/python -m pytest -q` -> **492 passed**
(487 at the start plus 5 new). `pyright --pythonpath ./.venv/bin/python`
clean on every file touched (one pre-existing `reportOptionalCall` in
`detect/bubbles.py:406` was there before). `black` run on the files touched.

### What the render showed, and what was fixed

`renders/lookie-03.mp4` (the session-3 state) confirmed two of the three
things: the opening caption is whole, and tall panels sit on the stretched
fill. Sound went from 37% of the film to 94% (the auto SFX and music work).
But the frames showed a caption at 21 s sliced at the top and left, and a
ghost of the words behind the "NOTHING" panel. Tracing the sliced caption
found a chain of three misses on one panel (p0006, a borderless caption drawn
at a 17-degree tilt):

1. **Tilted lettering was never read.** The letter finder found the five
   tilted lines, but the drop-shadow specks (2-6 px) were counted as
   punctuation and drove the line height down to 3 px, which split the
   block; and Tesseract reads a tilted line as junk (confidence 0.37-0.45).
   Fix in `detect/text.py`: `Line.h` uses real letters only
   (`MIN_LETTER_H`); every `Line` and `Block` now has an `angle` (baseline
   skew fitted through the letter centres). Fix in `detect/bubbles.py`:
   `levelled_crop` turns an open candidate level before OCR when its skew is
   at least `LEVEL_ANGLE` (2.5 degrees). The caption now reads at 0.92:
   "To eliminate any enemies who would threaten the emperor and his
   subjects." Tests: `test_tilted_lettering_gets_its_skew_measured`,
   `test_tilted_caption_is_read_after_levelling`.
2. Because there was no text box, the **text-safe camera rule had nothing to
   protect** and pushed in 1.18x on a panel that is all words. Fixed by 1.
3. Because there was no text box, the **person detector's text-overlap
   filter let the lettering through as a person** (score 0.85, 99% of the
   panel), so depth3d floated the words as a character layer, with ghosting.
   Fixed by 1: p0006 now has no characters, and chapter 1 went from 12 cast
   to 11.

Re-running detect on chapter 1: 118 -> **132 bubbles with text**, mean OCR
confidence 0.814, 32 panels grown to cover their lettering; the script grew
from 118 to **125 lines**.

**Two more camera and fill fixes from the second look (`lookie-04`):**
- The title logo "BAD BORN BLOOD" lost its last letter to a slow drift: the
  panel already spans the frame edge to edge, and the OCR cannot read a
  stylised logo, so the text-safe rule had no box. New camera rule
  `rule_strip_stays_whole` in `camera/rules.py`: a panel wider than
  `WIDE_STRIP_ASPECT` (2.4:1) is held whole and still, no shake. Seven shots
  in chapter 1 are affected. Test: `test_a_wide_strip_panel_is_held_whole`.
- The `blur` backdrop was too gentle for big lettering, so the words showed
  through as ghosts above and below the panel. The blur is now three times
  stronger (`render/context.py`, `sw / 12`), checked by eye on the "NOTHING"
  shot: colour wash, no ghost words.

**Cast finder, third pass: faces found identities (`scene/cast.py`).**
The contact sheet showed that every junk cluster (hands, an eye, a gun,
armour, an emblem) was made of appearances without a face, and the rows that
mixed two people were glued by faceless body crops. `_labels` now clusters
only the faced appearances; a faceless one joins the character whose faced
pictures it is closest to (`ATTACH_THRESHOLD` 0.85 in blended units,
`ATTACH_QUANTILE` 0.25, never into a character already in its panel), or
stays `UNPLACED`: no cast entry, no extra, still a person in its panel. A
chapter with no faces at all clusters on bodies as before. Chapter 1: **9
cast, 0 extras**, 27 rejected, 26 unplaced (was 11 cast + 2 extras with
three junk rows). On the sheet, the lead, the blond, the bearded soldier, the
red-haired one and the tan-armoured one are each one clean row; two rows
still mix fragments (`tools/cast_sheet.py` to see). `scene.json` appearances
carry a `placement` field now: cast, extra, unplaced or rejected. Tests:
`test_faceless_appearances_never_found_a_character`,
`test_a_chapter_with_no_faces_is_clustered_on_bodies`, and the pipeline
test checks `placement`.

**New tool: `tools/rebuild_chapter.py`** runs detect -> analyze -> script ->
voice -> audio -> timeline -> render through a running server, one job after
another, with `--from STEP` to start part way. Start it with `setsid -f`
(the Bash tool's 10-minute cap will kill it otherwise) and read its log in
`docs/crew/logs/`. Analyze reused its per-panel cache and took 15 s; the
90-second render takes about 4 minutes.

**Worth knowing: the shot clip cache (`work/render/shots/`) keys on the
inputs and settings, not on the renderer code.** After a change to a style,
the backdrop or the camera maths, delete that folder or the old clips are
reused silently (`lookie-03` reused 18 of 24 clips from a render session 3
had started and stopped; that was fine because the inputs had not changed
since, but a code change would not have shown).

### Later in session 4 (02:00-02:50), while Emerson watched and asked

Verified unless marked otherwise. Emerson's verdicts: the visuals are
"honestly very impressive"; the reader misses words and says letters
instead of words; the cast finder "sucks"; every style looked the same;
renders vanished; rendering is slow. What was done about each:

- **Cast editor backend (`scene/cast.py`, `api/scene.py`):** an
  `assignments` ledger in cast.json (`chapter/panel:index` -> cast id or
  "none"). `apply_assignments` replays it after every analysis, `build`
  reserves ledger target ids and keeps their name and voice, and
  `sync_scene_ids` writes the result into scene.json. API: `PUT
  /series/{s}/cast` takes `assign` (target id, "new" or "none") and `merge`
  now writes the ledger too; `GET /series/{s}/cast/unsorted?chapter=` and
  `/cast/appearances?chapter=` list crops with ledger keys. Tests:
  `test_assignments_split_drop_and_survive_a_rerun`,
  `test_cast_api_assign_and_unsorted`. **UI:** `static/js/tabs/cast.js` has
  a crop bench (per-character "Crops (n)" buttons and an "Unsorted crops"
  button, tick boxes, "Move ticked to" a character / a new character / not a
  person) and "Merge selected" now goes through the server. Cards and the
  bench are screenshot-verified (08:55: 55 unsorted crops of chapter 1 with
  tick boxes, two ticked, the move control). Note for `tools/ui_shots.py`:
  its `--js` used to run twice, which toggled the bench closed again;
  fixed. Two cosmetic things fixed at 09:05: extras now get a real sample
  picture under `assets/extras/<id>/` (they pointed at a chapter-relative
  cutout the tab could not resolve), and asset pictures fit their cards
  (`#extrasGrid/#bgGrid/#propsGrid .cover` in `app.css`). The extras
  pictures appear after the next analyze; not screenshot-checked yet.
- **Cast finder:** faces found identities (`_labels`), a two-seed median
  split cuts clusters glued by look-alike pairs (`_split_glued`,
  `SPLIT_MEDIAN` 1.05), card pictures are head crops (`sample_image`). Chapter
  1: 10 cast, 0 extras, no junk rows; two rows still mix fragments.
- **Reader:** letters up to 150 px tall count (`MAX_LETTER_H`), a tall blob
  with letters inside it is a balloon not a letter (`_drop_containers`),
  and `dedupe` drops a fragment inside a bigger candidate but drops the
  *container* when it holds two well-read candidates (`reads_well`: two real
  words at conf 0.7). Measured: 132 bubbles with 30 junk -> 117 with 20
  junk, 3 real lines lost, **before** the `reads_well` fix; the run after
  that fix was interrupted, so its numbers are unknown. Junk readings on
  chapter 1 are 2-3 letter fragments of big lettering ("READERS" -> "Ad").
- **Renderer:** shots render in parallel worker processes
  (`render_workers`, half the logical cores, `PANELFORGE_RENDER_WORKERS`
  overrides); Emerson's backend measured 5 shots (20.6 s) in 43 s. Encoding
  was already on the GPU (h264_vaapi).
- **Render tab bugs:** the style dropdown read `s.id` where the API gives
  `name`, so no chosen style ever reached a render (all films were the
  chapter default); fixed. Renders with the same style and aspect overwrote
  one file; `_unused_path` now adds -2, -3. Test extended.
- **Tools:** `tools/ui_shots.py --js` runs JavaScript after a tab loads.
  `~/.claude/tools/usage.py` reads the account usage meter for pacing.

- **"Just watch" mode (done, 02:40-02:50):** timeline settings `sound`
  (full / music / silent) and `layers` (0..1). `CameraSettings.voiced` makes
  `rule_timing` dwell by reading pace when there are no voices; the mixer
  drops voice clips unless `sound == "full"`; `render_timeline` writes no
  audio track for `silent`; depth3d skips the cutout layering when `layers`
  is near 0 and scales the layers' own movement by it otherwise. A render
  whose `sound` differs from the saved plan re-plans in memory
  (`api/render.py`, "re-planning shots for sound=..."), so the saved
  timeline and edited shots are untouched. Render tab and settings drawer
  have a Sound select and a "Character layers (3D style)" slider
  (screenshot-verified); disabled style stubs are hidden from the Style
  list. Verified with `renders/watch-test2.mp4` (30 s, music only, layers 0;
  frames whole). Tests: `test_silent_and_music_films_dwell_by_reading_pace`,
  `test_sound_setting_drops_voices_or_the_whole_track`. 497 tests pass; one
  test flaked once in the full run and passed on rerun (not identified).

- **comix.to chapter list (done 02:55):** `sources/comix.py` walks the
  title's list by loading `?page=N` directly until a page adds nothing; the
  pager's "Next" button is missing on some renders, which stopped every walk
  at page 8 (81 of 102 chapters, never chapters 1-21). Verified live: 102
  chapters listed. A fetch of chapters 2 and 3 was queued on the scratch
  server (job 20260919-025505-c34c03, port 8460, PID in
  `docs/.scratch_server.pid`) -- check `PanelForgeData/series/bad-born-blood/
  chapters/0002` and `0003` for `chapter.json` and pages; if the server is
  gone, re-run `POST /api/fetch/chapters {"series":"bad-born-blood",
  "chapters":[2,3]}` on a fresh scratch server.
- **USB HDD:** Emerson asked for it to be remounted (never wiped). At 02:53
  no USB storage was attached at all (lsblk shows only the NVMe; lsusb shows
  the dock, mouse, audio, LAN). When it appears: `udisksctl mount -b
  /dev/sda1`, nothing else.

### After the 04:09 window reset (04:18-05:00), continuous work

- **Jobs survive native crashes (`panelforge/subjob.py`):** the scratch
  server died at 04:23 with "longjmp causes uninitialized stack frame"
  inside an analyze job. Detect and analyze now run in a child process
  (`python -m panelforge.subjob <kind> <chapter_dir>`) that reports LOG /
  PROGRESS / RESULT lines over stdout; a crash fails that job only. Verified
  on the real chapter through the API.
- **Cast across chapters (`scene/cast.py`, `scene/pipeline.py`):** every
  analysed chapter's appearances join the grouping
  (`load_chapter_appearances`, shared with `tools/cast_sheet.py`); keys are
  chapter-qualified (`panel_key`, `akey`); other chapters' scene.json ids are
  synced after each analysis. **Cast = seen in 2+ chapters or 6+ panels**
  (`CAST_MIN_CHAPTERS`, `CAST_MIN_PANELS`), everyone else an extra. Tests
  updated. Not yet run on real data with more than one chapter: chapters 2-4
  were being analysed (jobs queued on port 8460, logs
  `docs/crew/logs/rebuild-ch{2,3,4}.log`); after they finish, re-run analyze
  on chapter 1 and look at `tools/cast_sheet.py` per chapter.
- **Chapters fetched:** 2, 3, 4 complete (156, 124, 119 pages); 5-10 queued
  again at 04:27 (job 20260919-042718-10fdce). comix.to lists all 102.
- **Reader, measured on chapter 1 after every fix: 98 bubbles, mean OCR
  confidence 0.86, 3 suspect (two of them genuine), 0 real lines lost** --
  from 132 bubbles with 30 junk readings. The last two rules: between a
  candidate inside another, keep the one that reads better (`dedupe`), and
  a lone 2-3 letter "word" passes only from `SHORT_OK` or at conf 0.9 with
  a known word (`looks_like_text`). One caption's letters are missing in the
  page image itself (comix.to canvas capture glitch, chapter 1 around
  y=80000-90000 "AN EXHAUSTION OF RESOURCES"); page verification should
  re-capture such pages -- open.
- **2.5D puppet style (`styles/puppet25d.py`, enabled):** breathing about
  the hip, sway about the neck while talking, blinks on a deterministic
  schedule and lip-flap during the character's lines, all as warps of the
  cutout; `Depth3D.layer_image` is the hook. Eyes and mouth come from
  `rig.find_eyes` / `rig.mouth_from_eyes` on the cutout pixels, **which is
  precise but rare (7 of 60 faces on chapter 1) -- the rig template boxes
  are not used because they put a blink on the hair of a profile.** So most
  characters only breathe and sway. Next: a real anime landmark model
  (`animeface` needs its nvxs C library built; hysts/anime-face-detector
  needs torch + mmcv, ~2 GB; the venv has no torch). Tests:
  `tests/test_render_puppet25d.py`. Verified by eye on chapter 1 head crops
  that the template boxes were wrong and the finder's boxes are right when
  found.
- 502 tests; `test_character_layer_parallaxes_more_than_a_rigid_render`
  fails now and then in the full run and passes alone (order-dependent,
  not investigated).
- Wake-ups: ScheduleWakeup long delays never fired in this session; a
  CronCreate job every 28 minutes (session-only, 7-day expiry) is the
  fallback. Emerson's pacing rule is in `~/.claude/CLAUDE.md`.

- **MediaForge's manga downloader (done 04:58):** comix.to goes through
  `tools/fetch_cli.py` (`list`, `get`), a command-line front on
  `panelforge.sources`; MediaForge's `manga.py` calls it for `CDP_SITES`.
  Verified outside the Tk UI: 102 chapters listed, chapter 1 saved as 142
  pages in MediaForge's layout. See `apps/mediaforge/WIP.md`.

- **Words -> expression (`audio/emotion.py` layer 3, `WORDS`):** when the
  face gives "neutral", the line's own words set the expression (angry,
  scared, sad, happy, determined, surprised, smug, pained); 19 of 107
  chapter-1 lines get one. Test `test_words_give_an_expression...`.
- **Jan reads the page (`audio/llm_pass.py`, `POST
  /chapters/{s}/{c}/script/llm`):** batches of one scene with context;
  takes a speaker only when geometry was unsure (< 0.7) and the name is in
  the panel or the one before; an expression only where face and words gave
  neutral; a text fix only when it is a small edit. Every verdict lands on
  the line under `llm` (editor can show/undo). PanelForge's Jan settings are
  mounted in `web_app.py` (role "script", default `Qwen3_5-4B-IQ4_XS`).
  Tests: `tests/test_audio_llm_pass.py` (fake model). **A live trial on
  chapter 1 was running in the background at 05:20, writing to
  `chapters/0001/work/script-llm-trial.json`** (not script.json): look at its
  `llm` records before wiring the button. Jan's router was started by this
  session (`llama-server --models-preset ... --port 1337`, log
  `~/Forge/outputs/jan-router.log`); leave it running.
- Loop: cron `f2a4cc52` ticks at :03/:18/:33/:48 with the 70/92 governor;
  final clean-session handoff due after ~19:09.

- **Scan groups (05:50-06:05):** comix.to lists every chapter once per
  scan group (Bad Born Blood: WebToon 1-92, Asura 93-100, plus Falcon,
  Kraken, Lagoon); the list kept the first, which was Asura. Now
  `sources/comix.py` keeps every group, `library/fetch.pick_group` chooses
  the wanted one per chapter number (`group` on `POST /api/fetch/chapters`),
  the Library tab has a "Scan group" select, `tools/fetch_cli.py list
  --group`, and MediaForge has a "Scan group" field (default WebToon).
  Chapter 1 was WebToon already; chapters 2-10 were Asura and were queued
  for re-fetch as WebToon at 06:04 (job 20260919-060435-63e60a on port
  8460). Their Asura-based detect/analyze results are stale after that:
  re-run detect+analyze for 2-10 (rebuild_chapter.py --to analyze).
- **Model pass, live trial on chapter 1:** 885 s on the 4B (37 tiny
  batches; batches now fill to 14 lines across scenes), 3 speakers, 13
  expressions, 3 text fixes, all sensible ("All of th isis" -> "All of this
  is"). The model may now also set delivery (speed, pitch, gain, pause)
  with a reason, clamped to the DSP limits. `janboot.ensure_router` starts
  Jan's router when none is running (never restarts one) and the
  `script/llm` endpoint calls it; `tools/rebuild_chapter.py` has an `llm`
  step after `script` (`--no-llm` skips it). The endpoint itself is untested
  live on the scratch server (the pass was verified in-process).
- **Render list shows how a film was made (06:35):** every render writes a
  `.json` sidecar (settings, shots, seconds) and `/api/renders` reads it;
  the Render tab's list shows style · sound · aspect · length. Older films
  without a sidecar show only their name.
- **The GPU is shared and that was the crash (06:45):** the scene models
  run on OpenVINO's GPU device (Iris Xe, OpenCL) and a loaded Jan model
  (llama.cpp on Vulkan) holds the same GPU; then the OpenCL kernel build
  fails (`CL_BUILD_PROGRAM_FAILURE`) or the process segfaults. Seen on
  chapters 2 and 3 with the 4B loaded; session 3's unexplained server death
  was probably this too. `subjob.run_in_child` now releases Jan's loaded
  models before an analyze job (`_free_the_gpu`) and, if the GPU still
  fails, runs the job again with `PANELFORGE_SCENE_DEVICE=CPU`. So: a model
  step and an analyze step never run at the same time on this laptop.
- WebToon re-fetch of chapters 2-10 finished 06:22 (e.g. chapter 2: 186
  pages). Detect+analyze for 0002-0010 re-queued at 06:50 via
  `docs/crew/run-chapters.sh` (logs `docs/crew/logs/rebuild-00NN.log`); about 25 min each. When done: re-run
  analyze on 0001, then `tools/cast_sheet.py` per chapter to judge the
  cross-chapter cast.
- **Bulk runs (07:05):** `POST /api/series/{s}/run` with `first`/`last` (or
  `chapters`) and `steps` (fetch, detect, analyze, script, llm, voice,
  audio, timeline, render; defaults to all) runs every step chapter after
  chapter as one job in lane "batch", calling the app's own API
  (`panelforge/batch.py`, the same sequencing `tools/rebuild_chapter.py`
  uses). A failed step stops that chapter only. Tests
  `tests/test_batch.py`. UI (07:20): a "Run chapters" card in the Library
  tab (series, from, to, scan group, step tick boxes, live log), rendered
  and screenshot-checked; it sends the Render tab's saved settings for the
  render step. Not yet run end to end on real chapters.
- **Cast across chapters on real data (07:30):** after chapter 2 (WebToon)
  analysed, the series cast is 9 characters, each seen in both chapters
  (c01 32+29 appearances, c02 11+19, ...), 2 extras -- identities carry
  across chapters. Chapters 3 and 4 still contributed one stale (Asura)
  appearance each until their re-analysis lands. **c01's voice (af_alloy)
  had been lost somewhere in today's re-analyses**; set again at 07:32.
  A new test pins that a second chapter keeps the first's names and voices
  (`test_a_second_chapter_keeps...`, passes), so the loss came from
  elsewhere (the crashed 04:23 runs?) -- watch for it after chapters 3-10.
- **Chapter 2 cast sheet (08:15, `tools/cast_sheet.py bad-born-blood
  0002`):** the tool re-clusters one chapter on its own, so it does not
  show the series grouping; on chapter 2 alone it gives one 39-crop row that
  mixes the lead with the bearded man and others, a clean blond row, and
  mixed soldier/robot rows. So chapter 2 is harder than chapter 1 for the
  finder. Two follow-ups: make the sheet show the *series* cast ids from
  scene.json (one row per cast id) instead of re-clustering, and judge the
  lead/bearded mix there; the hand editor is the safety net either way.
- **Series cast sheet (08:35, `tools/cast_sheet.py bad-born-blood
  --series out.jpg`, saved as `docs/crew/cast-series-2026-09-19.jpg`):** one
  row per cast id over chapters 1-7 as the app has them. 21 cast, 4 extras.
  Judged by eye: c03 (blond) and c10 (pink hair) are clean across every
  chapter; c01 (145 crops) merges the red-haired man with the dark-haired
  lead; c07 is the blond again (a split of c03); c06 is armour and machinery,
  not a person; c05 mixes the bearded man with others. With seven chapters
  the "2+ chapters" rule lets recurring junk become cast, so the next tuning
  is a stricter `is_person` for faceless recurring crops, and the hand editor
  (merge c03+c07, split c01, drop c06) is the way to a correct cast today.
- **Disappearing objects in the 3D style (07:50):** boxes the person
  filter rejected or left unplaced (a gun, a hand, an emblem, a faceless
  crop) were still cut out of the background at analysis and drawn as
  floating layers on their thin masks, so most of the object vanished.
  `depth3d.build_scene` now pastes those cutouts back into the background
  where they were and floats only cast and extras (`_paste`). Test
  `test_rejected_detections_stay_in_the_background`. Checked by eye on
  chapter 1 (08:00): the RATATATA gun panel shows the gun and hands whole.
  The shot clip cache does not know about this: delete
  `work/render/shots/` before re-rendering an old film.

- 09:15, second window: 513 tests pass (the parallax test flaked once
  more in a full run and passed on rerun). The live model pass on chapter
  1 was queued through the endpoint (job 20260919-091347-a898e5 on port
  8460), waiting for chapter 10's analysis to finish; read its log next.

- 09:35: "Read page with model" button in the Chapter tab (next to Run
  analyze) calls `script/llm` and reports the counts; endpoint listed in
  CONTRACTS.md and the frontend contract test. The live pass on chapter 1
  started at 09:26 through the endpoint (12 batches of up to 14 lines);
  read `script.json` lines' `llm` records when it is done.

- 09:50: the settings drawer has a "Local model (Jan)" group drawn by the
  shared `forge_jan.js` (role "Page reading", idle-release minutes, live
  status); screenshot-verified. The model picker defaults to "Whatever Jan
  has" -- `llm_pass.DEFAULT_MODEL` (the 4B) is used when nothing is chosen.

- **Live model pass through the endpoint (09:26-09:52, chapter 1):** 12
  batches, all lines answered; 4 speakers moved, 10 expressions, 32
  deliveries with reasons ("showing off", "shocked exclamation",
  "celebratory shout"), 0 text fixes (the reader is clean). 65 of 107 lines
  carry an `llm` record. One systematic miss fixed at 10:05: first-person
  captions ("I surpassed my own limitations!") are the lead's thoughts, not
  narration; the prompt now says so and a character given to a caption
  turns the line's kind into "thought" (test added). Not yet re-run.

- **Cast needs faces (10:20):** with ten chapters the series cast had grown
  to 30 entries; every junk one had 1-2 faced crops with dozens of faceless
  armour/gun pieces attached, every real character 11+. `CAST_MIN_FACED = 3`
  faced appearances is now required for cast (`cast.group`); test updated.
  The scratch server still runs the old rule: restart it after the queued
  chapter-1 analyze + model pass (jobs 20260919-101337-d4bc96 / -0ab0d7)
  finish, then re-run analyze on one chapter to regroup the series.

- 10:50: a 14-line batch with delivery fields overran the model's 900-token
  answer and came back unparseable ("0 of 14 lines answered"). The answer
  budget is 1800 tokens now and an unparseable batch is asked again in two
  halves (`llm_pass.run`, test added). Applies after the server restart.

- 11:05: scratch server restarted on all of today's rules; a chapter-10
  re-analysis regrouped the series cast under the faced-pictures rule:
  **30 cast -> 20 cast, 15 extras** (the armour, gun and machinery entries
  are extras now); c01 keeps af_alloy. The cast step took about 8 minutes
  for 1380 appearances -- fixed at 11:20: `cluster.quantile_linkage` keeps
  a score matrix and re-scores only the merged cluster after each merge;
  identical merges to the old code (checked on random data with
  cannot-links), 300 items 94 s -> 1 s. The `_split_glued` step still calls
  it on each cluster; fine. Note: grouping over ten chapters means about 1500
  appearances, and `cluster.quantile_linkage` is pure Python and roughly
  cubic, so the cast step of an analysis is now minutes, not seconds --
  worth a numpy rewrite or a cap on how many faceless crops join.

- 11:30: chain on chapter 1 from the model pass through a 90 s render
  (`renders/lookie-07.mp4`, log `docs/crew/logs/rebuild-ch1-lookie-07.log`)
  started detached, to have one film with every rule from today: clean
  reader, faced cast, words/model expressions and deliveries, pasted-back
  objects. Done 12:00: 93.7 s, 24 shots in 135 s, 94% with sound; frames
  checked by eye (12:15): captions whole, gun and hands whole, nothing
  odd. Script after the model pass: 55 speech, 37 caption, 9 thought (the
  first-person captions), 14 speakers moved by the model. Only Emerson can
  judge the sound.

- 12:05: the Timeline tab's line editor shows *why* a line sounds as it
  does: the expression and its strength, the rule cues, and what the model
  read (speaker, expression, reason, text fix, each marked "taken" when it
  was applied). Screenshot-checked 14:00 with a line selected ("cues:
  small lettering, wavy lettering, tense mood, hall acoustics / model read:
  speaker narrator (taken) · neutral").

- 12:40: eleven lines had no speaker: narration boxes the reader classed
  as speech (the model said "narrator" and the guard refused it for
  non-captions) plus stale junk lines because the 11:30 chain started at
  the model step without rebuilding the script after the last detect. The
  guard now accepts narrator for any line in a panel with nobody in it
  (test), the server was restarted, and a chain from `script` to a 90 s
  `lookie-08` render was started (log `rebuild-ch1-lookie-08.log`).
  Lesson: after a detect, always rebuild the script before the model pass
  (`rebuild_chapter.py --from script`). Result 12:55: 89 lines, every line
  has a speaker (narrator 50, c01 16, c02 9, ...), 4 thoughts, expressions
  on 39 lines (determined 12, smug 8, sad 7, scared 5, surprised 4);
  `lookie-08.mp4` rendering.

- **Puppet eyes: landmark model candidates (12:50, not installed --
  Emerson reviews installs):** (a) `hysts/anime-face-detector` on GitHub:
  anime face boxes plus 28 landmarks (eyes, mouth), MIT licence, needs
  PyTorch + mmcv/mmdet/mmpose (about 2 GB; the venv has no torch);
  (b) nagadomi's `animeface-2009` (the `animeface` PyPI package): face,
  eyes, nose and mouth positions from a C library, tiny, but the package
  needs its `nvxs` library built first (the pip install failed on that);
  (c) `lbpcascade_animeface` (nagadomi): faces only, no landmarks, so no
  help for eyes. The rig then gets `eyes_from: "model"` and the puppet
  style animates any face with model landmarks.

- 13:15: 9:16 vertical output checked (`renders/vertical-test.mp4`, 30 s,
  1080x1920, just-watch): wide captions sit centred on the blurred fill,
  tilted caption whole. The nit that a wide caption's lettering touched
  the frame edge in portrait is fixed (13:40): `rule_strip_stays_whole`
  gives a wide strip zoom 0.94 in a portrait frame (an `_air` key that
  `clamp_key` lets go below 1; ordinary keys still never do), and the rule
  now runs after `rule_text_safe`. Tests updated. Not re-rendered.
- `lookie-08.mp4` (12:59): 93.8 s, the film from the clean script.

- **In-between frames (14:25, third window):** new transition
  `transitions/morph.py`: DIS optical flow between the two real frames
  (half-size, then scaled), the outgoing frame warped forward by u, the
  incoming warped back by 1-u, blended with an eased mix. Farneback found
  only a third of a 40 px shift; DIS finds it exactly. The `inbetween`
  style is now enabled: the 3D style with morph as its preferred
  transition. Tests `tests/test_transitions_morph.py` (a moving square
  travels instead of ghosting). Seen on real drawings at 14:30: between two
  balloon-heavy panels the words turned to mush mid-way, so
  `choose_auto` never picks morph when either panel keeps lettering (test).
  At 14:50 a morph between two unrelated art panels was a liquid smear,
  so the morph now also needs a shared character on both sides
  (`_shared_cast` in `choose_auto`, test). On chapter 1 that leaves the
  cuts t0055, t0056, t0078 (three of 123 with lettering kept; more with
  bubbles erased). Seen at 15:00 on t0055 -> t0056 (same characters,
  close-up of grins -> wider action panel): shapes travel and settle, a
  plausible in-between, with smear where drawn SFX lettering comes through
  -- fixed 15:15: `PanelInfo.has_text` now also counts the drawn sound
  words the scene analysis found (`sfx_text`), so neither the morph nor a
  mirror flip goes through them (test).
- **Erase + subtitles looked at (15:30, `renders/subs-test.mp4`):**
  subtitles draw fine (boxed, top of frame), but erasing a caption-only
  panel left a blank white slab for seconds. Now a panel that is mostly
  lettering (`kind == "caption-only"` or bubbles covering 45%+ of it)
  keeps its lettering in erase mode and gets no duplicate subtitle
  (`bubbles.keeps_its_lettering`, test). Not re-rendered.

- **Reader across all ten chapters (15:45):** 43-114 bubbles per chapter,
  mean OCR 0.81-0.87, 2-14 suspect. Chapter 4's 14 were the comic's own
  HUD boxes reading "ERROR" (light lettering in dark boxes), which the
  classifier called speech, so the narrator would say it thirteen times.
  New rule `bubbles.is_screen_text`: light-on-dark lettering in a closed
  box that is boxy or a single word is screen/sign text -> kind `sfx`
  (shown, never voiced); `polarity` is now written on every bubble. Test
  added; chapter 4 re-detected: 13 screen texts, none voiced.
- **c01's merge is not separable automatically (16:00):** on the series
  data the 132-face cluster (red-haired man + dark-haired lead) is compact
  (median within-distance 0.64) and neither the two-seed nor a spectral
  (Fiedler) split finds two big sides -- the CCIP face embedding sees them
  as one person and only the hair colour histogram (weight 1.0 against
  4.0 for the face) disagrees. Options: raise the hair weight only when the
  face embedding is near-tied (risky), or let the model pass (with the
  cutout image, the 4B has a vision head) judge merges, or the bench. Left
  to the bench for now.
- Puppet eyes: an edge-energy eye-line finder was tried on the 60 chapter-1
  faces and is not reliable either (24%-62% of face height); a landmark
  model (candidates above) is the way.
- **The model pass now looks at the picture (16:20):** the 4B loads a
  vision projector, and a panel image through Jan (OpenAI-style content
  array, 640 px JPEG data URL) is answered correctly -- on chapter 1's
  p0038 it named who says which balloon from the drawing. New
  `llm_pass.vision_pass`: for every panel with two or more cast standing
  in it and a line the geometry is unsure about (`conf < 0.7`), the panel
  crop goes to the model with the cast ids, their names and where each
  stands (left/centre/right, top/middle/bottom); the answer is taken only
  when it names an id in that panel, and recorded as `llm.vision_speaker`.
  Runs after the text pass inside `POST .../script/llm`. Tests (fake
  model): asks only where two stand and the line is unsure, takes a seen
  answer, ignores an unknown id, survives a failed request. Not yet
  measured on a real chapter (Jan was busy with chapter 2's text pass).
- **The text pass, three times faster (16:10-16:35):** the 4B generates
  at 6 tokens/s on this laptop (llama-server timings; prompt reading
  12-90 t/s depending on how busy the CPU is), and a 12-14 line batch with
  a JSON object per line was 770 output tokens, 2.5-5 minutes on chapters 2
  and 3. Asking it to leave out defaults did nothing except make it drop
  the quotes on its keys (`{2: {...}}`, unparseable -- `_parse_any` now
  quotes bare number keys and strips trailing commas). The answer is now
  **one pipe-separated line per numbered line** (`n | speaker | expression
  | intensity | delivery | why | fix`, `_parse_lines`, JSON still accepted
  as a fallback) and **delivery is words, not numbers** (`DELIVERY_WORDS`:
  fast, slow, quiet, loud, whisper, shout, flat, low, high, breathless,
  drawn out, pause -> knob values through `delivery_knobs`; the old
  numbers object still works). Same batch of 12 chapter-3 lines: 770 ->
  256 output tokens, 12 of 12 parsed, speakers and moods as sensible as
  before. Tests updated (10 in `test_audio_llm_pass.py`).
- **Jan dropped the model under a running request (16:07):** the router
  logged `unload: stopping model instance Qwen3_5-4B-IQ4_XS` mid-batch and
  chapter 2 lost batches 8 and 9 ("proxy error: Failed to read
  connection"). No caller found: not this app (`_free_the_gpu` only runs
  before analyze, and the scratch server logged no idle release), no other
  Claude session, Dossier's log is from the 16th. `llm_pass._ask_twice`
  now asks once more after 8 s on a dropped connection (the router loads
  the model again on the next request); test added. If it happens again,
  look at `~/Forge/outputs/jan-router.log` for who called `/models/unload`.
  Later (17:05): the router has unloaded the 4B eight times today
  (router minutes 15, 98, 294, 351, 416, 478, 662, 712 = 05:21, 06:44,
  09:59, 10:56, 12:01, 13:03, 16:07, 16:57; the router started 05:05:25).
  The last two came 20 s after a request finished and nothing of mine
  was running that releases models. The scratch server's idle watcher
  logs with a plain `print`, which a backend with its output sent to a
  file buffers -- so its "released idle Jan model" lines could never
  reach `scratch-8460.log`. `shared/forge_jan.py` now logs with
  `flush=True` (`_print_now`; shared tests pass), so the next unload
  will show whether the watcher is the one. If it is, the fault is in
  `AppJan.idle_models` judging a busy model idle; the fix would be to
  count a model as active while any `/slots` is processing, not only
  by this app's own in-flight requests.
- **The reader's words (16:10-16:40), replayed over all 881 voiced bubbles
  of chapters 1-10:** balloon edges came through as strokes (`/~`, `'\\`,
  `/7`, a leading `7`, `& = S s 2` after the last sentence), the pronoun I
  was read as `1`, `T` or `[` ("1 GUESS", "LIKE T SAID", "[T TAKES", "1S
  THIS"), stray single consonants floated mid-sentence ("V THAT N KID'S"),
  and names were split into dictionary scraps ("BELLATO" -> "bella to",
  "WURT" -> "wu rt", "I LAY" for Ilay). `detect/normalize.clean_raw` now
  strips the strokes, fixes those I reads, drops lone consonants (keeping
  stutters "N-no", initials "Mr. K", A and I), and trims scrap runs at both
  ends. **New: a learned series glossary** (`normalize.learn_glossary`,
  called at the start of every detect): any unknown word of 4+ letters read
  in 3+ bubbles of the series' other chapters, plus the cast names, is a
  word and is never split -- Bad Born Blood learns bellato, corite, ilay,
  kartika, accretia, kinuan. Two-letter split pieces are limited to real
  function words (`normalize.TWO_LETTER`). `bubbles.looks_like_text` is
  stricter for short reads (a lone `!` or a 2-4 letter read needs OCR
  confidence 0.7; one known word of 3+ letters passes at 0.55; two-letter
  "words" only count when they are function words) and drops anything with
  over 15% stroke characters. Replay result: 21 reads dropped, all junk
  ("N 9 an", "! -dl", "Rt - I", "Od hed ou nt") except one cut-off "But
  I-"; the real short words ("Fool", "Head.", "Haha!", "Yeah.") stay.
  Tests `tests/test_detect_normalize.py` (7, on the real samples).
  Chapters 4-10 re-detected with it (`docs/crew/logs/redetect-4-10.log`;
  counts within one or two of before, chapter 5's texts read cleanly).
  **`tools/renormalize.py <series> [chapters]`** re-cleans every
  un-edited bubble from `text_raw` with the current cleaner and glossary,
  no OCR (102 texts changed across the series at 16:35). Later additions:
  a trailing `...7` / `?7` stroke, "THAVE" -> "I have", glossary words the
  reader split ("BELLA TO" -> Bellato) are joined, a word is learned from
  two sightings (Bellato appears once per chapter). Chapters 1-3 are being
  re-detected, re-cleaned and rebuilt script -> model -> voice -> audio ->
  timeline by `docs/crew/chain-1-3.sh` (log `docs/crew/logs/chain-1-3.log`,
  started 16:38).
- **Two classification bugs found in the chapter 1 re-read (16:50):**
  the prologue's white-on-black captions ("..And earth was destroyed.")
  became screen text (never voiced) because `is_screen_text` only looked
  at the box shape -- now a read of more than three words is never a
  readout (`SCREEN_MAX_WORDS`); and ordinary open captions became sound
  words because the sound-word bar was a fixed 28 px letter height, which
  this high-resolution webtoon's normal lettering reaches -- now the bar
  is 1.7x the chapter's median letter height (`SFX_LINE_SCALE`,
  `classify(..., med_line_h)`). Chapter 1 had 17 "sfx" reads of which 12
  were real lines. Tests added in `test_detect_pipeline.py`; chapters 1-3
  need one more re-detect (the chain was already past detect when this
  was found; chapters 4-10 too, at the next quiet moment:
  `for c in 0004..0010: python -m panelforge.subjob detect <chapter dir>`).
- **Casting by the model (16:55, `audio/casting.py`):** every cast
  member without a hand-chosen voice had none, so all but c01 spoke with
  the preview voice `am_michael`. `POST /series/{s}/cast/voices/auto`
  (button "Cast voices with the model" in the Cast tab) shows the model
  each character's card pictures (up to three, side by side), takes
  `gender | age | timbre` and gives leads first a distinct Kokoro voice
  from a per-timbre table (`TIMBRE_VOICES`), with pitch and speed by age
  (`AGE_KNOBS`); the narrator's voice and hand-chosen voices are never
  reused or touched; a model pick carries `source: "model"` and a `why`
  shown on the card. Tests `tests/test_audio_casting.py` (3, fake model).
  **Run on the real cast (17:05-17:18, 797 s with the chain sharing
  Jan):** 19 of 19 described; the model calls almost everyone "male,
  adult" (a military manhwa; c20 female; c18, c29 teens) with dark or
  bright timbres. The model file has nine American men and the narrator
  holds one, so `assign_voices` now also draws on the British men and,
  once every voice is taken, shares a voice with a pitch and speed
  offset (`REUSE_OFFSETS`, "shared, pitched -0.8" in the why); the
  narrator's voice is never given out. Result: c02 am_puck, c03 am_adam,
  c05 am_onyx, c15 am_michael, c10 am_fenrir, c11 am_echo, c13 am_liam,
  c16 am_eric, c20 af_kore, c19 bm_george, c22 bm_daniel, c18 bm_lewis,
  c23 bm_fable, then six shared voices for the small parts. Chapter 1
  was voiced before the casting landed; `docs/crew/after-chain.sh`
  (running, log `docs/crew/logs/after-chain.log`) waits for the chain,
  re-voices chapter 1 (voice -> audio -> timeline) and renders
  `lookie-09`. Tests: 4 in `test_audio_casting.py`.
- **Picture pass measured on chapter 1 (16:54):** the text pass took 6.8
  min (8 batches of 7-8 lines, 30-50 s each with the CPU otherwise idle),
  the picture pass 2.3 min (9 panels where two cast stand and a line was
  unsure, about 15 s each); 4 speakers came from the pictures, and every
  picture verdict agreed with the drawing where I checked (p0042: the
  two lines go to c02 and c01 in turn). The vision answers also
  confirmed the text pass's own speaker moves. Whole model step for a
  chapter: about 9 minutes on this laptop.
- **Bulk runs gather first, then cast, then build (17:00, `batch.py`):**
  the steps fetch/detect/analyze now run for every chapter before any
  script/llm/voice/audio/timeline/render step, the model casts voices in
  between (`POST .../cast/voices/auto`, unless `cast: false`; a tick box
  on the Library card), so chapter 1 is voiced knowing the whole cast.
  Tests updated (5 in `test_batch.py`). Also: big open lettering that
  forms a sentence ("..And earth was destroyed.") is a caption, not a
  sound word. Suite: 540 passing. Cast tab screenshot with the new button
  taken (headless Chrome, 16:56).
- **Can the 4B find eyes? (17:05, tried):** asked for pixel boxes of the
  eyes and mouth on c01's and c02's card pictures (800x1000 px, 60-70 s
  each). The answer is coarse: one eye box right, the other beside the
  eye, the mouth shifted (`docs/crew/eyes-by-model-c01.jpg`). Not a
  landmark model, but a usable prior: a plan that fits this laptop is to
  ask once per cast member on the card pictures (downscaled to ~450 px,
  ~15 s), turn the boxes into an eye/mouth layout relative to the face
  box, carry that layout to the character's other appearances (same
  drawing style) and let `rig.find_eyes` refine inside the prior boxes
  with relaxed thresholds. Per-appearance requests are out (hundreds a
  chapter at 15 s). Not built.
- **Series words, editable (17:35):** the glossary the reader learns is
  now the user's too: `glossary.json` in the series folder holds `words`
  (always in the glossary) and `banned` (never), merged by
  `learn_glossary`; `GET|PUT /api/series/{s}/words` (GET also lists what
  was learned); a "Series words" fold-out under the inspector on the
  Chapter tab. Tests (normalize + route). Screenshot taken; the live
  server on 8460 predates the route, so the panel said "Not Found" there
  -- restart it (kill the PID in `docs/crew/scratch-8460.pid`, start
  again as in WIP.md) before trying it.
- **Off-panel speakers (17:50):** chapter 2 came back with 43 of 96
  lines on the narrator, 19 of them balloons -- the prompt only allowed
  ids drawn in the panel or the one before, so a balloon in a panel with
  nobody drawn had to be "narrator". `gather` now collects everyone
  drawn anywhere in the same scene; a line in an empty panel is offered
  "in this scene: ..." plus whether its balloon has a tail, the system
  prompt says such a balloon is someone speaking off-panel, and `apply`
  accepts an id from the scene there. Every `why` is now kept on the
  line (before, only with a delivery). Test added (11 in the file).
  `docs/crew/after-chain.sh` was replaced: after the chain it restarts
  the scratch server on this code, re-reads chapter 1 with the model,
  re-voices it and renders `lookie-09`.
- **Scroll reader (17:55, Emerson: "the renders are so messed up ...
  make a thing that will just read the comic scrolling down without
  cutting images"):** new timeline mode `scroll` and style `scroll`
  (`styles/scroll.py`, `timeline.plan_scroll`). The strip is shown as
  drawn, whole width (55% of a 16:9 frame over a dark blurred copy, all
  of a 9:16 frame), the window moves down at reading pace and pauses on
  each panel while its lines play; a panel that fits is centred whole, a
  taller one is scrolled top to bottom over its shot; every cut is a
  plain cut, no panel crops, no cut-outs, no camera inside the art.
  Render tab: Mode "Scroll reader"; a render with a mode, aspect, pace or
  sound different from the saved timeline is re-planned in memory.
  Verified: 4 tests (`tests/test_render_scroll.py`), and
  `chapters/0001/renders/scroll-test.mp4` (63 s, 16:9, 71 s to render,
  frames looked at: caption, lettering and art whole, sides dark).
  `tools/scroll_render.py <series> <chapter> <name> <seconds|0> <aspect>`
  renders one without the server; `docs/crew/scroll-renders.sh` is
  rendering whole-chapter scroll films for chapters 1 (both aspects), 2
  and 3 (log `docs/crew/logs/scroll-renders.log`). Also found: the
  16:50 render-worker change (`PR_SET_PDEATHSIG`) killed every worker
  as soon as the pool's helper thread exited -- replaced by a watchdog
  thread that ends a worker when its parent is gone; the parallel path
  now runs (19 shots on 6 workers). Spawned workers need a real
  `__main__` (a script file), not a heredoc.
  18:12: `chapters/0001/renders/scroll-16x9.mp4` is the whole chapter
  as a scroll film: 598 s, 123 shots, rendered in 585 s (about real
  time), 202 MB; frames at 120/300/480 s show the emblem, the armoured
  figure and the two characters whole with the balloon intact -- nothing
  cut. The 9:16 one is rendering next, then chapters 2 and 3.
  18:00: the Render tab's default mode is now the scroll reader
  (`core.js` defaults; a saved setting in the browser still wins).
  About "t h is f or t he": that was the old word splitter cutting
  all-caps words into dictionary scraps; since 16:30 a piece must be a
  real word of 2+ letters (or a/I), and names are learned per series.
- **Emerson at 18:25:** the scroll film is "almost pretty good"; the
  voices are not good yet; he wants it easier to pick who speaks and
  which voice ("selection of object for voices"), and text slanting
  downwards is not read while upward text is.
  - **Slants (18:35):** synthetic captions at +-8..25 degrees read both
    ways already; at 30 degrees neither did -- adjacent letters on a
    steep baseline sit more than 0.45 letter heights apart, so the line
    chain broke. `text.group_lines` now allows 0.6; a slanted block's
    stray piece lying mostly over the kept whole is dropped
    (`bubbles._covered`). Now +-25 clean, +30 clean, -30 with one stray
    fragment, 35 split. Test `test_caption_slanting_downhill_is_read_too`
    (25 degrees). His real downhill page is unknown -- if a specific
    page still fails, save its panel crop and test on that.
  - **Speaker and voice editing (built 18:40, verified by screenshot):**
    the Cast & voices tab has a **Lines** card: type a chapter, "Load
    lines", and every line shows its balloon as drawn (new route
    `GET .../bubbles/{bid}/image`, strip crop + 14 px margin), its text,
    who says it and the model's reason, a row of faces (narrator, every
    cast picture, "nobody") -- click a face to change the speaker (sets
    `edited`, saved to script.json after 0.4 s; the builder keeps edited
    lines), an audio player and "Re-speak" (saves, then
    `POST .../lines/{id}/voice {}` with the new speaker's voice). Filters:
    a word search and "only unsure" (`lineUnsure`: picture disagrees with
    the speaker, a non-caption given to the narrator, or low balloon
    confidence with no model read). Code: `static/js/tabs/cast.js`
    (`loadLines`, `renderLines`, `onLinesClick`), CSS `.line-row`,
    `.face-pick` in `static/css/app.css`; test
    `test_balloon_crop_route_cuts_the_drawn_balloon_with_a_margin`.
    Suite 549. **19:30:** each row also has **Edit**, opening an editor
    under the line: the words (saved to script.json, `edited` set), a
    voice for this line only (`voice_override.voice`, kept by Re-speak,
    which now sends the line's override instead of `{}`), an expression
    and how strongly (`POST .../script/lines/{id}/emotion`, which re-runs
    the delivery rules and speaks the line again; "automatic" resets).
    Screenshot verified (`lineEditor`, `onLineEditorChange` in cast.js,
    `.line-editor` in app.css). **19:40:** "Speak N changed lines" button
    in the Lines header -- lines whose speaker, voice or words changed
    here (`S.dirty`) are spoken again one after another with one click
    (per-line voice route in sequence, no new backend); Re-speak on a
    row clears its mark. Checked in the browser with the save stubbed.
    **19:45:** a render now re-plans the shots by itself when lines were
    spoken again since the timeline was built (`timeline.lines_respoken`:
    a line's `dur` in script.json differs from the planned shot's by more
    than 0.05 s; edited shots are left alone) -- otherwise a longer new
    voice was cut short or ran into the next shot. Logged as
    "re-planning shots for N re-spoken line(s)". Test
    `test_a_respoken_line_marks_the_film_for_replanning`; chapters 1-3 on
    disk report 0 stale lines. So Emerson's loop is: fix speakers/voices
    in the Lines editor -> Speak changed lines -> Render (scroll) and the
    timing follows.
    **19:42:** "Render scroll film" button beside it (scroll mode with
    the Render tab's aspect/sound/pace, file `scroll-16x9.mp4` or
    `scroll-9x16.mp4`; refuses while changed lines are unspoken). The
    request body was checked on the live server with a 20 s render
    (job done, file deleted again). Emerson's whole loop now lives in
    the Lines card: click faces -> Speak changed lines -> Render scroll
    film. **19:55:** "▶ hear" on every row plays the words in the voice
    the current pick would get (own override, else the speaker's cast
    voice, else the narrator's) through `/api/voices/audition` -- nothing
    saved -- so a speaker or voice can be tried before Re-speak. Route
    checked live (200, a wav). **20:00:** a speaker filter in the Lines
    header (everyone / Narrator / each cast member, with line counts) to
    check one voice at a time; screenshot checked.
    **19:50 -- glow on the spoken balloon (scroll reader):** while a
    line plays, its balloon wears a soft amber ring that fades in and
    out over 0.25 s (`styles/scroll.py` `_glow`/`_ring`, constants
    `GLOW_*`), so the eye finds the words being read while the strip
    moves. Style setting `highlight` (default on). **19:49:** the Render
    tab now draws every style's own knobs from the `/api/styles` listing
    (slider + number field for numbers, tick box for yes/no; in scroll
    mode the scroll style's knobs: strip width, glow), saved in the
    editor settings as `render_style_settings` and sent as
    `style_settings` (new `RenderReq` field, merged over the timeline's
    style by style; a changed knob re-plans the shots; the width knob
    reaches `plan_scroll`). Tests: `test_render_settings_from_the_form...`
    (knobs reach the film), `test_scroll_width_knob_changes_the_plan`;
    screenshot of the Render tab checked. Test `test_the_balloon_being_spoken_gets_a_glow...`;
    checked on a real chapter-1 frame (`docs/crew/glow-c01.jpg`). The
    next scroll render picks it up (workers import the code fresh).
    **21:40, Emerson: "the chapter 2 render is not very good"** (no
    detail yet). A contact sheet of the film showed balloons drawn over
    the gutter cut off at the window's top while read (356 s, 548 s):
    the resting scroll clamped the window to the panel's own range.
    `_scroll_keys` now lets the balloon win when it pokes out of the
    panel box (test extended); chapter 2 `scroll-16x9.mp4` was rendered
    again (21:43, only the 16 changed shots re-drawn, 134 reused from the
    clip cache -- the cache key covers the scroll plan) and the 548 s
    moment now shows the double balloon whole with the ring
    (`docs/crew/c02-548-fixed.jpg`). Whatever else he meant (voices?
    music? pace?) is unknown -- ask him first thing.
    **22:30, glide:** between two lines the resting scroll used to
    drift slowly from one balloon to the next across the whole pause;
    now it keeps resting and glides over in the last `SCROLL_MOVE_LEAD`
    (0.6 s) before the line (test extended). In practice inert on this series:
    lines inside one shot follow each other within 0.55 s, so no glide
    key is ever added (`after-glide.sh` re-rendered 1-2 shots a film at
    22:52). It matters only for a page with long pauses between balloons.
    **All six scroll films of chapters 1-3 (16:9 and 9:16) are final
    as of 22:52**, without the ring, with the resting scroll, the new
    music and the moved thoughts.
    **21:47, Emerson: "it's got yellow boxes around the text."** The
    ring round the spoken balloon is what he saw; it is now off by
    default (`highlight` default False in `styles/scroll.py`; the Render
    tab's tick box turns it on) and every scroll film of chapters 1-3
    (16:9 then 9:16) is rendering again without it from 21:48
    (`docs/crew/no-ring.sh`, PID in `no-ring.pid`). First attempt
    (21:48-21:52) reused the cached clips *with* the ring -- the clip key
    carries the style's `version`, not its defaults -- so `Scroll.version`
    is now 2 and the six films render again in full from 21:58 (about 10
    min each, done by about 23:00). Chapter 1's 16:9 film was checked at
    22:15: no boxes (the only amber left is the art's own fire and
    lettering); the other five follow, chapter 2 16:9 from 22:07. Lesson for next time: bump the style version whenever
    a drawing default changes.
    **21:30:** giving a line to "nobody" in the Lines card now also
    drops its sound at once (the old wav would have kept playing), and
    `lines_respoken` counts such a line as a timing change so the next
    render re-plans the shot (test extended).
    **Tilted lettering finder (21:35):** `tools/tilted.py <series>
    <chapter> [min_degrees]` finds the reader's text blocks, keeps the
    tilted ones, reads them the reader's way (levelled crop, OCR, the
    same text test) and prints each with its angle, confidence, whether a
    balloon covers it ("NOT READ" otherwise) and the words. Chapter 1 has
    one tilted text (uphill, read). Chapters 2-10 are being scanned to
    `docs/crew/logs/tilted.log` (PID in `tilted.pid`): any "NOT READ"
    line there is Emerson's downhill page. **Result (21:45): none.**
    Chapters 2-10 have four tilted texts the block finder sees (+15 to
    +41 degrees) and all are read. So the downhill page he saw is one
    where `text.find_blocks` does not even form a block (letters not
    grouped into lines at that slant) -- the next step is his page: save
    the panel crop and run `find_blocks` on it.
    **Reader (19:40, 20:35):** every balloon record now keeps its `angle`
    (degrees, downhill-to-the-right > 0) so tilted lettering can be listed
    from `bubbles.json` after the next detect run. Chapter 1 spoke a junk
    read aloud ("_Was in he wor kgs.", conf 0.50) because the glued-word
    rescue split WASIN -> WAS IN and WORKGS -> WOR KGS ("known"
    three-letter junk from the word list); `_word_known` now trusts a
    split only at conf >= `GLUE_MIN_CONF` (0.6), test
    `test_a_doubtful_read_is_not_rescued_by_splitting_its_words`; line
    l0019 was silenced by hand (speaker nobody, edited). No other spoken
    balloon in chapters 1-3 reads under 0.6.
    **Music (19:55):** found what was wrong with it without being told:
    the auto pass placed one music segment per run of equal panel mood,
    and the scene analysis flips mood almost every panel (chapter 1: 123
    panels, 60 segments, chapter 2: 95) -- the score crossfaded every few
    seconds. New `music/plan.py` (`segments`, `MIN_PANELS=4`): a segment
    is at least a scene (the scene's most frequent mood, ties to the
    stronger feeling), agreeing neighbours join, a stretch under four
    panels joins the one before. Chapters 1-3 now carry 4 / 8 / 5
    segments (`audio/auto` re-run on all three at 19:53; user-edited
    music blocks are kept as before). Tests `tests/test_music_plan.py`
    (6). Renders of chapters 1-3 with the new music and the glow are
    queued (`docs/crew/after-glow.sh`, PID in `after-glow.pid`, log
    `scroll-renders.log`; ~10 min each). Emerson still has to say
    whether the moods themselves fit -- only he can hear it. (20:22: the
    saved `timeline.json` lists music by id and a plan built before the
    pass kept naming the old segments; `audio/auto` now rewrites that list,
    and chapters 1-3 were brought in step by hand. The scroll films are
    unaffected: `tools/scroll_render.py` plans afresh.)
    **Thoughts read by the narrator (20:05):** the speaker filter showed
    the narrator with 51 of chapter 1's 94 lines, 16 of them thought
    balloons the model had given to the drawn character (c01, c02, c05
    ...) -- `apply` refused because the scene's "narrator, it's a caption
    box" guess comes at 0.8, above `SPEAKER_TAKEOVER`. That guess is the
    kind rule, not knowledge of who thinks it: `_guess_conf` in
    `llm_pass.py` now caps it at `CAPTION_GUESS_CONF=0.5` for caption
    boxes, so the model's character wins (test
    `test_a_first_person_caption_becomes_the_characters_thought` now uses
    the real 0.8). `tools/replay_llm.py <series> [chapters]` re-applies
    the stored model answers without asking the model: chapters 1-3 moved
    16 / 18 / 8 lines to their characters (sound cleared), then the voice
    job with the new `only_missing: true` spoke just those (jobs
    20:00). `after-glow.sh` was stopped (its films would have been
    superseded) and `docs/crew/after-voices.sh` (PID in `after-voices.pid`)
    renders chapters 1-3 `scroll-16x9.mp4` with everything -- new music,
    glow, moved thoughts -- from 20:03, about 10 min each. Suite 559.
    **Chapter 1's film checked (20:15):** 588 s, sound on, the amber
    ring visible round "I'm up against five death row criminals" at
    222 s (`docs/crew/film-222` was the check frame) -- but that balloon
    sat half below the window while it was read: a panel taller than the
    window drifted top to bottom at one speed. **Resting scroll (20:18):**
    `timeline._scroll_keys` gives such a shot `scroll.keys` [(time, y)]:
    the window moves to each balloon by the time its line starts (a quick
    move if it must -- the sound cannot wait), holds there for the line,
    then goes on to the panel's bottom; `styles/scroll._keyed_y` eases
    between keys. Panels that fit, and shots without lines, keep the
    plain plan (no keys). Test
    `test_a_tall_panel_rests_on_each_balloon_while_its_line_plays`; real
    frame `docs/crew/rest-c01.jpg` (balloon whole, ring on). Suite 560.
    `docs/crew/after-rest.sh` (PID in `after-rest.pid`) renders chapters
    1-2 once more after `after-voices.sh`; chapter 3's render already
    starts after the change. Expect all three final by about 21:10.
  - **Lost on the way (18:36):** restarting the scratch server for the
    new route killed the `lookie-09` render job that `after-chain.sh` was
    waiting on (16 minutes in). It was the old cutting style Emerson
    called messed up, so it was not restarted; `after-chain.sh` then
    ended with "connection refused". The scroll renders run outside the
    server (`tools/scroll_render.py`) and were untouched: chapter 2
    `scroll-16x9.mp4` done, chapter 3 rendering since 18:33.
- **`docs/crew/chain-all.sh` (restarted 16:57 with the final classifier, log
  `docs/crew/logs/chain-all.log`):** re-detects chapters 1-3 with the
  fixed classifier, rebuilds each script -> model -> voice -> audio ->
  timeline, then re-detects 4-10 and re-cleans their text. Expect about
  an hour. When "== all done" is in the log: render chapter 1 as
  `lookie-09` (depth3d, 16:9, full sound) and look at frames; run the
  casting on the real cast and re-voice.
- **Cancel reaches the model pass (16:37):** a cancelled script-llm job
  kept asking Jan for half an hour (the lane stayed blocked); `run` and
  `vision_pass` take `check=job.check` and stop between batches/panels.
- **Render workers no longer outlive a killed server (16:50):** six pool
  workers (2.8 GB) from the 02:50 scratch server were still alive at
  16:45 under the fork server. The pool now spawns workers as direct
  children with `PR_SET_PDEATHSIG` (`renderer._die_with_parent`); checked
  by killing a parent and seeing both workers go.

**Open (refreshed 17:30; everything from the earlier list is done except 1):**
1. Puppet eyes and mouth on every face: an anime face landmark model
   (candidates need Emerson's install review: hysts/anime-face-detector,
   nagadomi animeface-2009, lbpcascade_animeface), or the vision-prior
   plan at 17:05 (the 4B's coarse boxes on the card pictures, carried to
   the character's other faces, refined by `rig.find_eyes`).
2. The series cast by hand on the crop bench: c01 merges the red-haired
   man and the dark-haired lead; c03/c07 are one person split.
3. Watch and listen to `lookie-09` (only Emerson can judge the sound);
   look at frames for objects coming apart in the 3D styles.
4. Bulk run 1-3 end to end from the Library card on a restarted server
   (two-phase run with casting has only a fake-API test).
5. ~~Who unloads Jan's model~~ **Found 19:50:** Dossier's `janidle.py`
   (17 "released idle Jan model" lines in `outputs/dossier.log`; the shared
   `forge_jan.release` gets 401 and never unloads). Its CPU-tick test misses
   a request that has just arrived, so it now asks the model server's
   `/slots` before an unload (`slots_busy`); live once Dossier restarts.
   PanelForge's `_ask_twice` retry stays as the safety net.
6. Re-capture the glitched comix.to page (missing letters in "AN
   EXHAUSTION OF RESOURCES"). (MediaForge's downloader: the two fetcher
   calls its buttons make were exercised at 17:45 -- list gives 102
   chapters and the groups, get captured 186 pages of chapter 2 in 163 s
   with the file names its compile step expects; see MediaForge's
   WIP.md. A wrong title link now logs why.)

### State at the stop

- `renders/lookie-05.mp4`: 90 s of chapter 1, depth3d, rendered from an
  empty clip cache with every fix above. Measured on `lookie-04` (same
  inputs, before the two camera and fill fixes): 92.4 s, peak -0.6 dBFS,
  RMS -21.5 dBFS, **96% of the film has sound**, 3 s of silence.
- Chapter 1 data on disk: 123 panels, 132 bubbles, 125 lines (all voiced,
  preview voice `am_michael` where no voice is chosen), 9 cast, 0 extras,
  timeline of 123 shots. `renders/lookie-06.mp4` is the render after the
  cast regroup (same picture as lookie-05; speakers changed ids).
- Scratch server on port 8460 stopped, PID file removed.

### Improve next, in order

1. **Cast editor in the UI**: merge, split, rename, "not a person", and an
   unsorted tray for the 26 unplaced and 27 rejected crops, with edits that
   survive re-analysis. Mask fill and aspect did not separate the junk (the
   junk had fill 0.06-0.99), so no more automatic tuning there.
2. **Bubble order:** the tilted caption on p0006 was numbered b0127 although
   it is the sixth panel; check `order_bubbles` for open captions.
3. **Props extraction** (none yet), Korean/Japanese OCR and translate, the
   Forge Claude panel account picker.
4. Look at the whole 90 s with sound: the voices, SFX and music placements
   have only been measured, not listened to.


Emerson asked for one agent, no subagents, and for the handoff to be written
before the weekly usage limit runs out. Everything below is verified unless it
says otherwise.

**Checks at the end of the session:** `.venv/bin/python -m pytest -q` ->
**480 passed** (472 at the start plus 8 new). `pyright --pythonpath
./.venv/bin/python` clean on every file touched. `black` run on those files.
`/api/health` lists all five API modules with none failed.

### 1. The look-see movie exists now

`~/PanelForgeData/series/bad-born-blood/chapters/0001/renders/lookie-01.mp4`
and `lookie-02.mp4` (the second one after the camera fix below).
Measured: 95.1 s, 1920x1080, 30 fps, h264 (VAAPI on the iGPU), audio muxed,
24 of the 123 shots, 220 s to render (2.3 s of work per second of film).

The pipeline it came from, in order, all through the API on port 8460:
`script/build` (118 lines) -> `voice {"preview_voice": "am_michael"}`
(118 lines synthesised, 54 of them on the preview voice) ->
`timeline/auto {"settings": {"style": "depth3d"}}` (123 shots, 623.7 s) ->
`render {"aspect": "16:9", "bubbles": "keep", "style": "depth3d",
"out_name": "lookie-01", "max_seconds": 90}`.

**Honest judgement of the picture** (frames pulled with ffmpeg and looked at):
- The depth3d look itself is working: the panel sits on a blurred backdrop,
  the camera dollies, there is haze and grain, and the bubbles are readable
  where they are in frame.
- **Tall webtoon panels leave big empty side areas.** A narrow panel in a 16:9
  frame is pillarboxed with a blurred fill, and it reads as dead space.
  Worth trying: fill the sides with the neighbouring strip content, or push
  in further on tall panels, or letterbox deliberately with a border.
- **Text gets cut by the frame edge** (see the fix below, and the part of it
  that is still open).
- Some shots push in so far that the drawing is unreadable; the establishing
  key on a tall panel starts at zoom 2.4.

### 2. New: render part of a chapter (`shot_ids`, `max_seconds`)

`POST /api/chapters/{series}/{chapter}/render` now takes `shot_ids` (a list)
or `max_seconds` (the first N seconds worth of shots). Neither touches
`timeline.json`, which is what made the look-see render possible without
throwing away the full 10-minute timeline. Unknown shot ids give a 404.
Code: `_limit_shots` in `panelforge/api/render.py`. Tests:
`tests/test_render_api.py::test_limit_shots_picks_ids_or_the_first_seconds`
and `::test_partial_render_leaves_the_saved_timeline_alone`.

### 3. New camera rule: the words are never sliced

`rule_text_safe` in `panelforge/camera/rules.py` (in `RULES`, just before
`rule_clamp`). For every camera key it pulls the zoom back (never in) and
nudges the centre until the bubble being read at that moment is fully in
view and no other bubble is cut by the frame edge. Text far outside the view
is left alone, so a close push-in on a face still happens. It does nothing
when bubbles are erased and subtitles are burned in instead.
Tests: `tests/test_render_camera.py::test_text_is_never_sliced_by_the_frame_edge`
and `::test_text_safe_is_off_when_bubbles_are_erased`.

**Still open on the same problem.** The very first shot still shows cut text
in `lookie-02.mp4`, and the cause is not the camera:
- The panel box from detect is slightly tighter than the lettering drawn on
  it. Panel `p0001` is `[84, 240, 644, 220]` while its caption `b0002` is
  `[80, 328, 643, 120]` -- the caption starts 4 px left of the panel, so the
  crop itself loses those pixels and no camera move can bring them back.
- The renderer also pushes in about 6% on shots with shake
  (`extra_zoom` in `panelforge/render/context.py`, `matrix`), which eats the
  1.06 margin the camera rule leaves.
- Fix to write next: in `panelforge/detect/pipeline.py`, after the bubbles
  are merged, grow each panel box to cover the text assigned to it (cap the
  growth, clamp to the strip, do not swallow a neighbouring panel), re-save
  the crops for the panels that changed, and re-write `panels.json`. Then
  make the text-safe margin allow for the shake push-in.

### 4. The character and asset finder (Emerson: "it really does suck")

He is right, and the measurements say why. Before this session, chapter 1
gave **19 cast members plus 7 extras out of 147 appearances** for what is
really a handful of characters.

**What was wrong, measured:**
- The person detector fires on things that are not people: caption boxes, a
  gloved hand, machinery, an emblem, near-empty crops. Those were clustered
  into "characters", which is where most of the 19 came from.
- Average linkage asks *every* pair of pictures of a person to look alike, so
  one character drawn from the front, in profile and in shadow split into
  three identities. Cluster counts on the real chapter: 29 clusters at the
  old threshold, and only 7-9 once the linkage stops using the mean.

**What changed:**
- `cluster.quantile_linkage` (in `panelforge/scene/cluster.py`): merges on the
  q-quantile of the cross distances (q = 0.15) instead of the mean, so a
  character whose views mostly match is one identity, while the cannot-link
  rule still keeps two people drawn in the same panel apart.
- `cast.is_person` (in `panelforge/scene/cast.py`): an appearance only reaches
  the clustering if the detector score is at least 0.35, it covers at least
  1.2% of the panel, it does not sit mostly on top of a speech balloon, and,
  when no face was found, it is both confident (0.55) and sizeable (5%).
  Rejected appearances get label `cast.REJECTED`, stay in `scene.json` with
  `cast_id: null`, and never become cast or extras -- nothing is deleted.
- The detector score is now stored per character in `scene.json`, so this
  filter can be re-tuned without re-running the models.
- Thresholds live at the top of `cast.py`: `MIN_SCORE`, `MIN_AREA_FRAC`,
  `FACELESS_MIN_SCORE`, `FACELESS_MIN_AREA`, `TEXT_OVERLAP_MAX`,
  `CLUSTER_QUANTILE`, `CLUSTER_THRESHOLD`.

**Measured effect on chapter 1:** 147 appearances -> 119 kept as people.
The clustering threshold was then tightened (see section 5), and the data on
disk at the end of the session is **12 cast and 2 extras** from 148
appearances, with 27 dropped as not people.

**Honest verdict: better, not fixed.** Contact sheets from
`tools/cast_sheet.py` (new this session) still show rows that mix two
different characters, and a few non-character crops still survive, though the
junk now lands mostly in its own small clusters rather than inside a
character's. The
remaining work, in the order that will pay off most:
1. Cluster on the **face** crop rather than the whole person box when a face
   was found. Hair and clothes dominate the current colour histograms, and
   CCIP was trained on character crops, not on gloves and armour.
2. Feed the cutout mask fill and aspect ratio into `is_person` (an almost
   empty or extremely thin crop is not a person).
3. Split, don't just merge: after clustering, re-check each cluster and split
   it when two clear sub-groups sit far apart.
4. Give the UI a merge/split/name editor so Emerson can fix what is left by
   hand -- the data model already supports it (`cast.json` keeps names,
   colours and voices across re-runs by appearance overlap).

Backgrounds and props are still thin: 2 backgrounds and 0 props for 123
panels. Props were never extracted; that code path needs writing.

### 5. Second half of session 3 (after "keep going")

**Checks:** 487 tests pass, pyright clean on every file touched, black run.
Note: `black` was run over `panelforge/`, `tools/` and `tests/` as a whole,
not only the files touched, so 18 files show formatting-only changes.

**Detect: panels no longer crop their own lettering.**
`panels.grow_to_text` widens a panel box to cover the balloons and captions
assigned to it, by at most 6% of the panel (and 48 px), never outside the
strip and never into a neighbouring panel, and never on a hand-edited panel.
`detect/pipeline.py` calls it after the bubbles are merged and re-saves the
crops that changed. On chapter 1, **31 of 123 panels grew**, most by one to
four pixels -- which is exactly the amount that was slicing the first
caption. Tests: three in `tests/test_detect_pipeline.py`.

**Camera: the text-safe margin now allows for the shake.** A shaking shot is
drawn about 6% larger than the planned frame, which was eating the margin.
`_safe_margin` in `camera/rules.py` adds that back, plus the wobble.

**Render: a fill that does not look like dead space.** Tall webtoon panels in
a 16:9 frame used to sit on a dark blurred square. There is now a `backdrop`
setting -- `auto` (the default), `stretch` (the panel's own edges carried
outwards and blurred), `blur` (the old fill) and `black`. `auto` picks
`stretch` when the panel is much narrower than the frame.
`render/context.py: backdrop_mode`, tested in `tests/test_render_video.py`.

**Render settings from the UI actually reach the film now.** The render tab
was sending `mode`, `pace` and `motion_strength`, and `RenderBody` did not
have those fields, so pydantic dropped them: the sliders did nothing. They
are now real fields, with `transition`, `effects` and `backdrop`, validated
and passed into the timeline settings. Test:
`test_render_settings_from_the_form_reach_the_film`.

**The UI has been screenshot-verified at last.** New tool:
`tools/ui_shots.py --port 8461 --series test-series --chapter 0001 --out DIR`
drives headless Flatpak Chrome over the DevTools protocol, sets the working
series and chapter in localStorage (which is why plain `--screenshot` only
ever photographed an empty app) and saves one PNG per tab. It disables the
browser cache, or the shot shows yesterday's JavaScript. **Always point it at
a server started with a temporary `PANELFORGE_DATA`.** What the screenshots
showed:
- Library, Chapter, Cast & voices, Previews, Timeline and Render all render
  correctly, and the Chapter tab edits panels and bubbles on the strip.
- **Two endpoints in the frontend did not exist on the backend:** per-shot
  re-render called `/render/shot/{id}` and per-line re-speak called
  `/script/lines/{id}/voice`. The backend serves `/shots/{id}/render` and
  `/lines/{id}/voice`. Both were fixed, so those two editing features work
  now instead of showing "not wired up yet".
- New guard test `test_every_frontend_api_url_exists_on_the_app` compares
  every `/api/...` URL in `static/js` against the app's own OpenAPI paths,
  which is what catches this class of bug. (The older contract test compared
  against a hand-written list, which is how the two wrong URLs passed.)
- All the "helper-N hasn't landed yet" placeholder messages are gone from the
  UI copy; they now say what to do instead ("No timeline yet -- press Auto
  camera/transitions to plan one").
- The render tab and the settings drawer gained "Around the panel"
  (backdrop), "First seconds only" (`max_seconds`) and a file name box.

**Cast finder, second pass: the head, not the whole body.** The person crop
is mostly clothes and background, so two characters in the same uniform
looked alike. `scene/panel.py` now also embeds the head (the face box zoomed
1.7x) and stores it in `feats.npz` as `ccip_face` plus a `face_has` flag;
`cast._face_matrix` turns that into a distance that is NaN wherever a face is
missing, blended at a higher weight than the whole-person embedding. The
panel cache `VERSION` went to 4, so this needs a full re-analysis to take
effect.

### 6. State at the stop (2026-09-19, about 00:55)

Emerson stopped the session to stay inside the weekly usage limit. Nothing is
left running: both scratch servers (ports 8460 and 8461) and the analysis
script were stopped and `docs/.scratch_server.pid` removed.

**Checks at the stop:** 487 tests pass, pyright clean on every file touched,
black run (over `panelforge/`, `tools/` and `tests/` as a whole, so 18 files
carry formatting-only changes).

**Chapter 1 data on disk is current and consistent:**
- 123 panels, **31 of them grown** so their lettering is no longer cropped.
- `scene.json`: 123 panels, 21 scenes, 3 locations, 148 appearances,
  118 speakers guessed.
- `cast.json`: **12 cast, 2 extras** (it was 19 cast plus 7 extras at the
  start of the session), with 27 appearances dropped as not people. Names are
  "character N" and voices are null except `c01` and the narrator, which were
  set in an earlier session.
- `script.json`: 118 lines, all voiced (48 on the temporary `preview_voice`
  `am_michael`), plus **14 auto SFX and 64 auto mood-music segments** from
  `POST /api/chapters/.../audio/auto`, which had never been run on real data.
- `timeline.json`: 123 shots, depth3d, planned with the new text-safe camera.

**The one thing left half-done: the film has not been re-rendered.**
`renders/lookie-01.mp4` and `lookie-02.mp4` are from **before** the panel
growth, the shake-aware text margin, the stretched backdrop and the auto
music. The next session's first command should be the render, and then a look
at the frames:

```
.venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8460   # scratch
curl -s -X POST -H 'content-type: application/json' \
  -d '{"aspect":"16:9","bubbles":"keep","style":"depth3d","out_name":"lookie-03",
       "max_seconds":90,"backdrop":"auto"}' \
  http://127.0.0.1:8460/api/chapters/bad-born-blood/0001/render
```
Expect most shots to re-render (about 4 minutes for 90 seconds of film), then
pull frames with ffmpeg and check three things: the opening caption is whole,
tall panels no longer sit on dead space, and the film is no longer two thirds
silent.

**Measured on `lookie-02.mp4`** (ffmpeg plus a numpy pass over the audio):
95.1 s, peak -0.7 dBFS, RMS -23.7 dBFS, **only 33% of the film has any sound
at all**, 30 separate sound runs, 63 s of silence. That silence is what the
auto SFX and music above are meant to fill; it is unverified until the render.

**One oddity worth knowing:** a scratch uvicorn started with `setsid -f` died
on its own mid-session with a clean log and no OOM. Long jobs are safer run as
a standalone script (see `docs/crew/logs/analyze-ch1-v4.log`, written by a
small script that calls `scene.pipeline.run_analyze` directly).

**How to redo the measurements:** `.venv/bin/python tools/cast_sheet.py
bad-born-blood 0001 sheet.jpg` re-runs `cast.group` with the current
thresholds, prints how many appearances were dropped and the cluster sizes,
and writes a contact sheet with one row per cluster. Look at the sheet: a
good row is one person drawn several ways, a bad row mixes two people or
holds crops that are not people. That is how the numbers above were checked.

## Session 2 stopped here (2026-09-17, about 22:00) -- read this first

Emerson ended the session to hand off. **Next session: one agent, no
subagents** (his instruction). Everything below is verified unless marked.

**State at the stop:**
- Tests: **472 passed** (full suite, after helper-7 and helper-9 landed).
  `/api/health`: every API module loads (library, detect, scene, audio,
  render).
- **Chapter 1 analyze was still running in the background** when the session
  ended: `docs/crew/logs/analyze-ch1.log` (started 21:39, 43 of 123 panels at
  21:47, about 25 s per panel, so it should finish around 22:25). It writes
  `~/PanelForgeData/series/bad-born-blood/chapters/0001/scene.json`,
  `~/PanelForgeData/series/bad-born-blood/cast.json` and
  `work/scene/stats.json` **only at the end**. If the log ends with a
  traceback instead of `scene.json written`, fix the cause and re-run it
  through the API (`POST /api/chapters/bad-born-blood/0001/analyze`) or the
  script pattern below ("How to run detect and analyze by hand"). Re-runs
  are cheap: every finished panel is cached under `work/scene/cache/`.
- A scratch server may still be up on port 8460 (pid in
  `docs/.scratch_server.pid`); stop it with `kill $(cat docs/.scratch_server.pid)`.
- The status snapshot script (`docs/.status_snapshot.pid`) may still be
  running; it is harmless.
- Helper-8 (Forge Claude panel two-account login) was **cut off by the
  usage limit** (resets 02:20 AWST) while writing its docs; its checks had
  passed. Log: `docs/crew/helper-8.md`; app: `~/Forge/apps/claude`
  (runner.py profiles, `/api/profiles` routes, login relay, 20 tests done;
  the account picker UI, screenshot and WIP/README updates were next).
  Task 8 is still `taken` on the board; release it before resuming
  (`crew.py release panelforge helper-8`).
- The session itself ended at the usage limit right after the 472-pass run
  was reported by helpers 7 and 9; the commander's own final full-suite run
  did not happen, so treat "472 passed" as helper-reported, and run
  `.venv/bin/python -m pytest -q` first thing.

**Next session, in order:**
1. Confirm `scene.json` exists (see above). Look at `work/scene/stats.json`.
   Check `cast.json`: clusters are automatic and names are "character N";
   voices are all null (Emerson picks them).
2. **The look-see movie** (Emerson's ask, still undelivered):
   `POST /api/chapters/bad-born-blood/0001/script/build`, then
   `POST .../voice {"preview_voice": "<a kokoro id from GET /api/voices>"}`,
   then `POST .../timeline/auto`, then `POST .../render {"aspect": "16:9",
   "bubbles": "keep", "style": "depth3d", "out_name": "lookie-01"}` with the
   timeline trimmed to the first 1-2 minutes of shots (PUT the timeline with
   the first N shots, or pass `shot_ids` if the render endpoint accepts it;
   see `panelforge/api/render.py`). Target file:
   `~/PanelForgeData/series/bad-born-blood/chapters/0001/renders/lookie-01.mp4`.
   Then **look at frames** (ffmpeg -> jpg, Read tool) and listen to nothing
   (no speakers here); judge the picture honestly.
3. **depth3d chunk 3** (helper-7's log, "Next"): render 3-4 real panels with
   the real bg/depth/cutouts, pull frames, tune `feather`, parallax and
   haze on real art. Then mark task 7 done on the board.
4. Editing features and UI tabs (`static/`, 6 tabs, 3167 lines, never
   screenshot-verified; `tests/test_ui_static.py` only checks routes).
   Start the app on a scratch port against the real data (read-only),
   screenshot every tab, fix what is broken, wire the new endpoints
   (`detect/stats`, `scene/stats`, cast edits, `script/lines/{id}/emotion`,
   per-shot render). Mocks and screenshots must use a temp `PANELFORGE_DATA`.
5. Emerson's other asks still open: (g) a toggle to OCR and translate Korean
   or Japanese (plan in "Ledger" below); the Forge Claude panel account
   picker (helper-8's "Next"); README/WIP kept current.

**How to run detect and analyze by hand** (no server): a script that
inserts the app dir into `sys.path` and calls
`panelforge.detect.pipeline.run_detect(chapter_dir, job)` /
`panelforge.scene.pipeline.run_analyze(chapter_dir, job)` with a small job
object having `log`, `progress`, `check`. Run it with `setsid -f
.venv/bin/python script.py > log 2>&1` and read the log. Never `pkill -f`.

**iGPU (new this session):** `openvino` is installed in the venv.
`panelforge/scene/registry.py` compiles fixed-shape models on the Iris Xe
(`PANELFORGE_SCENE_DEVICE=GPU`, the default; `CPU` to disable). Measured on
one page: faces 1.6 s -> 0.2 s, segmentation 2.45 s -> 0.23 s. Depth stays on
CPU (`CPU_ONLY`) because its input shape changes per panel and OpenVINO
recompiles for every new shape (14 s on GPU vs 6.6 s on CPU). The analyze
run that was in progress started before this change, so it ran on CPU.

## Session 2 (2026-09-17, from 21:24, new account, unattended)

Resumed per "Resuming on a new account": stale claims released, tests
110 passed, `/api/health` showed `api.detect`, `api.scene`, `api.render`
missing (never written in session 1). Commander solo on detect and scene,
plus helpers launched from this session (Emerson allowed more helpers, then
asked to keep spend down; none were launched after that):

| helper | model | task | area | outcome |
|---|---|---|---|---|
| 7 | Opus | 7 | depth3d style, `api/render.py`, previews, per-shot render | landed, 17 new tests; real layered check pending scene.json; task left taken |
| 8 | Opus | 8 | Forge Claude panel (`~/Forge/apps/claude`): two-account login | backend and 20 tests done; UI picker not done; task taken |
| 9 | Opus | 9 | audio: expression-driven voice acting | **done** on the board; 380 audio tests |

## Resuming on a new account (start here)

1. Read this file, then `docs/STATUS.md`. STATUS is rewritten automatically
   every 3 minutes by `docs/status_snapshot.py` (no AI tokens used). It holds
   the crew board, each helper's own log copied in, and a file count per
   area. Its timestamp shows when the build last moved.
2. **Resuming is expensive, so keep it lean.** Emerson measured that a
   cold-start agent costs about 50,000 tokens. Relaunching a commander plus 6
   helpers uses about 35% of his 5-hour limit before doing anything. **Do not
   relaunch the whole crew.** Resume solo, or with at most 1-2 helpers, only
   for areas whose task is not `done` on the board. Give a helper only its
   own area's section of `CONTRACTS.md` and its own `docs/crew/helper-N.md`,
   not every document.
3. **Clear stale claims first.** A helper that was cut off still holds its
   file claims. Check with
   `/usr/bin/python3 ~/.claude/skills/crew/crew.py status panelforge`, then
   release them with `crew.py release panelforge helper-N` before a new
   worker takes the area.
4. Run the tests (`.venv/bin/python -m pytest -q`) and check `/api/health`
   (it lists API modules that failed to import) before building more.
5. **The status script:** its process id is in `docs/.status_snapshot.pid`.
   It stops by itself when every task is done, or after 14 hours. Restart it
   with `setsid -f .venv/bin/python docs/status_snapshot.py`. Stop it with
   `kill $(cat docs/.status_snapshot.pid)`, never `pkill -f`.

## The user

- Emerson (he/him). Solo developer on Arch Linux with Hyprland. Likes a light
  joke; keep the facts plain.
- He wants many questions asked, in batches of four, before building.
- Broad permission to act. No guardrail hooks. Never remove existing features.
- The laptop is a Dell Latitude 5430: **Intel Iris Xe (no NVIDIA)**, 31 GB RAM,
  about 74 GB free disk. Disk is tight, so ask before big downloads.
- Jan (local LLM server at 127.0.0.1:1337) is shared live with other sessions.
  Do not restart it. Load models on demand.

## What PanelForge is

A new app in the `~/Forge` hub (see `~/Forge/README.md`, `~/Forge/docs/archive/MANIFEST-to-2026-09-24.md`
and any app's `forge_app.json` for the registry pattern). It turns manga,
**mainly manhwa/webtoon long strips**, with English text into a **voiced
movie**. The long-term dream is a game built around the story's world
(playing the main character or a side character), but **for now only the
movie maker**.

### Decisions (all from Emerson, 2026-09-17)

- **Name:** PanelForge. A Forge app with the hub theme.
- **Input:**
  - Built-in automated fetcher: paste a chapter or title link, pick the scan,
    and fetch chapter by chapter. It should link to or reuse MediaForge's
    manga downloader (`~/Forge/apps/mediaforge/web_app.py`, around line
    1149), which does not work here right now: it needs a Chrome that
    Selenium can find, and the only Chrome is the Flatpak one.
  - Also takes image folders, CBZ/CBR/PDF, and drag and drop.
  - **The fetcher must be correct: no corrupt pages, no scrambled squares,
    no wrong order.** Always do two passes, because images sometimes fail
    to load.
- **Side feature:** export a whole chapter or series as one PDF for reading
  on a Kindle.
- **Panels:** long strips must be cut into panels intelligently. Panels and
  sprites are sometimes split across separate images, so stitch the strip
  before cutting.
- **Styles, built in stages, all wanted:**
  - voiced slideshow
  - motion comic (pan and zoom)
  - 2.5D puppets (blink, lip-flap, breathing)
  - depth-map 3D panels
  - real 3D character models
  - AI in-between frames
- **Previews:** every option gets a short preview in the app (about 10
  seconds or 5 panels):
  - the same panels side by side in each style
  - a per-panel quick look
  - a voice audition using the character's real line
- **Voices:**
  - Kokoro TTS. Model files: `~/NovelMakerData/tts_voices/kokoro-v1.0.onnx`
    and `voices-v1.0.bin`.
  - **Emerson picks every voice.** No automatic assignment.
  - A narrator voice for caption boxes.
  - Thought bubbles sound softer, with a slight echo.
  - Punctuation drives emotion: `!` is faster and louder, `...` is slower.
- **Sound:**
  - Try automatic SFX (from drawn sound words) and automatic mood music.
  - Also an editor where Emerson places music and sounds himself.
  - Reuse PulseForge parts where they fit (`~/Forge/apps/pulseforge`).
- **Editor:** a full timeline editor covering:
  - panel order and cut lines
  - bubble text and speaker
  - timing and camera moves
  - music and SFX placement
- **Camera and transitions:**
  - Intelligent, driven by rules about the scene and where characters are,
    were and will be.
  - Auto camera by scene, a page-reveal mode and a panel-to-panel mode.
  - Motion strength, pace and transition type are settings, not fixed values.
- **Speech bubbles:** a per-render toggle between keeping the originals and
  erasing them (inpaint) with subtitles.
- **Output:** 16:9 1080p MP4 and 9:16 vertical MP4.
- **Extraction:**
  - Named cast library (recurring characters are named once and keep their
    voice and assets).
  - Extras and common people.
  - Buildings and backgrounds.
  - Props and SFX lettering.
  - Assets stay inside PanelForge, not a shared Forge store.
- **Render budget:** overnight background jobs are fine. AI models may use up
  to about 15 GB of disk. List each model with its real source and size, and
  get Emerson's pick before downloading.
- **Build approach:** Emerson asked for a big crew (6 helpers via the `crew`
  skill) to build most of it in one go, planned first.

## Status

### Verified
- **Test chapter fully and correctly downloaded:** *Bad Born Blood* chapter 1
  from comix.to, 166 pages in order at `testdata/bad-born-blood/ch001/`
  (`001` to `166`). The 150 plain pages are `.webp`. The 16 scrambled pages
  (every multiple of 10) are lossless `.png` screenshots of the reader's
  unscrambled canvas, and all are 800×1280.
- **How that was checked:**
  - Every file decodes.
  - Contact sheets were inspected by eye.
  - The 90 plain pages that could be compared match a separate direct
    download byte for byte.
  - The brightness difference where the bottom of one page meets the top of
    the next looks the same for scrambled pages as for plain ones (largest
    canvas seam 11.3, largest plain seam 14.8, median 2.7). So there are no
    stray tile edges or half-drawn pages.
- **Working fetch method:** `tools/proto_comix_fetch.py`, run with
  `~/Forge/apps/mediaforge/.venv/bin/python tools/proto_comix_fetch.py
  <chapter url> <out dir> [page,list]`. It is a prototype to turn into the
  real `sources/comix` module. Its rules:
  - Headless Flatpak Chrome over CDP with the viewport fixed at 1000×1400
    and a device scale of 1.
  - A style tag hides everything except page images and canvases.
  - Pages are visited by `.rpage-page[data-page=N]`.
  - Plain `<img>` pages download their `src` with a Referer header.
  - `<canvas>` pages: scroll to `block:start`, wait 2 seconds, take a
    clipped `Page.captureScreenshot` at scale canvas.width/rect.width. The
    capture is accepted only when it has real content (grayscale stddev
    above 4) **and** two captures in a row are byte-identical. Up to 20
    tries.
  - Two passes per page.
- `canvas.toDataURL()` does **not** work (it returns an empty image).
  Screenshots taken while the page is still loading, or with the reader UI
  showing, come out blank or with the page counter burned in. Both were hit
  and fixed.

### Crew build in progress (started 2026-09-17)

The foundation is written and **verified** (pytest 5 passed, black clean,
pyright 0 errors):
- `web_app.py` mounts the API modules listed in `panelforge/api_registry.py`.
  A broken module shows up at `/api/health` instead of crashing the app.
- `panelforge/paths.py`: data lives in `~/PanelForgeData`.
- `panelforge/store.py`: atomic JSON writes.
- `panelforge/jobs.py`: background jobs with lanes, cancel and a status file.
- `panelforge/models.py`: model downloads under a hard 15 GB budget, logged
  to `~/PanelForgeData/models/MODELS.jsonl`.
- `forge_app.json` (port 8449), `.venv` (fastapi, uvicorn, numpy, opencv
  headless, pillow, onnxruntime, pymupdf, websocket-client, pytest, httpx),
  and `tests/test_foundation.py`.
- **`CONTRACTS.md` is the shared agreement:** data formats, endpoints,
  ground rules, and who owns which files.
- The test chapter is registered at
  `~/PanelForgeData/series/bad-born-blood/chapters/0001/` (hardlinked pages
  plus `chapter.json`).

Six helpers were launched through the crew board
(`/usr/bin/python3 ~/.claude/skills/crew/crew.py status panelforge`). Each
keeps a resumable log in `docs/crew/helper-N.md`. **If this session died,
read those logs to see how far each area got,** then continue that area
yourself or with a new helper.

| helper | model | area |
|---|---|---|
| 1 | Sonnet | library: comix + generic fetchers (two passes, verified pages), imports, Kindle PDF, shared `~/Forge/shared/forge_mangafetch.py`, MediaForge link |
| 2 | Opus | detect: strip stitching, panel cutting, bubbles, English OCR, accuracy numbers |
| 3 | Opus | scene: cast clustering, extras, backgrounds and inpaint, depth, cutouts, 2.5D rigs, mood, speaker guesses |
| 4 | Sonnet | audio: Kokoro voices (Emerson picks), script and emotion rules, procedural SFX, procedural mood music, `mix_timeline` |
| 5 | Opus | render: styles registry, effects, intelligent camera, transitions, timeline auto, previews, MP4 16:9 and 9:16 |
| 6 | Sonnet | UI: every tab in `static/`, screenshot-verified |

**Requirements added mid-build:**
- **Animation, not image-to-video generation.** The manga drawings are the
  base frames, animated with camera, layers, rigs, in-betweens between real
  drawings, effects and rules.
- **Everything automatic is editable in the editor** (sent to helpers 4, 5
  and 6):
  - per line: text, speaker, voice, emotion, re-speak
  - per SFX and music item: swap, move, gain, delete, add
  - per shot: re-render
  - Edited items become `source:"user"` / `edited:true`, and auto re-runs
    never overwrite them.

**The commander still has to:** integrate each report, run the full test
suite, restart the app and check the whole pipeline end to end on chapter 1,
write `README.md` and `WIP.md`, add a `~/Forge/docs/archive/MANIFEST-to-2026-09-24.md` entry, update
`~/Forge/PROGRESS.json`, and clear the claims.

**Progress log (commander):**
- 21:25: **helper-4 (audio) finished.** Kokoro runs through `kokoro-onnx`
  with the existing model files (54 voices). Also done: emotion rules, the
  script builder, per-line re-speak, 16 synthesized SFX recipes, 6 mood-music
  generators, `mix_timeline`, and every audio endpoint. The commander re-ran
  the tests: **44 passed** (39 audio plus 5 foundation). Not yet run against a
  real timeline from render. The user SFX and music library folders are
  empty. Details are in `docs/crew/helper-4.md`.
- 21:25: **Emerson's priority is the cinematic 3D-ish manga style first.**
  That is the layered depth scene: inpainted background, depth, character
  cutouts, dolly and parallax, depth-of-field blur, atmosphere and action
  effects. helper-3 was told to produce depth, cutouts and backgrounds first,
  and helper-5 to build depth3d first.
- **Emerson wants a rough look-see movie this session:**
  `~/PanelForgeData/series/bad-born-blood/chapters/0001/renders/lookie-01.mp4`,
  1-2 minutes of the start of chapter 1 in the depth3d style. Voices come from
  a temporary `preview_voice` used only for this preview; Emerson still picks
  every real voice.

## Session 1 stopped here (2026-09-17, about 21:40, usage limit)

Emerson stopped the session because the usage limit was nearly used up. **All
helpers were stopped mid-task.** Only helper-4 (audio) had finished. Next
session:

1. Read `docs/STATUS.md`, which is regenerated every 3 minutes. It has the
   crew board and every `docs/crew/helper-N.md` log, each saying where that
   helper stopped.
2. Release the stale claims:
   `for n in 1 2 3 5 6; do /usr/bin/python3 ~/.claude/skills/crew/crew.py release panelforge helper-$n; done`.
3. Run `.venv/bin/python -m pytest -q`. The last full run a helper reported
   was 86 passing, before the stop. Then check `/api/health` for modules that
   fail to import.
4. **Resume lean:** solo, or 1-2 helpers (see "Resuming on a new account").

**Open items at the stop, in priority order:**
- **Chapter 1 data needs rebuilding.** At 21:11 helper-6's UI mock overwrote
  the real `panels/bubbles/scene/script/timeline.json` in
  `~/PanelForgeData/series/bad-born-blood/chapters/0001/`. The mock files are
  gone now, and only `chapter.json` and `strip.json` remain. Re-run detect,
  then analyze. **Rule:** UI mocks and screenshots must use a temp
  `PANELFORGE_DATA`, never the real folder. helper-6 was told; check that its
  tests follow it.
- **Top priority (Emerson): the cinematic 3D-ish style (`depth3d`).** Layered
  inpainted background, depth, character cutouts, dolly and parallax,
  depth-of-field blur, atmosphere, action effects. helper-3 was producing
  depth, cutouts and backgrounds first; helper-5 was building depth3d.
- **The look-see movie was never delivered.** Target:
  `renders/lookie-01.mp4`, 1-2 minutes of the start of chapter 1 in depth3d.
  For preview only, voices use `preview_voice` (helper-4 built it and it is
  tested).
- **New requirement: expression-driven voice acting.** Kokoro's delivery
  should follow facial expressions, environment acoustics, balloon shape and
  lettering style (size, weight, wavy, bold). The contract fields are written
  in `CONTRACTS.md`, section "Expression cues for voice acting". Status:
  - Sent to helper-2 (bubble `style`), helper-3 (`expression`, `acoustics`)
    and helper-6 (show and override the cues). They were stopped right after,
    so this is probably **not started**.
  - Never sent to audio: the rules that map cues to Kokoro speed, style
    blending, gain and DSP are **not started**.
- **Everything automatic must be editable** (per-line re-speak, swapping and
  moving SFX and music, per-shot re-render). Audio endpoints: done. Render and
  UI: check the helper logs.

**Scope decision (Emerson, 2026-09-17):** full quality in every area, not a
minimal basic path. He will add subscription capacity across several sessions
and accounts. So resume lean on tokens (solo or 1-2 helpers), but never cut
the ambition.

### Later stages (not in this crew)
- Real 3D character models (the `model3d` style slot is reserved).
- The game built around the manga's world, with play as the main character
  or a side character.
