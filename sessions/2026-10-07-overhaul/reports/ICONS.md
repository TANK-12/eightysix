# Icons: one shared drawn style for every Forge app

date: 2026-10-07 · for: both · Relay task 66 (split out of task 63), session Wakana

## What Emerson asked (21:00)

- Mission Control icon: he doesn't like it. He likes the Claude logo, so make something cool built on that.
- Jan Tune and Power looked too alike (both were ⚡).
- Make the app icons cooler overall: still recognisable, in one shared style.

## What was built (commits acc42c6 and the critic-fix commit after it)

- **`shared/forge_icons.js`**: the icon registry. It holds one SVG glyph per app, keyed by the app's folder name
  in `apps/`, plus one for the Pixel games folder (`groups/pixel-games.json`). That makes 39 glyphs.
  Every glyph sits on a 24×24 grid and uses one style: a 1.8 round stroke in `currentColor`, a soft 30% fill
  for the body, and solid fills for small details. The hub tints each icon tile with the app's accent, so the
  glyph takes that colour.
- **Mission**: the Claude spark (12 uneven tapered rays) drawn in Claude orange `#e8875f`, with a tilted
  orbit and three dots for sessions riding it, on its blue tile. It is the only glyph with a fixed colour.
  The **Claude app** has the same spark inside a chat bubble, in its own accent, so the two read as one family
  without looking alike.
- **Jan Tune** is three slider tracks with gold knobs. **Power** is the power symbol on green. Different shapes
  and different colours.
- Duplicate emoji are gone: Terminal (`>_` window) vs Keymap (keyboard), Files (folder) vs Dossier (profile
  sheet), NovelForge (pen nib) vs InkForge (open book), PanelForge (comic panels) vs Codec Player (film frame
  with play), Mission vs Janhollow (a station with solar wings).
- **`hub/index.html`**: one `<script src="../shared/forge_icons.js">`, a `setIcon(el, info, key)` and
  `iconEl()` helper, and every place that used to drop `iconFor()` text into an element goes through them:
  tile, dock, top-bar app markers, folder mini-icons, group chooser cards, Jump back in, overview, media art
  fallback, app menu title. `.forge-glyph` CSS sizes the SVG at 1.15em of its holder's font size.
- **The emoji stays as the fallback.** An app without a glyph, or a hub that failed to load the file, shows the
  `icon` emoji from its `forge_app.json` exactly as before. A manifest may also name another glyph with an
  optional `glyph` field, but forge.py does not pass that field through yet, so for now the app id is the key.
- **No forge.py change**, so no Forge restart is needed. The live Forge shows the new icons the next time the
  hub page reloads.

Adding an app's icon is one entry in `shared/forge_icons.js`. `tests/test_icons.py` fails until every app in
`apps/` and every folder in `groups/` has one.

## Checked (verified)

- `tests/test_icons.py`: 7 passed. It covers every app and folder having a glyph, each glyph being well-formed
  SVG in the shared style, no two glyphs being the same, Jan Tune ≠ Power in shape, Mission carrying the Claude
  spark and orange (and nothing else carrying the orange), the emoji fallback, and repaint skipping. It caught one
  real bug while being written: a duplicate `stroke` attribute on the Claude bubble's spark, which would have
  dropped its outline.
- `tests/browser/run.sh` (after the critic fixes): 996 PASS, 5 FAIL. It includes a new `hub_groups` check that the
  Pixel games folder's tile and dock show its drawn icon. None of the failures come from this change. `hub_level` (and its
  "wave moves with the levels" check) fails the same way on the pre-edit hub (a rerun on a copy with the old
  hub). `hub_music_skip` uses the same off-screen WebKit probe. `claude_stream` and `claude_pic_tag` load
  `apps/claude/static/claude_common.js`, which another session has uncommitted edits in. `hub_bar` passes with
  its marker check updated to accept a drawn glyph.
- Headless Chrome screenshots of the real hub, with eight apps open, before and after:
  `reports/icons-before-after.png` (sent to Emerson). The top bar now shows a power symbol beside gold
  sliders where it used to show two identical ⚡.

## Critic (fresh Opus agent, read the request and the diff)

1. Fixed, confirmed: folders never got their glyph. The hub keys a folder as `group:pixel-games`, so the lookup
   missed it and showed 👾 next to PixelForge's drawn invader. `setIcon` now strips the `group:` prefix, and the
   harness check above covers it.
2. Partly fixed: Jan Tune's manifest emoji and its page heading were still ⚡, the same as Power. Both are now 🎚️.
   Still open: Mission Control's own in-app header logo is the old node graph. `apps/mission` is held by task 67
   (Ren), so this went to them on the crew board.
3. Fixed: the Pixel games heart had a loose chip and a stray line. It is now a clean pixel heart with a glint.
4. Not changed: at the ~11px folder mini-icon size, Comix (burst) and Settings (gear) both read as jagged circles.
   At tile, dock and bar size they are distinct.
5. Fixed, latent: a folder made from a drawn-icon app would have kept an empty SVG box in its dock icon.
6. Fixed: Mission's orbit clipped about 0.4 units at the right edge. It is pulled in to 94%.
7. Fixed: `paint()` now checks "already painted" before it builds any markup, so a status tick costs nothing for
   drawn icons.

## Not done / for later

- The section pills (Create 🔨, Watch & listen 🎧, …) and the bar's own buttons still use emoji or text. They
  are not app icons, so they were left alone. The same registry could draw them.
- Inside each app (its own header or favicon) the old emoji is still used. Only the hub draws the new glyphs.
- Not yet seen in the live Forge window. A hub reload (or Emerson's next Forge start) shows them.

Later (task 70, 2026-10-07): Settings > Icons switches between these drawn icons (New) and the old emoji (Classic); see `sessions/2026-10-07-icon-style-switch.md`.
