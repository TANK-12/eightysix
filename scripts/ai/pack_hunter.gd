extends LegionBrain
## Grauwolf, the pack hunter (enemies.json "behaviour": "pack_hunter"): the pack spreads round the
## target, each to its own flank angle off the target's heading (ai.flank_angles_deg by pack index,
## ai.flank_radius_m out), firing unguided rockets in volleys of ai.rocket_volley while it runs; once at its spot, after
## ai.close_after_s or when the launcher is empty (or at twice close_after_s regardless), it charges in and swings its high-frequency blades within ai.blade_reach_m,
## then breaks off to its flank again. A blade cut is a hit on the part nearest the blade tip, with
## the blade's own momentum (ai.blade_push_kg x ai.blade_speed_m_s) as the push.

signal blade_hit(dealt: float)

var phase := "flank"  # flank, close
var blade_hits := 0
var _phase_s := 0.0
var _swing_left := 0.0
var _volley := 0
var _volley_gap := 0.0
var _flank_ref := Vector3.ZERO  # latched line to a still target, so the flank spot stays put
var _flank_a := NAN  # latched flank angle (radians) for this run


func _start_flank() -> void:
	phase = "flank"
	_phase_s = 0.0
	_flank_ref = Vector3.ZERO
	_flank_a = NAN


func set_state(s: String) -> void:
	if s != state:
		_start_flank()
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
		_volley_gap = maxf(_volley_gap - dt, 0.0)
		if d > float(band[0]) and _volley_gap <= 0.0:
			if try_fire("grauwolf_rockets", float(ai.get("rocket_cone_deg", 3.0)), float(ai.get("rocket_spread_mrad", 12.0)), float(band[1])) != null:
				_volley += 1
				if _volley >= int(ai.get("rocket_volley", 2)):
					_volley = 0
					_volley_gap = float(ai.get("rocket_volley_gap_s", 3.0))
		var after := float(ai.get("close_after_s", 8.0))
		if (there and (_phase_s > after or empty)) or _phase_s > after * 2.0:
			phase = "close"
			_phase_s = 0.0
	else:
		steer_to(target.global_position if sees else last_known, speed)
		face(target.global_position if sees else last_known)
		unit.aim_point = null
		if _blade(d) or _phase_s > float(ai.get("close_give_up_s", 10.0)):
			_start_flank()


## Where this packmate goes: its angle off the target's heading (or, while the target stands still,
## off the line to it as it was when this flank run began), flank_radius_m out from the target.
## The still-target line is latched: measured afresh each think, it turned with the unit as it ran,
## so the spot ran ahead of it and the pack never spread (test_ai's pack test failed 2 runs in 3).
func flank_spot() -> Vector3:
	var ref := _flat(_target_v)
	if ref.length() < 2.0:
		if _flank_ref == Vector3.ZERO:
			_flank_ref = _flat(last_known - unit.global_position).normalized()
		ref = _flank_ref
	ref = ref.normalized()
	if ref.length() < 0.1:
		ref = Vector3.FORWARD
	if is_nan(_flank_a):
		_flank_a = flank_angle(ref)
	return last_known + ref.rotated(Vector3.UP, _flank_a) * float(ai.get("flank_radius_m", 70.0))


## This unit's flank angle (radians), handed out so no two packmates cross paths: the pack's
## first n angles from ai.flank_angles_deg, ordered left to right, go to the hunters ordered by
## where they stand across the line to the target. By pack index alone, a wolf on the left could
## draw the right flank and its neighbour the left; their keep-apart push then held them side by
## side and both ran straight at the target (test_ai's pack test, about one run in three).
func flank_angle(ref: Vector3) -> float:
	var angles: Array = ai.get("flank_angles_deg", [70.0, -70.0, 140.0, -140.0, 0.0])
	var right := ref.rotated(Vector3.UP, PI * 0.5)
	var mates: Array = [self]
	for b: LegionBrain in pack:
		if b != self and is_instance_valid(b) and not b.unit.dead and b.has_method("flank_angle") and not mates.has(b):
			mates.append(b)
	var n := mini(mates.size(), angles.size())
	var mine: Array = angles.slice(0, n).map(func(d: Variant) -> float: return deg_to_rad(float(d)))
	mine.sort_custom(func(x: float, y: float) -> bool: return sin(x) < sin(y))
	var across := func(b: LegionBrain) -> float: return _flat(b.unit.global_position - last_known).dot(right)
	mates.sort_custom(func(x: LegionBrain, y: LegionBrain) -> bool: return across.call(x) < across.call(y))
	var rank := mates.find(self)
	return float(mine[rank]) if rank < n else deg_to_rad(float(angles[pack_index % angles.size()]))


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
