# Forge freezes, theme load-in speed, Mission conversations, power saving (2026-10-08)

date: 2026-10-08 · for: both · session ejb-f7 (Tetsu, commander) with three Opus helpers

## What Emerson asked (his words, typos kept)

1. "opening apps in forge often freezes forge so i have to open and close"; later "things in forge keep spasing only a little bit but everything in gerneal" and "since the big code session yesterday things kind of keep freezing".
2. "the theme and effect reload now like all the app pill things at home screen see if you can make that faster"; then "is the app icon and text bars the effect load in kind of thing".
3. "mission control still doesnt have its own conversations thing"; then "make a copy of the enjoy conversations interface and put it in the mission control, it has selectors for model and effort and ultracode and ultrathink. what does ultrathink and ultracode do".
4. "split the work to get it done fast" (three crew-deep helpers, Opus).
5. "the live 2d thing still opens on auto at claude start up i dont want that".
6. "make the power saving mode way better as well and just make forge more power efficient and desktop".
7. "how do I stop with the power probes" (the probe windows that popped up on screen).
8. "how do I change the app icons".
9. "make sure the whatsapp thing still works like yesterday".
10. "get other relay sessions running or quick start if free and useful".

## Owners

- Commander (ejb-f7): forge.py, tests/test_off_main_loop.py, apps/claude/static/stage.js, this brief, PROGRESS.json.
- Helper A: apps/mission (+ shared/forge_convo.js), the Conversations view.
- Helper B: hub/index.html applyTheme path + shared theme JS, the home screen load-in.
- Helper C: desktop/, apps/power, power parts of hub/index.html.
- Relay 94: session names on the Board and the Relay page. Relay 95: Eighty Six music for friends' copies.

## State

- 1 freeze: done+checked (tests) in 10e6123, live after a Forge restart. Stats read now on a worker (was the main loop: temperatures 45 ms every 30 s, disks can block on a sleeping drive); the overview picture 0.9 s after each app open is drawn from the frame on screen (about 75 ms, page keeps running) instead of WebKit's full software repaint (0.25-0.32 s with the page frozen); closing an app while it starts no longer crashes its start thread (reproduced by a test first). The hard freeze itself was not reproduced, so these are the measured hitches, not a proven cause of every freeze.
- 5 Live2D: done+checked (headless shot, Claude tests 194 pass). The animated avatar was already off at load; the avatar pane itself now starts shut every load.
- 7 probes: the windows were the commander's two timing probes (closed on their own) and possibly helper C's; helper C told to open no more windows.
- 9 WhatsApp: checked. Relay's Whatsie is logged in, chat "Indeed" open, the boss's poll has been clean since 06:01. Gmail polling fails with AUTHENTICATIONFAILED (app password), so mail tasks do not arrive.
- 10 Relay: tasks 94 and 95 queued and starting.
- 3 Mission Conversations: done+checked (b893319, Mission tests 99 pass, headless Chrome shots in apps/mission/docs/2026-10-08-conversations-*.png). Its own nav view: session list left, Enjoy copy right (model, effort, may, Normal/Ultracode, Limits, ultrathink, reasoning, Claude/Jan, plan & progress) sharing the Claude app's run_controls/enjoy files through /claude-ui/; other sessions get the transcript chat, ended ones "Resume here". Not checked: a real send into a live chat, the look in Forge's WebKit. Live once Mission is closed and reopened in Forge (its backend restarts).
- 2, 6: helpers running.
