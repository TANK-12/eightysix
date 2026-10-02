class_name LegionMech
extends RigidBody3D
## A Legion unit (lane A4) built from its game export (lane B2, assets/models/legion/<id>.json + glb):
## rigid parts in a node tree, turned at their joints (hip yaw, hip pitch, knee per leg; turret, gun,
## launcher, head and blades). One rigid body whose mass, centre of mass and inertia are summed from
## the parts (physics supplement point 2). Parts that never move are its colliders; parts that ride a
## joint are hitboxes that follow the pose (point 1: no capsules). Every planted foot is a spring
## and damper from its hip to the ground, so the legs carry the body, and the drive and turn are
## forces through the feet capped by their grip (mu x the load they carry): nothing pushes the body
## that the feet could not. Part 4 (Emerson: "walking very broken", "they walk on cliffs"): each
## leg is an active-suspension actuator (the body's weight shared over the legs that are down, with
## the same stiffness whatever their number, capped at the leg's load limit), and a foot only lands
## on a foothold it could stand on: not steeper than gait.max_slope_deg, not above the hip's reach
## (gait.step_up), found by a ray from hip height so roofs and wall tops are out of reach. A leg with
## no foothold keeps its old one. A gait clock swings the legs in two alternating groups (a tripod
## for six legs, two sets of four for the Löwe's eight); the stride grows with speed up to the leg's
## reach (gait.step_m) and the cadence follows from it; each foot lands where the body will be half a
## stance later. Feel numbers are enemies.json "gait"; the brain (scripts/ai/) sets move_goal,
## face_dir and the aim.

signal stepped(leg: String)
signal hit_taken(key: String, dealt: float, info: Dictionary)
signal part_lost(key: String)
signal destroyed
signal fired(weapon: String, ammo: String)

const LAYER_WORLD := 1
const LAYER_MECH := 2
const LAYER_HITBOX := 4
const LAYER_DEBRIS := 16
const LEG_JOINTS := ["hip_yaw", "hip_pitch", "knee"]

var enemy_id := ""
var def: Dictionary = {}
var data: Dictionary = {}
var model: Node3D
var lite: Node3D  # the lite export shown past lod_m (null when there is none)
var legs: Array = []
var damage: DamageModel
var weapons: Dictionary = {}  # weapon id -> WeaponState
var is_player := false
var dead := false
## What the brain asks for: horizontal velocity (world, m/s), the way to face (world, flat) and
## the point the turret or launcher should aim at (null: rest).
var move_goal := Vector3.ZERO
var face_dir := Vector3.ZERO
var aim_point: Variant = null
var planted_count := 0
const FALL_MIN_AIR_S := 0.35
var _air_s := 0.0
var _fall_v := 0.0
var support_n := 0.0
var speed_scale := 1.0
## Weak-point effects: a lost optic narrows sight (brains read sight_scale); lost arms stop the guns.
var sight_scale := 1.0
var arms_ok := true

var _g: Dictionary = {}
var _rest: Dictionary = {}  # node name -> Transform3D (model space, rest)
var _nodes: Dictionary = {}  # node name -> Node3D
var _lite_nodes: Dictionary = {}  # node name -> Node3D in the lite model
var _joint_parent: Dictionary = {}  # joint part -> the joint part it rides on ("" = the body)
var _node_owner: Dictionary = {}  # glb node name -> the joint it follows
var _pose_dirty := false
var _parts: Dictionary = {}  # part name -> export part entry
var _joints: Dictionary = {}  # part name -> export joint entry
var _owner_of: Dictionary = {}  # part name -> part name of the joint it rides ("" = rigid with the body)
var _delta: Dictionary = {}  # joint part -> Transform3D (model-space motion from rest)
var _angle: Dictionary = {}  # joint part -> radians now
var _moving_boxes: Array = []  # [Area3D, joint part]: each joint's hitboxes
var _hit_areas: Dictionary = {}  # joint part -> Area3D holding the hitboxes that ride it
var _colliders: Dictionary = {}  # damage key -> [CollisionShape3D]
var _phase := 0.0
var _k := 0.0
var _c := 0.0
var _stride := 3.0  # the longest a foot travels under the body in one stance, m
var _leg_max_n := 0.0  # one leg's load limit, N
var _weak: Dictionary = {}  # damage key -> weak-point entry from enemies.json "damage.weak"
var _aim_joints: Dictionary = {}  # kind -> part name (turret_yaw, gun_pitch, launcher_yaw ...)
var _wreck_s := 0.0


static func model_data(enemy_def: Dictionary) -> Dictionary:
	var path := str(enemy_def.get("model", "")).get_basename() + ".json"
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}


static func can_build(enemy_id_: String) -> bool:
	if not Registry.has_entry("enemies", enemy_id_):
		return false
	var e := Registry.entry("enemies", enemy_id_)
	return ResourceLoader.exists(str(e.get("model", ""))) and not model_data(e).is_empty()


static func build(enemy_id_: String) -> LegionMech:
	if not can_build(enemy_id_):
		push_error("LegionMech: '%s' has no synced export (tools/sync_models.py legion)" % enemy_id_)
		return null
	var body := LegionMech.new()
	body.name = "Legion_" + enemy_id_
	body._setup(enemy_id_)
	return body


func _setup(id: String) -> void:
	enemy_id = id
	def = Registry.entry("enemies", id)
	data = model_data(def)
	_g = def.get("gait", {})
	collision_layer = LAYER_MECH
	collision_mask = LAYER_WORLD | LAYER_MECH | LAYER_DEBRIS
	can_sleep = false
	add_to_group("legion")
	add_to_group("mechs")
	set_meta("combat", self)
	linear_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
	linear_damp = 0.0
	angular_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
	angular_damp = 0.0
	var scene: PackedScene = load(str(def["model"]))
	model = scene.instantiate() as Node3D
	model.name = "Model"
	add_child(model)
	_index_nodes(model, Transform3D.IDENTITY, true)
	_add_lite_model()
	for p: Dictionary in data.get("parts", []):
		_parts[str(p["name"])] = p
	for j: Dictionary in data.get("joints", []):
		_joints[str(j["part"])] = j
		_delta[str(j["part"])] = Transform3D.IDENTITY
		_angle[str(j["part"])] = 0.0
		if not str(j["kind"]) in LEG_JOINTS:
			_aim_joints[str(j["kind"])] = str(j["part"])
	for name: String in _parts:
		_owner_of[name] = _joint_owner(name)
	_build_legs()
	_build_damage()
	_build_colliders()
	_build_mass()
	for w: String in def.get("weapons", []):
		if Registry.has_entry("weapons", w):
			weapons[w] = WeaponState.new(w, Registry.entry("weapons", w), true)
	var brain_path := "res://scripts/ai/%s.gd" % str(def.get("behaviour", ""))
	if ResourceLoader.exists(brain_path):
		var brain := Node.new()
		brain.set_script(load(brain_path))
		brain.name = "Brain"
		add_child(brain)


## Distance LOD: B2's lite export (same joints and node tree, a third of the meshes, so a third of
## the draw calls in every pass) shows past "lod_m" (enemies.json, default 150 m); the full model
## shows inside it. Both are posed by the same joints; sockets and colliders come from the full one.
func _add_lite_model() -> void:
	var path := str(def["model"]).get_basename() + "_lite.glb"
	var lod := float(def.get("lod_m", 150.0))
	if lod <= 0.0 or not ResourceLoader.exists(path):
		return
	lite = (load(path) as PackedScene).instantiate() as Node3D
	lite.name = "ModelLite"
	add_child(lite)
	for n: Node in lite.find_children("*", "Node3D", true, false):
		_lite_nodes[str(n.name)] = n
	set_lod(lod)


## Where the lite model takes over, metres (0: the full model at every distance).
func set_lod(metres: float) -> void:
	if lite == null:
		return
	for gi: Node in model.find_children("*", "GeometryInstance3D", true, false):
		(gi as GeometryInstance3D).visibility_range_end = metres
		(gi as GeometryInstance3D).visibility_range_end_margin = 10.0 if metres > 0.0 else 0.0
	lite.visible = metres > 0.0
	for gi: Node in lite.find_children("*", "GeometryInstance3D", true, false):
		(gi as GeometryInstance3D).visibility_range_begin = metres
		(gi as GeometryInstance3D).visibility_range_begin_margin = 10.0


func _index_nodes(n: Node, parent_xf: Transform3D, is_root: bool) -> void:
	var xf := parent_xf
	if n is Node3D and not is_root:
		xf = parent_xf * (n as Node3D).transform
		_rest[str(n.name)] = xf
		_nodes[str(n.name)] = n
	for c: Node in n.get_children():
		_index_nodes(c, xf, false)


## The joint part a part moves with: itself if it has a joint, else the nearest solid parent that does.
func _joint_owner(part: String) -> String:
	var p := part
	while p != "" and p != "None":
		if _joints.has(p):
			return p
		p = str(_parts.get(p, {}).get("parent", ""))
	return ""


static func _v(a: Variant) -> Vector3:
	var arr: Array = a
	return Vector3(float(arr[0]), float(arr[1]), float(arr[2]))


func _socket_rest(name: String) -> Vector3:
	for s: Dictionary in data.get("sockets", []):
		if str(s["name"]) == name:
			return _v(s["pos"])
	return Vector3.ZERO


# --- build -------------------------------------------------------------------------------------


func _build_legs() -> void:
	var side_order: Dictionary = {}
	for tag: String in data.get("legs", {}):
		var leg_def: Dictionary = data["legs"][tag]
		var chain: Array = leg_def["chain"]
		var hip := str(chain[0]["part"])
		var thigh := str(chain[1]["part"])
		var shin := str(chain[2]["part"])
		var p0 := _v(_joints[hip]["pivot"])
		var p1 := _v(_joints[thigh]["pivot"])
		var p2 := _v(_joints[shin]["pivot"])
		var axis := _v(_joints[thigh]["axis"]).normalized()
		var sole := _socket_rest(str(leg_def["sole_socket"]))
		var leg := {
			"tag": tag,
			"hip": hip,
			"thigh": thigh,
			"shin": shin,
			"p0": p0,
			"p1": p1,
			"p2": p2,
			"axis": axis,
			"sole": sole,
			"l1": p1.distance_to(p2),
			"l2": _plane(sole - p2, axis).length(),
			"k": (sole - p1).dot(axis),
			"height": p0.y - sole.y,
			"side": signf(sole.x),
			"planted": Vector3.ZERO,
			"foot": Vector3.ZERO,
			"swing_t": -1.0,
			"from": Vector3.ZERO,
			"to": Vector3.ZERO,
			"down": false,
			"group": 0,
		}
		legs.append(leg)
		var side := "R" if sole.x > 0.0 else "L"
		if not side_order.has(side):
			side_order[side] = []
		(side_order[side] as Array).append(leg)
	# Two alternating groups: along each side front to back, and the two sides out of step, so a
	# six-legged unit walks on tripods and the Löwe on two sets of four.
	for side: String in side_order:
		var list: Array = side_order[side]
		list.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return (a["sole"] as Vector3).z < (b["sole"] as Vector3).z)
		for i in list.size():
			(list[i] as Dictionary)["group"] = (i + (0 if side == "R" else 1)) % 2
	var reach := 0.0
	for leg: Dictionary in legs:
		reach += Vector2((leg["sole"] as Vector3).x - (leg["p0"] as Vector3).x, (leg["sole"] as Vector3).z - (leg["p0"] as Vector3).z).length()
	reach /= maxf(legs.size(), 1)
	_stride = float(_g.get("step_m", reach * 0.9))


static func _plane(v: Vector3, n: Vector3) -> Vector3:
	return v - n * v.dot(n)


## Damage zones (keys on the colliders): "hull" (the core: lost = destroyed), "leg_<tag>" per leg,
## "arms" for the guns, and one per weak point from the export ("wp_<name>"), each with its share of
## the unit's health and its armour from enemies.json "damage". A weak point can pass a share of
## what it takes on to the hull ("to_hull"): the way in past the thick plates.
func _build_damage() -> void:
	var dmg_cfg: Dictionary = def.get("damage", {})
	var tune: Dictionary = Registry.tune("damage", {}).duplicate()
	tune["legs_lost_to_destroy"] = int(dmg_cfg.get("legs_lost_to_destroy", ceili(legs.size() / 2.0)))
	tune["repair_delay_s"] = INF
	damage = DamageModel.new({}, tune)
	var health := float(def.get("health", 1000.0))
	var armour := float(def.get("armour_mm", 10.0))
	damage.add_part("hull", def.get("label", enemy_id) + " hull", "core", health, armour)
	var leg_cfg: Dictionary = dmg_cfg.get("leg", {})
	for leg: Dictionary in legs:
		var key := "leg_" + str(leg["tag"])
		damage.add_part(key, "leg " + str(leg["tag"]), "leg", health * float(leg_cfg.get("share", 0.3)), float(leg_cfg.get("armour_mm", armour * 0.5)), str(leg["tag"]))
		damage.legs[str(leg["tag"])] = [key]
	var arm_cfg: Dictionary = dmg_cfg.get("arms", {})
	damage.add_part("arms", "weapons", "weapon", health * float(arm_cfg.get("share", 0.2)), float(arm_cfg.get("armour_mm", armour * 0.5)))
	var weak_cfg: Dictionary = dmg_cfg.get("weak", {})
	for wp: String in data.get("weak_points", {}):
		var cfg: Dictionary = weak_cfg.get(wp, {})
		var key := "wp_" + wp
		damage.add_part(key, wp.replace("_", " "), "weak", health * float(cfg.get("share", 0.2)), float(cfg.get("armour_mm", armour * 0.5)))
		_weak[key] = cfg
	damage.part_lost.connect(_on_part_lost)
	damage.destroyed.connect(_on_destroyed)


## The damage key a part's collider carries.
func zone_of(part: String) -> String:
	for wp: String in data.get("weak_points", {}):
		if part in (data["weak_points"][wp] as Array):
			if wp == "leg_joints":
				var tag := _leg_tag_of(part)
				return "knee_" + tag if damage.has("knee_" + tag) else "wp_leg_joints"
			return "wp_" + wp
	var p: Dictionary = _parts.get(part, {})
	if str(p.get("class", "")) == "leg":
		var tag := _leg_tag_of(part)
		if tag != "":
			return "leg_" + tag
	if str(p.get("class", "")) == "weapon":
		return "arms"
	return "hull"


func _leg_tag_of(part: String) -> String:
	var p := part
	while p != "" and p != "None":
		for leg: Dictionary in legs:
			if p == leg["hip"]:
				return str(leg["tag"])
		p = str(_parts.get(p, {}).get("parent", ""))
	return ""


func _build_colliders() -> void:
	# Knee weak points per leg (each leg's knee is its own key so it also cripples that leg).
	if data.get("weak_points", {}).has("leg_joints"):
		var cfg: Dictionary = _weak.get("wp_leg_joints", {})
		var health := float(def.get("health", 1000.0))
		for leg: Dictionary in legs:
			var key := "knee_" + str(leg["tag"])
			damage.add_part(key, "knee " + str(leg["tag"]), "weak", health * float(cfg.get("share", 0.15)), float(cfg.get("armour_mm", 4.0)), str(leg["tag"]))
			(damage.legs[str(leg["tag"])] as Array).append(key)
			_weak[key] = cfg
	# Jointed parts are hitboxes in one Area3D per joint, moved as one with the joint each tick
	# (moving each shape on its own cost the Löwe 95 shape moves a tick: most of the Legion's CPU).
	var boxes := Node3D.new()
	boxes.name = "Hitboxes"
	add_child(boxes)
	for name: String in _parts:
		var p: Dictionary = _parts[name]
		if not bool(p.get("collider", false)) or (p.get("hull", []) as Array).size() < 4:
			continue
		var pts := PackedVector3Array()
		for h: Array in p["hull"]:
			pts.append(Vector3(float(h[0]), float(h[1]), float(h[2])))
		var shape := ConvexPolygonShape3D.new()
		shape.points = pts
		var cs := CollisionShape3D.new()
		cs.shape = shape
		cs.name = "Collider_" + name
		var key := zone_of(name)
		cs.set_meta("damage_key", key)
		cs.set_meta("part_id", name)
		var owner_joint := str(_owner_of[name])
		if owner_joint == "":
			add_child(cs)
		else:
			if not _hit_areas.has(owner_joint):
				var area := Area3D.new()
				area.name = "Hitbox_" + owner_joint
				area.collision_layer = LAYER_HITBOX
				area.collision_mask = 0
				area.monitoring = false
				area.monitorable = false
				boxes.add_child(area)
				_hit_areas[owner_joint] = area
				_moving_boxes.append([area, owner_joint])
			(_hit_areas[owner_joint] as Area3D).add_child(cs)
		if not _colliders.has(key):
			_colliders[key] = []
		(_colliders[key] as Array).append(cs)


func _build_mass() -> void:
	var pieces: Array = []
	for p: Dictionary in data.get("parts", []):
		var size := Vector3.ZERO
		var hull: Array = p.get("hull", [])
		if hull.size() >= 4:
			var box := AABB(_v(hull[0]), Vector3.ZERO)
			for h: Array in hull:
				box = box.expand(_v(h))
			size = box.size
		pieces.append({"mass": float(p.get("mass_kg", 0.0)), "position": _v(p.get("com", [0, 0, 0])), "size": size})
	var info := MechMass.sum(pieces)
	mass = float(info["mass"])
	center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	center_of_mass = info["com"]
	inertia = info["inertia"]
	# The whole body's stiffness: it bobs at gait.bounce_hz however many legs are down (each planted
	# leg takes k / n), and one leg can carry gait.leg_max_load body weights at most.
	var w := TAU * float(_g.get("bounce_hz", 1.4))
	_k = mass * w * w
	_c = 2.0 * float(_g.get("damping_ratio", 0.7)) * sqrt(_k * mass)
	_leg_max_n = mass * 9.81 * float(_g.get("leg_max_load", 0.9))


# --- each tick ----------------------------------------------------------------------------------


func _ready() -> void:
	for leg: Dictionary in legs:
		var at := global_transform * (leg["sole"] as Vector3)
		var hold: Variant = foothold(leg, at, at.y)
		leg["planted"] = hold if hold != null else _ground_below(at, at)
		leg["foot"] = leg["planted"]
		leg["down"] = true
		leg["ok"] = hold != null
	_pose()


func _physics_process(delta: float) -> void:
	for w: WeaponState in weapons.values():
		w.tick(delta)
	if dead:
		_wreck_s += delta
		return
	_track_fall(delta)
	_step_gait(delta)
	_pose()


## A long fall hurts (lane B5 part 3, a bridge span dropping under a column): while no foot is planted the
## fastest downward speed is kept; landing on two or more feet after more than FALL_MIN_AIR_S in the air costs
## hull, def "fall".hull_per_m_s of the unit's health for every m/s over "fall".safe_m_s (default 9, about a
## 4 m drop; 0.1 per m/s, so 15 m/s from a 12 m drop takes about 60 %).
func _track_fall(delta: float) -> void:
	if planted_count == 0:
		_air_s += delta
		_fall_v = minf(_fall_v, linear_velocity.y)
		return
	var speed := -_fall_v
	var air := _air_s
	_air_s = 0.0
	_fall_v = 0.0
	var cfg: Dictionary = def.get("fall", {})
	var over := speed - float(cfg.get("safe_m_s", 9.0))
	if air > FALL_MIN_AIR_S and planted_count >= 2 and over > 0.0:
		var amount := float(def.get("health", 1500.0)) * float(cfg.get("hull_per_m_s", 0.1)) * over
		take_hit({"key": "hull", "damage": amount, "penetration_mm": 100000.0, "splash": true, "point": global_position})


func _integrate_forces(state: PhysicsDirectBodyState3D) -> void:
	if dead:
		planted_count = 0
		support_n = 0.0
		return
	var xf := state.transform
	var com := xf.basis * center_of_mass
	planted_count = 0
	support_n = 0.0
	var lever := 0.0
	# Which legs stand on a foothold within reach: each carries its share of the weight plus k / n
	# and c / n of the body's spring, so the bob and the load stay the same with 2 legs down or 6.
	var standing: Array = []
	for leg: Dictionary in legs:
		if not bool(leg["down"]) or not bool(leg.get("ok", true)):
			continue
		var hip_w := xf * (leg["p0"] as Vector3)
		var reach := float(leg["l1"]) + float(leg["l2"]) + 0.3
		if hip_w.distance_to(leg["planted"] as Vector3) <= reach:
			standing.append(leg)
	var n := maxf(standing.size(), 1.0)
	var weight := mass * state.total_gravity.length()
	# Levelling (an attitude sensor in the suspension): each hip aims at the standing feet's mean
	# height plus its ride height, gait.level of the way from its own foot's, so a bump under one
	# foot does not tip the body and the body still follows a hill by the rest.
	# A hip higher or lower than the standing hips' mean (the body rolling or pitching) is pushed
	# back gait.attitude_gain times as hard as the whole body's bob: the narrow-hipped Ameise needs it.
	var ground_y := 0.0
	var hips_y := 0.0
	for leg: Dictionary in standing:
		ground_y += (leg["planted"] as Vector3).y / n
		hips_y += (xf * (leg["p0"] as Vector3)).y / n
	var level := float(_g.get("level", 0.7))
	var attitude := float(_g.get("attitude_gain", 2.0))
	for leg: Dictionary in standing:
		var hip_w := xf * (leg["p0"] as Vector3)
		var foot: Vector3 = leg["planted"]
		var rest_h := float(leg["height"]) * float(_g.get("ride", 1.0))
		var hip_y := hips_y + (hip_w.y - hips_y) * attitude
		var squeeze := rest_h - (hip_y - lerpf(foot.y, ground_y, level))
		if squeeze < -rest_h * 0.35:
			continue  # the foot is far below the hip: the leg hangs at full stretch and carries nothing
		var hip_v := state.get_velocity_at_local_position(hip_w - xf.origin)
		var f := clampf(weight / n + (_k * squeeze - _c * hip_v.y) / n, 0.0, _leg_max_n)
		if f <= 0.0:
			continue
		state.apply_force(Vector3.UP * f, hip_w - xf.origin)
		planted_count += 1
		support_n += f
		lever += Vector2(hip_w.x - xf.origin.x, hip_w.z - xf.origin.z).length()
	_keel(state)
	if planted_count == 0:
		return
	lever /= planted_count
	var mu := float(_g.get("grip", 0.7))
	# Walking needs the stepping legs: with fewer than half its legs on footholds (the rest on a
	# wall or a cliff face) a unit pushes with that share of its grip, so it cannot shove its hull
	# up a wall on one leg.
	var grip := mu * support_n * clampf(float(planted_count) / maxf(legs.size() * 0.5, 1.0), 0.0, 1.0)
	if planted_count < 2:
		grip = 0.0  # one leg cannot walk
	var v := state.linear_velocity
	var goal := move_goal * speed_scale
	var want := Vector3(goal.x - v.x, 0.0, goal.z - v.z) * mass / maxf(float(_g.get("drive_s", 0.4)), 0.05)
	if want.length() > grip:
		want = want.normalized() * grip
	state.apply_force(want, com)
	# Turn toward face_dir through the feet; also damp spin about the vertical.
	var fwd := -xf.basis.z
	var yaw_err := 0.0
	if face_dir.length() > 0.1:
		yaw_err = Vector2(fwd.x, fwd.z).angle_to(Vector2(face_dir.x, face_dir.z))
	var max_w := deg_to_rad(float(def.get("turn_deg_s", 90.0)))
	var w_goal := clampf(-yaw_err * float(_g.get("turn_gain", 4.0)), -max_w, max_w)
	var iy := inertia.y
	var torque := iy * (w_goal - state.angular_velocity.y) / maxf(float(_g.get("turn_s", 0.25)), 0.05)
	torque = clampf(torque, -grip * lever, grip * lever)
	state.apply_torque(Vector3.UP * torque)


## Upright keel (lane B5 part 3; the Juggernaut has one in game mode): past gait.keep_deg of lean from the ground
## under it (world up with under two feet down) a righting torque grows with the lean, capped, and the tilting spin
## is damped. None in flight (nothing to push against), so a falling unit tumbles as it fell. Without it the Legion
## rolled on the big map's hills and lay on their backs for minutes.
func _keel(state: PhysicsDirectBodyState3D) -> void:
	var keep := deg_to_rad(float(_g.get("keep_deg", 40.0)))
	var v := state.linear_velocity
	var up := state.transform.basis.y
	var target := Vector3.UP
	if planted_count >= 2:
		var from := state.transform.origin + Vector3.UP * 0.5
		var q := PhysicsRayQueryParameters3D.create(from, from + Vector3.DOWN * 12.0, 1)
		var hit := state.get_space_state().intersect_ray(q)
		if not hit.is_empty():
			target = hit["normal"]
	elif v.length() > 3.0 or absf(v.y) > 2.0:
		return
	var lean := up.angle_to(target)
	if lean <= keep:
		return
	var axis := up.cross(target)
	if axis.length() < 0.0001:
		axis = state.transform.basis.z  # exactly upside down: roll about the nose
	var push := float(_g.get("keep_stiffness", 20.0)) * minf((lean - keep) / keep, 3.0)
	var w := state.angular_velocity
	var spin := w - up * w.dot(up)
	var accel := axis.normalized() * push - spin * float(_g.get("keep_damping", 4.0))
	state.apply_torque(accel * inertia.x)


func _step_gait(dt: float) -> void:
	var xf := global_transform
	var v := linear_velocity
	var vh := Vector3(v.x, 0.0, v.z)
	# Walking duty at low speed, running duty from gait.run_m_s; the cadence is the one that keeps
	# each stance within the leg's reach (stance length = speed x duty / cadence <= step_m).
	var run := smoothstep(0.0, float(_g.get("run_m_s", 10.0)), vh.length())
	var duty := lerpf(float(_g.get("duty", 0.6)), float(_g.get("duty_run", 0.5)), run)
	var max_hz := float(_g.get("max_cadence_hz", 3.0))
	var spin := absf(angular_velocity.y)
	var need := (vh.length() + spin * 2.0) * duty / maxf(_stride, 0.1)
	var settle := 0.0
	for leg: Dictionary in legs:
		var home := _home(leg, xf, vh, 0.0)
		if Vector2(home.x - (leg["planted"] as Vector3).x, home.z - (leg["planted"] as Vector3).z).length() > _stride * 0.18:
			settle = float(_g.get("settle_hz", 1.6))
	var hz := clampf(maxf(need, settle), 0.0, max_hz)
	var before := _phase
	_phase = fposmod(_phase + hz * dt, 1.0)
	var stance_s := duty / maxf(hz, 0.5)
	var swing_s := (1.0 - duty) / maxf(hz, 0.5)
	for leg: Dictionary in legs:
		var start := 0.0 if int(leg["group"]) == 0 else 0.5
		var window := 1.0 - duty
		var swinging := float(leg["swing_t"]) >= 0.0
		if not swinging and hz > 0.0 and _crossed(before, _phase, start) and _leg_alive(leg):
			leg["swing_t"] = 0.0
			leg["from"] = leg["planted"]
			leg["down"] = false
			swinging = true
		if swinging:
			var t := float(leg["swing_t"]) + dt / maxf(swing_s, 0.05)
			leg["swing_t"] = t
			# Aim the landing at where the hip will be half a stance from now.
			var home := _home(leg, xf, vh, stance_s * 0.5 + swing_s * (1.0 - minf(t, 1.0)))
			leg["to"] = home
			var s := smoothstep(0.0, 1.0, minf(t, 1.0))
			var lift := float(_g.get("lift_m", 0.6)) * clampf(vh.length() / 4.0 + 0.4, 0.4, 1.0)
			leg["foot"] = (leg["from"] as Vector3).lerp(home, s) + Vector3.UP * sin(s * PI) * lift
			if t >= 1.0 or (window <= 0.0):
				# Land on the nearest foothold it could stand on along the way back to where it
				# lifted; none (a cliff face, a wall): it touches down where it was going but
				# carries nothing and grips nothing there, and tries again next step.
				var hold: Variant = null
				for f: float in [1.0, 0.7, 0.4]:
					hold = foothold(leg, (leg["from"] as Vector3).lerp(home, f), (leg["from"] as Vector3).y)
					if hold != null:
						break
				leg["ok"] = hold != null
				leg["planted"] = hold if hold != null else _ground_below(home, home)
				leg["foot"] = leg["planted"]
				leg["swing_t"] = -1.0
				leg["down"] = true
				stepped.emit(str(leg["tag"]))
		else:
			leg["foot"] = leg["planted"]


static func _crossed(a: float, b: float, mark: float) -> bool:
	if b >= a:
		return a < mark and b >= mark or (a == 0.0 and mark == 0.0 and b > 0.0)
	return mark > a or mark <= b


func _leg_alive(leg: Dictionary) -> bool:
	return damage.leg_health(str(leg["tag"])) > 0.0


## Where a leg's foot belongs `ahead_s` from now: its rest spot under the body, carried along by the
## body's velocity and spin. Laid out by the heading alone: a body that leans must not place its
## feet where they keep it leaning.
func _home(leg: Dictionary, xf: Transform3D, vh: Vector3, ahead_s: float) -> Vector3:
	var spread := float(_g.get("spread", 1.0))
	var sole: Vector3 = leg["sole"]
	var rest := Vector3(sole.x * spread, sole.y, sole.z)
	var turn := Basis(Vector3.UP, angular_velocity.y * ahead_s)
	var fwd := -xf.basis.z
	var heading := Basis(Vector3.UP, atan2(-fwd.x, -fwd.z))
	var at := xf.origin + turn * (heading * rest) + vh * ahead_s
	return Vector3(at.x, (leg["planted"] as Vector3).y, at.z)


## Where leg `leg`'s foot could stand near `at` (world), or null: the ground straight down from the
## hip's height (so nothing above the hip: roofs, wall tops, a cliff's rim), no steeper than
## gait.max_slope_deg across the foot's footprint, and no higher than gait.step_up x the hip height above `from_y` (where the
## foot lifted from).
func foothold(leg: Dictionary, at: Vector3, from_y: float) -> Variant:
	if not is_inside_tree():
		return null
	var hip_w := global_transform * (leg["p0"] as Vector3)
	var rest_h := float(leg["height"])
	var top := minf(hip_w.y - rest_h * 0.15, from_y + rest_h * float(_g.get("step_up", 0.5)))
	var q := PhysicsRayQueryParameters3D.create(Vector3(at.x, hip_w.y, at.z), Vector3(at.x, hip_w.y - rest_h * 3.0, at.z), LAYER_WORLD)
	q.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		return null
	var p: Vector3 = hit["position"]
	if p.y > top:
		return null
	# The slope across the foot's footprint (gait.foot_m either way), not one small bump's face.
	var r := float(_g.get("foot_m", 0.8))
	var h := func(dx: float, dz: float) -> float:
		# From well above the foot: a face rising beside it counts, even where it overhangs the hip.
		var y0 := maxf(hip_w.y, p.y + rest_h * 2.0)
		var qq := PhysicsRayQueryParameters3D.create(Vector3(p.x + dx, y0, p.z + dz), Vector3(p.x + dx, p.y - rest_h * 2.0, p.z + dz), LAYER_WORLD)
		qq.exclude = [get_rid()]
		var hh := get_world_3d().direct_space_state.intersect_ray(qq)
		return (hh["position"] as Vector3).y if not hh.is_empty() else p.y
	# The steeper side each way, so the toe of a cliff (flat on one side) still reads as the cliff.
	var gx := maxf(absf(float(h.call(r, 0.0)) - p.y), absf(p.y - float(h.call(-r, 0.0)))) / r
	var gz := maxf(absf(float(h.call(0.0, r)) - p.y), absf(p.y - float(h.call(0.0, -r)))) / r
	if Vector2(gx, gz).length() > tan(deg_to_rad(float(_g.get("max_slope_deg", 38.0)))):
		return null
	return p


func _ground_below(at: Vector3, fallback: Vector3) -> Vector3:
	if not is_inside_tree():
		return fallback
	var space := get_world_3d().direct_space_state
	var hip_y := global_position.y + 2.0
	var q := PhysicsRayQueryParameters3D.create(Vector3(at.x, hip_y, at.z), Vector3(at.x, hip_y - 14.0, at.z), LAYER_WORLD)
	q.exclude = [get_rid()]
	var hit := space.intersect_ray(q)
	return hit["position"] if not hit.is_empty() else Vector3(at.x, global_position.y, at.z)


# --- pose: leg IK and aim joints, then the moving hitboxes follow -------------------------------------


func _pose() -> void:
	var inv := global_transform.affine_inverse()
	for leg: Dictionary in legs:
		if dead:
			continue
		_solve_leg(leg, inv * (leg["foot"] as Vector3))
	_aim_joints_toward(get_physics_process_delta_time())
	for part: String in _joints:
		_apply_joint(part)
	_pose_dirty = true
	for pair: Array in _moving_boxes:
		(pair[0] as Area3D).transform = _delta_of(str(pair[1]))


## Hip yaw about the body's up, then hip pitch and knee in the leg's plane (both about the thigh
## axis), so the sole lands on `t` (model space). The sole's fixed offset along the pitch axis (k)
## is kept by choosing the yaw that puts the target at that offset.
func _solve_leg(leg: Dictionary, t: Vector3) -> void:
	var p0: Vector3 = leg["p0"]
	var axis: Vector3 = leg["axis"]
	var k := float(leg["k"])
	var v := t - p0
	var vh := Vector2(v.x, v.z)
	var ah := Vector2(axis.x, axis.z)
	var yaw := 0.0
	if vh.length() > absf(k) + 0.01:
		# Want (rotated axis) . v == k: angle between them = acos(k / |vh|), on the rest side.
		var base := ah.angle_to(vh)
		var off := acos(clampf(k / vh.length(), -1.0, 1.0))
		var a1 := base - off
		var a2 := base + off
		yaw = -(a1 if absf(wrapf(a1, -PI, PI)) < absf(wrapf(a2, -PI, PI)) else a2)
		yaw = wrapf(yaw, -PI, PI)
	var ry := Basis(Vector3.UP, yaw)
	var ax := ry * axis
	var p1 := p0 + ry * ((leg["p1"] as Vector3) - p0)
	var p2 := p0 + ry * ((leg["p2"] as Vector3) - p0)
	var sole := p0 + ry * ((leg["sole"] as Vector3) - p0)
	var u1 := p2 - p1
	var l1 := u1.length()
	var e1 := u1 / maxf(l1, 0.001)
	var e2 := ax.cross(e1)
	var w := _plane(sole - p2, ax)
	var l2 := w.length()
	var beta0 := atan2(w.dot(e2), w.dot(e1))
	var tp := _plane(t - p1, ax)
	var d := clampf(tp.length(), absf(l1 - l2) + 0.01, l1 + l2 - 0.01)
	var inner := acos(clampf((l1 * l1 + l2 * l2 - d * d) / (2.0 * l1 * l2), -1.0, 1.0))
	var sigma := signf(beta0) if beta0 != 0.0 else 1.0
	var beta := sigma * (PI - inner)
	var knee := beta - beta0
	var reach := Vector2(l1 + l2 * cos(beta), l2 * sin(beta))
	var want := Vector2(tp.dot(e1), tp.dot(e2))
	var hip := want.angle() - reach.angle()
	_angle[leg["hip"]] = yaw
	_angle[leg["thigh"]] = hip
	_angle[leg["shin"]] = knee


## Turret / launcher yaw and gun / launcher pitch toward aim_point at the joint's rate limit
## (gait.aim_deg_s); the blades and head stay at rest unless a brain sets them.
func _aim_joints_toward(dt: float) -> void:
	var rate := deg_to_rad(float(_g.get("aim_deg_s", 40.0))) * dt
	var target: Variant = aim_point
	for kind: String in ["turret_yaw", "launcher_yaw"]:
		if not _aim_joints.has(kind):
			continue
		var part: String = _aim_joints[kind]
		var want := 0.0
		if target != null:
			var local := global_transform.affine_inverse() * (target as Vector3)
			var pivot := _v(_joints[part]["pivot"])
			var d := local - pivot
			want = atan2(-d.x, -d.z)
		_angle[part] = _approach_angle(float(_angle[part]), want, rate)
	for kind: String in ["gun_pitch", "launcher_pitch"]:
		if not _aim_joints.has(kind):
			continue
		var part: String = _aim_joints[kind]
		var want := float(_g.get(kind + "_rest_deg", 0.0)) * PI / 180.0
		if target != null:
			var yaw_part: String = _aim_joints.get("turret_yaw" if kind == "gun_pitch" else "launcher_yaw", "")
			var yaw := float(_angle.get(yaw_part, 0.0))
			var local := global_transform.affine_inverse() * (target as Vector3)
			var pivot := _v(_joints[part]["pivot"])
			var d := Basis(Vector3.UP, -yaw) * (local - pivot)
			want = atan2(d.y, -d.z) + deg_to_rad(float(_g.get(kind + "_lead_deg", 0.0)))
		var lo := deg_to_rad(float(_g.get(kind + "_min_deg", -10.0)))
		var hi := deg_to_rad(float(_g.get(kind + "_max_deg", 30.0)))
		_angle[part] = clampf(_approach_angle(float(_angle[part]), want, rate * 1.5), lo, hi)


static func _approach_angle(now: float, want: float, step: float) -> float:
	var diff := wrapf(want - now, -PI, PI)
	return now + clampf(diff, -step, step)


## How far the turret (or launcher) still has to swing to bear on aim_point, radians (0 when none).
func aim_error() -> float:
	if aim_point == null:
		return PI
	for kind: String in ["turret_yaw", "launcher_yaw"]:
		if _aim_joints.has(kind):
			var part: String = _aim_joints[kind]
			var local := global_transform.affine_inverse() * (aim_point as Vector3)
			var d := local - _v(_joints[part]["pivot"])
			return absf(wrapf(atan2(-d.x, -d.z) - float(_angle[part]), -PI, PI))
	var to := (aim_point as Vector3) - global_position
	var fwd := -global_transform.basis.z
	return absf(Vector2(fwd.x, fwd.z).angle_to(Vector2(to.x, to.z)))


func _delta_of(part: String) -> Transform3D:
	return _delta.get(part, Transform3D.IDENTITY) if part != "" else Transform3D.IDENTITY


func _apply_joint(part: String) -> void:
	var j: Dictionary = _joints[part]
	if not _joint_parent.has(part):
		_joint_parent[part] = _joint_owner(str(_parts.get(part, {}).get("parent", "")))
	var pivot := _v(j["pivot"])
	var local := Transform3D(Basis(_v(j["axis"]).normalized(), float(_angle[part])), Vector3.ZERO)
	var about := Transform3D(Basis.IDENTITY, pivot) * local * Transform3D(Basis.IDENTITY, -pivot)
	_delta[part] = _delta_of(str(_joint_parent[part])) * about


## Writes the joints' pose onto the model's nodes and the lite twin. Only the eye needs it, so it
## runs once per drawn frame (each write moves every mesh under that node); the hitboxes follow
## _delta every physics tick. Profiled: posing the nodes at 120 Hz cost most of the Legion's CPU.
func _write_pose() -> void:
	for part: String in _joints:
		var node: Node3D = _nodes.get(part)
		if node == null:
			continue
		var parent_node := node.get_parent() as Node3D
		var parent_posed := Transform3D.IDENTITY
		if parent_node != null and parent_node != model:
			var pn := str(parent_node.name)
			if not _node_owner.has(pn):
				_node_owner[pn] = _owner_for_node(parent_node)
			parent_posed = _delta_of(str(_node_owner[pn])) * (_rest[pn] as Transform3D)
		node.transform = parent_posed.affine_inverse() * (_delta[part] as Transform3D) * (_rest[part] as Transform3D)
		var twin: Node3D = _lite_nodes.get(part)
		if twin != null:
			twin.transform = node.transform


func _process(_delta_s: float) -> void:
	if _pose_dirty:
		_pose_dirty = false
		_write_pose()


## The joint whose motion a glb node follows (the nearest export part up its tree, then that part's joint).
func _owner_for_node(n: Node) -> String:
	var at := n
	while at != null and at != model:
		var nm := str(at.name)
		if _parts.has(nm):
			return str(_owner_of[nm])
		at = at.get_parent()
	return ""


## A socket's world transform (glb node "socket_<name>"), following the pose.
func socket(name: String) -> Transform3D:
	var n: Node3D = _nodes.get("socket_" + name)
	if n != null and n.is_inside_tree():
		return n.global_transform
	return global_transform * Transform3D(Basis.IDENTITY, _socket_rest(name))


func socket_names(prefix: String) -> PackedStringArray:
	var out := PackedStringArray()
	for s: Dictionary in data.get("sockets", []):
		if str(s["name"]).begins_with(prefix):
			out.append(str(s["name"]))
	return out


## Where a leg's sole is now (world), from the posed glb socket: the IK check uses it.
func sole_world(leg: Dictionary) -> Vector3:
	var sock := str(data["legs"][leg["tag"]]["sole_socket"])
	return socket(sock).origin


# --- weapons ------------------------------------------------------------------------------------


## Fires `weapon_id` from the socket at `muzzle` along `dir` with `spread_mrad` of random error.
## Returns the round, or null when the weapon cannot fire this tick.
func fire(weapon_id: String, muzzle: Transform3D, dir: Vector3, spread_mrad: float = 0.0) -> Projectile:
	if dead or not arms_ok or not weapons.has(weapon_id):
		return null
	var ws: WeaponState = weapons[weapon_id]
	var ammo := ws.fire()
	if ammo.is_empty():
		return null
	var err := spread_mrad * 0.001
	var aim := dir.normalized()
	var side := aim.cross(Vector3.UP).normalized() if absf(aim.y) < 0.99 else Vector3.RIGHT
	var up := side.cross(aim)
	aim = (aim + side * randfn(0.0, err) + up * randfn(0.0, err)).normalized()
	var speed := float(ammo.get("muzzle_m_s", 800.0))
	var skip: Array[RID] = [get_rid()]
	for area: Area3D in _hit_areas.values():
		skip.append(area.get_rid())
	var wdef := Registry.entry("weapons", weapon_id)
	var p := Projectile.spawn(get_parent(), muzzle.origin + aim * 0.3, aim * speed + linear_velocity, ammo, self, 1.0, skip)
	# Recoil: the round's and the gas's momentum back into the body at the muzzle.
	var kick := Ballistics.recoil_impulse(wdef, ammo)
	if kick > 0.0:
		apply_impulse(-aim * kick, muzzle.origin - global_position)
	CombatFx.muzzle(get_parent(), muzzle.origin, aim, clampf(float(ammo.get("projectile_kg", 0.01)) * 0.6, 0.25, 2.5))
	fired.emit(weapon_id, str(ammo.get("id", "")))
	return p


# --- taking hits --------------------------------------------------------------------------------


func take_hit(info: Dictionary) -> Dictionary:
	var key := str(info.get("key", ""))
	var point: Vector3 = info.get("point", global_position)
	if not damage.has(key):
		key = nearest_key(point)
	var r := damage.hit(key, float(info.get("damage", 0.0)), float(info.get("penetration_mm", 0.0)))
	var weak: Dictionary = _weak.get(key, {})
	if bool(r["penetrated"]) and float(weak.get("to_hull", 0.0)) > 0.0 and key != "hull":
		var through := damage.hit("hull", float(r["dealt"]) * float(weak["to_hull"]), INF)
		r["dealt"] = float(r["dealt"]) + float(through["dealt"])
	if not bool(info.get("splash", false)):
		var dir: Vector3 = info.get("dir", Vector3.ZERO)
		apply_impulse(dir * float(info.get("projectile_kg", 1.0)) * float(info.get("speed", 0.0)), point - global_position)
		var mark := CombatFx.decal(self, point, info.get("normal", Vector3.UP), 0.8 if bool(r["penetrated"]) else 0.45)
		mark.cull_mask = CombatFx.MECH_LAYERS
	hit_taken.emit(key, float(r["dealt"]), info)
	return r


func nearest_key(point: Vector3) -> String:
	var best := "hull"
	var best_d := INF
	for key: String in _colliders:
		if not damage.has(key) or damage.is_lost(key):
			continue
		for cs: CollisionShape3D in _colliders[key]:
			var d := cs.global_position.distance_to(point)
			if d < best_d:
				best_d = d
				best = key
	return best


func _on_part_lost(key: String) -> void:
	part_lost.emit(key)
	if key == "wp_optic_sensor":
		sight_scale = float(_weak.get(key, {}).get("sight_scale_lost", 0.3))
	elif key == "arms" or key == "wp_rocket_pod":
		arms_ok = key != "arms" and arms_ok
		if key == "wp_rocket_pod":
			weapons.erase("grauwolf_rockets")
	if key.begins_with("leg_") or key.begins_with("knee_"):
		var tag := key.get_slice("_", 1)
		for leg: Dictionary in legs:
			if str(leg["tag"]) == tag:
				leg["down"] = false
				leg["swing_t"] = -1.0
				# A dead leg hangs: its foot drops under the hip.
				leg["foot"] = global_transform * ((leg["p0"] as Vector3) + Vector3(0, -float(leg["height"]) * 0.6, 0))
		var alive := 0
		for leg: Dictionary in legs:
			if _leg_alive(leg):
				alive += 1
		speed_scale = clampf(float(alive) / maxf(legs.size(), 1.0), 0.2, 1.0)
	CombatFx.smoke(get_parent(), global_position + Vector3.UP * float(_g.get("smoke_height_m", 2.0)), Vector3.UP, 10, 2.0, Color(0.15, 0.14, 0.13, 0.7))


func _on_destroyed() -> void:
	if dead:
		return
	dead = true
	move_goal = Vector3.ZERO
	aim_point = null
	var brain := get_node_or_null("Brain")
	if brain != null:
		brain.process_mode = Node.PROCESS_MODE_DISABLED
	var at := global_transform * center_of_mass
	CombatFx.impact(get_parent(), at, Vector3.UP, true, true)
	CombatFx.flash_light(get_parent(), at, Color(1.0, 0.55, 0.25), 6.0, 30.0, 0.5)
	CombatFx.smoke(get_parent(), at, Vector3.UP, 30, 4.0, Color(0.1, 0.09, 0.08, 0.85), 6.0)
	# The legs stop holding: the body drops onto its belly and stays where it fell.
	can_sleep = true
	destroyed.emit()


## Every key's health, 0..1 (for the HUD and tests).
func health_fraction() -> float:
	return 0.0 if dead else damage.fraction("hull")


func telemetry() -> Dictionary:
	return {
		"id": enemy_id,
		"speed": snappedf(linear_velocity.length(), 0.01),
		"planted": planted_count,
		"support_t": snappedf(support_n / 9810.0, 0.01),
		"hull": snappedf(damage.fraction("hull"), 0.01),
		"dead": dead,
		"tilt_deg": snappedf(rad_to_deg(global_transform.basis.y.angle_to(Vector3.UP)), 0.1),
		"sleeping": sleeping,
		"move_goal": snappedf(move_goal.length(), 0.1),
	}
