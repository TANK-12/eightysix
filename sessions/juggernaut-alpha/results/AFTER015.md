# After 015: grapple line and cockpit view (Emerson's notes, 2026-10-03)
date: 2026-10-03 · for: both · Tetsu (ejb-cb, hey) · commit 920c41e in ~/Games/eightysix

**Try this:** fire the grapple while driving fast: the line now stays on the launcher instead of hanging where it
was flown. Hit a Legion with it: the dart stays in it and the cable drags it. Press the view key for the cockpit: you
now look out through the optical sensor at the front of the pod (Settings > Gameplay > Cockpit view from switches
back to the pilot seat).

1. **Grapple line left behind (verified by test).** In flight the line was drawn through the world points the dart
   passed, so at speed it hung behind the mech. Now `WireAnchor.dragged()` shifts it with the launcher, fading to zero
   at the dart (test_the_flying_line_stays_on_the_launcher_when_the_mech_moves). This is a drawing model, reasoned, not
   a simulated cable.
2. **Dart did not stay in what it hit (verified by test).** `anchor_point` was a fixed world point; it now rides on the
   body the dart bit, and a rigid body gets the cable's tension back (equal and opposite); damping uses the relative
   speed of the two ends; the dart lets go if the body is freed. test_the_anchor_rides_on_a_moving_body: anchor follows
   a 3 m move, reeling pulls a 200 kg box toward the mech. Not checked in a real mission against a walking Legion.
3. **Cockpit view "really close" (screenshot).** The eye sat at the pilot seat socket, level with the 57 mm's pivot,
   so the barrel and pod plates filled the frame (images/497 vs **images/527-r3_cockpit_range**). New setting
   `gameplay.cockpit_eye`, default `eye` = the model's front optical-sensor socket (mechs.json cameras.eye); the sensor
   housing and visor are in cockpit_hide (they sat 6 and 18 cm from the lens). The view is now open, with the side
   armour at the lower corners. fps not measured: other sessions' bots were on the GPU (the shot shows 17 fps for that reason).

Tests: test_grapple 16/16, test_cockpit 9/9, test_juggernaut 27/27. Full suite 439 passed, 14 failed, all in other
sessions' unfinished work (Relay 38's new test_clip, Relay 36's test_real_maps forest and roof textures in test_world_look).
