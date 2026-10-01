class_name LegionBrain
extends Node
## The Legion's brain (lane A4 part 2): a child of a LegionMech named "Brain", picked by
## enemies.json "behaviour" (scout.gd, pack_hunter.gd, heavy.gd extend this). It only sets what the
## body asks for (move_goal, face_dir, aim_point) and pulls triggers through LegionMech.fire(), so
## every move goes through the legs' grip and every shot through the real guns.
##
## Perception: sight is a cone (enemies.json perception.sight_fov_deg) out to sight_range_m x the
## unit's sight_scale (a shot-out optic sees a third as far), with a clear line from the optic socket
## to the target; hearing picks up the target's footfalls and gunfire inside hearing_range_m x the
## "ai" hear scales (a 57 mm shot carries much further than a step), with an error that grows with
## distance. A hit from the target gives its position away. What it last saw or heard is remembered
## for memory_s. States: patrol (walk a loop round home), alert (go and look where the contact was),
## attack (the behaviour's own fight), retreat (back off towards home under retreat_health_fraction).
## Units spawned together are a pack and share every contact (the Legion's network). Steering: rays
## at hip height turn the unit off walls and steep rock, and units keep apart. The figures are the
## enemies.json "ai" block.

signal state_changed(state: String)
signal spotted(at: Vector3)

const STATES := ["patrol", "alert", "attack", "retreat"]
const WORLD_MASK := 1

var unit: LegionMech
var ai: Dictionary = {}
var perception: Dictionary = {}
var state := "patrol"
var target: RigidBody3D = null
## Where the target was last seen or heard (world), and how long ago (INF: never).
var last_known := Vector3.ZERO
var contact_age_s := INF
var sees := false
var home := Vector3.ZERO
var pack: Array = []  # LegionBrain: the units it was spawned with (itself included)
var pack_index := 0
var state_age_s := 0.0
var shots := 0
var _route: Array[Vector3] = []
var _route_i := 0
var _route_wait := 0.0
var _think_left := 0.0
var _steer_dir := Vector3.ZERO
var _goal := Vector3.ZERO
var _target_v := Vector3.ZERO
var _shot_i := 0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	unit = get_parent() as LegionMech
	ai = unit.def.get("ai", {})
	perception = unit.def.get("perception", {})
	_rng.seed = hash(unit.name) ^ int(ai.get("seed", 0))
	unit.hit_taken.connect(_on_hit_taken)
	if pack.is_empty():
		pack = [self]
	_think_left = _rng.randf() / maxf(float(ai.get("think_hz", 5.0)), 0.5)
	if home == Vector3.ZERO:
		home = unit.global_position if unit.is_inside_tree() else unit.position
	_make_route()


## Called by the mission before the unit enters the tree: where it lives and who it hunts with.
func setup(home_at: Vector3, members: Array, index: int, seed_value: int) -> void:
	home = home_at
	pack = members
	pack_index = index
	_rng.seed = seed_value


func _make_route() -> void:
	_route.clear()
	var r := float(ai.get("patrol_radius_m", 50.0))
	var n := int(ai.get("patrol_points", 4))
	var a0 := _rng.randf() * TAU
	for i in n:
		var a := a0 + TAU * float(i) / float(n) + _rng.randf_range(-0.4, 0.4)
		_route.append(home + Vector3(cos(a), 0.0, sin(a)) * r * _rng.randf_range(0.5, 1.0))


func _physics_process(delta: float) -> void:
	if unit == null or unit.dead:
		return
	_find_target()
	contact_age_s += delta
	state_age_s += delta
	if target != null:
		var k := 1.0 - exp(-delta / maxf(float(ai.get("lead_smooth_s", 0.6)), 0.05))
		_target_v = _target_v.lerp(target.linear_velocity, k)
	_think_left -= delta
	if _think_left <= 0.0:
		_think_left += 1.0 / maxf(float(ai.get("think_hz", 5.0)), 0.5)
		_perceive()
		_choose_state()
		_think()
		update_steering(_goal)
	match state:
		"patrol":
			_patrol(delta)
		"alert":
			_alert(delta)
		"attack":
			_attack(delta)
		"retreat":
			_retreat(delta)


# --- perception ---------------------------------------------------------------------------------


func _find_target() -> void:
	if target != null and is_instance_valid(target):
		return
	target = get_tree().get_first_node_in_group("player_mech") as RigidBody3D
	if target == null:
		return
	if target.has_signal("stepped"):
		target.connect("stepped", _on_target_stepped)
	var combat: Object = target.get_meta("combat") if target.has_meta("combat") else null
	if combat != null and combat.has_signal("fired"):
		combat.connect("fired", _on_target_fired)


func target_alive() -> bool:
	if target == null or not is_instance_valid(target):
		return false
	var combat: Object = target.get_meta("combat") if target.has_meta("combat") else null
	if combat != null and combat.get("damage") != null:
		return not bool((combat.get("damage") as DamageModel).is_destroyed)
	return true


func target_centre() -> Vector3:
	if target.center_of_mass_mode == RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM:
		return target.global_transform * target.center_of_mass
	return target.global_position


func eye() -> Vector3:
	return unit.socket("optic").origin


func can_see(at: Vector3) -> bool:
	var from := eye()
	var to := at - from
	var range_m := float(perception.get("sight_range_m", 300.0)) * unit.sight_scale
	if to.length() > range_m:
		return false
	var fwd := -unit.global_transform.basis.z
	var half := deg_to_rad(float(perception.get("sight_fov_deg", 120.0)) * 0.5)
	if absf(Vector2(fwd.x, fwd.z).angle_to(Vector2(to.x, to.z))) > half:
		return false
	var q := PhysicsRayQueryParameters3D.create(from, at, WORLD_MASK)
	return unit.get_world_3d().direct_space_state.intersect_ray(q).is_empty()


func _perceive() -> void:
	sees = false
	if not target_alive():
		return
	if can_see(target_centre()) or can_see(target.global_position + Vector3.UP * 0.5):
		sees = true
		_contact(target_centre(), true)


## A contact: remember it and pass it to the pack.
func _contact(at: Vector3, seen: bool) -> void:
	var fresh := contact_age_s > float(perception.get("memory_s", 15.0))
	last_known = at
	contact_age_s = 0.0
	if seen and (fresh or state == "patrol"):
		spotted.emit(at)
	for b: LegionBrain in pack:
		if b != self and is_instance_valid(b) and not b.unit.dead:
			b.hear_of(at)


## Told of a contact by a packmate or a calling scout.
func hear_of(at: Vector3) -> void:
	if contact_age_s > 0.5:
		last_known = at
		contact_age_s = 0.0


func _heard(scale_key: String, default_scale: float) -> void:
	if not target_alive() or unit.dead:
		return
	var range_m := float(perception.get("hearing_range_m", 250.0)) * float(ai.get(scale_key, default_scale))
	var d := unit.global_position.distance_to(target.global_position)
	if d > range_m:
		return
	var err := d * float(ai.get("hearing_error", 0.1))
	_contact(target.global_position + Vector3(_rng.randfn(0.0, err), 0.0, _rng.randfn(0.0, err)), false)


func _on_target_stepped(_leg: String) -> void:
	_heard("hear_step_scale", 0.4)


func _on_target_fired(_weapon: String, _ammo: String) -> void:
	_heard("hear_shot_scale", 3.0)


func _on_hit_taken(_key: String, _dealt: float, info: Dictionary) -> void:
	var shooter: Variant = info.get("shooter")
	if shooter is Node3D and is_instance_valid(shooter) and shooter == target:
		_contact(target.global_position, false)


# --- states -------------------------------------------------------------------------------------


func _choose_state() -> void:
	var memory := float(perception.get("memory_s", 15.0))
	var want := state
	var retreat_at := float(unit.def.get("retreat_health_fraction", 0.0))
	if not target_alive():
		want = "patrol"
	elif retreat_at > 0.0 and unit.health_fraction() < retreat_at and contact_age_s < memory * 2.0:
		want = "retreat"
	elif sees or (state == "attack" and contact_age_s < float(ai.get("hold_attack_s", 4.0))):
		want = "attack"
	elif contact_age_s < memory:
		want = "alert"
	else:
		want = "patrol"
	set_state(want)


func set_state(s: String) -> void:
	if s == state:
		return
	state = s
	state_age_s = 0.0
	if s == "patrol":
		unit.aim_point = null
	state_changed.emit(s)


## Behaviours hook in here once per think (5 Hz).
func _think() -> void:
	pass


func _patrol(dt: float) -> void:
	if _route.is_empty():
		hold()
		return
	var goal := _route[_route_i]
	if _flat(goal - unit.global_position).length() < float(ai.get("arrive_m", 6.0)):
		hold()
		_route_wait += dt
		if _route_wait > float(ai.get("patrol_wait_s", 3.0)):
			_route_wait = 0.0
			_route_i = (_route_i + 1) % _route.size()
		return
	steer_to(goal, float(ai.get("patrol_speed_m_s", 4.0)))


func _alert(_dt: float) -> void:
	unit.aim_point = last_known + Vector3.UP
	if _flat(last_known - unit.global_position).length() < float(ai.get("search_reach_m", 25.0)):
		hold()
		face(last_known)
		return
	steer_to(last_known, float(ai.get("alert_speed_m_s", 8.0)))


## The behaviour's fight; the base one walks at the target and shoots whatever bears.
func _attack(_dt: float) -> void:
	steer_to(last_known, float(ai.get("alert_speed_m_s", 8.0)))
	face(last_known)


func _retreat(_dt: float) -> void:
	var away := _flat(home - last_known).normalized()
	if away.length() < 0.1:
		away = _flat(unit.global_position - last_known).normalized()
	steer_to(home + away * float(ai.get("retreat_m", 120.0)), float(unit.def.get("speed_m_s", 10.0)))


# --- moving -------------------------------------------------------------------------------------


func hold() -> void:
	unit.move_goal = Vector3.ZERO


## Walk towards `goal` at `speed` (m/s, capped by the unit's top speed), turning off obstacles and
## away from other Legion; faces the way it walks unless the behaviour calls face() after.
func steer_to(goal: Vector3, speed: float) -> void:
	_goal = goal
	var to := _flat(goal - unit.global_position)
	var dist := to.length()
	if dist < 1.0:
		hold()
		return
	var dir := to / dist
	if _steer_dir.length() > 0.1 and absf(_steer_dir.angle_to(dir)) < PI * 0.6:
		dir = _steer_dir
	dir = (dir + _separation()).normalized()
	var top := float(unit.def.get("speed_m_s", 10.0))
	var v := minf(minf(speed, top), dist * 0.8)
	unit.move_goal = dir * v
	unit.face_dir = dir


## Move along world direction `dir` (flat) at `speed`.
func steer_dir(dir: Vector3, speed: float) -> void:
	steer_to(unit.global_position + _flat(dir).normalized() * 50.0, speed)


func face(at: Vector3) -> void:
	var d := _flat(at - unit.global_position)
	if d.length() > 0.5:
		unit.face_dir = d.normalized()


## Once per think: if the way to the goal is blocked by a wall or a steep face, the first clear
## heading round it (rays fanned left and right at hip height).
func update_steering(goal: Vector3) -> void:
	_steer_dir = Vector3.ZERO
	var to := _flat(goal - unit.global_position)
	if to.length() < 2.0:
		return
	var dir := to.normalized()
	var look := clampf(unit.linear_velocity.length() * 1.5, 8.0, 30.0)
	look = minf(look, to.length())
	var from := unit.global_transform * unit.center_of_mass
	var side := 1.0 if pack_index % 2 == 0 else -1.0
	for deg: float in [0.0, 25.0, -25.0, 50.0, -50.0, 80.0, -80.0, 120.0, -120.0]:
		var d := dir.rotated(Vector3.UP, deg_to_rad(deg * side))
		if not _blocked(from, d, look):
			if deg != 0.0:
				_steer_dir = d
			return


func _blocked(from: Vector3, dir: Vector3, length: float) -> bool:
	var q := PhysicsRayQueryParameters3D.create(from, from + dir * length, WORLD_MASK)
	var hit := unit.get_world_3d().direct_space_state.intersect_ray(q)
	return not hit.is_empty() and (hit["normal"] as Vector3).y < float(ai.get("steep_normal_y", 0.6))


func _separation() -> Vector3:
	var push := Vector3.ZERO
	var keep := float(ai.get("keep_apart_m", 10.0))
	for n: Node in get_tree().get_nodes_in_group("legion"):
		var other := n as LegionMech
		if other == null or other == unit or other.dead:
			continue
		var d := _flat(unit.global_position - other.global_position)
		var l := d.length()
		if l < keep and l > 0.01:
			push += d / l * (1.0 - l / keep)
	return push


static func _flat(v: Vector3) -> Vector3:
	return Vector3(v.x, 0.0, v.z)


# --- shooting -----------------------------------------------------------------------------------


## Where to aim a round leaving `from` at `speed` (m/s) to meet the target: its smoothed velocity
## times the flight time, plus the drop over that time (so a jinking target defeats the lead).
func lead(from: Vector3, speed: float, drag: float = 0.0) -> Vector3:
	var at := target_centre()
	var g := Registry.tune_f("physics.gravity_m_s2", 9.81)
	var t := 0.0
	for i in 3:
		var d := from.distance_to(at)
		var v := maxf(speed * exp(-drag * t * 0.5), 1.0)
		t = d / v
		at = target_centre() + _target_v * t
	return at + Vector3.UP * 0.5 * g * t * t


func target_speed() -> float:
	return _flat(_target_v).length()


func distance_to_target() -> float:
	return unit.global_position.distance_to(target.global_position) if target != null else INF


## Fires `weapon_id` from its next muzzle socket (enemies.json ai.muzzles) at the lead point when
## the turret, launcher or body bears within `cone_deg` and the target is within `range_m`, once
## ai.react_s has passed since it went over to attack.
func try_fire(weapon_id: String, cone_deg: float, spread_mrad: float, range_m: float) -> Projectile:
	if not sees or not unit.weapons.has(weapon_id):
		return null
	# The first sight of a target takes a moment to classify and lay the guns (ai.react_s).
	if state == "attack" and state_age_s < float(ai.get("react_s", 1.0)):
		return null
	var ws: WeaponState = unit.weapons[weapon_id]
	if not ws.can_fire():
		return null
	var muzzles: Array = (ai.get("muzzles", {}) as Dictionary).get(weapon_id, [])
	if muzzles.is_empty():
		return null
	var m := str(muzzles[_shot_i % muzzles.size()])
	var at := unit.socket(m)
	var ammo: Dictionary = (ws.def.get("ammo", {}) as Dictionary).get(ws.loaded_ammo, {})
	var aim := lead(at.origin, float(ammo.get("muzzle_m_s", 800.0)), float(ammo.get("drag_per_s", 0.0)))
	if at.origin.distance_to(aim) > range_m:
		return null
	if rad_to_deg(bearing_error(aim)) > cone_deg:
		return null
	var p := unit.fire(weapon_id, at, (aim - at.origin).normalized(), spread_mrad)
	if p != null:
		_shot_i += 1
		shots += 1
	return p


## How far off the unit's guns bear on `at`, radians: the turret or launcher's swing still to go,
## or the body's heading for guns fixed to the body.
func bearing_error(at: Vector3) -> float:
	var keep: Variant = unit.aim_point
	unit.aim_point = at
	var e := unit.aim_error()
	unit.aim_point = keep
	return e


func telemetry() -> Dictionary:
	return {
		"state": state,
		"sees": sees,
		"contact_age_s": snappedf(contact_age_s, 0.1) if contact_age_s < 1e6 else -1.0,
		"shots": shots,
	}
