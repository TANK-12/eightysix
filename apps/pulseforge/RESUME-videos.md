# Where the two videos got to — stopped 2026-09-08, to pick up tomorrow

## Stopped cleanly
Nothing is running. The `tide-and-time` render was killed at ~45% and its temp
dir removed. The `moonlit-drift` project was deleted by the user.

## What is still on disk
- `~/PulseForgeData/projects/tide-and-time/` — the music-linked project, built
  and verified, not yet rendered.
- Build scripts (regenerate either project from scratch in seconds):
  `/tmp/.../scratchpad/build_video.py` (ambience) and `build_linked.py`
  (music-linked). **These are in /tmp and will not survive a reboot** — copy
  them into the repo if they are worth keeping.

## The two real problems to fix first

1. **No music.** Neither video ever had a music track from ncs.io. NCS needs a
   human to click through their download gate; that is the blocker and it has
   not moved. The fix is not code: put 4-6 NCS mp3s in a folder, then point
   `build_linked.py`'s `SRC` at them.

2. **The audio is far too loud.** `render._audio_filter()` normalises every
   render to **-14 LUFS**, which is YouTube's *music* target. For a bed of
   rain/wind/waves that is punishingly hot — ambience and sleep videos normally
   sit around -20 to -24 LUFS. This is a real defect in the app, not just in
   that project: **the loudness target should depend on what the audio is**, or
   at minimum be a per-project setting. Not yet fixed.
   - Cheap check: `ffmpeg -i <out.mp4> -af ebur128=peak=true -f null -`
   - Cheap fix for an existing file (no re-encode of the video):
     `ffmpeg -i in.mp4 -af loudnorm=I=-22 -c:v copy -c:a aac -b:a 256k out.mp4`

## What is genuinely done and verified (v8 work, all tested)
- `musicmap.py` tempo is now averaged over inlier beat gaps, not the median of
  frame-quantised ones. The test track was reading **120 BPM when it is 118**;
  bar error 33.8 ms -> 0.1 ms, and loop drift over a 3.3-minute shot 3.32 s ->
  0.01 s.
- Section naming falls back to relative loudness when timbre clustering
  collapses (which it does on any track with one consistent arrangement — every
  section was coming back "chorus").
- `palette.py`: bloom is a hump on highlight *amount*, not a ramp on bright
  *area* (it was blooming already-bright pictures hardest and clipping them);
  film grades are damped on flat vector artwork; warmth is read from the lit
  parts so sunsets stop reading as cold.
- `auto-look` writes to `shot["look"]` / `shot["camera"]`, not `shot["params"]`
  which nothing reads.
- 306 tests pass, pyright clean apart from the pre-existing `forge_art` warning.

## Also worth knowing
The `render_dir` setting (Settings tab, `~/Videos/PulseForge`) is **read by
nothing**. Every render path is built from the project folder. Either wire it up
or remove the control.
