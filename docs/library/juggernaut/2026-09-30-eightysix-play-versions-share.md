# Eighty Six: how to play, go back a version, and share with friends

date: 2026-09-30 · for: both · by Kaito (ejb-89/ejb-4f)

**Play (always the latest):** search "Eighty Six" (or "86", "juggernaut") in the app search, or Forge ›
Eighty Six › Play, or `~/Games/eightysix/tools/play.sh`. If the game changed since the last build, it rebuilds
first (a few seconds, a notification says so), then starts. If that rebuild fails, it plays the last good version.

**Versions:** every build that differs is kept in `~/Games/eightysix/build/versions/NNN-date_time/` and is never
deleted. Play an old one from Forge › Eighty Six › Versions, from the launcher's right-click "Play the previous
version", or `tools/play.sh --version 3`. List: `python3 tools/builds.py list`. Each costs about 22 MB.
The source code itself is in git (`~/Games/eightysix`, commit shown next to each version).

**Share with friends:** Forge › Eighty Six › "Make share zips", or `python3 tools/builds.py share`. Takes about
25 s and makes three zips in the newest version's `share/` folder (about 195 MB for the three):
| Zip | Size (v002) | Friend does |
|---|---|---|
| `...-windows.zip` | 61 MB | unzip, run `eightysix.exe`; SmartScreen: More info › Run anyway (not signed) |
| `...-linux.zip` | 51 MB | unzip, run `eightysix.x86_64` |
| `...-macos.zip` | 83 MB | unzip, move to Applications; first time right-click › Open (not notarised by Apple) |
Each zip carries a HOW-TO-RUN.txt with those steps. Send them any way you like (Drive, Discord, USB);
nothing is uploaded automatically.

**Checked on 2026-09-30:** Linux build on this laptop (desktop launcher, screenshot); Windows build starts
under Wine (headless only). **Not checked:** Windows with graphics on a real PC, macOS on a real Mac.
