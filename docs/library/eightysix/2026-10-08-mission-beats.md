# Eighty Six: mission beats

date: 2026-10-08 · for: both

Built by a helper of Riku (session ejb-6a). Spec 5.2 P0, gap 2: "every story moment rides on them".

## What it is

A mission in `data/missions.json` may carry a `"beats"` list: the scripted story moments of that mission.
A beat is one entry:

```json
{"id": "at_gate", "when": {"on": "area_entered", "area": "gate"},
 "do": [{"do": "spawn", "groups": [{"enemy": "ameise", "count": 1, "area": "east", "tag": "late"}]},
        {"do": "radio", "line": "m1.wave1.010"}]}
```

It fires once, the first time its trigger holds, and runs its actions in order. `"enabled": false` switches a
beat off. Units are SI: metres on the map's x and z, seconds, health as a fraction 0..1. Waves count from 1.

**Triggers** (`"on"`):

| on | fields |
|---|---|
| wave_started | wave |
| wave_cleared | wave |
| unit_destroyed | enemy (enemies.json id) and/or tag (a spawn group's tag), count (default 1) |
| area_entered | area (a mission area; its radius_m, 20 m if it has none), or at [x, z] with radius_m (required). A name the mission lacks never fires |
| timer | after_s, since: "start" (default) or a beat id |
| part_shot_off | enemy, part: a damage key (wp_optic_sensor) or a kind (core, leg, weapon, weak); both optional |
| health_below | fraction (the player's armour left, all parts) |
| beat_done | beat |

**Actions** (`"do"`):

| do | fields | what it does |
|---|---|---|
| radio | line (a dialogue database id, data/dialogue/*.json), or event (a radio.json event), or text + speaker (a draft, test_only missions only) | emits `Mission.radio_line(speaker, text, line or event id)`; an event goes to the Handler radio; a line or text goes to it once radio.gd has `say_text` |
| objective | text | sets the objective line |
| spawn | groups (as a wave's, each may add tag); alerted | spawns them into the current wave |
| music | cue (music.json id), fallback | plays the cue, or the fallback when the cue's file is missing; music set to off stays off |
| weather | id (weather.json) | calls the map's existing `set_weather(id)` |
| camera | note | a hook that only logs for now |
| fade | to (0..1), seconds, color [r, g, b] | a full-screen cover, over the HUD and under the radio subtitles |
| end | result: won, lost or scripted; text | ends the mission; scripted is a story ending, recorded as a win, the objective shows text. Nothing after it runs: not the rest of its actions, not beats chained on it |

## Where it lives

- `scripts/mission/beats.gd`, class `MissionBeats`. Two halves, per the AAA plan section 7 rule 5:
  - **the pure runner**: `feed(event)`, `tick(dt_s, facts)`, `problems(list, areas, known)` and every `_when_*`
    trigger test. Data in, fired beats out, no engine calls; another engine re-types it as it is.
  - **the engine edge**: `run(mission, beat)` and one `_do_*` handler per action, a few lines each.
- `scripts/mission/mission.gd`: the hooks. `_start_beats()` builds the runner only when the mission has a
  beats list (else `beats` stays null and nothing new runs). The mission feeds `wave_started`, `unit_destroyed`
  (with the group's tag), `wave_cleared` (before the last wave's win, so a beat may end it its own way),
  `part_shot_off`, and a `tick` each physics step with the player's [x, z] and armour left. New public bits:
  `spawn_groups(groups, alerted)` (the old wave spawning, pulled out unchanged), `end_as(result, text)`,
  signal `radio_line(speaker, text, line)`, state `"scripted"`, and a `"beats"` key in `summary()` (only with
  beats; the beats whose actions ran, in order).
- `data/missions.json`: the schema is in `_about`. `beats_demo` is a **test-only** mission (`"status": "test_only"`,
  on test_range), so `Mission.for_map` never offers it. The two playable missions have no beats and play as
  before.
- `tests/test_mission_beats.gd`: one test per trigger (pure runner), one per action (a mission in a bare level),
  the `problems` check, every mission's beats against the registries, a mission without beats has no runner,
  and `beats_demo` played from the registry to its scripted end.

## How to extend

- **A new trigger**: one `_when_<name>(when, event) -> bool` function in beats.gd and one `TRIGGERS` entry
  (`"test"` the function name, `"needs"` the required fields, `"a|b"` for either). If it needs a new event, one
  `_beat({...})` call where the mission sees it.
- **A new action**: one `_do_<name>(mission, action)` function and one `ACTIONS` entry.
- **A beat**: one entry in a mission's `beats` list. `MissionBeats.problems()` names unknown triggers, actions,
  areas, beats, enemies, music, weather and radio lines; the registry test runs it over every mission.

## Verified

- `tools/run_tests.sh test_mission` (both files): **32 passed, 0 failed in 81.7 s** (11 old mission tests, 21
  new beats tests).
- Neighbouring suites, each run alone: test_after_action 6/6, test_radio 4/4, test_squad 11/11,
  test_kill_cam 4/4, test_registry 11/11, test_tone 5/5, test_tutorial 4/4, test_bot 5/5. test_scripts 1/1 for
  its own test; the runner also reported another helper's untracked `tests/test_zz_golden_scratch.gd` as "does not
  compile" (not part of this work).
- No warnings or script errors from beats.gd or mission.gd in the test output.

## Reasoned, not checked

- **Nothing seen on screen.** No GPU run in this wave. The fade's alpha over time is tested headless. The
  first build's claim about draw order was wrong; see the fix round below for the corrected placement.
- (Superseded by the fix round: `line` now means a dialogue database id and the radio.json event is `event`.)
  **A beat's `text` radio line is not shown to the player yet.** `HandlerRadio` (scripts/ui/radio.gd, not this
  helper's file) only says radio.json events. The text goes out on `Mission.radio_line`, and the handler calls
  `say_text(speaker, text)` on the radio if it has one. To show it: add `say_text` to radio.gd and nothing else
  changes. `line` (a radio.json event) does reach the radio, a frame late so a first-wave beat is not lost
  before the HUD exists.
- **Music cues are transient**: the music player's own context switch (combat starts or ends) may pick another
  track later. A cue that must hold needs a "hold" in music.gd.
- **A "scripted" end shows the normal end screen** (MissionHud opens it on `ended(true)`), as a stand-in until
  the campaign runner moves on to the next mission.
- Spec 5.2 also lists "scripted death" and a real camera move as actions; not in this item, each is one new
  action when wanted.

## Decisions taken (defaults, for Emerson)

- Waves count from 1 in beat data (as the summary and HUD show them), 0 in code.
- Beats fire once each; no repeating beats.
- Spawned groups join the current wave, so a wave is not cleared while they live.
- Scripted endings count as a win for the after-action records.
- The demo beats live in a test-only mission, not in ashen_first_contact.

## Fix round (2026-10-08)

A critic reviewed the first build (no blockers, no majors, seven minors). A second helper of Riku fixed all
seven, test first: each new test was run and seen to fail before the fix (8 failing), then pass. Commit `b9af2e8` (the first build was `5cc4b6e`).

**What changed**

1. **Misnamed area.** `area_entered` with an area name the mission does not have never fires (it used to become
   a 20 m circle at [0, 0] and fire near the map origin). A point (`at`) now needs its own `radius_m`; without it
   the beat never fires and `problems()` names it. A named area without a radius keeps 20 m, the same default
   spawns use.
2. **`problems()` survives bad shapes and names more.** A `when` or an action that is not an object, a beat that
   waits on itself (`since` or `beat` naming itself, or a ring such as a waits on b, b waits on a), a wave
   outside 1..the last (waves count from 1 in data), an unknown part (with the Legion's damage keys passed in),
   a fade `to` outside 0..1, a radio `text` in a mission that is not test_only, an unknown dialogue line.
   `feed()` and `run()` skip such entries instead of stopping on a script error.
3. **mission.gd branches now tested in a mission**: a wave_cleared beat that spawns re-opens the wave (state
   running, still wave 1, the next wave not counting down, the spawned unit's death then starts wave 2); a
   wave_cleared beat on the last wave ends it scripted, not won; a leg the player shoots off reaches
   `part_shot_off`, and a hit on the Juggernaut reaches `health_below`. The "Wave cleared. More Legion inbound"
   line is now sent after the beats and the re-check, so it is not shown (and the Handler radio does not call
   wave cleared) while a beat's spawned units fight; a wave_cleared beat that set its own objective keeps it.
   Missions without beats send the same line in the same order as before.
4. **Stopping after an end.** `run()` does nothing once the mission has ended and stops after the action that
   ends it; `Mission._beat` stops feeding the rest. `summary()["beats"]` now lists `played` (beats whose actions
   ran), while `order` stays the pure runner's "triggered" list.
5. **Fade draw order, corrected.** Godot 4 stacks canvas layers by layer number, then by each layer's index
   among its own siblings, so the radio (layer 13, a child of MissionHud) and a cover on 13 under the mission had
   no set order. The cover now goes on the radio's layer as the radio's sibling, just before it: over the HUD
   (12), under the subtitles. Without a radio it sits on 13 under the mission; a radio that turns up later moves
   it on the next fade. Tested headless by parent, layer and index; **not looked at on screen**.
6. **`"status": "test_only"`** for beats_demo, the word mechs.json and the hangar already use.
7. **Dialogue lines by id.** The radio action's `line` is now an id in the dialogue database
   (`data/dialogue/*.json` entries, read once by `MissionBeats.dialogue_lines()`): speaker label and text come
   from there, so no English goes into missions.json. `event` is a radio.json event (the old `line`). A drafted
   `text` (+ `speaker`) works only as a fallback and `problems()` reports it outside test_only missions
   (mission.gd passes the wave count, test_only and the dialogue ids when it starts the runner).
   `Mission.radio_line` now carries `(speaker, text, line)`: the resolved text, and the dialogue id or event id;
   for an event it waits a frame and carries the text the Handler radio picked ("" when no radio said it).

**Checked** (headless, `tools/run_tests.sh`):

- `test_mission`: 40 passed (11 mission + 29 beats). The only failure in every run is another helper's
  in-progress `tests/test_legs_realmesh.gd` ("does not compile"), not part of this work.
- test_radio 4/4, test_telemetry 16/16, test_after_action 6/6, test_registry 9/9, test_bot 5/5, test_squad 11/11,
  test_kill_cam 4/4, test_scripts 1/1 for its own test (plus other helpers' uncompilable test_legs_realmesh,
  test_textures and test_world_look).
- The registry test runs `problems()` over every mission with every list known (enemies, music, weather,
  radio events, dialogue ids, Legion damage keys built from each enemy, wave counts, test_only): no problems.

**Still open (decisions and notes for Emerson and Riku)**

- A dialogue `line` or drafted `text` reaches the screen only once `scripts/ui/radio.gd` has
  `say_text(speaker, text)`; HandlerRadio also always shows "Handler One" as the speaker. Not this item's file.
  Until then such lines go out on `Mission.radio_line` only. A simpler alternative to the sibling placement:
  move the radio to its own layer (14) in radio.gd.
- The act I database's own beat triggers count waves from 0 (`"wave_started:0"`), while missions.json beats
  count from 1, as the HUD does. Its fixer was told; the dialogue file was not edited here.
- `problems()` does not yet check that a dialogue line belongs to the mission using it (the database's
  `missions.<id>.game_mission`); a one-line check once the campaign runner maps missions.
- The speaker shown for a dialogue line is the speaker's `label` (Shin, Raiden); the `callsign` is the other
  choice if the radio should read like comms.
- The dialogue reader lives in beats.gd as one static function; when a dialogue player or subtitle system
  arrives it should move there and beats.gd call it.
