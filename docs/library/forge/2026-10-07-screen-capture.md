# Screen capture: what works on this laptop

date: 2026-10-07 · for: both · relay task 53

- **Real screen, unattended: works.** GNOME's own screencast D-Bus API, wrapped in
  `~/.claude/skills/screen-capture/livecast.py` (skill `screen-capture`). Measured:
  Forge background mode with the pointer circling, 15 s, 361 frames = 24 fps at 1920x1080
  (Forge's particle fps setting is 25).
- **Monitors off = 10 fps.** With the screen blanked (PowerSaveMode 3) every cast came out at
  exactly 10 fps (100 ms per frame). `--wake` turns the monitors on for the capture and back off.
- **Refused or broken:** Shell.Screenshot ("Screenshot is not allowed"), grim, wf-recorder,
  gnome-screenshot, gpu-screen-recorder (EGL load fails on the mesa/llvm mismatch).
- **Off-screen renders** of the hub in headless Chrome: about 2 fps in real time (software
  WebGL); stepping virtual time gives smooth fixed 20 fps clips at about 1.5 s per frame.
