# AI Studio feature audit

date: 2026-10-08 · for: both · by: helper-4 (Ami), crew `ai-studio`

Every existing feature was run end to end **without the GPU and without a
model**. A fake sd-server (`tests/sd_stub.py`) answers the same A1111-style
routes as `bin/sd-server` (`/sdapi/v1/samplers`, `/txt2img`, `/img2img`)
with solid-colour PNGs (img2img returns the init image nudged toward a
colour), on scratch ports 9011-9030. RIFE is the real binary forced onto the
CPU (`-g -1`, 64 px frames). Real-ESRGAN has no CPU mode, so the tests use a
stand-in script with the same flags that resizes with Pillow. ffmpeg and
ffprobe are real. All paths are temp dirs; Emerson's `models/`, `outputs/`
and live server on 8430 were not touched (read-only counts below).

Tests: `tests/test_features_units.py` (42) and
`tests/test_features_pipeline.py` (21), run with
`.venv/bin/python -m pytest -q tests`. Full suite with every helper's tests
at the time: **306 passed, 128 skipped** (skips are other helpers' live/opt-in
tests).

## Summary

| Feature | Before | Now | Fixed in |
|---|---|---|---|
| txt2img / img2img request building | works | works | - |
| sd-server errors (500, down) | works (EngineError, 502) | works | - |
| Image: upscale + jpg/png + library | works | works | - |
| Image batch on GPU + CPU | fragile: a dead CPU server failed the batch | works, falls back to GPU | hybrid.py |
| Upscale tool failures | **broken**: exit 0, no file, then a 500 | reported to helper-1 | engine.py (helper-1) |
| Warp video: pans | **broken**: black strip on the wrong side, 3% more per frame | mirror-filled, sweep-tested | motion.py |
| Warp video: zoom-out | **broken**: crashes every time | works | motion.py |
| Warp video: orbit | fragile: tiny black corners | mirror-filled | motion.py |
| Repeated warps | fragile: one resample per frame, blur builds up | one resample per block | motion.py, longform.py |
| Anti-drift blend | **broken**: ghosted any moving camera | colour match instead | motion.py, longform.py |
| Long pans (many frames) | fragile: after ~30 frames 90% of the input was filler | re-bases on the newest healed frame every N frames | longform.py |
| Seeds | fragile: seed used for the first frame only, the rest random | one seed per scene, all frames | longform.py |
| Scene cross-fade | fragile: could blend into an older scene | clamped to its own two scenes | longform.py |
| One-keyframe video | **broken**: RIFE "decode image failed" on one frame (verified); the video is then one frame, 1/12 s (reasoned) | frame held for hold_frames | longform.py |
| RIFE interpolation | works (CPU check) | works; frame count now (n-1)*hold+1 | longform.py |
| ffmpeg assembly | works for even sizes; **broken** for odd sizes | reported to helper-1 | engine.py (helper-1) |
| GPU + CPU scheduler | fragile: CPU grabbed the last frame; one dead backend failed the job | tail rule, failover, retire | hybrid.py |
| Job state | fragile: no status/phase/error; non-atomic writes | status, phase, error, atomic | longform.py |
| Job cancel | **missing** | `longform.request_cancel`; route asked of helper-1 | longform.py (+ app.py) |
| Library search | works (U1 fixes kept) | works | - |
| Library delete | works | works | - |
| Thumbnails | fragile: gallery loads full 2048 px JPGs and whole mp4s | `thumb_url` (<=384 px), video first frame | library.py (+ static, helper-3) |
| Failed-job leftovers | fragile: never shown, never listed | `library.orphans()` lists them (deletes nothing) | library.py |
| DB connections | fragile: never closed | closed every call | library.py |
| Outputs serving | works: `..` and outside paths are 404 | works | - |

## Evidence

### Request building (works)

`test_txt2img_sends_a1111_body_and_saves_png`,
`test_img2img_sends_the_init_image_from_bytes_or_path`,
`test_lcm_lora_tag_added_once`, `test_server_errors_become_engine_errors`:
the stub receives `prompt, negative_prompt, width, height, steps, cfg_scale,
sampler_name, seed` (+ `init_images` base64 of the exact input PNG and
`denoising_strength` for img2img); the LCM tag is added once; a 500 or a
closed port is an `EngineError`. `strings bin/sd-server` lists the same field
names (`sampler_name`, `denoising_strength`, `init_images`, `cfg_scale`).
Reasoned, not verified: that the real server honours every field the same
way (no real generation was run).

### Motion presets (pans and zoom-out broken)

Old `motion.py`, 100x100 red frame, each preset applied 1, 10 and 30 times
(`/tmp/h4/probe_motion.py`):

```
pan-left   step  1 black 0.030
pan-left   step 10 black 0.300
pan-left   step 30 black 0.900      (same for pan-right/up/down)
zoom-in    step 30 black 0.000
  File "src/motion.py", line 52, in apply_motion
    img = img.resize((w, h), Image.LANCZOS, box=box)
ValueError: box offset can't be negative      (zoom-out, first step)
orbit-cw 1 black 0.001
```

Cause: `_edge_extend_fill` pasted the fill strip on the side the content
moves *toward*, not the side the camera reveals; zoom-out asked Pillow for a
box outside the image. Through the old video pipeline with the stub
(`/tmp/h4/probe_old.py`):

```
zoom-out FAILED: ValueError box offset can't be negative
pan-right 8 OK; last frame dark fraction 0.047
seeds sent for a scene with seed=1: [-1, 1]
dead CPU server: FAILED: EngineError sd-server unreachable at http://127.0.0.1:9 ...
state keys: ['backend_counts', 'completed_frames', 'frames', 'job_id', 'scenes', 'started_at', 'total_frames']
```

Fix: `motion.warp(image, preset, steps=n)` is one affine resample of a
mirror-tiled copy of the frame (pan offsets folded by the mirror period,
zoom-out pre-shrinks the frame so the mosaic stays small). Sweep test:
every preset x steps 1-60 x sizes 64x64 / 96x64 / 64x96, plus 30 chained
single steps: **no dark pixel anywhere** (27 cases). Direction tests: pans
move content against the camera, pan-down moves it up, zoom-in widens a bar
and zoom-out narrows it, rotation matches Pillow's `rotate()` direction as
before (mean pixel difference 2.8 against 40.9 for the opposite direction).

### Anti-drift blend (ghosting) and long pans

The old job pulled the warped frame toward the anchor *picture* every 4
frames (`Image.blend(frame, anchor, 0.15)`), so a panned frame got a 15%
copy of the unpanned one: a ghost. Its inputs were also pure warps of the
first frame, so after 30 frames of a 3% pan the input was 90% filler.

Now (longform docstring): frames go in blocks of `anchor_interval`; each
block warps from the newest healed frame (one resample), so new scenery
painted by img2img is carried forward; each healed frame's colours (mean and
spread per channel) are pulled toward the anchor by `anchor_weight`.
`test_color_match_fixes_colour_without_ghosting`: colour error cut to under a
third, no blue from the anchor's bar position appears. `test_motion_reaches_the_frames`:
a two-colour anchor panned right moves the colour edge 32 -> lower -> lower
through the healed frames.

### RIFE and ffmpeg

```
rife-ncnn-vulkan -i 3 frames (64 px) -o out -n 9 -g -1   -> rc 0, 9 PNGs 00000001.png.., 0.14 s
rife ... -i dir with 1 frame -n 1                        -> "decode image r/one/ failed", rc 0
rife ... -i empty dir                                     -> Segmentation fault, rc 139
rife ... -m /nonexist                                     -> rc 255, no output
ffmpeg 9 RIFE frames -> h264 64x64, ffprobe nb_read_frames 9
ffmpeg 65x63 frames  -> "width not divisible by 2 (65x63)", rc 187
realesrgan ... -i nonexist.png                            -> rc 0, no output file
realesrgan ... -g -1                                      -> "invalid gpu device", rc 255 (no CPU mode)
```

`test_two_scene_video_end_to_end`: two scenes (pan-right 7 frames, zoom-out
4), both backends, cross-fade 2, RIFE on CPU, ffmpeg; ffprobe says `h264
64x64 yuv420p`, 41 frames = (11-1)*4+1; state.json `done`, 11/11 frames,
one seed per scene; the second scene starts with img2img (one txt2img in
total). `test_single_keyframe_video_holds_the_frame`: 1 keyframe, hold 6 ->
6 frames. `test_api_video_and_delete`: the `/api/generate/video` handler
end to end, then `/api/jobs/{id}/state` says done, delete removes the row
and folder.

### Scheduler (hybrid.py)

`test_tail_rule_keeps_last_frames_off_the_slow_cpu` (GPU 0.05 s, CPU 0.5 s,
4 tasks: all on GPU), `test_cpu_still_helps_with_a_long_queue` (20 tasks:
both work), `test_dead_cpu_server_slows_the_job_but_does_not_fail_it`
(CPU retired, all 8 done on GPU), `test_error_on_every_backend_is_raised`
(this one hung the first rebuilt version: the tail rule waited for a GPU
that had already failed the task; fixed and kept as a regression test),
`test_cancel_drops_waiting_tasks`, `test_api_image_batch_uses_both_backends`
(6 seeds 10-15 spread over both stub servers).

### Job state and cancel

`test_cancel_stops_at_the_next_frame`: 30-frame job, cancel file after
0.3 s, stops within 3 s, state `cancelled`. `test_failure_is_recorded_in_state`:
both servers 500 -> state `failed` with the error. `test_state_file_is_never_half_written`:
a reader thread parsing state.json during 300 rewrites saw no broken JSON
(writes go to `state.json.tmp` then `os.replace`).

### Library

`test_library_thumbnails_for_images_and_videos` (1600x1200 JPG -> <=384 px
thumb; mp4 -> first-frame thumb, never enlarged; a row whose file is gone
says `missing`), `test_library_output_path_stays_inside_outputs`,
`test_library_orphans_lists_failed_job_folders`, `test_library_closes_its_connections`
(200 record/search/delete rounds, open file count steady), and the 37 U1
cases in `tests/test_u1_robustness.py` still pass.

Read-only look at Emerson's live `outputs/` (not changed): 16 job folders,
13 library rows, 3 orphans: `bb6e723a6f35` and `8bbf525ee384` (failed video
jobs: state.json + keyframes), `29c5f0445927` (empty). Left in place.

## Reported to other owners (not edited here)

To helper-1 (board note 8): upscale/interpolate exit 0 without output, so
check the output exists; odd sizes break libx264 (pad to even); map
`hybrid.Cancelled` to a 409 and add `POST /api/jobs/{id}/cancel` calling
`longform.request_cancel`; update the `anchor_interval` / `anchor_weight`
comments; `batch_count` allows 64 but is capped at 8 silently.
To helper-3 (note 9): use `thumb_url` in the gallery.

## Not verified

- No real generation: the stub stands in for the model. Whether the real
  sd-server heals mirror-filled edges well is reasoned, not seen.
- Real-ESRGAN was not run on the GPU (Relay 110 was measuring fps on it);
  only its flags and failure exits were checked.
- Speed of the new block scheduling against the old one on real hardware.
- Video requests still run inside the HTTP request (app.py); a job cannot be
  cancelled from the page until helper-1 adds the route.
