# Mission Control tab switch: dimmed frames before and after
date: 2026-10-07 · for: both

Measured in headless Chrome at 1300x840 on live data, 16 switches between
Map and Sessions, 20 animation frames sampled after each click
(script: /tmp/t73/switch.py, scratch).

- Before (commit ae962d1, 220 ms fade-in per view): 165 frames with the view
  below full opacity (about 10 per switch); no long tasks; worst frame 17 ms.
- After (Relay task 73, fade removed): 0 dimmed frames; no long tasks; worst
  frame 22 ms (headless noise, both near 16.7 ms).
