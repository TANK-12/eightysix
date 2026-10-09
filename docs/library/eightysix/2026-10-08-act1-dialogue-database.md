# Eighty Six: the Act I dialogue database, its lint and its script

date: 2026-10-08 · for: both · built by a helper of Riku (session ejb-6a)

## What it is

The spec's phase 0.2 asks for "Act I's script written for Emerson to read". The AAA plan's D18 default asks for one
JSON file per act, with every line's id, speaker, text, mission, beat, conditions, priority, cool-down and voice file.
Three pieces now exist in `~/Games/eightysix`:

| File | What it does |
|---|---|
| `data/dialogue/act1.json` | 425 lines, about 2,200 words: the Prologue M0 "The 86th Sector", M1 "First contact", M2 "Spearhead" (with M2's history class on Lena's console), the night talks N0, N1, N2, and 191 combat calls for those missions |
| `tools/dialogue_lint.py` | checks a dialogue file (stdlib Python): ids, fields, known speakers, subtitle limits, reading speed, capitals, banned words, conditions, repeats, and that the dead stay silent |
| `tools/dialogue_script.py` | renders the file as a screenplay for Emerson: `2026-10-08-act1-script-draft.md` beside this doc |
| `tools/tests/test_dialogue_lint.py`, `tools/tests/test_dialogue_script.py` | 40 tests, including "act1.json lints clean" and "every line appears in the script" |

**Corrected in the fix round:** the beat runner already exists (`scripts/mission/beats.gd`, commit 5cc4b6e, doc
`2026-10-08-mission-beats.md`). What does not exist yet is the link from the runner and the radio to this file:
nothing plays these lines in a mission, and the radio that picks lines by context (AAA plan section 11, feature 1)
is a separate roadmap item. The beats here are written in the runner's own trigger form (see "Fix round" below). `Registry` only loads top-level `data/*.json`, so the
`data/dialogue/` folder changes nothing in the game today. `test_registry` still passes, 11 of 11.

## The file, block by block

Engine-neutral by section 7 of the AAA plan: plain JSON, seconds and metres, asset ids rather than paths (`voice` is
an id, empty until recorded), and no Godot types.

- `rules`: the subtitle limits (2 lines of 42 characters, at most 17 characters a second), the default display time
  (1.5 s minimum, 14 characters a second plus 0.5 s), `no_repeat_s` 180, the priority bands (story 40, danger 30,
  order 20, call 10, banter 0), the capitals allowed (`HQ`, `RAID` in Para-RAID), the banned words, and the
  quiet-speaker rule (Shin must have fewer words than each main speaker).
- `speakers`: 14 voices, each with a label, full name, callsign, side, a note on how they speak (the spec's 3.4),
  and for the fallen `dies_in` (and `dies_at`, the beat). Kujo `dies_in` M0 at `m0.kujo`. Kaie (M3) and Daiya (M6)
  carry their later missions.
- `channels`: `para_raid` (close and dry, D16), `broadcast` (HQ, radio-treated), `room` (heard at the base),
  `console` (text on Lena's console, with no subtitle limits).
- `facts`: what a condition may test: `handler` (old, none, lena), `alive`, `who`, `time`, `after_death`,
  `not_done` (teaching nudges), `beat_s`, `bridge_dropped`.
- `missions`: m0, n0, m1, n1, m2, n2 in story order. Each one names the game's mission (`ashen_first_contact` and
  `frontier_sweep` exist; M0's mission does not exist yet), the map, the light and the length.
- `beats`: 24 story beats with a time (`at_s`), title, tone (the spec's 3.2 palette), a trigger `when` in the beat
  runner's own form (`{"on": "wave_started", "wave": 1}`, waves from 1), and a stage direction.
- `triggers_pending`: the triggers these beats need that the runner does not have yet (see "Fix round").
- `events`: 21 combat events with how often each fires in a fight (`interval_s`), the default priority, and,
  where needed, the missions it can happen in (no Löwe in M0).
- `entries`: the lines, keyed by id (registry style). Story ids are `<beat>.<order>` (`m0.kujo.130`), and orders
  step by 10 so a new line slots in between. Combat ids are `<event>.<speaker>.<n>` (`kill.kurena.2`). Optional
  fields are `note` (how it is said), `before` (a direction just before the line), `channel`, `choice` (the
  player's pick, flavour only, per D3) and `display_s`.

How the game should play it (this is the contract for the runner, not yet built). A story beat plays its lines in
order and skips any line whose conditions do not hold when it comes up. When a combat event fires, the radio picks a
line for that event whose missions and conditions match and that is not cooling down; combat calls cool down 240 s.
A higher priority cuts a lower one, and a call never cuts a story line.

## How to use it

```
cd ~/Games/eightysix
python3 tools/dialogue_lint.py                      # every data/dialogue/*.json; exit 1 on errors
python3 tools/dialogue_script.py --date 2026-10-08  # writes <date>-act1-script-draft.md in this folder
python3 -m unittest discover -s tools/tests         # all Python tool tests
```

`dialogue_script.py` will not overwrite an existing script: Emerson may have marked it up. Re-render with a new
`--date`, or pass `--force` only when the old copy holds no notes.

## How to extend it

- **A line:** add one entry, then run the lint. The lint names the line and the rule it broke.
- **Act II:** a new `data/dialogue/act2.json` with the same blocks. The lint and the renderer take any file, and
  both scripts default to every file in the folder. Kaie's `dies_in: m3` starts to bite once M3 is in a file.
- **A new event or fact:** one entry in `events` or `facts`. The lint then expects each combat mission to have
  `ceil(180 / interval_s)` lines for a new event.
- **Voices:** fill `voice` with an asset id. The reading-speed check uses `display_s`, so set it to the clip length
  when voicing. With the default display rule no line can read faster than 14 characters a second, so the check
  only bites on an explicit `display_s`.

## Writing choices (decisions for Emerson, with the defaults taken)

1. **Callsigns on the link, names at the base** (setup 7 and the base tone). In M0 to M2 everyone on the Para-RAID
   uses callsigns. Real names appear only in base scenes, among the 86. Lev calls Shin "Shin".
2. **The eight main combat speakers** are Shin, Raiden, Theo, Kurena, Anju, Kaie, Daiya and Lena. Each has 18 to
   26 calls for Act I, against the plan's 60 each for the whole game. Kujo has 12 calls, M0 only, each needing him
   alive. The old Handler has 4.
3. **Lena says "I'm sorry about Sirius"** in N0. It is the one condolence in the act and a formula rather than a
   stated feeling. She only knows his callsign, and Theo repeats it once the link closes. Cut it if it reads as
   melodrama.
4. **Invented, marked [new]:** the Halberd squadron in M0's rescue (Volume 1 has the rescue; the unit's name was
   not checked). Who calls Daiya's cat what: Theo "Whitey", Kujo "Blackie", Anju "Calico", Kurena "Kitty" (canon
   has the four names, not who uses which). The staging of the history class as slides and Lena's withdrawn
   note. Lev's "Leave the board" answering his own "Rub that out" from that morning. Kujo's "Make mine neat. Your
   handwriting's awful." tying to Shin's box of names (setup 2).
5. **Canon kept:** Kujo dies in M0, at night, on a rescue, to a self-propelled mine he takes for a wounded
   soldier. The mercy shot is the player's, and only a direction marks it: no line rewards it. Lena introduces
   herself that night. Shin is alone against the heaviest units in M2. Callsigns are from the 86 wiki's Spearhead
   Squadron page, read 2026-10-08: Kirschblüte (Kaie), Sirius (Kujo), Black Dog (Daiya). Matthew's and Mina's
   bunks are bare in M0's opening direction.
6. **Lines the AAA plan already wrote** are used as written: "Contact. North-east. Six.", "I'm logging off. Don't
   call.", "Noted.", "Thank you, everyone.", "She thanked us.", "How did you do that?", "Undertaker. Acknowledged.",
   "They're coming. North-east.". Everything else is new.
7. **Lena drops her script only from M5** (setup 17). In M2 she is "still on her script, but quicker".

## Verified (checks run on 2026-10-08) and reasoned

Verified:
- `python3 -m unittest discover -s tools/tests`: `Ran 74 tests ... OK`. The 40 new ones passed alone too:
  `Ran 40 tests ... OK`. Each lint rule's test was written before its code and seen failing first. That covers
  duplicate-id messages, events limited to missions, choice groups counting once, and capitals in directions.
- `python3 tools/dialogue_lint.py`: `act1.json: 425 lines, 0 errors, 0 warnings`.
- Faults seeded into a copy of the real file are caught:
  - Kujo speaking in M1 gives `kujo dies in m0, before m1`.
  - "CLEAR." gives `words in capitals: CLEAR`.
  - A line repeated 20 times gives `4 subtitle lines`.
  - Kujo speaking at the base after his death gives `kujo dies at m0.kujo, earlier`.
- `pyright` on the four Python files: 0 errors. `black` was run on them.
- `tools/run_tests.sh test_registry`: `11 passed, 0 failed`. The new folder does not disturb the registry.
- The script renders all 425 ids (a test checks every one) into a 1,068-line markdown file.

Reasoned, not checked:
- That the lines match episodes 1 and 2 beyond the beats the spec and the wiki give. The spec's rule stands:
  watch the episode before voicing.
- That the tone holds (no melodrama, Shin quiet, the Republic banal) is the writer's judgement plus the lint's
  word and word-count checks. No critic agent read it.
- That 180 s without repeats is enough. The `interval_s` figures are estimates of how often each event fires;
  bot telemetry from a real fight should replace them.
- (Withdrawn in the fix round: "the trigger strings are a proposal for the beat runner, which does not exist yet".
  The runner existed; the triggers are now in its form.)

## Fix round (2026-10-08)

An independent critic reviewed the first version and found five major and seven minor problems. A second helper of
Riku fixed them the same day. Each behaviour fix had its test written first and seen failing (24 red on the first
run: 10 failures and 14 errors), then passing. Nothing was deleted from this doc. Corrections above are marked.

### What changed

1. **Beat triggers are in the runner's own form.** Each beat now has `when: {"on": ..., <fields>}`, as
   `scripts/mission/beats.gd` and `data/missions.json` read it. The old `trigger` strings are gone, and waves count
   from 1. The first version counted from 0, so every wave beat would have fired one wave late and the first never.
   Now `m1.wave1` is `{"on": "wave_started", "wave": 1}` and `m2.finale` is wave 4, frontier_sweep's last.
   **Triggers the runner still lacks** are listed in the file's `triggers_pending` block:

   | trigger | fields | used by | why the runner lacks it |
   |---|---|---|---|
   | `mission_start` | none | m0.base, m1.brief, m2.brief | the runner has a clock from the start, but no beat can fire on the start itself |
   | `mission_won` | none | m1.debrief, m2.class | mission.gd ends the mission; no beat hears the win |
   | `after` | mission | n0.chime, n1.dishes, n2.footnote | a night talk sits between missions, outside any one mission's runner |
   | `ally_destroyed` | who | m0.after (Sirius) | added in this round, see below |

   `ally_destroyed` is new here. The first version started `m0.after` on `beat_done: m0.kujo`, but the runner sends
   `beat_done` the moment the named beat *begins*. So "after" would have played over Kujo's own lines. It has to wait
   for his machine to be destroyed.

   The lint now reads the runner's `TRIGGERS` straight from `beats.gd` (`runner_triggers()`), so the list never goes
   stale. It checks that every beat has a `when` and that its trigger is in beats.gd or in `triggers_pending`. Each
   trigger must carry its required fields, and waves must count from 1. A wave or area must exist in the game mission
   the dialogue mission names (from `data/missions.json`). A `beat_done` or `since` must name a real beat, and a `who`
   a real speaker. If the runner gains a pending trigger, the lint warns you to take it off the pending list. The
   script shows each trigger in plain words, such as "Starts on: wave 1 starts." A pending trigger is marked "(a
   trigger the runner does not have yet)".

   M0 has no mission entry yet, so its area names (`bay_door`, `mill_field`, `base`) cannot be checked. They must
   exist when M0's mission is written.
2. **Combat calls state nothing the radio cannot know.** The radio picks a call by event, so it cannot know a
   bearing, range, count or time. 30 calls were rewritten without them. Examples: "Reloading. Ten seconds." became
   "Reloading. Cover me." (the 57 mm reloads in 4.5 s, weapons.json). "Contact. Eight hundred, by the trees." became
   "Contact. Lining it up." "The town is clear. All units, move south." became "Your sector is clear. All units,
   advance." Shin's heard contacts lost their directions.

   New lint rule: a call above banter priority may not contain a word from `rules.call_specifics` (compass points,
   "left", hundred, thousand, metres, kilometres, seconds, minutes) or a number word from two up. "One" is allowed
   because it is also a pronoun. Banter (`lull`) may state fixed facts, such as Kujo's 128. "Right" and "front" are
   not on the list, because "all right" and "front plate" are idioms; calls using them as directions were fixed by
   hand.
3. **Distances fit the map.** "That's eight kilometres." (M0 is on small_map, 1,024 m) became "Other side of the
   valley." New lint rule: `spoken_metres()` reads stated distances, either a number with a unit or a bare "eight
   hundred" range call. Any distance longer than the diagonal of the mission's map (`data/maps.json`) is an error.
4. **No joking after a death.** New rule `rules.after_death_min_priority: 30`. In a combat mission where a squad mate
   dies (M0), every call below danger priority carries `after_death: false`, so after Kujo dies only story lines and
   danger calls play. The lint enforces this. Two joking danger calls also got it by hand: Theo's "Not dead yet." and
   "stop asking". By design, this means M0 has no `order`, `ack` or `lull` calls after the death.
5. **Shin speaks least, in each mission.** The quiet check now runs per combat mission as well as over the file. It
   counts story lines plus combat calls, weighted by how often each event fires in the mission's `length_s` and
   shared evenly among that event's lines. That is an estimate. Shin's lines were trimmed:

   | was | now |
   |---|---|
   | "Grauwolf. Four. Coming fast." | "Grauwolves. Fast." |
   | "Sirius, stop. That isn't one of them." | "Sirius. Stop." |
   | "Werewolf, Gunslinger. With me. West side." | "Werewolf, Gunslinger. West." |
   | "Werewolf, hold the road. I'll take the Löwe." | "Werewolf, the road. I'll take it." |
   | "Undertaker. Returning to the squad." | "Returning." |

   Estimated words heard (story plus weighted calls):

   | mission | Shin | next lowest |
   |---|---|---|
   | M0 | 141 | Anju 293 |
   | M1 | 106 | Anju 240 |
   | M2 | 159 | Anju 343 |

   Over the whole file, Shin has 106 words and Anju 153. The heard-contact calls stay Shin's (setup 4): with the
   weighting they do not make him the loudest.
6. **The mercy shot can come early.** Every line of `m0.kujo` now carries `alive: [kujo]`, so the beat stops when
   he dies, whenever the player fires. New lint rule: every line in a speaker's `dies_at` beat needs that speaker
   alive.
7. **The M2 finale matches frontier_sweep wave 4** (one Löwe on lake_road, two Grauwolves on east_shore, one Ameise).
   Shin: "Löwe. Lake road." Lena: "Two coming round the east shore." The direction is now: "his marker closes on the
   Löwe; the two from the shore turn after him."
8. **Lint gaps closed.** Banned words are now checked in notes, `before` directions and beat titles and directions.
   `display_s` of 0 or less is an error instead of a crash. A single word wider than a subtitle line is an error.
   *Not changed:* the reading-speed check still cannot fail on default display times. This is by design: the default
   is 14 characters a second plus 0.5 s, under the 17 limit. The check is there for `display_s` overrides and voice
   clip lengths, and the existing `test_reading_speed_uses_the_display_time` shows it bites there. No lint can stop
   melodrama such as "I miss him so much"; that still needs a reader.
9. **Events about the speaker's own machine.** `reloading`, `hit_taken`, `hit_heavy`, `armour_low` and `disabled`
   are marked `self: true`. The lint now wants a line from each of `rules.self_speakers` (Raiden, Theo, Kurena, Anju,
   Kaie, Daiya, and Kujo in M0) in each combat mission. 11 calls were added, for example "Snow Witch is down. Legs
   gone. I'm all right." Shin, the player, is left out on purpose: the HUD shows his own hits, and it keeps him
   quiet. Combat calls now total 202, about 40% of the AAA plan 9.8 target ("about 60 each" for eight speakers, for
   the whole game). Later acts should grow them.
10. **No Löwe in M0.** The five `lowe_fired` lines that listed m0 now list only m1 and m2. New lint rule: a call
    must be in its event's `missions`.
11. **Pillar 3 in stage directions.** "Shin climbs down and cuts a strip of aluminium" became "Undertaker's hatch
    opens. Close by Sirius's wreck, the sound of a cutter on aluminium." "The squad at the table" became "The mess
    hall: chairs, plates, a tap dripping. Nobody talking." New lint rule: `rules.unseen` lists words that would put a
    person on screen ("climbs", "at the table", "his face", "nods"...), and the lint checks beat directions and
    `before` directions for them. It is a word list, so it catches the common slips, not every one.
12. **Unchecked facts are marked, and setup 3 is planted.**
    - Kujo's callsign Sirius is tagged [canon]. The first writer read it on the wiki's Spearhead Squadron page, and
      a web search on 2026-10-08 agrees, but the wiki page itself returned an error (HTTP 402) in this round.
    - "Kaie leads the fourth platoon" and "Kujo is in Kaie's platoon" are tagged [new, not checked].
    - Theo's sketchbook is planted at the base: `m0.base.170` Kujo "Fox. Did you finish the old Handler yet?" and
      `m0.base.180` Theo "I've only got his voice. He's getting a moustache.", with pages turning and a pencil heard,
      not seen.

The script draft `2026-10-08-act1-script-draft.md` was re-rendered with `--force`. It held no notes: the critic
had found it byte-identical to a fresh render.

### Decisions for Emerson (fix round)

- `ally_destroyed` is a fourth pending trigger, beyond the three the task named, because `beat_done` cannot mean
  "after the beat's lines".
- Shin has no self-event lines (hits, armour, disabled) beyond the ones he already had. The HUD shows his machine.
- After Kujo dies, only danger calls play in M0.
- The radio's specifics rule is strict: no counts or ranges in event-picked calls. If you want "Two, moving east"
  back, it needs run-time placeholders (`{count}`, `{bearing}`) filled by the radio (AAA feature 4).
- The heard-contact calls stay Shin's only.

### Verified in the fix round

- `python3 -m unittest discover -s tools/tests`: `Ran 112 tests ... OK`. Of these, 55 are dialogue-lint tests (30
  before) and 12 are script tests (10 before). The new tests went red first: `FAILED (failures=10, errors=14)` for
  the lint and `FAILED (failures=1, errors=1)` for the script.
- `python3 tools/dialogue_lint.py`: `act1.json: 438 lines, 0 errors, 0 warnings`.
- The critic's faults, seeded into a copy of the real file, are all caught now:
  - `banned words in note: i feel, tears`
  - `a word wider than a subtitle line (60 characters, at most 42)`
  - `display_s must be more than 0 seconds`
  - `hit_taken.theo.1: a squad mate dies in m0: a call below priority 30 needs after_death: false`
  - `m0.kujo.090: kujo dies in m0.kujo: the line needs alive: [kujo]`
  - `wave 0: waves count from 1`
  - `wave 5: frontier_sweep has 4 waves`
  - `says 8000 m, but m0 is on small_map, a 1024 m square`
  - `reloading.kurena.1: a call the radio picks by event cannot know this: ten, seconds`
  - `lowe_fired happens only in m1, m2, not m0`
  - `pillar 3, no people on screen: 'climbs'`
  - `disabled in m0: no line for anju's own machine`
- `black` was run on the four Python files. `pyright` on them gives 0 errors, 0 warnings and 0 informations.
- `tools/run_tests.sh test_registry.gd`: 9 passed, 1 failed. The failure is `test_legs_realmesh.gd does not
  compile`, a test file in Riku's lane that is being edited right now. It does not touch dialogue.
- Another helper's uncommitted work on `beats.gd` reads `entries` (speaker, text, mission, beat, channel) from this
  file. Those fields are unchanged, and the only line id it names (`m1.brief.010`) is unchanged.

Reasoned, not checked: the word weighting in the quiet check is an estimate (uniform picking, conditions ignored).
The new and rewritten lines have not been read by a tone critic. Kaie's platoon is still unverified.
