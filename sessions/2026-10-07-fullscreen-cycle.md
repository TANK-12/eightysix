# Alt+F full screen cycle + Relay State box
date: 2026-10-07 · for: both

Ask: Alt+F cycles three levels in Forge (maximised under GNOME's bar, then window full
screen keeping Forge's bar, then the app alone with the bar on hover), starting at level 0;
Relay's State box should not vanish after about 4 s.

## State
- Alt+F three-level cycle in forge.py FullScreen.key: done, checked by tests/test_fullscreen.py (11/11)
- Start at level 0 (maximised, start_fullscreen off): done, not checked live (needs a Forge restart)
- Hover brings the bar down at level 2: already existed (bar-edge reveal), not re-checked live
- Relay State box stays open across refreshes: done, checked in headless Chrome
