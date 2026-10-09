# Brief: Eighty Six sound pass and music (lane B4)

date: 2026-10-01 · for: Claude · from: Emerson via Sora (ejb-49)

Game: `~/Games/eightysix` (Godot 4.7). Read first: `PLAN.md` (sound and music rules), `results/B4.md`
(what B4 part 1 built: synth library, `Sfx` autoload, MechSounds, reverb zones, review page, mix check).

## Emerson's asks

1. **Music, just download it.** Do not ask which uploads: he said go. Use `yt-dlp` (on the machine,
   `/usr/bin/yt-dlp`) to fetch the *86* soundtrack from YouTube: openings and endings in English and Japanese
   versions, and the score; prefer 1-hour loop uploads where they exist. Keep the source's own bitrate (no
   re-encode up to 320). Files go in `~/Music/86/` (personal use, never inside the repo or a share zip), each
   listed by path in `data/music.json`. Add a music player (menu, explore, combat).
2. **He mixes it himself in settings.** Audio settings with separate volume sliders at least for master,
   music, guns, mech (steps, hydraulics), environment (wind, ambience) and UI, plus a music track picker.
   Saved with the other settings. Neat and deep, like the rest of the menus.
3. **The gun is far too quiet** (and other sounds "and stuff"). Raise the 57 mm main gun so it is clearly the
   loudest thing in the game, and check the 12.7 mm sub guns, impacts and casings against it. Measure levels
   with the in-game mix check before and after and write the numbers down.
4. **There is a background noise.** A constant hiss/hum under everything. Find what makes it (wind loop,
   a synth take with a noise floor, reverb tail, a looping sound that never stops) by measuring, remove or fix
   it, and show before/after levels in a quiet spot.

## Rules

- Disk is short: check free space before downloading and say how many MB the music takes.
- Coordinate on the crew board (`crew` skill, crew `forge`): Kana (b4-part2) and Koharu (ejb-a4, A4) are in
  this repo. Claim `scripts/audio/`, `assets/audio/`, the audio json files and the settings audio page before
  editing; do not touch others' uncommitted files.
- Versions: Play no longer numbers builds. When the part is finished and committed and `git status` is clean,
  save one with `python3 tools/builds.py save --note "sound pass: ..."` (it refuses on a dirty tree).
- Done means: tests pass, the mix check numbers are in `results/B4.md`, the README and PLAN status row are
  current, and Emerson gets a "try this" note telling him where the sliders are.
