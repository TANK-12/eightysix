class_name JumpCharge
extends RefCounted
## Hold-to-charge jump (physics supplement, point 3): how fast the mech leaves the ground for a
## given hold time. Game mode uses the tuned magic-motor range; test bench mode works it out from
## what the leg actuators can really deliver: energy over their stroke, capped by how fast they move.


static func fraction(hold_s: float, min_hold_s: float, full_s: float) -> float:
	if hold_s < min_hold_s:
		return 0.0
	return clampf((hold_s - min_hold_s) / maxf(full_s - min_hold_s, 0.001), 0.0, 1.0)


## p: tuning.json "standin.jump" (min_hold_s, full_charge_s, min_launch_m_s, max_launch_m_s).
static func game_speed(hold_s: float, p: Dictionary) -> float:
	var min_hold := float(p.get("min_hold_s", 0.12))
	if hold_s < min_hold:
		return 0.0
	var f := fraction(hold_s, min_hold, float(p.get("full_charge_s", 1.0)))
	return lerpf(float(p.get("min_launch_m_s", 4.0)), float(p.get("max_launch_m_s", 10.0)), f)


## actuators: resolved parts.json actuator entries. bench: tuning.json "jump_bench".
static func bench_speed(
	hold_s: float, mass_kg: float, actuators: Array, leg_reach_m: float, p: Dictionary, bench: Dictionary
) -> float:
	var min_hold := float(p.get("min_hold_s", 0.12))
	if hold_s < min_hold or mass_kg <= 0.0:
		return 0.0
	var f := fraction(hold_s, min_hold, float(p.get("full_charge_s", 1.0)))
	var kinds: Array = bench.get("leg_joint_kinds", ["hip_pitch", "knee"])
	var use := float(bench.get("stroke_use", 0.7))
	var energy := 0.0
	var cap := INF
	for a: Dictionary in actuators:
		if not str(a.get("joint", "")) in kinds:
			continue
		var b: Dictionary = a.get("bench", {})
		energy += (
			float(b.get("peak_force_n", 0.0))
			* float(b.get("stroke_m", 0.0))
			* use
			* float(b.get("efficiency", 1.0))
		)
		cap = minf(cap, bench_speed_cap(b, leg_reach_m))
	if energy <= 0.0:
		return 0.0
	return minf(sqrt(2.0 * energy * f / mass_kg), cap)


## The fastest a foot can push the body with this actuator: its joint rate times half the leg reach.
static func bench_speed_cap(bench: Dictionary, leg_reach_m: float) -> float:
	var lever := maxf(float(bench.get("lever_arm_m", 0.3)), 0.01)
	return float(bench.get("no_load_speed_m_s", 0.2)) / lever * leg_reach_m * 0.5
