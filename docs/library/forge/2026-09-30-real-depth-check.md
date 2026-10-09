# Real-depth 2.5D wallpaper: first check with a real picture
date: 2026-09-30 · for: both

Done by Chihiro (ejb-d5), finishing the ejb-95 GPU-easing handoff in sessions/QUICKSTART.md.

- **Test fix:** `tests/browser/hub_ease_harness.js`, "moving the view bends the picture", read a 16 px strip that sat inside one stripe of the test picture. It now reads the whole middle row. Result: run.sh hub_ease 27/27 PASS, and 825 PASS / 1 FAIL for the whole suite. The failure is forge_media "with its length", which Kohaku (ejb-ae) found to be a flake.
- **Real picture (verified, headless Chrome with software WebGL):** the hub copy used Emerson's real theme (space3.jpg, its depth map and cut-out, depth strength 3, drift off), drawn at view offsets -1 and +1. Mean pixel change was 6.6 / 6.5 / 7.2 (R/G/B); 11.8% of pixels changed by more than 8. The astronaut stays pinned and the background moves around it. Picture: `2026-09-30-real-depth-two-views.png` (left -1, right +1).
- **Not checked:** the running Forge on the real GPU (it needs a restart), the drift, and the beat.
