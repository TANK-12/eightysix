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
## at hip height turn the unit off walls, and the ground ahead is probed at foot level (part 4,
## Emerson: "they walk on cliffs", "they climb the edge wall"): a rise steeper than the legs can grip
## (gait.max_slope_deg) or a step up past the hip blocks that way. Every goal is kept inside the map's
## Legion area (maps.json "legion_area_half_m"), so they patrol, hunt and stop inside it. Units keep
## apart. The figures are the enemies.json "ai" block.

signal state_changed(state: String)
signal spotted(at: Vector3)

const STATES := ["patrol", "alert", "attack", "retreat"]
const WORLD_MASK := 1
const NAV_MIN_M := 70.0  # nearer than this a goal is walked at directly
const NAV_REPLAN_S := 8.0
const NAV_PASSED_M := 22.0  # a waypoint this close is behind it
const NAV_LOOKAHEAD := 2  # steer to the waypoint this many ahead of the next one
const NAV_BOGGED_S := 10.0  # a unit that walked less than NAV_BOGGED_M in this long on a path is bogged down
const NAV_BOGGED_M := 10.0

var unit: LegionMech
var ai: Dictionary = {}
var perception: Dictionary = {}
var state := "patrol"
var target: RigidBody3D = null
const RETARGET_S := 1.5
const RETARGET_MARGIN_M := 40.0  # a new Juggernaut must be this much nearer than the current one to switch
var _retarget_s := 0.0
## Where the target was last seen or heard (world), and how long ago (INF: never).
var last_known := Vector3.ZERO
var contact_age_s := INF
var sees := false
var home := Vector3.ZERO
## Half the side of the square (centred on the map's origin) the unit may walk in; INF: anywhere.
var area_half_m := INF
## The map's water line (the mission sets it where the map has one): ground more than ai.max_wade_m under
## it is not ground the unit walks onto. -INF: no water.
var water_y := -INF
var pack: Array = []  # LegionBrain: the units it was spawned with (itself included)
var pack_index := 0
var state_age_s := 0.0
var shots := 0
var _route: Array[Vector3] = []
var _fixed_route: Array[Vector3] = []
## A routed unit's options (a mission group's "once" and "trigger_m"): walk the route once and stay at its
## last stop; and wait where it spawned until the target is within march_trigger_m.
var route_once := false
var march_trigger_m := 0.0
var _marching := false
var _route_done := false
var _provoked := false  # hit since it set out
var _route_i := 0
var _route_wait := 0.0
var _think_left := 0.0
var _steer_dir := Vector3.ZERO
var _goal := Vector3.ZERO
## The map's path-finding (a level's `nav`, set by the mission). A far goal is reached by its waypoints: the unit
## steers to one about 30 m along the path, and asks again when the goal moves or every NAV_REPLAN_S.
var nav: LegionNav
var _path := PackedVector3Array()
var _path_i := 0
var _path_goal := Vector3.INF
var _path_at_ms := 0
var bogged := 0  # times it hardly moved along a path and had the cells ahead and under it closed
var _bog_pos := Vector3.INF
var _bog_ms := 0
var _target_v := Vector3.ZERO
var _shot_i := 0
var _stuck_s := 0.0
var _steer_age := 0.0
var _detour_s := 0.0
var _detour := Vector3.ZERO
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
## `route`: the stops it patrols between, in order and round again (a mission group's "route"); empty: a
## random loop round home.
func setup(home_at: Vector3, members: Array, index: int, seed_value: int, route: Array[Vector3] = []) -> void:
	home = home_at
	pack = members
	pack_index = index
	_rng.seed = seed_value
	_fixed_route = route


func _make_route() -> void:
	_route.clear()
	if not _fixed_route.is_empty():
		_route.append_array(_fixed_route)
		return
	var r := float(ai.get("patrol_radius_m", 50.0))
	var n := int(ai.get("patrol_points", 4))
	var a0 := _rng.randf() * TAU
	for i in n:
		var a := a0 + TAU * float(i) / float(n) + _rng.randf_range(-0.4, 0.4)
		_route.append(in_area(home + Vector3(cos(a), 0.0, sin(a)) * r * _rng.randf_range(0.5, 1.0)))


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
	if _unstick(delta):
		return
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


## The Juggernaut it hunts: the player's, or (lane A5) the nearest living one of the player's squad when that
## is closer by more than RETARGET_MARGIN_M. Looked at again every RETARGET_S; with no squad it is always the player.
func _find_target() -> void:
	_retarget_s -= get_physics_process_delta_time()
	if target != null and is_instance_valid(target) and _retarget_s > 0.0:
		return
	_retarget_s = RETARGET_S
	var best := target if target != null and is_instance_valid(target) and target_alive() else null
	var best_d := INF if best == null else unit.global_position.distance_to(best.global_position) - RETARGET_MARGIN_M
	for group: String in ["player_mech", "squad_mech"]:
		for n: Node in get_tree().get_nodes_in_group(group):
			var m := n as RigidBody3D
			if m == null or m == best or not _alive_mech(m):
				continue
			var d := unit.global_position.distance_to(m.global_position)
			if d < best_d:
				best = m
				best_d = d
	if best != null and best != target:
		_set_target(best)


func _set_target(m: RigidBody3D) -> void:
	if target != null and is_instance_valid(target):
		if target.has_signal("stepped") and target.is_connected("stepped", _on_target_stepped):
			target.disconnect("stepped", _on_target_stepped)
		var old: Object = target.get_meta("combat") if target.has_meta("combat") else null
		if old != null and old.has_signal("fired") and old.is_connected("fired", _on_target_fired):
			old.disconnect("fired", _on_target_fired)
		_target_v = m.linear_velocity
	target = m
	if target.has_signal("stepped"):
		target.connect("stepped", _on_target_stepped)
	var combat: Object = target.get_meta("combat") if target.has_meta("combat") else null
	if combat != null and combat.has_signal("fired"):
		combat.connect("fired", _on_target_fired)


static func _alive_mech(m: RigidBody3D) -> bool:
	var combat: Object = m.get_meta("combat") if m.has_meta("combat") else null
	return combat == null or combat.get("damage") == null or not bool((combat.get("damage") as DamageModel).is_destroyed)


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
	_provoked = true
	var shooter: Variant = info.get("shooter")
	if shooter is Node3D and is_instance_valid(shooter) and shooter == target:
		_contact(target.global_position, false)


# --- states -------------------------------------------------------------------------------------


func _choose_state() -> void:
	var memory := float(perception.get("memory_s", 15.0))
	var want := state
	var retreat_at := float(unit.def.get("retreat_health_fraction", 0.0))
	if not target_alive() or _holds_formation():
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


## A column on a once-only route keeps marching, ignoring what it sees, until it gets to the last stop or is
## hit (convoy discipline: this is what lets a player watch it cross a bridge).
func _holds_formation() -> bool:
	return route_once and _marching and not _route_done and not _provoked and not _fixed_route.is_empty()


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
	var routed := not _fixed_route.is_empty()  # a column keeps walking: close stops, no waiting at them
	if routed and march_trigger_m > 0.0 and not _marching:
		_marching = target != null and is_instance_valid(target) and _flat(target.global_position - unit.global_position).length() < march_trigger_m
		if not _marching:
			hold()
			return
	var goal := _route[_route_i]
	if _flat(goal - unit.global_position).length() < float(ai.get("route_arrive_m", 3.0) if routed else ai.get("arrive_m", 6.0)):
		if routed and route_once and _route_i == _route.size() - 1:
			_route_done = true
			hold()
		elif routed:
			_route_i = (_route_i + 1) % _route.size()
		else:
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
	goal = _nav_goal(in_area(goal))
	_goal = goal
	var to := _flat(goal - unit.global_position)
	var dist := to.length()
	if dist < 1.0:
		hold()
		return
	var dir := to / dist
	if _steer_dir.length() > 0.1:
		dir = _steer_dir  # update_steering's way round (smallest turn off the goal that is clear)
	dir = (dir + _separation()).normalized()
	var top := float(unit.def.get("speed_m_s", 10.0))
	var v := minf(minf(speed, top), dist * 0.8)
	unit.move_goal = dir * v
	unit.face_dir = dir


## `goal` itself when it is near, there is no nav, or the unit walks a fixed route (a column has its own stops);
## else the waypoint a little way along the path to it, or `goal` when there is no path (straight at it, as before).
func _nav_goal(goal: Vector3) -> Vector3:
	var here := unit.global_position
	if nav == null or not _fixed_route.is_empty() or _flat(goal - here).length() < NAV_MIN_M:
		_path = PackedVector3Array()
		_bog_pos = Vector3.INF
		return goal
	var now := Time.get_ticks_msec()
	if now - _bog_ms > int(NAV_BOGGED_S * 1000.0):
		# Hardly moved along a path for NAV_BOGGED_S: what is ahead cannot be crossed (a crag the grid did
		# not show). Close that cell for everyone and find another way.
		if _bog_pos != Vector3.INF and not _path.is_empty() and _flat(here - _bog_pos).length() < NAV_BOGGED_M:
			var ahead := _flat(_path[mini(_path_i, _path.size() - 1)] - here).normalized()
			var step := LegionNav.CELL_M * 0.6
			nav.block(here.x + ahead.x * step, here.z + ahead.z * step)
			nav.block(here.x, here.z)  # and the ground it is stuck on
			bogged += 1
			_path = PackedVector3Array()
			if bogged >= 2 and unit.planted_count < 2:
				unit.shake_free()  # lying on a slope with nothing under its feet: hop off it
		_bog_pos = here
		_bog_ms = now
	if _path.is_empty() or _flat(goal - _path_goal).length() > 40.0 or now - _path_at_ms > int(NAV_REPLAN_S * 1000.0):
		_path = nav.path(here, goal)
		_path_i = 0
		_path_goal = goal
		_path_at_ms = now
	if _path.is_empty():
		return goal
	var closest := _path_i
	for k in range(_path_i, mini(_path_i + 6, _path.size())):
		if _flat(_path[k] - here).length() < _flat(_path[closest] - here).length():
			closest = k
	_path_i = closest
	while _path_i < _path.size() - 1 and _flat(_path[_path_i] - here).length() < NAV_PASSED_M:
		_path_i += 1
	return _path[mini(_path_i + NAV_LOOKAHEAD, _path.size() - 1)]


## Stuck (asked to walk, barely moving for ai.stuck_s): back away at an angle for ai.detour_s, so
## a unit does not grind into a wall or the foot of a cliff. True while backing off.
func _unstick(dt: float) -> bool:
	if _detour_s > 0.0:
		_detour_s -= dt
		unit.move_goal = _detour * float(ai.get("alert_speed_m_s", 6.0)) * 0.6
		unit.face_dir = -_detour if state == "attack" else _detour
		return true
	var asked := _flat(unit.move_goal).length()
	if asked > 2.0 and _flat(unit.linear_velocity).length() < asked * 0.25:
		_stuck_s += dt
	else:
		_stuck_s = maxf(_stuck_s - dt, 0.0)
	if _stuck_s > float(ai.get("stuck_s", 1.5)):
		_stuck_s = 0.0
		_detour_s = float(ai.get("detour_s", 2.0))
		var back := -_flat(unit.move_goal).normalized()
		_detour = back.rotated(Vector3.UP, deg_to_rad(60.0 if _rng.randf() < 0.5 else -60.0))
		return true
	return false


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
	var to := _flat(goal - unit.global_position)
	if to.length() < 2.0:
		_steer_dir = Vector3.ZERO
		return
	var dir := to.normalized()
	var look := clampf(unit.linear_velocity.length() * 1.5, float(ai.get("look_min_m", 20.0)), 30.0)
	look = minf(look, to.length())
	var from := unit.global_transform * unit.center_of_mass
	# A way round, once taken, is kept for ai.steer_hold_s while it stays clear (no dithering in
	# and out of a dead end it only sees the back of from inside).
	_steer_age += 1.0 / maxf(float(ai.get("think_hz", 5.0)), 0.5)
	if _steer_dir.length() > 0.1 and _steer_age < float(ai.get("steer_hold_s", 3.0)):
		if not _blocked(from, _steer_dir, look) and walkable_ahead(_steer_dir, look):
			return
	var was := _steer_dir
	_steer_dir = Vector3.ZERO
	var side := 1.0 if pack_index % 2 == 0 else -1.0
	for deg: float in [0.0, 25.0, -25.0, 50.0, -50.0, 80.0, -80.0, 120.0, -120.0]:
		var d := dir.rotated(Vector3.UP, deg_to_rad(deg * side))
		if not _blocked(from, d, look) and walkable_ahead(d, look):
			if deg != 0.0:
				_steer_dir = d
				if was.length() < 0.1 or absf(was.angle_to(d)) > 0.1:
					_steer_age = 0.0
			return
	# Walled in on every side it looked: back out the way it came rather than shove into it.
	_steer_dir = -dir
	_steer_age = 0.0


func _blocked(from: Vector3, dir: Vector3, length: float) -> bool:
	var q := PhysicsRayQueryParameters3D.create(from, from + dir * length, WORLD_MASK)
	var hit := unit.get_world_3d().direct_space_state.intersect_ray(q)
	return not hit.is_empty() and (hit["normal"] as Vector3).y < float(ai.get("steep_normal_y", 0.6))


## `at` moved inside the Legion area (a margin of the unit's own size inside it).
func in_area(at: Vector3) -> Vector3:
	if area_half_m == INF:
		return at
	var h := area_half_m - 6.0
	return Vector3(clampf(at.x, -h, h), at.y, clampf(at.z, -h, h))


## Whether the ground along flat `dir` for `length` m past the unit's nose is ground the legs can
## walk, along three tracks (the middle and each side's feet): probed every ai.probe_step_m with a
## ray from high above (so a roof or a wall top counts as ground that rises), no rise or drop between two
## probes, or over the body's length, steeper than gait.max_slope_deg plus one step of gait.step_up x hip height, no probe
## deeper under the water line than ai.max_wade_m, and no probe outside the Legion area.
func walkable_ahead(dir: Vector3, length: float) -> bool:
	var space := unit.get_world_3d().direct_space_state
	var g: Dictionary = unit.def.get("gait", {})
	var step := float(ai.get("probe_step_m", 1.5))
	var hip_h := 2.0
	var half_w := 1.0
	var half_l := 1.0
	for leg: Dictionary in unit.legs:
		hip_h = float(leg["height"])
		half_w = maxf(half_w, absf((leg["sole"] as Vector3).x) * 0.8)
		half_l = maxf(half_l, absf((leg["sole"] as Vector3).z))
	var tan_max := tan(deg_to_rad(float(g.get("max_slope_deg", 38.0)) - float(ai.get("slope_margin_deg", 0.0))))
	var lift := hip_h * float(g.get("step_up", 0.5))
	var side := dir.cross(Vector3.UP).normalized()
	# Over the body's length the legs take one step up at most, so a bank that rises a little at every probe
	# but more than that over a body length is as much a wall as one ledge (lane B5 part 6: the Löwe walked
	# into a 2-3 m bank on the big map that its feet could not hold, and stood there).
	var span := maxi(int(ceilf(half_l * 2.0 / step)), 1)
	for off: float in [0.0, -half_w, half_w]:
		var at := unit.global_position + side * off
		var ys: Array[float] = [_ground_y(space, at)]
		var ledge_at := -INF  # where along the track the last probe steeper than the slope limit was
		var d := step
		while d <= length + half_l + 0.01:
			var p := at + dir * d
			if area_half_m != INF and (absf(p.x) > area_half_m or absf(p.z) > area_half_m):
				return false
			var y := _ground_y(space, p)
			if y < water_y - float(ai.get("max_wade_m", 0.6)):
				return false
			if absf(y - ys[-1]) > step * tan_max + lift:  # a rise it cannot climb, or a drop it would fall off (a bridge edge)
				return false
			var back := mini(span, ys.size())
			if absf(y - ys[-back]) > step * back * tan_max + lift:
				return false
			if absf(y - ys[-1]) > step * tan_max:  # a ledge: one per body length, not one at every probe
				if d - ledge_at < half_l * 2.0:
					return false
				ledge_at = d
			ys.append(y)
			d += step
	return true


func _ground_y(space: PhysicsDirectSpaceState3D, at: Vector3) -> float:
	var q := PhysicsRayQueryParameters3D.create(Vector3(at.x, at.y + 80.0, at.z), Vector3(at.x, at.y - 80.0, at.z), WORLD_MASK)
	var hit := space.intersect_ray(q)
	return (hit["position"] as Vector3).y if not hit.is_empty() else at.y


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
		"goal": [snappedf(_goal.x, 0.1), snappedf(_goal.z, 0.1)],
		"route_i": _route_i,
		"bogged": bogged,
		"steer": [snappedf(_steer_dir.x, 0.01), snappedf(_steer_dir.z, 0.01)],
	}
