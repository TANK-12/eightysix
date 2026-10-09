# U1 critic, group G11: AI Studio and PixelForge
date: 2026-10-08 · for: Claude · by the G11 critic (fresh session, launched by relay-86-work)

Reviewed commits e03fd10 (PixelForge) and 625af42 (AI Studio) against
`U1-worker-brief.md` and the draft report `reports/u1-G11.md`. Scratch servers
on 9015 (PixelForge, copies of `~/ForgeArtData` / `~/ForgeGameData` under
`/tmp/u1/G11-critic/data`) and 9016 (AI Studio, isolated copy with empty
`models/` and `bin/`, so nothing can generate). Both stopped by PID. Scripts:
`/tmp/u1/G11-critic/fuzz.py` (API) and `crit.py` (`pf_kill`, `pf_boot`,
`as_kill`, headless Chrome through `tests/cdp_driver.py`).

## Breaks

1. **medium, verified: a pack save accepts a sprite whose `tags` is not a
   list, and that sprite then breaks Ask Jan.**
   Where: `apps/pixelforge/web_app.py:96` `_pack_problems` (checks only that
   each sprite is an object); the crash is in `janart.py:167`
   `tile_choices()` (`"tile" in tags` with `tags == 5`), called by
   `GET /api/jan/art/ready` (`web_app.py:242`).
   Repro: `POST /api/art/packs` with
   `{"pack":{"id":"crit_p6","sprites":{"s":{"w":2,"h":1,"tags":5,"frames":[{"ms":0,"rows":[".."]}]}}}}`
   gives 200 and writes the pack. Then `GET /api/jan/art/ready` gives 500
   (`TypeError: argument of type 'int' is not a container or iterable`), and
   the Ask Jan panel says "server is not answering" every time it is opened.
   Deleting `crit-p6.json` brings the route back to 200. Games that read
   `tags` would hit the same thing. The commit message claims "malformed
   packs ... refused", but this one gets through.
   Fix: in `_pack_problems`, refuse a sprite whose `tags` is present and not a
   list of strings (and `frames` not a list of objects). Add a test that saves
   it and expects 422. Optionally make `tile_choices` skip non-list tags.

2. **low, verified: an art id that is too long for a filename is still a 500.**
   Where: `web_app.py` `keep_sprite` (`forge_art.save_palette`) and
   `keep_structure` (`forge_content.save`); `forge_art.slug` has no length cap.
   Repro: `POST /api/jan/art/keep-sprite` with `pack: "a"*300` (valid rows and
   palette) gives 500, `OSError: [Errno 36] File name too long`. Same for
   `POST /api/jan/art/keep-structure` with a 200 kB `id`. Nothing
   half-written (the palette save fails first). This bug was already there
   before the sweep, but the worker's claim "keep-sprite validates before
   writing anything" does not cover it.
   Fix: refuse ids or slugs longer than about 64 characters with a 422 in
   both routes (and in `put_pack` / `put_palette`, which give a 422 today only
   because an empty pack fails validation first).

3. **low, verified: size caps are partial; huge text still reaches disk.**
   Repro (all 200, written): a pack sprite named with 200 kB
   (`/api/art/packs`, crit_p2), `keep-structure` with a 200 kB `source`,
   `keep-world` with a 200 kB `label` and `description`. `palette.roles`
   `{"a":5}` and keep-sprite `tags:[null,5]` are also stored. Sounds now cap
   at 200 characters, but for an over-long `id` the 422 detail echoes the
   whole 200 kB id back to the toast.
   Fix: apply `TEXT_CAP` to sprite names, pack and palette labels, structure
   `source`, world label and description, and cut the id in the error text.

4. **low, verified: Sounds does not recover with the library.** After a failed
   first load (or opening Sounds while the server is down), the library card
   recovers by itself, but the sound list stays on "The sound library is not
   answering. Try again" until the user clicks.
   Where: `static/index.html` `loadLibrary` success path (~line 318) and
   `loadSounds` (~702).
   Repro: `crit.py pf_boot` (blocks `*/api/*` with `Network.setBlockedURLs`,
   opens `/?mode=sounds`, unblocks after 50 s). Output: `recovered library:
   True`, `sound list after recovery: The sound library is not answering. Try
   again`.
   Fix: in `loadLibrary`'s success branch, call `loadSounds()` when
   `SND.loaded === false`, or retry sounds from the same poll.

5. **low, verified: the boot card heading renders in all caps.** "THE ART
   LIBRARY IS NOT ANSWERING YET" because the card uses `<h3>`, which the
   page styles `text-transform: uppercase` for small section labels. A full
   sentence in caps reads as shouting, which Emerson's rules forbid.
   Screenshot: `/tmp/u1/G11-critic/shots/pf-bootdown-760.png`.
   Fix: use `<p class="card-title">` or `.card h3{text-transform:none;font-size:14px;color:var(--ink)}`.

6. **low, verified: NaN or Infinity in a request body is a 500, not a 422.**
   Where: `apps/ai-studio/src/app.py` request models (the new `Field` bounds).
   Repro: `POST /api/generate/image` with raw body
   `{"prompt":"a","cfg_scale":NaN}` (likewise `Infinity`, and
   `/api/generate/video` with `motion_strength: NaN`) gives 500,
   `ValueError: Out of range float values are not JSON compliant`: the bound
   correctly refuses the value, but FastAPI cannot JSON-encode the NaN echoed
   in the 422 body. The page never sends NaN (`num()` filters it), so only
   scripts reach this.
   Fix: `model_config = ConfigDict(allow_inf_nan=False)` on the float fields
   (or `Field(..., allow_inf_nan=False)`), which rejects NaN with a normal
   message, plus a test.

7. **low, verified: a library query that can never succeed is retried
   forever.** A 200 kB search makes uvicorn answer 400 ("Invalid HTTP request
   received."). The gallery shows "library failed (400) Trying again by
   itself..." and keeps polling (2 requests in 10 s, backing off to 30 s) until
   the search box changes. Not a storm, but the wording is not calm and the
   retry is pointless for a 4xx.
   Where: `static/index.html` `loadLibrary` catch (~line 728).
   Fix: retry only on network errors and 5xx; for a 4xx show "That search is
   too long" and stop. Optionally add `maxlength="500"` on `#search`.

8. **low, suspected (from the code; the check could not run, see "not
   covered"): a video finished while AI Studio is hidden never starts.**
   `showInStage` sets `autoplay = ForgeIdle.shown()`, and `stageRest` resumes
   only a video it paused itself (`stageVideoResting`). A video job that
   finishes while another hub app is in front therefore sits paused when the
   user comes back. Before the sweep it autoplayed.
   Where: `static/index.html` `showInStage` (~858) / `stageRest` (~868).
   Fix: when hidden, set `stageVideoResting = el` in `showInStage` instead of
   leaving autoplay off, so `stageRest` starts it on show.

9. **low, suspected: video thumbnails with `preload="metadata"` may show
   black in WebKitGTK.** Chrome paints the first frame with metadata preload;
   WebKitGTK/GStreamer often does not. Only the real Forge window can show
   this, and nobody has looked there (the worker says so too).
   Fix: check in the hub. If the tiles are blank, use `preload="auto"` only
   for thumbnails inside the viewport (IntersectionObserver), or a poster
   frame.

10. **low, pre-existing, suspected: edits made while a pack save is in
    flight are marked saved.** `#save` handler sets `E.dirty = false` after
    the answer, even if the user painted during the request, so the
    beforeunload guard does not warn. Not introduced by the sweep, but the
    new `send()` is the natural place to fix it (compare a change counter
    before and after).

## Checked and fine

- Tests: AI Studio 46 passed, PixelForge 43 passed (run myself). `black
  --check` clean on all touched .py. pyright: PixelForge 0 errors; AI Studio
  7 errors, the same 7 as on the pre-commit versions (checked by running
  pyright on `git show 625af42^:` copies).
- Commit hygiene: each commit touches only its own app (4 and 5 files), no
  other session's hunks, `git status` clean for both apps, no debug prints
  or commented-out code in the added lines, backups present in
  `backups/2026-10-07-overhaul/sweep/{ai-studio,pixelforge}/`.
- Real data compatibility: all 36 real sounds, 14 packs and 7 palettes pass the
  new validators (read-only check), so nothing Emerson has can no longer be
  re-saved.
- AI Studio library search: `"`, `a AND`, `NEAR(`, `*`, `prompt:a`, `^a`,
  unicode all give 200 (no 500). Bounds: width 63, seed 2^32, 4001-char
  prompt, gif, batch 65, keyframes 9999, 21 scenes, unknown motion (simple
  and per scene), 201 delete ids, wrong types all give readable 422s. Page
  options (sizes 384-1024, steps 1-40, cfg 1-20, batch 1-8, fps 6-30, hold
  2-16, keyframes 2-30, scene frames 1-30, all nine motions) sit inside the
  new bounds. Job ids are `uuid4().hex[:12]`, so the `isalnum` check on
  `/api/jobs/{id}/state` does not lock out real jobs.
- AI Studio server killed for real (by PID) with Models open: 3 requests in
  0-10 s, 7 in 10-30 s (models plus gallery retry, backing off), calm
  "Can't reach the AI Studio server right now. Trying again by itself..."
  in both panes; hub-hidden while down 0 fetch, 0 timer; restarted: recovered
  by itself to 5 model cards and 14 thumbnails; no page errors.
- PixelForge server killed for real: Save gives a calm toast (one POST for a
  double click while up), Sounds shows Try again, Ask Jan says to reopen;
  0 fetches in 0-30 s while down; after the restart, reopening Ask Jan loads
  the 7 sizes once (two more opens: still 7, no doubling); Sounds recovers on
  reopen; no page errors.
- PixelForge first-load failure (blocked API): calm card, 1 request in
  0-10 s and 2 in 10-30 s, 0 while hub-hidden, recovers by itself with the
  editor visible.
- Screenshots: the worker's after-sheets for all three PixelForge modes and
  the three AI Studio views at 760/1100/1500/1920, side by side with the
  before shots: no clipping, overlap or layout jumps. The theme matches the
  shared neutrals, and the thin scrollbars show at 760.
- Negative or huge sound numbers (`freq -5`, `duration 1e9`) are still
  stored: the worker documented ranges as the editor's business. That is a
  choice, not a break.

## Not covered

- The hidden-page 10 s counter rerun with the frame preview and stage video
  playing (`pfcheck.py rest`, `ascheck.py rest`, `crit.py
  as_hidden_finish`): headless Chrome died seconds after start once media
  played, because the machine was out of RAM (about 600 MB free, swap full;
  crew note #1155). I relied on the worker's results for those and on the
  code (both use `ForgeIdle.poll`). The rest checks with the server down
  (above) did run: 0 work while hidden.
- Nothing was looked at in the real Forge window (WebKitGTK). No generation,
  no Jan call. Rapid double clicks on the AI Studio model buttons were not
  re-run (the worker's `ascheck.py ui` covers them).
