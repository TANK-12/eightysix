# Eighty Six: the run log (telemetry) and its report

date: 2026-10-08 · for: both · written by a helper of Riku (session ejb-6a), AAA plan feature 8, gap 23, step N1

## What it is

Every run now writes a log: one file per level visit, one JSON object per line (JSON lines). The same
log comes from bot runs and from Emerson's own play, so a bot's numbers and a real session's numbers can
be compared, and a later engine (the bake-off) can be measured with the same tape.

- **Bots:** always on. Logs go to `user://telemetry/bot/` and the bot's `report.json` gets a
  `"telemetry"` field with the log's full path.
- **Play:** off by default. Settings > Gameplay > Play log > Keep a play log turns it on
  (`telemetry.play_log` in `data/settings.json`; moved there in the fix round below). Logs go to `user://telemetry/play/`.
- `user://` is `~/.local/share/godot/app_userdata/Eighty Six/` on this laptop.
- Each folder keeps the newest **20** runs; older ones are deleted when a new run starts. Nothing else in
  the folder is touched.
- A run starts when a level registers (`Game.register_level`) and ends when you leave the map (menu,
  Hangar, restart, another map), quit, close the window, or the bot finishes.

What a line looks like (real lines from a headless bot run on small_map):

```
{"kind":"run","t":0.0,"v":1,"mode":"bot","map":"small_map","started":"2026-10-08T21:57:19","sample_every_s":0.5,"spike_ms":50.0,"axes":"x east, y up, z south (north is -z), metres","build":"0.1.1-alpha","bot":"/tmp/claude-86/telebot/tele.json"}
{"kind":"wave","t":1.0,"pos":[-250.0,12.4,330.0],"wave":1,"waves":3,"units":2}
{"kind":"shot","t":2.01,"pos":[-249.3,12.5,328.9],"weapon":"gun_57mm","ammo":"apfsds"}
{"kind":"kill","t":3.02,"pos":[-245.5,12.8,322.0],"enemy":"ameise","at":[-124.2,10.7,147.1],"by_you":false,"distance_m":212.9}
{"kind":"end","t":5.5,"reason":"bot finished","lines":38}
```

The kinds: `run` (first line), `sample` (every 0.5 s: position, speed, health, mean and worst frame time
since the last sample, plus the mech's own heading, pitch, roll, airborne, grounded legs and skidding),
`units` (every 2 s while a mission runs: each Legion unit's id, position, hull health, brain state,
whether it sees you and its distance), `beat` (a story beat fired: id, trigger, mission time), `shot`, `hit_taken`, `part_lost`, `fall` (the mech tipped past the righting
angle), `stand_up` (upright again, with how long it lay; neither is logged once the mech is destroyed), `destroyed` (where you died), `wave`, `kill`,
`mission_end`, `spike` (a single frame over 50 ms of wall time), `end` (last line). Every event carries
`pos`, the player's position. `t` is game seconds since the run began; paused time (pause menu, photo
mode) is left out, and the first frame after a pause is not counted as a spike.

Units: metres, seconds, metres per second, milliseconds for frame times. Axes: x east, y up, z south
(north is -z), the game's own frame.

## The report

```
python3 tools/telemetry_report.py --latest          # the newest play log
python3 tools/telemetry_report.py --latest bot      # the newest bot log
python3 tools/telemetry_report.py <file.jsonl>      # one log
  options: --spike-ms MS (default: the log's own spike_ms)   --cell-m 50   --folder <telemetry folder>
```

Plain text, standard library only. Sections: a header (map, mode, build, length, why it ended, the
mission's result and grade), totals (shots, hits taken and damage, parts lost, kills and how many were
yours, falls, average time on the ground per fall, health at the end), **where you died** (position and
the hits in the 10 s before, by enemy type), **where you struggled** (50 m map squares ranked by trouble:
a hit taken counts 1, a part lost 3, a fall 2, a death 5; with the time spent there), **time per wave**
(each wave from its start to the next wave or the mission's end, with its kills, shots, hits taken and
falls), **time between beats** (each story beat with its mission time and the gap since the one
before), and **frame-time spikes** over the threshold the log was written with (count, the worst, which squares they cluster in, the ten
worst with their times). A log with no end line (the game was killed) still reads; the report says so,
and a half-written last line is skipped and counted. An empty log (a run still starting) gets a plain
message and exit code 1, and `--latest` skips a newest file that is still empty.

## How it is built

| File | What |
|---|---|
| `scripts/core/telemetry.gd` | `class_name Telemetry`. Pure rules at the top (`wanted`, `file_name`, `to_drop`, `encode`, `vec`: plain values in and out, so a port re-types them as they are); the engine side below (signals, files, a worker thread). |
| `data/telemetry.json` | The log's schema and settings: `log` (format version, sample and flush intervals, keep 20, spike 50 ms, folders) and one entry per kind with its fields and units. |
| `scripts/core/game.gd` | Owns one `Telemetry` child (`Game.telemetry`); begins a run in `register_level` (bots, or play with the setting on), ends it in `_leave_level` and `quit_game`. |
| `scripts/mission/mission.gd` | Three lines in `_ready`: an open log (group `telemetry`) gets the mission's waves, kills and end. |
| `scripts/core/bot.gd` | Two lines in `_finish`: closes the log before the quit and puts its path in `report.json`. |
| `data/settings.json` | The `telemetry.play_log` toggle (group "Play log" on the Menus and theme page). |
| `tools/telemetry_report.py` | The report. |
| `tests/test_telemetry.gd`, `tools/tests/test_telemetry_report.py` | The tests. |

Never blocking a frame: lines are built in memory (a `PackedStringArray`); every 2 s the buffer is handed
to a `WorkerThreadPool` task that writes and flushes it. If the last write is still running, the lines
wait for the next flush. Only the end of a run waits for the disk.

The player's events come from the mech's `MechCombat` signals (`fired`, `hit_taken`, `part_lost`,
`destroyed`); falls and stand-ups from the mech's own `is_tipped()` checked each frame; health from
`DamageModel.total_fraction()` (the same figure the after-action report calls armour left). Nothing in
`scripts/mech/` or `scripts/locomotion/` was changed.

## How to extend it

- **A new event:** add an entry to `data/telemetry.json` (`about` and `fields` with units), then one call
  `Game.telemetry.event("<kind>", {...})` where it happens (or a `_link` to a signal in `telemetry.gd`).
  A kind with no entry still logs but warns once. If the report should read it, add a function in
  `telemetry_report.py` and a test.
- **More in each sample:** add the field in `Telemetry._sample()` and in the `sample` entry's fields.
- **Different timings:** change `log` in `data/telemetry.json`; no code.
- **The AAA plan's pacing check** ("no stretch over 3 minutes without a story or fight beat") can be
  read from this log once the beat runner logs a `beat` event: one entry plus one call.

## Verified (with the check and its real result)

- `tools/run_tests.sh test_telemetry`: **9 passed, 0 failed**. They cover: the setting exists and is off
  by default, bots always log; file names sort in time order; rotation drops only the oldest `.jsonl`
  (25 runs, keep 20) and on disk leaves 20 logs with a `readme.txt` untouched; nothing reaches the file
  in the frame the lines are made, everything lands at the end; a short scripted fight (the rig's flat
  ground, the Juggernaut, one Ameise) logs `run`, `sample` (2 to 3 in just over a second), `wave`,
  `shot`, `hit_taken`, `part_lost`, `fall`, `stand_up` (with `down_s` > 0), `kill` (`by_you` true),
  `mission_end` (won) and `spike` (80 ms fed in counts, 20 ms does not), every kind is a
  `telemetry.json` entry, `t` never runs backwards and every event has a position; the player destroyed
  logs `destroyed` and a lost mission; with no run open nothing is written and the mission runs as before;
  through the real `Game` hooks, play logs nothing with the setting off, opens a `play` log with it on,
  and leaving the map closes it with reason "left the map".
- Suites touching the hooks, all passing after the change: test_mission 32/32, test_after_action 6/6,
  test_bot 5/5, test_settings 15/15 (the lineup check included), test_registry 11/11, test_radio 4/4,
  test_kill_cam 4/4, test_scripts 1/1, test_free_roam 3/3, test_squad 11/11, test_hangar 18/18,
  test_photo 3/3, test_pause 1/1. The full suite was not run (other helpers had files mid-edit).
- `python3 -m unittest discover -s tools/tests -p test_telemetry_report.py`: **9 passed** (half-written
  lines skipped and counted; where you died with the 10 s before; the worst square ranks first; wave
  times to the next wave and to the mission's end; a wave still going; spikes by threshold; the text
  report's lines and no shouting; a cut-short log says so; `--latest` picks the newest of a mode).
  `black` and `pyright` on both Python files: 0 errors.
- A real headless bot run (CPU only, `godot --headless ... -- --bot=<scratch script>`): exit 0, no
  errors, `report.json` names the log; the log held 1 run, 11 samples, 1 wave, 1 shot, 2 kills, 22
  spikes and 1 end line, and `telemetry_report.py --latest bot` printed the report (worst frame 295 ms
  at 1.0 s, the moment the script started the mission).
- Other helpers' bot runs during this work wrote logs through the new hook without anyone changing
  their scripts (small_map, big_map and brilon logs at 21:54 to 21:56).

## Reasoned, not measured

- That the flush never stalls a frame: the main thread only joins strings and queues a task; the write
  is on a worker thread. The time the main thread spends was not timed.
- Size: a sample line is about 150 bytes, so about 18 KB a minute plus events; a run held under 20 fps
  logs a spike every frame (up to about 60 KB a minute). 20 runs kept per folder stays small, but a very
  long, very slow session could make one file of a few megabytes.
- Headless frame times are not the game's: the headless spikes above are a dummy renderer on a busy
  CPU, not the fps the game gets on screen. Use logs from real windowed runs for frame-time work.

## Decisions taken by default (for Emerson)

- A run is one level visit, not one game session: restarting a mission starts a new log.
- The play log is off by default and sits on its own Gameplay page, Play log > Recording > Keep a play
  log (first on Menus and theme; moved in the fix round).
- A fall is the mech tipping over (past the righting tip angle, `is_tipped()`); a hard landing is not
  logged as a fall. Adding one is one entry plus a link to the mech's `landed` signal.
- The struggle weights (hit 1, part 3, fall 2, death 5) are a first guess in `TROUBLE_WEIGHTS` at the
  top of the report script.

## Fix round (2026-10-08)

A second helper of Riku fixed the critic's findings. Each behaviour fix had a failing test first, seen
red, then green.

Fixed:

1. **The report's spike threshold now follows the log.** `--spike-ms` defaults to the `spike_ms` in the
   log's run line (50 ms when there is none); the option still overrides it. Red first:
   `test_the_report_uses_the_log_s_own_spike_threshold` and `test_main_reads_the_threshold_from_the_log`
   (a log with spike_ms 33 and a 40 ms frame said "over 50 ms ... None"), green after.
2. **Samples carry the mech's own figures.** `data/telemetry.json` `log.mech_fields` names which of the
   mech's `telemetry()` figures each sample copies: heading_deg, pitch_deg, roll_deg, airborne,
   grounded_legs, skidding (each described in the sample entry). Test:
   `test_a_sample_carries_the_mech_s_own_figures`.
3. **Legion units are logged.** A new `units` line every `units_every_s` (2 s) while a mission runs, one
   row per unit of the wave from `Mission.unit_report()`, cut to `log.unit_fields` (id, pos, hull, state,
   sees, to_player_m). Test: `test_legion_units_are_sampled`.
4. **Story beats are logged.** `Mission` has a new signal `beat_fired(id, on)`, sent from one helper
   `_run_beat` that both beat loops use; the log writes `beat` lines (beat, on, mission_s), and the report
   has a "Time between beats" section. Tests: `test_story_beats_are_logged` (GDScript) and
   `test_time_between_beats`, `test_no_beats_says_so` (Python).
5. **No fall after death.** The log stops checking for falls once the player's mech is destroyed. Red
   first: `test_a_wreck_toppling_is_not_a_fall` found a fall after the destroyed line; green after.
6. **The untested hooks are tested.** `test_window_close_ends_the_run_as_closed` (the end line says
   "closed") and `test_the_bot_report_gets_the_log_path`: the bot's report step is now
   `Bot.close_run_log(log, report)`, a static function `_finish` calls, so a test can run it without
   quitting. `quit_game`'s one line `telemetry.end("quit")` is still untested, because the function quits
   the test process.
7. **The setting reads plainly.** It moved to its own Gameplay page "Play log", group "Recording", label
   "Keep a play log". The help no longer names a developer script and says "Test runs by the game's
   checking bot always keep a log of their own." Test: `test_the_play_log_toggle_reads_plainly_in_gameplay`
   (red on the old placement, green after). No screenshot of the new page was taken: no GPU runs were
   allowed in this wave, so Riku or Emerson should look at it once.
8. **Empty logs.** `main()` prints "This log is empty: ... The run may still be going, or it stopped
   before its first write." and returns 1; `--latest` skips a newest file of 0 bytes. Tests:
   `test_an_empty_log_says_so`, `test_latest_skips_a_newest_log_that_is_still_empty`.

Rejected, with evidence:

- **"The test leaves telemetry.play_log on and squad_size at 0 for later test files."** Not so:
  `after_each` calls `rig.free_all()`, and `tests/lib/mission_rig.gd` ends `free_all` with
  `Settings.reset_all_quietly()`, which puts every setting back to its default
  (`scripts/core/settings.gd`, `reset_all_quietly`). Checked by running: a temporary test placed after
  `test_game_logs_play_only_with_the_setting_on` asserted play_log false and squad_size 2.0, and passed
  (`ok test_zz_tmp_settings_after_game_test`); the temporary test was then removed.

Verified after the fixes:

- `tools/run_tests.sh test_telemetry.gd`: all 16 telemetry tests pass (9 old, 7 new). The same run
  shows other helpers' files that did not compile at the time (test_legs_realmesh, test_textures,
  test_world_look); those are not this item's.
- `python3 -m unittest discover -s tools/tests -p test_telemetry_report.py`: Ran 16 tests, OK. black
  clean, pyright 0 errors.
- test_settings, test_settings_screen, test_settings_search, test_mission, test_bot, test_after_action,
  test_radio, test_kill_cam: all their own tests pass. test_mission_beats had 3 failures at the time, in
  tests another helper was rewriting alongside uncommitted changes to beats.gd and mission.gd (problems
  wording, end-stops-chained, wave-cleared line); none touches the run log.
- A headless CPU bot run on small_map (start_mission, clear_wave, quit) exited 0 with errors []. Its log
  held run 1, sample 18, units 4, wave 1, kill 2, spike 1, end 1. A real sample line:
  `heading_deg 28.0, pitch_deg 2.9, roll_deg -2.4, airborne false, grounded_legs 4, skidding false`;
  a real units row: `id ameise, pos [-127.4, 10.1, 176.5], hull 1.0, state alert, sees false,
  to_player_m 196.7`. The report printed the new "Time between beats" section ("No story beats in this
  run.", since small_map's mission has no beats yet).

Reasoned, not measured: the units line costs one `unit_report()` every 2 s and the sample one mech
`telemetry()` call every 0.5 s; neither was timed. A units line for a wave of eight units is about 1 KB,
so about 30 KB a minute more at worst.

