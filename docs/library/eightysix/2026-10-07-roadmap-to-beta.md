# Eighty Six: roadmap from alpha 0.1 to beta

date: 2026-10-07 · for: both (Emerson, and any Claude session with no history) · written by Ami (Relay 65)

Built on the honest ratings in `2026-10-07-handoff.md`. How to run and build things, and a glossary of the terms
used here: `2026-10-07-guide.md`. This is a proposal: Emerson reorders, cuts or adds; his word wins.

## Where we are, in one paragraph

The **engine of the game is strong**: physics-true movement, real ballistics and per-part damage, a working
Legion AI, five maps (three of them real places), destruction in the hand-built towns, a good sound mix, menus
that are close to finished, and a test-and-bot setup that catches regressions. What is **thin** is the reason to
play: two missions, no campaign, no save game, a tutorial stub, and three beautiful real-place maps with nothing to
do on them. So the order below goes: a clean saved version, then something to do, then make the fight itself
sharper, then deepen the enemy, the squad and the world, then make it run everywhere and finish it.

## What "beta" means here

Beta is reached when all of these hold:
1. **Every system rated "almost polished" or better** in a fresh honest handoff.
2. **An evening of play:** a short campaign of about 8-10 missions across all five maps, with briefings, a save
   game and a reason to come back (loadouts, records).
3. **No known crash or game-breaking bug,** and a 30-minute bot soak on every map finishes clean.
4. **Emerson has played it through** and his notes from that playthrough are done.
5. **A friend can play it:** share zip installed and run on a real Windows PC and a Mac, without help, and every
   asset in it is licensed to be shared and credited.
6. Frame rate measured and reported per map and preset (graphics still win over frame rate).

After beta the work is balancing, content and polish, not new systems.

## Sizes

S = one session (one Relay task, a few hours). M = 2-4 sessions. L = 5-10 sessions. XL = more than 10.
Rough guesses from how long similar jobs took in the alpha wave, not promises. Getting one mission's last wave to
reach the player reliably took five sessions (B5 parts 3-7), so anything with Legion on a new map is sized up.

## The milestones, in order of impact

### 0.1.2: clean slate (S to M, 1-2 sessions) — do first
Everything else builds on a clean, saved, played version.
- Finish Relay 62's stand-up work (fix the one failing `test_righting` case), commit it with the stray `.uid`
  files, full suite green.
- Bump `project.godot` to 0.1.1-alpha, add "what's new and where to see it" to PLAYTEST.md (new sky, Hangar
  lights, grass, the leg-push stand-up), save **version 019**, Linux export boots.
- Re-run the Frontier sweep finale twice (`b5_finale_long` + `check_arrival.py`) after the slope-margin change,
  and drop the bridge under the column with real shells once.
- When Emerson allows GPU runs again: the 0.1.1 after-set (`a011_views` on all four presets), side-by-side sheets
  against images/623-626, and the fps table.
- **Emerson plays 019,** writes notes in `NOTES.md`, and answers the questions at the end of the handoff
  (Legion accuracy first: 0.3 needs it).

### 0.2: something to do (XL, 12-18 sessions) — the biggest gap
Turns a tech demo into a game.
- **A mission on every map,** each built on what the map is good at: Palouse (long open sight lines: a hunt
  against Löwe at range), Allegheny (an ambush among the firs, short sight), Brilon (a street fight), a second
  Sector 86 mission (defend a town or a bridge). Mission types as data in `missions.json`: destroy, defend,
  escort, recon, demolition. The real-place maps have never had Legion on them: expect path-finding work there
  (they need the nav grid the big map has).
- **Brilon's houses breakable,** at least along the mission's streets (today they are solid).
- **A short campaign** (about 8-10 missions) with a briefing and a debrief screen; the Handler's radio carries the
  story between them.
- **Save game:** campaign progress, loadout, records. One file in `user://`, with a version number so old saves
  still load.
- **Loadouts that matter:** the Hangar's parts list picks ammo and sub-arm kit per sortie; a few parts unlock
  through the campaign.
- **A real tutorial** as mission 0, replacing the stub, if Emerson wants one.

### 0.3: a sharper fight (M, 3-5 sessions)
Emerson called 013's third-person aim "OK, could still be better; it's fine", so this is polish, measured first.
- **Measure the aim:** a bot that fires at marked targets at known ranges and records where shells land against
  the crosshair. Change only what the numbers show is off; the 57 mm stays fixed to the body.
- **Legion accuracy** by Emerson's pick (ranging error, settle time, a setting, or measure first).
- **Hit feedback:** what you hit and what it did (part off, armour held), on the HUD and the radio.
- The resonance blade on a default pad button. A balance pass with a measured table (shots to kill and time to
  kill per Legion type, how long you survive each wave).
- Bisect and fix the air-turn and belly-scrape regression from version 013 (handoff known bug 2).
- Legs that collide with the world (today only the hull does), and the ledge climb's lift checked against the
  physics-only rule.

### 0.4: the Legion (L, 5-8 sessions) — enemies worth fighting
- Reshape the three Legion models to the anime (Grauwolf's swept V head and angled rocket box, the Löwe's long
  tapered turret, the Ameise's ringed sensor: results/B2.md), keeping the joints so the game keeps working.
- New types, one per session, each an `enemies.json` entry plus a brain: a long-range artillery type
  (Stachelschwein), a jamming swarm (Eintagsfliege) and a super-heavy as a boss (Dinosauria).
- AI: a path grid on Ashen valley too (no more crater pile-ups), group tactics (suppress and flank), per-type
  accuracy, retreat and regroup.

### 0.5: the squad (M, 3-4 sessions)
- Wingmen use the whole moveset: slide, jump, wire anchor.
- Handler view: pan and zoom, contact list, waypoints (shift-click), long-range pathing on the big map.
- Voices for the Handler and the squad using the local voices already in `~/Forge` (no new installs), the text
  kept as subtitles.

### 0.6: the world, "stupid high quality" (L, 6-10 sessions; can run alongside 0.2-0.5)
Emerson's standing ask: AAA, not low poly, never washed out.
- Sector 86's crags and towns to Brilon's standard; the ruined tower as real geometry; more town variety.
- Foliage that reaches the horizon (grass past 60 m, shrub and tree billboards), breakable trees.
- Time of day and weather that change inside a mission; one night mission (lights, flares, the Juggernaut's own
  lamps).
- Fix the Allegheny into-the-sun blow-out and the far shrubs' dark blobs.
- The Juggernaut model's remaining critic fixes, one per session (results/B1.md), alongside.

### 0.7: runs everywhere, shareable (M, 3-5 sessions)
- Find the Ultra 15 fps frame-pacing floor; get High to 30 on every map without losing looks (forest billboards,
  grass draw range per preset, shadow casters in towns).
- Run the share zips on a real Windows PC and a Mac (Emerson named a MacBook Air M5); fix what breaks.
- **Licences:** add the sounds and the map data to `assets/SOURCES.md`, replace or credit the Mixkit sounds, put
  the OpenStreetMap (ODbL) credit in the game and the zips.
- 30-minute soak bots on every map; find why off-screen bot runs stall now and then; loading times.

### 0.8 to beta: finish line (M, 3-5 sessions)
- Emerson's full playthrough notes, all of them.
- Menus and HUD polish for pad-first play; accessibility (text size, colour-blind marks, remappable everything).
- Bug bash with every bot script, full suite, and a fresh honest handoff that meets the beta definition above.
- Save the beta version, make share zips, write "what's new and where to see it" in PLAYTEST.md.

## Total and how to run it

Roughly **40-60 sessions** from here to beta. Two strands can run side by side without stepping on each other:
the game strand (0.2, 0.3, 0.4, 0.5, 0.7 in order) and the look-and-models strand (0.6, plus the Juggernaut and
Legion model work), with one GPU job at a time on this laptop. Each milestone ends with a saved version and a short
play by Emerson before the next one starts, so his notes steer the next step.

## Rules that hold for every milestone

Fun first, all of it from real physics. Graphics over frame rate, but measure and report. CC0 assets, credited.
Don't touch the grapple or middle-click until Emerson says so. No recoil reduction of any kind. Tests green and
headless; commit only your own files; never delete images, builds or anything Emerson made. Every session writes
what it verified and what it only reasoned about.
