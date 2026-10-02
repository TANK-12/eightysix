# Eighty Six: Emerson's playtest notes

date: 2026-10-01 · for: Claude (next track-A session reads this first)

## 2026-10-01 · version 010, mission "First contact"

- **Wave 1 (the two Ameise scouts): the models are broken.** So far this is the only wave whose models
  he has seen broken. Waves 2 and 3 are not confirmed either way, because he has not got past wave 2.
- **He can't get past wave 2 (the Grauwolf pack): they one-shot him.** Cause, checked in the data
  (not in a live run): the cockpit parts `jg2_canopy` and `jg2_pod_tub` have 1000 health and 0 mm
  armour, and both are kind "cockpit", which is critical (losing one destroys the mech). A
  `grauwolf_rockets` HEAT rocket does 1100 damage with 200 mm penetration, and the `grauwolf_blade`
  does 1400 with 250 mm. So one rocket or one blade hit on the cockpit kills him. Hits anywhere else
  don't, which is why it feels random. Suggested fix (not applied): raise the cockpit parts to about
  1500-2000 health so it takes two rockets. Workaround for now: Settings > Gameplay > "Damage you take"
  at 0.85x survives a rocket, and 0.7x survives the blade too.
