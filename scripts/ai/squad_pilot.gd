class_name SquadPilot
extends Node
## The pilot of an allied Juggernaut (lane A5). It drives through the same controls a player's hands do:
## a move stick (forward/back, sidestep), where to face (the body turns there under its own leg torque,
## like the mouse), sprint and the triggers. Nothing pushes the mech but its own legs and guns.
##
## Orders (from the Squad): "follow" keeps its formation slot beside the leader, "hold" stays where it was
## ordered, "move" walks to a point (the Handler view's click), "regroup" runs back in tight to the leader,
## "attack" closes on one Legion to a firing band. In every order it fights what it can see: it turns the
## body onto the nearest visible Legion inside engage_m and fires the 57 mm only when the bore line's real
## impact point (drop included) lands on that Legion and no friendly stands near the line.

const ORDERS := ["follow", "hold", "move", "regroup", "attack"]

var mech: RigidBody3D
var combat: Node
var squad: Node  # the Squad that owns it (its leader, the other members)
var id := ""
var entry: Dictionary = {}
var order := "follow"
var order_point := Vector3.ZERO  # "hold" and "move"
var order_target: Node3D = null  # "attack"
var target: Node3D = null  # the Legion it is fighting now
# What the hands are doing this tick (standin_mech._read_input reads these for a mech with a pilot):
var move := Vector2.ZERO  # x sidestep right, y forward, -1..1
var face_yaw := NAN  # the heading it wants the body on (radians, standin_mech's yaw); NAN: hold
var running := false
var pitch_deg := 0.0  # how far to tilt the body nose-up to bring the fixed 57 mm onto the target (drop included)
var brake := 0.0
var shots := 0

var _p: Dictionary = {}
var _think_left := 0.0
var _goal := Vector3.ZERO
var _rng := RandomNumberGenerator.new()
var _pitch_trim := 0.0


func setup(member_id: String, member: RigidBody3D, owner_squad: Node) -> void:
	id = member_id
	mech = member
	squad = owner_squad
	entry = Registry.entry("squad", member_id)
	_p = (Registry.file("squad").get("pilot", {}) as Dictionary).duplicate()
	if entry.has("engage_m"):
		_p["engage_m"] = entry["engage_m"]
	_rng.seed = hash(member_id)
	name = "Pilot"


func _ready() -> void:
	if mech == null:
		mech = get_parent() as RigidBody3D
	combat = mech.get_node_or_null("Combat")
	mech.set("pilot", self)
	_goal = mech.global_position


func give(kind: String, point: Variant = null, what: Node3D = null) -> void:
	if not kind in ORDERS:
		push_warning("SquadPilot: no order '%s'" % kind)
		return
	order = kind
	order_target = what
	if point is Vector3:
		order_point = point
	elif kind == "hold":
		order_point = mech.global_position
	_think_left = 0.0


func alive() -> bool:
	return mech != null and is_instance_valid(mech) and not (combat != null and combat.get("damage") != null and combat.damage.is_destroyed)


func _physics_process(delta: float) -> void:
	if not alive():
		move = Vector2.ZERO
		face_yaw = NAN
		running = false
		return
	_think_left -= delta
	if _think_left <= 0.0:
		_think_left += 1.0 / maxf(float(_p.get("think_hz", 5.0)), 0.5)
		_think()
	_steer()
	_shoot()


# --- deciding --------------------------------------------------------------------------------------


func _think() -> void:
	if order == "attack" and _legion_alive(order_target):
		target = order_target
	else:
		if order == "attack":
			order = "follow"  # its target is gone: back into formation
		target = _nearest_visible(float(_p.get("engage_m", 600.0)))
	_goal = goal()


## Where the order wants it to stand now (flat world point).
func goal() -> Vector3:
	var leader := _leader()
	match order:
		"hold", "move":
			return order_point
		"attack":
			if _legion_alive(order_target):
				var band: Array = _p.get("attack_band_m", [180.0, 420.0])
				var to := _flat(mech.global_position - order_target.global_position)
				var d := clampf(to.length(), float(band[0]), float(band[1]))
				return order_target.global_position + (to.normalized() if to.length() > 0.1 else Vector3.BACK) * d
	if leader == null:
		return mech.global_position
	var slot: Array = entry.get("slot", [0.0, 0.0, 15.0])
	var offset := Vector3(float(slot[0]), 0.0, float(slot[2]))
	if order == "regroup":
		offset *= float(_p.get("regroup_scale", 0.55))
	var yaw := Basis(Vector3.UP, _yaw(leader.global_transform.basis))
	return leader.global_position + yaw * offset


func _nearest_visible(range_m: float) -> Node3D:
	var best: Node3D = null
	var best_d := range_m
	for n: Node in get_tree().get_nodes_in_group("legion"):
		var u := n as Node3D
		if not _legion_alive(u):
			continue
		var d := mech.global_position.distance_to(u.global_position)
		if d < best_d and can_see(u):
			best = u
			best_d = d
	return best


## A clear line from the cockpit to the Legion's body (world geometry only, mechs do not block sight).
func can_see(u: Node3D) -> bool:
	var eye := mech.global_transform * Vector3(0.0, 1.0, -1.5)
	var at := _centre(u)
	var q := PhysicsRayQueryParameters3D.create(eye, at, 1)
	q.exclude = [mech.get_rid()]
	var hit := mech.get_world_3d().direct_space_state.intersect_ray(q)
	return hit.is_empty() or (hit["position"] as Vector3).distance_to(at) < 4.0


# --- driving ---------------------------------------------------------------------------------------


func _steer() -> void:
	var here := mech.global_position
	var to := _flat(_goal - here)
	var dist := to.length()
	var arrive := float(_p.get("arrive_m", 5.0))
	var want := Vector3.ZERO  # world direction and throttle, flat
	if dist > arrive:
		want = to / dist * clampf((dist - arrive) / maxf(float(_p.get("slow_m", 25.0)), 1.0), 0.15, 1.0)
	want += _keep_apart()
	want = want.limit_length(1.0)
	running = dist > float(_p.get("run_m", 45.0)) or order == "regroup" and dist > arrive * 3.0
	# The body faces what it fights; otherwise where it is going, or the leader's heading once in its slot.
	var face := Vector3.ZERO
	if target != null and _legion_alive(target):
		face = _flat(_centre(target) - here)
	elif want.length() > 0.2:
		face = want
	elif _leader() != null and order in ["follow", "regroup"]:
		face = -_leader().global_transform.basis.z
	face_yaw = atan2(-face.x, -face.z) if face.length() > 0.01 else NAN
	if target != null and _legion_alive(target):
		pitch_deg = _elevation()
	else:
		pitch_deg = 0.0
		_pitch_trim = move_toward(_pitch_trim, 0.0, get_physics_process_delta_time())
	# The move stick is in the body's own frame: y ahead, x to the right.
	var b := mech.global_transform.basis
	var fwd := _flat(-b.z)
	var right := _flat(b.x)
	move = Vector2(want.dot(right), want.dot(fwd)).limit_length(1.0)
	brake = 1.0 if dist <= arrive and mech.linear_velocity.length() > 3.0 and target == null else 0.0


## The bore elevation that puts a 57 mm round on the target's centre: the line of sight's angle plus the
## drop over the flight time (flat fire, so g t^2 / 2 over the range is close enough), plus a slow trim for
## how far the body's real gun line sits off the commanded tilt (the legs never tilt it exactly).
func _elevation() -> float:
	if combat == null or combat.get("gun") == null:
		return 0.0
	var muzzle: Vector3 = mech.global_transform * combat.muzzle_local()
	var to := _centre(target) - muzzle
	var flat := Vector2(to.x, to.z).length()
	var ammo: Dictionary = (combat.gun.def.get("ammo", {}) as Dictionary).get(combat.gun.loaded_ammo, {})
	var t := flat / maxf(float(ammo.get("muzzle_m_s", 1000.0)), 1.0)
	var want := rad_to_deg(atan2(to.y + 0.5 * 9.81 * t * t, flat))
	var dir: Vector3 = combat.gun_direction()
	var have := rad_to_deg(asin(clampf(dir.y, -1.0, 1.0)))
	# The legs tilt the body slowly (seconds), so the trim for its standing lean builds up slowly too.
	var dt := get_physics_process_delta_time()
	_pitch_trim = clampf(_pitch_trim + (want - have) * float(_p.get("pitch_trim_per_s", 0.6)) * dt, -8.0, 8.0)
	return want + _pitch_trim


## A push away from any other Juggernaut closer than keep_apart_m, so the squad does not walk into itself.
func _keep_apart() -> Vector3:
	var out := Vector3.ZERO
	var keep := float(_p.get("keep_apart_m", 14.0))
	for other: RigidBody3D in _friendlies():
		if other == mech:
			continue
		var away := _flat(mech.global_position - other.global_position)
		var d := away.length()
		if d < keep and d > 0.01:
			out += away / d * (1.0 - d / keep)
	return out


# --- shooting --------------------------------------------------------------------------------------


func _shoot() -> void:
	if combat == null:
		return
	if target == null or not _legion_alive(target):
		# Between fights it tops up a half-empty magazine (an empty one reloads by itself).
		if combat.get("gun") != null and combat.gun.magazine * 2 <= combat.gun.magazine_size:
			combat.gun.start_reload()
		return
	var d := mech.global_position.distance_to(target.global_position)
	if combat.get("gun") != null and combat.gun.can_fire() and d < float(_p.get("engage_m", 600.0)) and _on_target(combat.main_impact()):
		if combat.fire_main():
			shots += 1
	if combat.get("sub_guns") != null and d < float(_p.get("sub_engage_m", 350.0)) and _on_target(combat.sub_impact()):
		combat.fire_sub()


## Whether a gun's real impact point (combat.impact: the round's flight with drop) lands on the target,
## with no friendly Juggernaut standing near the line to it.
func _on_target(impact: Dictionary) -> bool:
	if impact.is_empty():
		return false
	var point: Vector3 = impact["point"]
	if point.distance_to(_centre(target)) > float(_p.get("hit_radius_m", 3.0)) + _radius(target):
		return false
	var from := mech.global_position
	var clear := float(_p.get("friendly_clear_m", 6.0))
	for other: RigidBody3D in _friendlies():
		if other == mech:
			continue
		var at := Geometry3D.get_closest_point_to_segment(other.global_position, from, point)
		if at.distance_to(other.global_position) < clear:
			return false
	return true


# --- helpers ---------------------------------------------------------------------------------------


func _leader() -> RigidBody3D:
	if squad != null and is_instance_valid(squad) and squad.get("leader") != null and is_instance_valid(squad.leader):
		return squad.leader
	return null


func _friendlies() -> Array:
	var out: Array = []
	for group: String in ["player_mech", "squad_mech"]:
		for n: Node in get_tree().get_nodes_in_group(group):
			if n is RigidBody3D:
				out.append(n)
	return out


static func _legion_alive(u: Node) -> bool:
	return u != null and is_instance_valid(u) and u.is_inside_tree() and not bool(u.get("dead"))


static func _centre(u: Node3D) -> Vector3:
	var body := u as RigidBody3D
	if body != null and body.center_of_mass_mode == RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM:
		return body.global_transform * body.center_of_mass
	return u.global_position


## A rough size for the "on target" test: the Legion's own size figure when it has one.
static func _radius(u: Node3D) -> float:
	var def: Variant = u.get("def")
	if def is Dictionary and (def as Dictionary).has("hit_radius_m"):
		return float(def["hit_radius_m"])
	return 2.0


static func _yaw(b: Basis) -> float:
	var f := -b.z
	return atan2(-f.x, -f.z)


static func _flat(v: Vector3) -> Vector3:
	return Vector3(v.x, 0.0, v.z)
