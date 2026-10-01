extends LegionBrain
## Löwe, the heavy (enemies.json "behaviour": "heavy"): advances slowly into its fighting range
## (ai.engage_range_m), squares its hull to the target and lets the turret do the work: the 120 mm
## leads the target and fires when the turret has settled on it (ai.fire_cone_deg for
## ai.settle_s), one round every 6 s from its autoloader, the first ones ranging in (ranging_mrad); the coaxial machine gun bursts inside
## ai.coax_range_m. Its next round is picked while the autoloader cycles: HE (a blast that shoves and
## spins what is near it) against a target moving faster than ai.he_when_target_m_s or further than
## ai.he_beyond_m, where a dart would likely miss; APFSDS against a still or close one.

var _settled_s := 0.0
var _rounds_on_target := 0
var _coax_burst := 0.0
var _coax_gap := 0.0


func _attack(dt: float) -> void:
	var band: Array = ai.get("engage_range_m", [180.0, 500.0])
	var d := distance_to_target()
	var slow := float(ai.get("advance_speed_m_s", 5.0))
	if d > float(band[1]):
		steer_to(last_known, slow)
	elif d < float(band[0]):
		steer_dir(_flat(unit.global_position - last_known), slow * 0.8)
	else:
		hold()
	face(last_known)
	var gun: WeaponState = unit.weapons.get("lowe_120mm")
	if gun == null:
		return
	var ammo: Dictionary = (gun.def.get("ammo", {}) as Dictionary).get(gun.loaded_ammo, {})
	var muzzle := unit.socket("muzzle").origin
	unit.aim_point = lead(muzzle, float(ammo.get("muzzle_m_s", 1650.0)), float(ammo.get("drag_per_s", 0.0))) if sees else last_known
	if sees and rad_to_deg(bearing_error(unit.aim_point)) < float(ai.get("fire_cone_deg", 0.6)):
		_settled_s += dt
	else:
		_settled_s = 0.0
	if _settled_s >= float(ai.get("settle_s", 0.6)):
		var p := try_fire("lowe_120mm", float(ai.get("fire_cone_deg", 0.6)), ranging_mrad(), float(ai.get("gun_range_m", 1200.0)))
		if p != null:
			_settled_s = 0.0
			_rounds_on_target += 1
			gun.selected_ammo = next_round()
	_coax(dt, d)


## The gun's error for the next round: the first at a new target is off by ai.first_round_mrad
## (range estimate, crosswind, a moving hull), halving with each round as the fall of shot corrects
## it, down to the gun's own ai.spread_mrad.
func ranging_mrad() -> float:
	var first := float(ai.get("first_round_mrad", 1.5))
	return maxf(float(ai.get("spread_mrad", 0.4)), first * pow(0.5, float(_rounds_on_target)))


func set_state(s: String) -> void:
	if s == "attack" and state != "attack":
		_rounds_on_target = 0
	super(s)


## The round to load next: HE for a fast or far target, APFSDS otherwise.
func next_round() -> String:
	var gun: WeaponState = unit.weapons.get("lowe_120mm")
	if gun == null or not gun.ammo_types.has("he"):
		return gun.selected_ammo if gun != null else ""
	if target_speed() > float(ai.get("he_when_target_m_s", 6.0)) or distance_to_target() > float(ai.get("he_beyond_m", 450.0)):
		return "he"
	return "apfsds"


func _coax(dt: float, d: float) -> void:
	if d > float(ai.get("coax_range_m", 400.0)):
		return
	if _coax_gap > 0.0:
		_coax_gap -= dt
		return
	if try_fire("lowe_mg", float(ai.get("coax_cone_deg", 3.0)), float(ai.get("coax_spread_mrad", 3.0)), float(ai.get("coax_range_m", 400.0))) != null or _coax_burst > 0.0:
		_coax_burst += dt
		if _coax_burst > float(ai.get("burst_s", 1.5)):
			_coax_burst = 0.0
			_coax_gap = float(ai.get("burst_gap_s", 2.0))
