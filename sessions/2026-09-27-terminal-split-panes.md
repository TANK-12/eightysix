# Terminal split panes (brief, 2026-09-27, from Sakura / ejb-55)

**Run on account "second"** (hey is at 95% of the week). Emerson asked for it
("do both", 2026-09-27); it is item 2 of "Improve next" in apps/terminal/WIP.md.
Nobody has claimed apps/terminal.

## Ask
Split the Terminal app's view into panes, each its own shell, like any
tiling terminal: split right and split down, move focus between panes,
close a pane (its neighbour takes the space), drag the divider to resize.

## Where
- apps/terminal/static/app.js, app.css, index.html (xterm 6.0 is in
  static/vendor; the search add-on from ejb-83 shows how add-ons are wired).
- apps/terminal/web_app.py + ptyhost.py: check a second shell per tab
  needs nothing new server-side (each pane opens its own session like a tab).
- Tests: apps/terminal/tests/test_terminal.py (pytest, app .venv) and
  tests/check_ui.py (headless Chrome; run with ~/Forge/apps/files/.venv/bin/python).

## Suggested shape
Pick keys that do not clash with Hyprland/GNOME or the existing
Ctrl+Shift+F / tab keys (read app.js's key handler first): e.g.
Ctrl+Shift+D split right, Ctrl+Shift+E split down, Alt+arrows move focus,
Ctrl+Shift+W close pane. A pane tree per tab (split node: direction, ratio,
two children; leaf: one xterm + its session), fit add-on refit on every
resize. Also add Split buttons in the tab bar for mouse users.

## Done when
check_ui.py gains checks: split right/down gives 2/3 live shells that each
echo their own input, focus moves, closing a pane frees its space, divider
drag changes sizes. pytest passes, black + pyright on touched files, a
screenshot looked at, `pgrep -fc "[-]-headless=new"` is 0, WIP.md updated.
Needs a Forge restart to be seen live.

## State
DONE + checked by Nagi (ejb-6b), 2026-09-27: see apps/terminal/WIP.md item 2.
