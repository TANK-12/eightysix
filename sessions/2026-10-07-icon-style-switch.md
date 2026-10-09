# Icon style switch: New / Classic

date: 2026-10-07 · for: both · Relay task 70 (Emi)

Emerson liked the new drawn icons (task 66, commits acc42c6 and 7d13c63) and
the old emoji. He asked for a switch between them. In Classic, Jan Tune and
Power had to stop sharing an icon, and Jan Tune and Mission Control needed new
emoji in the old style.

## What it is

- **The setting.** Settings > Glass and layout > **Icons**: New / Classic.
  It is the setting `icon_style` in `shared/forge_theme.py`. It is saved in
  the settings file like every other setting, and forge.py passes it to the
  hub in theme.js.
- **One flag in the registry.** `shared/forge_icons.js` now holds both styles:
  - `GLYPHS`: the drawn icons, as before.
  - `CLASSIC`: one emoji per app id.
  - `ForgeIcons.setStyle("new" | "classic")` switches and repaints every
    painted icon on the page in place, with no reload. Painted icons carry
    `data-icon` and `data-icon-text`. Only the icon itself is swapped, so the
    dock's tooltips stay.
  - `ForgeIcons.forget(el)` unmarks an element that stops showing an app icon:
    a folder's member grid, or the music box once album art arrives.
  - The hub's `applyTheme()` makes the one call,
    `ForgeIcons.setStyle(theme.icon_style)`. There is no per-app code.
- **Adding an app** means one entry in GLYPHS and one in CLASSIC.
  `tests/test_icons.py` fails until both exist.

## Classic emoji

Every app keeps the emoji from its manifest as it was before acc42c6
(`git show acc42c6^:apps/<app>/forge_app.json`), except these:

- Jan Tune: ⚡ → 🎛️ (Power keeps ⚡). Emerson asked for this.
- Mission Control: 🛰️ → 🚀 (Jan Hollow keeps 🛰️). Emerson asked for this.
- **Assumption:** the request also says "no two apps share an icon in either
  style". The old set had five more repeated pairs, so in each pair the newer
  app moved and the older or main app kept its emoji:
  - Files 🗂️ → 📁 (Dossier keeps 🗂️)
  - InkForge 📖 → 🖋️ (NovelForge keeps 📖)
  - Codec player 🎬 → 📺 (PanelForge keeps 🎬)
  - Terminal ⌨️ → 💻 (Keymap keeps ⌨️)
  - the Pixel games group 👾 → 🎮 (PixelForge keeps 👾)
- PrintForge did not exist before acc42c6 and uses its manifest's 🖨️.

The `icon` fields in the apps' `forge_app.json` files are **unchanged**.
Outside the hub they are still the fallback emoji, so the five old repeats
above still show there. Classic reads `CLASSIC`, not those fields. The critic
pointed out that this makes two lists; a test pins `CLASSIC` to the old
manifests except for the seven fixes. Folding the fixes back into the
manifests is a possible follow-up. It was left out here because those files
belong to other lanes (apps/mission is held by task 67).

## Needs one Forge restart

The running forge.py loaded the old `forge_theme` module. Until Forge is
restarted, the hub never receives `icon_style`, and the Settings app's
backend may not show the row at all. Emerson restarts Forge himself. After
that, switching is instant.

## Verified

- `tests/test_icons.py`: 14 passed. Node runs the registry with a small fake
  page. The tests check:
  - every app and folder has a glyph and a classic emoji
  - no two classic emoji are the same (ignoring the U+FE0F emoji-style mark)
  - the old drawn-glyph checks still pass
  - Classic matches the old manifests except for the seven fixes
  - New → Classic → Classic → New → (bad value) → (unset) round-trips, and a
    dock tooltip and an unmarked folder grid survive every step
  - an icon painted over a picture replaces it
  - the setting saves `classic`, and an unknown value is cleaned back to `new`
- `tests/browser/hub_icon_style_harness.js`, the real hub in headless Chrome
  with the live hub/status.js (39 tiles) plus a test folder: 20 PASS, run
  through run.sh as block `hub_icon_style`. It checks:
  - the switch repaints tiles, the top bar, the dock and the right-click menu
    title, with no reload
  - no repeats among the tiles in either style
  - the top bar shows 🎛️ ⚡ 🚀 in Classic
  - folder grids and dock tooltips survive
  - album art, the system-track 🎬, and the broken-picture fallback are left
    correct
- Settings app: a spare copy on a free port, with its DOM dumped in headless
  Chrome. The Icons row is under Glass and layout, with options New and
  Classic. The spare copy was stopped afterwards.
- Screenshots: real headless Chrome, 1600x1000, home screen with nine apps
  open:
  - `sessions/2026-10-07-icon-style-switch/hub-new.png`
  - `sessions/2026-10-07-icon-style-switch/hub-classic.png`
  - `sessions/2026-10-07-icon-style-switch/top-bar-new-over-classic.png`
- black and pyright are clean on `shared/forge_theme.py` and
  `tests/test_icons.py`. `node --check` passes on both JS files.
- `apps/settings` tests: 34 passed.

## Not verified

- Not seen in the live Forge window, because that needs the restart. Jan
  Hollow is in the Pixel games group, so the bar shows 🎮 for it there.
- The root `tests/` suite has failures that are not from this change, all in
  untracked or other sessions' work:
  - test_app_taglines (mission and printforge taglines)
  - test_forge_pad (no gamepad plugged in)
  - test_glass_budget and test_hub_hang (task 63, still in progress)
  - test_views (a GTK window crashes with no display)

## Critic (one Opus agent) and what came of it

Fixed:

- Music box: an icon was added beside album art after a switch.
- A broken picture was kept beside its fallback icon.
- A system track showed an app icon after a switch.

  The fix: `paint()` now clears the element whenever the icon is not its first
  child, and `NowPlaying.art()` forgets its mark.

- Test gaps, now covered: the folder check proved nothing, the "instant"
  timing check could never fail under virtual time, and there were no checks
  of the music box or the menu title and no Python test of the setting.

Not changed:

- Two emoji lists (see above).
- Look-alike pairs at small size: 📁 next to 🗂️, 📖 next to 📚, 🎮 next to 🕹️.
