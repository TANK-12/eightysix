# White-on-white text in the hub and the desktop widgets: found and fixed

date: 2026-10-07 · for: both

QUICKSTART item 2 (Emerson saw white text on near-white in the Forge hub and
the desktop widget app). Relay task 57, sessions Kohaku and the two before it.

## Where it was

1. **Text straight on the wallpaper** (home clock, date and greeting; zen
   clock, date, timer, intent and hint): white on a near-white picture. The
   test wallpaper was cache `8c31da48955e6e99` (wall_light .84).
2. **Glass panes at high strength** (Frosted and Liquid, and the widgets' own
   Glass look): the pane kept only about 20 to 58% of its dark fill, so bar,
   tiles and widgets turned light grey under white text on a bright picture.
3. **Desktop corner buttons** (⚙ and ✎ Widgets): faded to opacity .45 at rest,
   white on light grey (1.23:1) over a bright wallpaper.

## What changed

- `hub/index.html`: `--wall-light` from `theme.wall_light`; a soft dark pool
  behind the home hero and zen text, deeper the brighter the wallpaper; a
  floor under the dim layer (.38 at the brightest); tighter text shadows;
  accent letters mixed 55% with white.
- `shared/forge_glass.js`: on a bright wallpaper the panes keep more fill
  (`--glass-keep`), edges dim (`--glass-edge`), new `--glass-pane` (widgets'
  Glass look) and `--glass-solid` (dark fill .68 up to .88, read by
  `shared/glass/frosted.css`, `liquid.css` and the hub's `--glass-fill`).
- `shared/forge_widgets.css`: Glass widgets use `--glass-pane`.
- `desktop/particles.html`: the corner buttons are faint by dimmer text on a
  darker pill instead of a whole-button fade.

Dark wallpapers look the same as before (the extra darkening is 0 up to a
mid-bright picture).

## Checks (verified)

- `tests/browser/contrast_sweep.js` measures every shown text against what is
  behind it (WCAG ratio, 3:1 minimum; disabled buttons skipped, as WCAG does).
- `hub_contrast` (hub, dark and bright wallpaper, every look and glass kind):
  160 PASS, 0 FAIL. On the pre-fix hub: 46 FAIL.
- `desktop_contrast` (desktop page, dark and white wallpaper, material, glass,
  frosted and liquid at full strength, resting, editor and options open):
  25 PASS, 0 FAIL. On the pre-fix files: 10 FAIL.
- Both are in `tests/browser/run.sh`. Full run 2026-10-07: 997 PASS, 2 FAIL;
  the two (`hub_level`, `hub_music_skip`) print nothing because
  `tests/page_probe.py` (off-screen WebKit) hangs in the headless Relay session
  even on a one-line page and on the pre-fix hub, so they are not this change.
- Screenshots, before on top, after below:
  `2026-10-07-white-on-white-hub.png`, `2026-10-07-white-on-white-desktop.png`
  (headless Chrome, bright wallpaper).

## Not verified

- Not seen in the running Forge window or on the real GNOME desktop (Forge
  restart needed to load the new hub and shared files; never restarted by a
  Relay session).
- The desktop page gets `wall_light` from the hub's wallpaper; if the GNOME
  desktop picture differs from Forge's, the bright-wallpaper floor follows the
  wrong picture (reasoned from forge_theme.py, not checked).
