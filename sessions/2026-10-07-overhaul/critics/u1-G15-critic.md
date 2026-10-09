# U1 sweep critic, group G15 (PulseForge, commit 2af9e5a)
date: 2026-10-08 · for: Claude · by the G15 critic (Relay task 89)

Scratch: HOME `/tmp/u1/G15/critic/home{,A,B}`, servers on 9055-9057 (all stopped
by PID, ports free afterwards), Chrome only through `cdp_driver.chrome_page()`
(no browser left on this check's profile). Driver script and output:
`/tmp/u1/G15/critic/critic_ui.py`, `ui.log`; shots in `/tmp/u1/G15/critic/shots/`.

## Breaks

1. **High · verified · a number too big for a float bricks the whole app, even after a restart.**
   Where: `apps/pulseforge/web_app.py:103` (guard only catches the NaN/Infinity
   *words*), `web_app.py:364` (`update_settings` saves any value).
   Repro: `curl -X POST :9057/api/settings -H 'Content-Type: application/json' --data-binary '{"values": {"x": 1e999}}'`
   → 500, but `settings.json` now holds `"x": Infinity`; restart the server;
   `GET /api/state` → 500 forever. The page shows "PulseForge could not start:
   request failed (HTTP 500). Trying again by itself." and never boots (all nine
   tabs visible, no mode applied: `shots/bricked_settings_1100.png`); the queue
   line wrongly says "can't reach the PulseForge server". Same for a project:
   `PUT /api/projects/three {"song_gap": 1e999}` and `{"params":{"speed":-1e400}}`
   → saved as `Infinity`/`-Infinity`, then `GET /api/projects/three` → 500 (the
   very brick the sweep claims to have closed).
   Fix: in `RequestGuard`, after a successful `json.loads`, walk the result and
   refuse any float that is not `math.isfinite` (or pass `parse_float` that
   raises on inf). Also make `state.save_settings`/`Project.save` use
   `allow_nan=False` so nothing non-finite can ever reach disk.

2. **Medium · verified · the NaN guard is skipped for a Content-Type that is not lowercase.**
   Where: `web_app.py:92` (`if b"json" not in ctype`). FastAPI reads the type
   case-insensitively; the guard does not.
   Repro: `curl -X PUT :9055/api/projects/two -H 'Content-Type: Application/JSON' --data-binary '{"params": {"speed": Infinity}}'`
   → 500, `project.json` holds `"speed": Infinity`, `GET /api/projects/two` → 500.
   Fix: `ctype.lower()`; better, guard every body whatever its type (or check
   `json` in the lowered media type and also an empty type).

3. **Medium · verified · Import still lands on top of a project with the same name.**
   Where: `web_app.py:1652` (`projmod.create(info["name"] ...)` without
   `unique=True`), `pulseforge/projectfile.py:104` `restore` then overwrites the
   data. The sweep fixed this for Duplicate/Template only.
   Repro: project "Alpha" (title "Alpha own title", gap 1.5); export a project
   whose name is "Alpha" (`/tmp/u1/G15/critic/beta.pfproj`); `POST
   /api/projects/import -F file=@beta.pfproj` → 200, slug `alpha`; Alpha now reads
   "from Beta 0.0". The docstring says "into a new project".
   Fix: `projmod.create(..., unique=True)` there too, plus a test.

4. **Medium · verified · project names and snapshot labels still run as markup in two places.**
   Where: `static/index.html:1363` (`loadRenders`: `${r}` and `${p.name}` raw;
   the `data-thumb`/`data-del-r` attributes too), `static/scenery.js:534`
   (`${snap.label}`; also the confirm text at 537 is fine, it is text).
   Repro: project named `<img src=x onerror="window.__pwned=1">` with one render
   file → Advanced → Output: `#renderList img` = 1, `__pwned = True`
   (`shots/output_xss_1100.png`, broken image beside "a.mp4"). Snapshot labelled
   `<img src=y onerror="window.__pwned2=1">` → Scenery: `__pwned2 = True`.
   The report says names are escaped; only the Projects list and pre-flight are.
   Fix: `apEsc` (or `textContent`) in both, and extend `check_ui.py`'s markup
   check to the Output tab and the snapshot row.

5. **Medium · verified · a crafted or hand-edited .pfproj with NaN bricks the imported project.**
   Where: `pulseforge/projectfile.py:111` (`json.loads` accepts NaN) → `:129` save.
   Repro: `gamma.pfproj` with `"song_gap": NaN` in `pulseforge-project.json`;
   import → 200 slug `gamma`; `GET /api/projects/gamma` → 500.
   Fix: `parse_constant` that raises (→ 400 "that is not a PulseForge project
   file") and the same finite-number walk as break 1.

6. **Low · verified · different names collapse into one project.**
   Where: `pulseforge/project.py:24-26` (`slugify`) and `create` at `:277`.
   Repro: create "Song!", set its title, create "Song?" → same slug `song`;
   project now named "Song?" with the first one's title. Two non-ASCII names
   in the same second ("夜の雨", "朝") both get `project-1791406441`. The report's
   assumption covers "a name already in use", not two different names.
   Fix: in `create_project`, reopen only when the stored name equals the new
   name; otherwise `unique=True`.

7. **Low · verified · rename has no length cap.** `PUT /api/projects/six` with a
   200 kB `name` → 200, `/api/projects` then answers 201 kB. Create is capped
   at 300; `ProjectPatch.name` (`web_app.py` class `ProjectPatch`) is not.
   Fix: `Field(None, max_length=300)`.

8. **Low · suspected · the queue line says "can't reach the server" for any
   failure**, including a 500 from a reachable server (seen in break 1).
   `static/index.html` `pollQueue` catch. Fix: say "the server answered with an
   error" when the error carries an HTTP status.

## Checked and fine
- pytest: 349 passed, 1 skipped (`/tmp/u1/G15/critic/pytest.out`), matches the report.
- `black --check` on web_app.py, project.py, test_u1_sweep.py, check_ui.py: clean.
  pyright: 1 error, the pre-existing `forge_art` import (web_app.py:36).
- Commit 2af9e5a touches only `apps/pulseforge/` (6 files), no stray prints or
  commented-out code; WIP.md has the new top section. Working tree clean for the app.
- `%2E%2E`, `..%2F..%2Fx` → 400 "bad path"; `%00` slug → 404, delete is a no-op;
  `{"name":"   "}` → 400; empty body / `null` → 422; wrong-typed patches
  (`shots:[1]`, `cards:["x",5]`, `ambience.level:"x"` …) never 500 on GET,
  timeline, preflight, tracklist, snapshots (music-map 400, calm).
- Hidden by the hub for 10 s: fetch 0, rAF 0, timers 0.
- Server killed: 2 fetches in 0-10 s, 1 in 10-30 s, calm queue line; restarted:
  recovered by itself after 13.2 s. Boot retry while failing: 5 fetches in 20 s.
- Double click on Create: one POST.
- No page errors or unhandled rejections in the run.
- Screenshots at 760 / 1100 / 1500 / 1920 (Make, Compose, Output, Autopilot;
  sheets `shots/sheet_*.png`): no clipping, overlap or contrast problems seen;
  the Simple empty-preview note shows as intended.

## Not covered
- Real renders, preview loops and the paused-video behaviour (worker's check_ui
  covers the latter; not re-run).
- Double clicks on Duplicate / Template / Import / Studio buttons.
- WebKitGTK inside the real Forge window.
- Headless Chrome count on the machine was 7-8 before and after this run: other
  sessions' browsers, not this check's (its profile has none left).
