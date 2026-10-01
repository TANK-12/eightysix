extends LegionBrain
## Grauwolf, the pack hunter (enemies.json "behaviour": "pack_hunter"): the pack spreads round the
## target, each to its own flank angle off the target's heading (ai.flank_angles_deg by pack index,
## ai.flank_radius_m out), firing the rocket launcher while it runs; once at its spot, after
## ai.close_after_s or when the launcher is empty (or at twice close_after_s regardless), it charges in and swings its high-frequency blades within ai.blade_reach_m,
## then breaks off to its flank again. A blade cut is a hit on the part nearest the blade tip, with
## the blade's own momentum (ai.blade_push_kg x ai.blade_speed_m_s) as the push.

signal blade_hit(dealt: float)

var phase := "flank"  # flank, close
var blade_hits := 0
var _phase_s := 0.0
var _swing_left := 0.0


func set_state(s: String) -> void:
	if s != state:
		phase = "flank"
		_phase_s = 0.0
	super(s)


func _attack(dt: float) -> void:
	_phase_s += dt
	_swing_left = maxf(_swing_left - dt, 0.0)
	var speed := float(unit.def.get("speed_m_s", 22.0))
	var d := distance_to_target()
	var rockets: WeaponState = unit.weapons.get("grauwolf_rockets")
	var empty := rockets == null or (rockets.magazine == 0)
	if phase == "flank":
		var spot := flank_spot()
		steer_to(spot, speed)
		var there := _flat(spot - unit.global_position).length() < float(ai.get("flank_reach_m", 25.0))
		if there:
			face(last_known)
		unit.aim_point = target_centre() if sees else last_known
		var band: Array = ai.get("rocket_range_m", [60.0, 320.0])
		if d > float(band[0]):
			try_fire("grauwolf_rockets", float(ai.get("rocket_cone_deg", 3.0)), float(ai.get("rocket_spread_mrad", 6.0)), float(band[1]))
		var after := float(ai.get("close_after_s", 8.0))
		if (there and (_phase_s > after or empty)) or _phase_s > after * 2.0:
			phase = "close"
			_phase_s = 0.0
	else:
		steer_to(target.global_position if sees else last_known, speed)
		face(target.global_position if sees else last_known)
		unit.aim_point = null
		if _blade(d):
			phase = "flank"
			_phase_s = 0.0
		elif _phase_s > float(ai.get("close_give_up_s", 10.0)):
			phase = "flank"
			_phase_s = 0.0


## Where this packmate goes: its angle off the target's heading (or off the line to it while the
## target stands still), flank_radius_m out from the target.
func flank_spot() -> Vector3:
	var angles: Array = ai.get("flank_angles_deg", [70.0, -70.0, 140.0, -140.0, 0.0])
	var a := deg_to_rad(float(angles[pack_index % angles.size()]))
	var ref := _flat(_target_v)
	if ref.length() < 2.0:
		ref = _flat(unit.global_position - last_known).normalized() * -1.0
	ref = ref.normalized()
	if ref.length() < 0.1:
		ref = Vector3.FORWARD
	return last_known + ref.rotated(Vector3.UP, a) * float(ai.get("flank_radius_m", 70.0))


## Swings the blades when the target is in reach and in front; true when a cut landed.
func _blade(d: float) -> bool:
	if _swing_left > 0.0 or not unit.arms_ok or not target_alive():
		return false
	var reach := float(ai.get("blade_reach_m", 6.0))
	var tip := unit.socket("blade_tip_R").origin
	var near := target_centre()
	var gap := minf(tip.distance_to(near), d)
	var fwd := -unit.global_transform.basis.z
	var to := _flat(near - unit.global_position)
	if gap > reach or rad_to_deg(absf(Vector2(fwd.x, fwd.z).angle_to(Vector2(to.x, to.z)))) > float(ai.get("blade_face_deg", 40.0)):
		return false
	var wdef := Registry.entry("weapons", "grauwolf_blade")
	_swing_left = float(wdef.get("swing_s", 0.5))
	var receiver: Object = target.get_meta("combat") if target.has_meta("combat") else target
	if receiver == null or not receiver.has_method("take_hit"):
		return false
	var dir := (near - tip).normalized()
	var r: Dictionary = receiver.call(
		"take_hit",
		{
			"point": near.lerp(tip, 0.5),
			"normal": -dir,
			"dir": dir,
			"speed": float(ai.get("blade_speed_m_s", 12.0)),
			"projectile_kg": float(ai.get("blade_push_kg", 80.0)),
			"damage": float(wdef.get("damage", 1400.0)),
			"penetration_mm": float(ai.get("blade_penetration_mm", 250.0)),
			"ammo": "blade",
			"shooter": unit,
		}
	)
	blade_hits += 1
	CombatFx.sparks(unit.get_parent(), near.lerp(tip, 0.5), -dir, 40, 14.0, 90.0)
	blade_hit.emit(float(r.get("dealt", 0.0)))
	return true
