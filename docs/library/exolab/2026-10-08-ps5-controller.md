# PS5 controller for the Exo Lab game: connecting it, the laptop check, the buttons

date: 2026-10-08 · for: both (Emerson and Claude) · Relay task 115

## Connect the pad

**USB (simplest):** plug the DualSense in with a USB-C cable that carries
data (some cables only charge). The light bar comes on. Open the game, click
into its window once, then press a d-pad arrow on the pad: browsers only show
a pad to a page after a button press. The pause menu's controller line then
names it, and ✕ on Play starts.

That first press only wakes the pad: the game ignores it. In Forge it is
still the pad-as-mouse service's press (✕ is a click, ○ is Esc, L2 is Back),
which is why a d-pad arrow is the one to use: it does nothing on the pause
menu. From then on, while the game is in front and sees the pad, the service
stays quiet and every press is the game's.

**Bluetooth (once, then it remembers):**

1. Hold **Create** (the small button left of the touchpad) and **PS**
   together for about 3 seconds, until the light bar flashes quickly.
2. Pair it in the Bluetooth panel of Settings ("DualSense Wireless
   Controller"), or in a terminal:

       bluetoothctl
       scan on            (wait for "DualSense Wireless Controller" and its address)
       pair <address>
       trust <address>
       connect <address>
       scan off

3. After that, pressing **PS** on its own reconnects it.

Then open the game and press a button, as above.

## What the laptop check found (2026-10-08, verified by command)

- Kernel 7.2.9-arch1-1 ships `hid-playstation`, the DualSense driver, with
  device aliases for USB and Bluetooth (DualSense 054c:0ce6 and DualSense
  Edge 054c:0df2). It loads by itself when the pad connects.
- Bluetooth: bluez 5.87, the service is active and enabled, the adapter is
  powered and pairable. The input settings are the defaults
  (`UserspaceHID=true`, `ClassicBondedOnly=true`), which suit a paired
  DualSense. **The pad has never been paired** (it is not in
  `bluetoothctl devices`), so the Bluetooth pairing above is needed once.
- Permissions: udev's `70-uaccess.rules` gives the logged-in user every
  joystick device, and the user is in the `input` group as well.
- Forge's window is WebKitGTK (`WebKit2` 4.1, webkit2gtk-4.1 2.54.1). It and
  webkitgtk-6.0 both link libmanette 0.2.13, the Gamepads feature is on by
  default (checked through `WebKit2.Settings.get_all_features()`), and
  libmanette's built-in mapping list has the DualSense under hid-playstation
  over USB (`030000004c050000e60c000011810000`) and Bluetooth
  (`050000004c050000e60c000000810000`), so the page gets the standard layout
  both ways. Chrome and Firefox have their own DualSense mappings.
- Two things in Forge itself did need fixing (found in a second pass the
  same evening; commits 5ef18e7 and 472f0b7):
  1. The hub's app iframe allowed only fullscreen and the microphone. The
     Gamepad spec lets a cross-origin iframe (every Forge app, each on its own
     port) read pads only when the iframe allows `gamepad`, and the WebKitGTK
     library carries that refusal ("Third-party iframes are not allowed to
     call getGamepads() unless explicitly allowed via Feature-Policy
     (gamepad)"). The hub now allows `gamepad`, and the game survives a
     refusal (the pause menu says why).
     **Measured later that evening** (`tests/browser/check_gamepad_webkit.py`:
     an off-screen WebKitGTK 2.54.1 view made like the hub's, software only,
     no pad plugged in): an app-style iframe under the file:// hub is a secure
     context and `getGamepads()` answers with the new allow, with the old one
     and with none. So the old hub would probably have worked too; whether
     WebKit refuses once a pad is connected is still open (run that script
     with the pad plugged in to see). Either way the game starts.
  2. `forge-pad.service` (`shared/pad`) turns the pad into a mouse and keys
     while a Forge window has focus, so in the game ○ also pressed Esc
     (pause), L2 Alt+Left (back out of the game), the d-pad the arrow keys
     (walking) and ✕ a click (punch). The game now tells the hub it reads the
     pad itself, and while it is in front Forge writes 0 to
     `$XDG_RUNTIME_DIR/forge/pad-focus`, which the service already reads as
     "stay quiet". On the Exo Lab page and everywhere else the pad drives the
     desktop as before. The service reads the pad without taking it for
     itself (no exclusive grab) and its own virtual device has only mouse
     and keyboard keys, so WebKit still sees the real pad, and no second,
     phantom pad (checked in `shared/pad/forge_pad.py`).
- **Close and reopen Forge once** to load the Forge-side fixes: they live in
  the hub page and `forge.py` (the pad allowed in app frames, the
  pad-as-mouse service staying quiet, and since 2026-10-09 the game hearing
  when Forge's window loses focus), and Forge was not restarted that night.
- The pad was not connected during the check, so a real pad showing up in
  the window is **not verified**.

If it does not show up:

- `grep -A4 DualSense /proc/bus/input/devices` lists it once Linux has it;
  nothing there means the cable or the pairing.
- Linux has it but the game does not: click into the game window, then press
  a button (the page only sees pads after a press while it is in front).
- Steam can take over the pad while it runs; close Steam if buttons act
  oddly.
- The pause menu says "The controller cannot be read in this window": the
  window refused the pad (the reason is in brackets). Close and reopen Forge
  once; if it still says so, open the game in a browser tab and pass the
  reason on.
- A press does two things (○ also pauses, L2 leaves the game): Forge has not
  been reopened since the fix. Close and reopen it once. (A pop-out window
  is covered too since commit 7433529.)
- The touchpad moves the desktop pointer: hid-playstation makes it its own
  input device, which Hyprland drives like the laptop's touchpad. In the
  game a mouse click does nothing for 2 seconds after a pad button or a
  firm stick push (no punch, no click on the pause menu; keys, Enter on the
  menu included, still work), mouse moves do not turn the camera while the
  pad is in use, and the first click after that only hands the controls
  and the hints back to the mouse and keyboard (the next pad press takes
  them back). To turn the touchpad off as a pointer, a Hyprland per-device
  rule can disable it (the name shows in `hyprctl devices` while the pad is
  connected); not done, the Hyprland config was left alone.
- The soldier creeps with nobody touching the stick: the stick drifts past
  the deadzone (worn pads do). Raise `pad.deadzone` in `controls.json` from
  0.15 a little (0.2, say). A drifting stick also counts as steering, so
  the game pauses when its window loses focus.
- While the game is in front, PS does not go home (the pad-as-mouse service
  is quiet then). Leave through the pause menu's Back to Exo Lab.

## The buttons (from `apps/exolab/static/game/controls.json`)

The registry is the source of truth; the pause menu lists the same thing.

- Left stick: move (tilt a little to walk, all the way to run)
- Right stick: look
- ✕ jump, again in the air to boost jump
- L3 (press the left stick): sprint; stays on until you stop, or click it
  again mid-run
- L1: boost dash where the left stick points
- ○ slide while sprinting, ground slam in the air
- R2 or R1: punch, or throw the crate you hold
- □ lift a crate, again to put it down
- L2 (hold): walk
- D-pad: ▲ Armour, ▶ Strength, ▼ Speed, ◀ Cloak (again to switch off)
- △ repair broken arms
- Create: back to the start
- Options: pause menu. In the menu the d-pad or the left stick moves, ✕
  picks, ○ or Options goes back to the game. A stick or d-pad still held
  when the menu opens (or when the window comes back) moves nothing until
  it is let go, and the stick has to rest a moment (about a tenth of a
  second), so a dodge swinging through the centre or a slow walk does not
  count. The focus stops at the first and last item.

How the game reads the pad (critic fixes, commits 77fd779, b538a50,
cdcaed9 and 8509987):
with two pads it reads the one being used, not the first plugged in, and a
stick that drifts on its own does not count as using it; R2 and L2 count as
pressed past 30% and as let go under 20%, so a resting finger does not
repeat; L3 sprint ends once the stick has rested a quarter of a second, so a
flick through the centre keeps it; in pad play the game pauses when its
window or Forge's window loses focus (Forge's once it has been reopened) and
when the pad in use drops out (cable out, flat battery), also with a second
pad still connected; for 2 seconds after a pad button or a firm stick push
a mouse click does nothing, and while the pad is in use mouse moves do not
turn the camera (the touchpad); after that the first click hands the
controls back to the mouse.

The pad rumbles on a boost, a slam, a punch, a wall breaking, a throw, taking
damage, the arms breaking and going down (the `rumble` table in the same
file).
