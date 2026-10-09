# Eighty Six: sound part 2 mix numbers

date: 2026-10-01 · for: both

In-game mix check (`tools/bot_run.sh b4_sound_check`, music muted), Ashen valley, off screen.

| | before (run 187, synth) | after (run 205, downloaded) |
|---|---|---|
| 57 mm shot, loudest 0.25 s | -13.2 / -14.2 dBFS | -7.6 / -8.2 dBFS |
| shot over the run's median | +24.8 / +23.8 dB | +29.0 / +28.4 dB |
| 12.7 mm 1 s burst | not measured | -11.7 dBFS (+24.9 dB) |
| standing still | -41.1 dB | -52.9 dB |
| turning in place | -39.2 dB | -40.8 dB, no tone over 3 % (40 Hz-2 kHz) |

Cause of the quiet gun: Godot `AudioStreamPlayer3D.max_db` defaults to +3 dB and caps volume_db (raising the gun +3 -> +10 changed nothing until max_db was lifted to +24).

Library: 1,816 sounds, 274 MB in ~/Forge/shared/sound_library (Kenney 470 CC0, OpenGameArt ~1,280 CC0, Mixkit 65 explosions). Music: 23 tracks, 509 MB in ~/Music/86 (personal use).

Detail: ~/Forge/sessions/juggernaut-alpha/results/B4.md, "Part 2 (2026-10-01, Noa ejb-b9)".
