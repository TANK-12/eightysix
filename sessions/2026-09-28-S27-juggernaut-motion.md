# S27: Juggernaut motion from the new anime cuts, then Model 1's clips (2026-09-28)

Start line for a fresh session:
`Read ~/Forge/sessions/2026-09-28-S27-juggernaut-motion.md and do it.`

Written by Sakura (ejb-f4) for a reader with no history. Emerson is collecting **more anime
cuts** of the M1A4 Juggernaut (86: Eighty Six). The job has two parts: (A) a fast, accurate
movement analysis of the new cuts, then (B) feed it into Model 1's animation clips and finish
Model 1's paused render.

## Where things stand (verified on 2026-09-28 unless marked)
- **Model 1** = `~/Models/juggernaut/v2/`, finished at `jg2_m18_final.blend`. Read
  `v2/README.md` sections "Scale and axes", "Files" and "Status (Model 1 final)".
- **Model 2** = `~/Models/juggernaut/model2/` (Tsubaki, ejb-fd). It owns the on-screen
  Blender window. **Never edit model2/ or drive that window.** Work headless.
- **Nagi (ejb-6b)** builds a Godot game from Model 1 and exports `jg2_m18_final.blend`.
  Never overwrite m17 or m18. New work goes in `jg2_m19_<tag>.blend`. When it's saved,
  message Nagi its name (SendMessage), and post it on the crew board for the print session (ejb-fc).
- **First analysis already done:** `~/Models/juggernaut/refs/anime-motion/ANALYSIS.md`
  (Nagi; 4 clips c1-c4, 2 screenshots). Its findings: walk step 0.5 s per leg with a high
  lift and a stamp, CG run stride about 0.25 s, body low and level when running (no bob),
  skids/drifts with sparks, jump legs hang straight down (**never tuck**), gun raised 35-45
  degrees at rest, the body turns to aim. Its "Artefacts" section lists what not to copy.
- **Paused render:** the m18 final render job was frozen (SIGSTOP) at Emerson's request,
  because he needed the CPU. Blender pid 84013, script pid 84001, started 20:50, still on
  the action stills (`images/57_action_m18/`). Log `/tmp/jug/final_job.log`. It only
  survives until a reboot.
- Model 1 is open in its own Blender window (pid 90049) for Emerson to look at. Leave it be.

## Part A: movement analysis of the new cuts

### Where the cuts are
Emerson's recordings land in `~/Desktop/Juggernaut/refecne form the actuall anime/`
(that is the folder's real, misspelt name). The ones already analysed are
`Screencast From 2026-09-28 20-26-51 / 20-28-42 / 20-30-35 / 20-31-50.mp4`; anything newer
is new. If there is nothing new, ask Emerson where the cuts are. Don't guess.

### The tool (built and tested for this)
`~/Models/juggernaut/refs/anime-motion/cuts.py`, system python3 (ffmpeg + magick):
```
cd ~/Models/juggernaut/refs/anime-motion
python3 cuts.py prep "<new video>" ...     # each gets the next id: c5, c6, ...
python3 cuts.py detail c5 12.3 12.8        # one move, full 854 px, 2 across
```
- `prep` makes `cN_480p.mp4`, finds the cuts (scene score 0.15, flashes under 0.125 s
  merged), and keeps **every changing frame** (mpdecimate), so held drawings and paused
  playback collapse to one frame each and the burned-in time is the real time. It writes:
  - `cuts/cN_overview.jpg`: one tile per cut, plus one per 2 s of a long cut. **Look at
    this first.** One image covers a whole clip.
  - `cuts/cN_cutKK.jpg`: every changing frame of one cut, 6 across;
  - `cuts/cN.csv`: cut, start, end, number of drawings, frames per drawing (on 1s, 2s or 3s).
- Tested on Emerson's 20-28-42 recording: 16 cuts and 305 changing frames in 3.5 s. The
  overview shows every Juggernaut shot on one sheet. `detail c 16.6 17.2` found the same 12
  drawings as Nagi's hand count of the 0.5 s step loop.
- A 0.30 scene threshold missed most cuts in this dark, purple footage, which is why it's
  0.15. A pause can still merge two cuts; the 2 s overview tiles are there to catch that.

### Keep it cheap (tokens)
1. Overview sheet per clip. Note which cuts show a Juggernaut moving, and skip the rest
   (pilots, Legion, close-ups of faces).
2. Cut sheets only for those cuts.
3. `detail` only for a single move you are timing, **0.5 s or less** (a longer range makes a
   very tall sheet). Never open the single frames one by one.
4. Do the looking yourself in the main session. No subagents (Emerson's standing rule).

### What to measure, and how it maps to the clips
Current values in `v2/anim.py` (24 fps). Measure the anime value next to each one:

| Motion | anim.py now | Measure in the cuts |
|---|---|---|
| walk | `CREEP` 4-beat, one foot up at a time; cycle 48 fr (2.0 s), duty 0.75 (each foot swings 0.5 s), lift 0.22 m, 3.6 m in 168 fr | order legs lift in, swing time (lift to plant), lift height against knee height (1.77 m), stride against body length (stance is 3.9 m long, 5.7 m wide) |
| run | `TROT` diagonal pairs; cycle 16 fr (0.67 s), duty 0.5, lift 0.35 m, 12 m in 108 fr, body drops 0.10 m x speed | pairing (diagonal? bound?), step time (CG shot said 0.25 s), body height against standing, stance width |
| turn / strafe | walking turn 90 deg in 120 fr; strafe 2.2 m | whether it drifts or powerslides instead (ANALYSIS says drift, legs braced outside, sparks) |
| jump | crouch, take-off fr 27, land fr 51 (1.0 s air), 1.1 m high, 2.4 m long, **legs tuck** | air time, leg pose in the air (hang straight, spread?), landing crouch depth and recovery time |
| idle | gun raised `GUN_REST_PITCH` 7 deg, body scans +-9 deg | rest gun angle (35-45 in the anime) |
| fire | body turns 14 deg, gun +-3 deg; 3 shots at fr 36/54/72, recoil 0.35 m | shot spacing, recoil and body kick, flash shape |

How to read timing honestly:
- **Time only from the burned-in timestamps**, never from the number of tiles. Anime is
  drawn on 2s and 3s (see the csv), so one drawing can last 2-3 frames.
- **AMV editors retime footage** (speed ramps, slow motion on the beat). Trust a timing
  more when two cuts agree, or when it comes from the 3D CG sequence (drawn on 1s). Mark
  every number with the cut it came from and how sure you are.
- Speed in 2D shots is often faked: a held pose with the camera panning, plus dust. Don't
  read travel speed from those.
- Get sizes from the machine itself (body length, knee height), not from the screen.

### Output
Append to `ANALYSIS.md` a section `## Batch 2 (cN-cM, <date>)`: the per-cut table (which
cuts show what), findings per motion, and a table **measured / anim.py now / proposed**.
Don't rewrite Nagi's sections; correct them only with a note on what the new cuts show.
Post a one-line summary on the crew board, since Nagi (the game) and Tsubaki (Model 2) both use it.

## Part B: continue Model 1

1. **Ask Emerson before any heavy render.** He asked for his CPU and GPU back at 20:55.
   Stopping the paused job: `kill -CONT 84013 84001` resumes it and `kill 84013 84001`
   ends it. Partial images stay in `images/57_*`; never delete images.
2. Update the clips in `v2/anim.py` with Part A's numbers. Keep each change a named
   constant or clip parameter, the way `GUN_YAW_MAX` and `GUN_REST_PITCH` are. Known gaps:
   the jump tucks its legs (the anime hangs them straight), the run bobs the body, and
   there is no drift turn. A new clip = one function plus one `CLIPS` entry.
   **Limits on Model 1's geometry (measured on m18):**
   - gun pitch: the magazine hits the ground past about 13 deg (lowest point 0.50 m when
     level, 0.08 m at 10, -0.03 at 13), and the elevation ram runs out past about 20. So
     keep Model 1's gun under about 10 deg and write that down. The 40-degree rest is Model 2's.
   - knee-ram overlap at least 80 U in every clip (85.3 U lowest now, in the run).
3. Check headless, and save m19 from the same run:
   ```
   cd ~/Models/juggernaut/v2
   SKIP_CYCLE=1 SAVE=jg2_m19_anime_motion.blend blender -b jg2_m18_final.blend --python anim_checks.py
   ```
   Read `/tmp/jug/m18_report.json`: slip (pads within 0.005 mm, ankles within 0.004 mm),
   knee-ram overlap, gun ranges, and the magazine's height per clip (must stay above 0).
   Wider or lower stances change the ram numbers, so check each run.
   Look at the clips with a smoke render (3 frames each, into /tmp, light on the CPU):
   `JG_SMOKE=1 JG_CLIPS=walk,run blender -b jg2_m19_anime_motion.blend --python render_anim.py -- /tmp/jug/dry 640`.
4. When Emerson agrees to a full render:
   `setsid nohup ./render_final.sh jg2_m19_anime_motion.blend <first free images number> &`
   (the next free number is 60 unless more folders have appeared; it links onto the Desktop
   as `Renders/Model 1 - m19 anime motion/`).
5. Message Nagi the m19 name and post it on the board. Add a "Status (Model 1, m19)"
   section to `v2/README.md` that says what is verified, and a line to
   `~/Forge/sessions/2026-09-28-juggernaut-v2.md`.

## Rules
- Pace by `python3 ~/.claude/tools/usage.py`. At 95% of the 5-hour window, write the
  handoff and stop.
- Claim `~/Models/juggernaut/v2` on the crew board while you work in it, and release it after.
  `refs/anime-motion/` is shared with Nagi: add to it, don't rewrite Nagi's files.
- Keep every image. `black` and `pyright` any .py file you touch.

## Result (Ren, ejb-24, 2026-09-28)
Part A done: ANALYSIS.md "Batch 2" (c5-c8), `cuts.py strip` added, zoom sheets in cuts/zoom/. Part B done up to step 3: m19 = v2/jg2_m19_anime_motion.blend, checks in v2/README "Status (Model 1, m19 anime motion)". Step 4 (full render) not started: ask Emerson. The paused m18 job: 84001 was killed by Riku, 84013 is still SIGSTOPped.
