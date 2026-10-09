# Plan: Pixel games tab in the Forge hub

Build in a **fresh session**, second of three (after `~/Forge/apps/crewroom/docs/PLAN-crew-room-2.md`,
before `~/Forge/apps/janhollow/docs/PLAN-jan-world.md`). Start with: *"build ~/Forge/docs/plans/PLAN-pixel-games-tab.md"*.
This touches `forge.py` and `hub/`, so use the forge-session and crew skills:
other sessions are often working in Forge, and both files need a backup first.

## His words (2026-09-16)

> "make ember fild part fo the pixel games tab and put this jan world as a new
> pixel game"

## Question asked, answer verbatim

| Question | Options offered | Answer |
|---|---|---|
| What should the 'pixel games tab' be? | One tile, chooser inside / Arcade joins it too / Separate tiles, grouped under a heading | "One tile, chooser inside (Recommended)" |

So Arcade stays its own tile. Emberfield moves inside, and the Jan world game
(`~/Forge/apps/janhollow/docs/PLAN-jan-world.md`) joins when it exists.

## Asked at the start (2026-09-16, session ejb-34), answers verbatim

| Question | Answer |
|---|---|
| What should Ctrl+number open? | "The chooser (Recommended)" |
| Should Crew Room join the tab? | "Keep its own tile (Recommended)" |
| What do picker cards show? | "Icon, name, tagline (Recommended)" |
| Build order | "Both, tab first", then Crew Room 2 moved ahead: "Build it first here" |

The Jan world game is named **Janhollow** (`apps/janhollow`).

## Design

- **Groups are data.** One file per group, e.g.
  `~/Forge/groups/pixel-games.json` with `id`, `label`, `icon`, `accent`,
  `order` and a one-line blurb. An app joins with one manifest field,
  `"group": "pixel-games"`. A future pixel game is one line in its own
  `forge_app.json`; nothing in `forge.py` or the hub names an app or a group.
- `forge.py` discovers groups beside apps and hands both to the hub (today the
  app list reaches the hub through the generated `window.FORGE_STATUS` file,
  `forge.py` around line 313).
- **Hub**: the dock, home tiles and workspace bar show one entry per group in
  place of its member apps. Opening it shows a chooser of member cards (icon,
  label, tagline). Picking one opens that app as its normal workspace, so its
  own full-screen behaviour (`"fullscreen": "auto"`) still applies. A group
  with one member still shows the chooser.
- **Nothing is lost.** `#app=emberfield` deep links, Emberfield's saves, its
  full screen and its lazy start keep working. Ask Emerson at the start of that
  session what Ctrl+number should open: the group, or the last game played in
  it.
- The hub loads from `file://` and cannot use `shared/forge.css`, so styles go
  in `hub/index.html` with the palette tokens it already keeps.

## Checks

- A Python test that discovery reads groups and attaches members, and that a
  manifest naming a missing group is shown as a normal tile, not dropped.
- A browser check in `tests/browser/` in the style of `hub_adds_a_tool.html`:
  one Pixel games tile, a chooser that lists Emberfield, and opening it works.
- Screenshot the home screen and the chooser. The running Forge needs a restart
  to show this; say so in the handoff.
- Update `~/Forge/README.md` (manifest fields table: `group`; a short section on
  groups), `PROGRESS.json`, and Emberfield's `MANIFEST.json` (where it now
  lives in the hub).
