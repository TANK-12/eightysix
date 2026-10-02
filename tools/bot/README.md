# Bot scripts

date: 2026-09-30 · for: both · lane A1

A bot script is JSON played by the `Bot` autoload (`scripts/core/bot.gd`) when the game starts with
`-- --bot=res://tools/bot/<name>.json --out=<folder>`. `tools/bot_run.sh <name>` does that off screen
and puts the output in the next `images/NNN-<name>/`; `tools/fps_log.py` plays `fps_route` once per preset.
`tools/check_arrival.py <folder>` reads a run's `report.json` (made with `report_legion` calls, as `b5_finale_long`
makes) and says whether every Legion unit reached the Juggernaut (exit 1 when one did not).
`tools/bot_run.sh <name> --build` plays the same script on the exported game (`build/linux/`, from
`tools/export.sh`), so a build can be checked the same way as the source.

```json
{"name": "smoke", "map": "test_range (optional: start there, clock starts when it is up)",
 "steps": [{"at": 1.5, "shot": "main-menu"}, ...]}
```

Each step has `at` (seconds on the bot clock) and one action:

| Step | What it does |
|---|---|
| `{"press": "move_forward", "strength": 1.0, "for": 3.0}` | presses an input action; `for` releases it later |
| `{"release": "jump"}` | releases an action |
| `{"shot": "name"}` | saves `NN-name.png` of the next drawn frame |
| `{"sample": "label"}` | appends the player mech's `telemetry()` to `samples` |
| `{"measure": 20.0, "label": "route"}` | frame times for that long: avg, 1% low, min fps, plus GPU/CPU ms and the uncapped estimate |
| `{"setting": "controls.sprint_mode", "value": "hold"}` | sets a setting for this run only (not saved) |
| `{"goto": "menu" / "pause" / "map:<id>" / "settings:<section>/<page>"}` | scene flow |
| `{"call": "open_maps", "args": []}` | calls a method on the current scene |
| `{"wait": "level"}` | stops the clock until the map being loaded is up (90 s limit) |
| `{"quit": true}` | writes `report.json` and quits |

Scripts: `smoke.json` (menus, every settings page, loading, the range: walk, charge jump, run, skid,
pause), `fps_route.json` (a fixed 20 s drive for frame rates), `jg_check.json` (the real Juggernaut
stands then walks), and `long_walk.json` (the 10-minute no-fall soak: a zigzag walk/run/skid path that
stays inside the test range, sampling telemetry every 20 s; `tools/bot_run.sh long_walk --timeout=650`).
