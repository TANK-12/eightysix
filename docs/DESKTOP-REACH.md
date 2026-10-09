# Desktop reach and multi-account (session 2026-09-25)

What Emerson asked for, in his words: a way for Claude to interact with "my desktop file system blender firefox and all the other apps... not in headless ways", get "the claude app of forge working", "2 gmail accounts and 2 claude accounts at once" (later: 2+ Claude Code subscriptions, 2 claude.ai logins, 1+ Gemini, all as options), "end up being in the forge app, fine if login is in browser", "folders of chats", Unreal or Unity, and then "whichever you find easier" with "very good looking graphics" and "mechs and stl and 3d mechs and testing as animations or games", all "a skill or set of skills you call when I ask".

Decisions: **Godot 4** is the engine (plain-text scenes, easiest for Claude to build and verify). **Blender** covers models, mechs, STL and film-quality renders. **Unreal 5** comes later on the USB4 NVMe enclosure (Epic ships Linux builds; the Iris Xe is too slow for Lumen and Nanite in real time, but Movie Render Queue can render offline). Unity was not chosen.

## The pieces

| piece | where | what it does |
|---|---|---|
| Accounts registry | `shared/accounts.json`, `shared/forge_accounts.py` | One entry per web login (claude-a, claude-b, gemini-a, gmail-1, gmail-2). Each has its own Firefox profile in `~/.local/share/forge/accounts/<id>/firefox` with a 50 MB cache cap. `python3 shared/forge_accounts.py list \| open <id> [--control]` |
| BiDi client | `shared/forge_bidi.py` | Firefox's built-in remote protocol (WebDriver BiDi), blocking, one session per call. |
| Per-account WebKit sessions | `forge_views.py` (`ViewHost.session`) | A view created with `session: "<id>"` gets its own cookie store in `~/.local/share/forge/accounts/<id>/webkit`. The `cookies` op takes `session` too. |
| Logins app | `apps/logins` (port 8454, role `logins`) | One tab per account inside Forge. "Sign in in Firefox", then "Bring login in" copies that profile's cookies into the tab's session. |
| Claude app | `apps/claude` | "Web logins" list under Accounts (opens the Logins app). **Folders** of conversations: `+ folder`, drag a chat onto a folder, 📁 button, rename, collapse, delete (keeps the chats). `folders.json` in the data dir, `meta["folder"]` per conversation. |
| Page tools | `apps/acchan/acchan/tools/pages.py` | `list_accounts`, `open_account(control)`, `page_tabs/open/read/click/fill/run_js` on a visible Firefox with remote control. |
| Blender bridge | `shared/bridges/blender/forge_bridge.py`, `apps/acchan/acchan/tools/blender.py` | Socket on 127.0.0.1:9876, token in `~/.local/share/forge/bridges/blender.token` (600). Code runs on Blender's main thread via `bpy.app.timers`. Helpers: `forge.scene_summary/print_check/export_stl/viewport_shot/render`. Tools: `blender_launch/run/scene/print_check/export_stl/viewport_shot/render`. |
| Godot bridge | `shared/bridges/godot/addons/forge_bridge/`, `apps/acchan/acchan/tools/godot.py` | EditorPlugin, TCP 127.0.0.1:9878, token `godot.token`. Tools: `godot_new_project` (good-looking Forward+ template: AgX, SDFGI, SSAO, glow, fog), `godot_open`, `godot_editor`, `godot_check`, `godot_play` (records PNG frames). |
| Skills | `~/.claude/skills/mech-forge`, `~/.claude/skills/godot-forge` | Claude loads them on its own for models, mechs, STL, renders, games. |

Installed: `blender` 5.2.1 and `godot` 4.7.2 (pacman), `websockets` in the acchan, claude and logins venvs, and a new `apps/logins/.venv`.

## The sign-in lesson (read before touching Firefox)

Firefox started with `--remote-debugging-port` sets `navigator.webdriver = true` and paints red warning stripes in the address bar. **Google then refuses to sign in** ("this browser may not be secure"). `dom.webdriver.enabled=false` does not hide it (tested on 155). So:

- Sign-in windows start with remote control **off** (`open_account` default). `--control` or `open_account(control=true)` is for Claude to read and click, after signing in.
- The first version made the main Firefox launcher always add the port, and put Gmail in containers of the main Firefox. Both were **removed** the same day: `~/.local/share/applications/firefox.desktop` was deleted and the main profile's `user.js` (only Forge's lines) was deleted. Left behind: the "Gmail 1" and "Gmail 2" containers in the main profile's `containers.json` (harmless; the original is in `backups/accounts-2026-09-25/containers.json`, restore it only while Firefox is closed), and `privacy.userContext.enabled` may stay true in prefs.js.
- Creating a BiDi user context (`browser.createUserContext`) on a real profile saves a junk `webdriver-<uuid>` container. The code never does that.

## Blender/Godot upgrade (2026-09-25, S4 session)

- `mech-forge` is now the general Blender skill (mechs, props, characters,
  scenes, animation): organic models from assets/VRM only, `forge.look`
  presets (studio / hdri:<id> / toon), Poly Haven via `assets_*`, Rigify,
  `export_godot`, a headless `blender -b` fallback when tools are missing,
  and "no renders when Emerson says so".
- `godot-forge` knows `godot_new_project(template="third_person")`, the shared
  add-ons (Phantom Camera, godot-vrm patched for 4.7, MToon), the new clean
  message "No script, scene or model import errors.", and "no primitive
  stand-ins in anything shown".
- Acchan's `launch_app` opens every app again (display variables adopted from
  the session) and opens Forge apps inside Forge (`shared/forge_open.py`).
- Open: a real character for the template waits on Emerson's pick (board).

## Verified vs not

Verified (real runs, 2026-09-25):
- Tests: `tests/test_forge_accounts.py` + `tests/test_blender_bridge.py` 22 passed (acchan venv); `tests/test_views.py` ALL PASS (4, incl. per-session cookies); acchan `tests/test_core.py` 110; claude `tests` 52 (incl. folders); logins `tests` 7.
- Page tools drove a visible Firefox: fill, fill a contenteditable, click, read, run JS.
- Five account windows opened side by side with no remote port.
- Cookies read from real account profiles (9, 6, 3 before sign-in).
- Blender on screen: launched with the bridge, built a 3-part mech leg, print check "printable" per part, a 28 KB STL, a viewport shot, a 4.6 s EEVEE render.
- Godot on screen: template project, `godot_check` clean, `godot_play` recorded 86 frames (template renders with sky, shadow and fog), editor bridge opened a scene and read the tree, and refused a wrong token.
- Claude app with folders: headless Chrome screenshot (folders, counts, highlight, web logins list).
- Logins page renders standalone.

Not verified yet:
- **Logins inside the real Forge window**: needs Forge restarted (forge_views.py changed, new app). Not restarted, because Emerson was using it.
- "Bring login in" end to end with a real signed-in account (needs his sign-ins).
- Whether Google keeps a session that was imported into WebKit (it may ask to sign in again inside Forge; if so, the fallback is using the account's Firefox window).
- The second Claude Code account (profile `second`): sign-in was started and its page opened in the claude-b window, waiting for Emerson's code.
- New Acchan tools in Claude Code sessions: the acchan MCP server must restart (a new Claude Code session does it).

## Next

1. Restart Forge. Open Logins, sign in to each account in Firefox, press Bring login in, and screenshot it.
2. Unreal 5 on the USB4 NVMe (Epic account needed), with a Python remote-execution bridge and a skill like godot-forge.
3. A proper mech: use mech-forge for a full rigged walker, and godot-forge for a playable test.

## 2026-09-27: Blender and Godot kit for game assets

Verified: 26 Blender add-ons installed from extensions.blender.org and
enabled (listed in the `mech-forge` skill); Magic UV removed (fails on 5.2).
Blender prefs: online access on, 64 undo steps, autosave every 2 min, no
splash. Official Blender MCP (projects.blender.org/lab/blender_mcp v1.0.3)
installed: add-on auto-starts on port 9876, server in
`~/.local/share/blender-mcp/.venv`, registered as `blender-official` in
Claude Code; a stdio test listed its 26 tools. Not verified yet: a live
call into an open Blender (needs a Claude Code restart and Blender open).
Godot: 8 new add-ons in `~/Forge/shared/godot_addons/` (GUT on by default,
the rest opt-in via `.forge-disabled`), Cyclops and Dialogic autoloads via
`.forge-autoload`; all loaded in a headless 4.7 import. Godot's Blender
path set so `.blend` files import directly. Reference skill packs cloned to
`~/.claude/reference/`. Not done: MPFB asset packs, kitbash library.
