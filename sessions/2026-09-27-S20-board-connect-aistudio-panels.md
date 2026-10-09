# S20: board-connect fix and B41 AI Studio panels (2026-09-27)

Session Koharu (ejb-ce), resumed as Riku (ejb-cf-acd5) after the weekly limit.

## Done and verified
- Board connect, part 1 (outside git, ~/.claude/skills/crew/notes_hook.py):
  Claude-app sessions start in ~, and the notes hook only auto-joined
  sessions whose folder was inside ~/Forge, so none of them got Emerson's
  Board notes. It now joins on the first prompt or tool call that names ~/Forge.
- Board connect, part 2 (crew.py): `crew join` takes the Claude-app tab name, so
  the Board and the tab agree.
- Board connect, part 3 (crew.py session_names): two live sessions shared the
  derived name ejb-cf, so both answered as Toru. The older keeps the name and
  the newer gets a suffix. Tests: crew 23 OK, notes hook 10 OK, pyright clean.
- B41 (apps/ai-studio): Settings/Preview/Library are draggable, resizable
  cards via the new shared/forge_panels.js, with Reset layout and a stacked
  column below 760 px. tests/browser/forge_panels.html is 16/16 and in run.sh
  (full run 567 PASS). AI Studio pytest 9 passed. Screenshots checked.

## Open
- While it shared the name, this session's hook may have marked Toru's notes
  #254-#285 as delivered. Toru should run `crew notes forge` to check.
- Re-split 2026-09-27 (Board #289-ish), when only Nagi, Umi and this session
  were left: this session = #257 (hub music, visualiser vs Qobuz, Acchan logs);
  Nagi = app groups then A22(b); Umi = Claude app speed then B20 widgets;
  Terminal split panes to whoever frees up first.

## #257 hub music, visualiser and Acchan logs (same session, 2026-09-27)
Done and tested:
- Visualiser deaf to QBZ: cava's exit raced the hub's own stop, came back as
  "cava stopped", and the hub switched to hearing only the Forge music until
  a restart. Fixed in shared/forge_music.py (stop() remembers the process it
  ended; tests/test_forge_music.py runs the race 20 times). The hub now also
  retries a cava that really stopped after 10 s (hub/index.html
  Visual.systemOff; 4 checks in tests/browser/hub_music_harness.js). run.sh 593 PASS.
- Acchan logs: its only errors were two failed shutdowns, from forge_jan
  unloading a model while Jan was closing (connection refused). An unreachable
  Jan now returns quietly (tests/test_forge_jan.py).
Found, not fixed (reasoned about, not proven):
- The hub music reached the speakers twice at once, measured live: the
  audio element's own stream and the Web Audio stream, correlation 1.0. An
  isolated WebKitGTK test (element routed before or after play, with or
  without a source reload) always gave one Web Audio stream only, so the
  hub does something extra to cause it. Suspected link to "the visualiser
  moves but no sound": not proven. Next step: log Music.g.routed and
  ctx.state in the live hub when Emerson hears silence.
