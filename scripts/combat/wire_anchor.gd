class_name WireAnchor
extends Node3D
## The Juggernaut's wire anchors (weapons.json "wire_anchor", launchers on the sub-arms). Lane A3 part
## 4 (Emerson's playtest of version 5: "I can't aim up much so swinging is kind of impossible"): the
## dart goes where you aim, the chase camera's crosshair (or the mech's look direction when no camera
## follows it), as far as the sub-arms can elevate and swing (grapple.arm_*), with a small nudge
## toward a level's marked grapple points near the aim. It bites only a grapple surface (physics
## layer 7) within range. Attached, the cable is a one-sided spring: slack does nothing, taut pulls
## the socket towards the anchor. All real: the winch stalls at max_tension_n, reels no faster than
## its power allows (winch_power_w / tension), and the 16 mm steel wire snaps above cable_break_n held
## for snap_after_s. Swinging is free (gravity and momentum). Pay out lengthens the cable: hanging on
## it, you abseil down. Pressing fire again lets go.

signal attached(point: Vector3)
signal released
signal snapped

enum State { IDLE, FLYING, ATTACHED }

const SURFACE_MASK := 64

var state := State.IDLE
var mech: RigidBody3D
var def: Dictionary = {}
var sockets: Array = []  # body-frame anchor sockets (left and right)
var socket_local := Vector3.ZERO
var anchor_point := Vector3.ZERO
var rope_len := 0.0
var tension := 0.0
var reel := 0  # -1 reel in, +1 pay out (a caller's choice: tests and AI)
var _over_s := 0.0
var _input_reel := 0  # the player's reel buttons, which win while held
var _g: Dictionary = {}
var _dart_pos := Vector3.ZERO
var _dart_to := Vector3.ZERO
var _miss := false
const ROPE_SEGMENTS := 10

var _rope: Array[MeshInstance3D] = []
var _dart: MeshInstance3D


func setup(body: RigidBody3D, weapon_def: Dictionary, socket_list: Array) -> void:
	mech = body
	def = weapon_def
	sockets = socket_list
	if sockets.is_empty():
		sockets = [Vector3(0.0, 0.0, -1.5)]
	socket_local = sockets[0]
	_g = Registry.tune("grapple", {})


func _ready() -> void:
	top_level = true
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.035
	cyl.bottom_radius = 0.035
	cyl.height = 1.0
	cyl.radial_segments = 6
	cyl.rings = 1
	var steel := StandardMaterial3D.new()
	steel.albedo_color = Color(0.16, 0.16, 0.17)
	steel.metallic = 0.9
	steel.roughness = 0.35
	cyl.material = steel
	for i in ROPE_SEGMENTS:
		var seg := MeshInstance3D.new()
		seg.mesh = cyl
		seg.visible = false
		seg.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(seg)
		_rope.append(seg)
	_dart = MeshInstance3D.new()
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.16
	cone.height = 0.7
	cone.radial_segments = 8
	cone.rings = 1
	cone.material = steel
	_dart.mesh = cone
	_dart.visible = false
	add_child(_dart)


func range_m() -> float:
	return float(def.get("range_m", 80.0))


## Where the player aims: the chase camera's centre ray when a camera follows this mech, else the
## mech's look direction from the anchor sockets. [origin, direction].
func aim_ray() -> Array:
	var cam := mech.get_viewport().get_camera_3d() if mech.is_inside_tree() else null
	if cam != null and "target" in cam and cam.get("target") == mech:
		return [cam.global_position, -cam.global_transform.basis.z]
	var dir: Vector3 = mech.call("look_direction") if mech.has_method("look_direction") else -mech.global_transform.basis.z
	return [mech.global_transform * _mid_socket(), dir]


## What a shot would do now: {"state": "ok" | "range" | "surface", "point", "normal", "socket",
## "clamped"}. "ok" bites a grapple surface; "surface" means the aim is on something the dart cannot
## bite; "range" means nothing within range (point is then where the dart would give up).
func preview() -> Dictionary:
	if mech == null or not mech.is_inside_tree():
		return {"state": "range", "point": Vector3.ZERO, "socket": _mid_socket(), "clamped": false}
	var xf := mech.global_transform
	var space := mech.get_world_3d().direct_space_state
	var from := xf * _mid_socket()
	var ray := aim_ray()
	var o: Vector3 = ray[0]
	var d: Vector3 = (ray[1] as Vector3).normalized()
	# The crosshair's point: the first thing the aim ray meets (anything solid), or far along it.
	var reach := range_m() + o.distance_to(from)
	var q := PhysicsRayQueryParameters3D.create(o, o + d * reach, 1 | SURFACE_MASK, [mech.get_rid()])
	var hit := space.intersect_ray(q)
	var aim_point: Vector3 = hit["position"] if not hit.is_empty() else o + d * reach
	aim_point = _assist(from, aim_point, space)
	var want := (aim_point - from).normalized()
	var dir := _arm_limit(want, xf.basis)
	var clamped := dir.angle_to(want) > 0.01
	q = PhysicsRayQueryParameters3D.create(from, from + dir * range_m(), 1 | SURFACE_MASK, [mech.get_rid()])
	hit = space.intersect_ray(q)
	if hit.is_empty():
		return {"state": "range", "point": from + dir * range_m(), "socket": _socket_towards(from + dir * range_m()), "clamped": clamped}
	var p: Vector3 = hit["position"]
	var body := hit["collider"] as CollisionObject3D
	var ok := body != null and (body.collision_layer & SURFACE_MASK) != 0
	return {"state": "ok" if ok else "surface", "point": p, "normal": hit["normal"], "socket": _socket_towards(p), "clamped": clamped}


## The grapple surface a shot would bite now ({"point", "normal", "socket"}), or {}.
func find_target() -> Dictionary:
	var p := preview()
	return p if str(p["state"]) == "ok" else {}


## The sub-arms elevate from grapple.arm_pitch_min_deg to arm_pitch_max_deg and swing
## arm_yaw_deg either side of the heading; a direction past that is pulled back inside.
func _arm_limit(dir: Vector3, basis: Basis) -> Vector3:
	var local := basis.inverse() * dir
	var yaw := atan2(-local.x, -local.z)
	var pitch := asin(clampf(local.y, -1.0, 1.0))
	var ymax := deg_to_rad(float(_g.get("arm_yaw_deg", 30.0)))
	yaw = clampf(yaw, -ymax, ymax)
	pitch = clampf(pitch, deg_to_rad(float(_g.get("arm_pitch_min_deg", -15.0))), deg_to_rad(float(_g.get("arm_pitch_max_deg", 80.0))))
	var out := Vector3(-sin(yaw) * cos(pitch), sin(pitch), -cos(yaw) * cos(pitch))
	return (basis * out).normalized()


## A small nudge (grapple.assist_cone_deg) toward the nearest marked grapple point (a level's
## `grapple_points`, lane B3) around the aim, if the dart can see it and it is in range.
func _assist(from: Vector3, aim_point: Vector3, space: PhysicsDirectSpaceState3D) -> Vector3:
	var level := Game.level
	if level == null or not is_instance_valid(level) or not ("grapple_points" in level):
		return aim_point
	var cone := deg_to_rad(float(_g.get("assist_cone_deg", 8.0)))
	var aim := (aim_point - from).normalized()
	var best := aim_point
	var best_angle := cone
	for p: Vector3 in level.get("grapple_points"):
		var to := p - from
		if to.length() > range_m():
			continue
		var angle := aim.angle_to(to.normalized())
		if angle >= best_angle:
			continue
		var q := PhysicsRayQueryParameters3D.create(from, p + to.normalized() * 0.5, SURFACE_MASK, [mech.get_rid()])
		var hit := space.intersect_ray(q)
		if hit.is_empty() or (hit["position"] as Vector3).distance_to(p) > 1.5:
			continue  # something else is in the way
		best_angle = angle
		best = p
	return best


func _mid_socket() -> Vector3:
	var sum := Vector3.ZERO
	for s: Vector3 in sockets:
		sum += s
	return sum / maxf(sockets.size(), 1)


func _socket_towards(point: Vector3) -> Vector3:
	var local := mech.to_local(point)
	var best: Vector3 = sockets[0]
	for s: Vector3 in sockets:
		if signf(s.x) == signf(local.x):
			best = s
	return best


## Fires the dart, or lets go if one is already out. True when a dart left towards a surface.
func fire() -> bool:
	if state != State.IDLE:
		release()
		return false
	var target := preview()
	var xf := mech.global_transform
	_miss = str(target["state"]) != "ok"
	socket_local = target["socket"]
	_dart_to = target["point"]
	_dart_pos = xf * socket_local
	state = State.FLYING
	if mech.get("is_player"):
		Rumble.play("fire_sub")
	return not _miss


func release() -> void:
	if state == State.IDLE:
		return
	state = State.IDLE
	tension = 0.0
	reel = 0
	_input_reel = 0
	_over_s = 0.0
	if mech != null and mech.get("is_player"):
		Rumble.stop("grapple_tension")
	released.emit()


func _attach() -> void:
	state = State.ATTACHED
	anchor_point = _dart_to
	rope_len = (mech.global_transform * socket_local).distance_to(anchor_point)
	var parent := mech.get_parent()
	CombatFx.sparks(parent, anchor_point, (mech.global_position - anchor_point).normalized(), 16, 10.0)
	CombatFx.smoke(parent, anchor_point, Vector3.UP, 6, 0.9, Color(0.5, 0.46, 0.4, 0.6), 1.2, 2.0)
	if mech.get("is_player"):
		Rumble.play("grapple_attach")
	attached.emit(anchor_point)


func _physics_process(delta: float) -> void:
	if mech == null or not is_instance_valid(mech):
		return
	if mech.get("is_player") and not Game.is_paused():
		if Input.is_action_just_pressed("grapple_fire"):
			fire()
		_input_reel = 0
		if Input.is_action_pressed("grapple_reel_in"):
			_input_reel = -1
		elif Input.is_action_pressed("grapple_pay_out"):
			_input_reel = 1
	if state == State.FLYING:
		var speed := float(def.get("anchor_speed_m_s", 120.0))
		_dart_pos = _dart_pos.move_toward(_dart_to, speed * delta)
		if _dart_pos.distance_to(_dart_to) < 0.01:
			if _miss:
				release()
			else:
				_attach()
	elif state == State.ATTACHED:
		_pull(delta)


func _pull(delta: float) -> void:
	var xf := mech.global_transform
	var socket_w := xf * socket_local
	var d := anchor_point - socket_w
	var dist := d.length()
	var m := mech.mass
	var k := float(_g.get("stiffness_n_per_m_per_t", 60000.0)) * m / 1000.0
	var r := _input_reel if _input_reel != 0 else reel
	# The winch stalls at max tension instead of reeling on (it cannot out-pull its own motor), and
	# under load it reels no faster than its power allows: 120 kW lifts the 5.4 t mech at about 2 m/s.
	var cap := float(def.get("max_tension_n", 120000.0))
	if r < 0 and tension < cap * 0.98:
		var speed := minf(float(def.get("reel_in_m_s", 8.0)), float(def.get("winch_power_w", 120000.0)) / maxf(tension, 1.0))
		rope_len = maxf(rope_len - speed * delta, float(_g.get("min_len_m", 3.0)))
	elif r > 0:
		# Free-spooling while the mech hangs on the cable would drop it and the catch would snap the
		# wire (3 m of fall is ~380 kN on this cable), so off the ground the winch lowers at lower_m_s,
		# a controlled abseil; on its feet the mech's weight is not on the cable and it free-spools.
		var hanging := int(mech.get("grounded_legs")) == 0
		var out := float(def.get("lower_m_s", 4.0)) if hanging else float(def.get("pay_out_m_s", 12.0))
		rope_len = minf(rope_len + out * delta, range_m())
	var stretch := dist - rope_len
	if stretch <= 0.0 or dist < 0.01:
		tension = 0.0
		if mech.get("is_player"):
			Rumble.stop("grapple_tension")
		return
	var n := d / dist
	var c := 2.0 * float(_g.get("damping_ratio", 0.4)) * sqrt(k * m)
	var com_w := xf * mech.center_of_mass
	var v_socket := mech.linear_velocity + mech.angular_velocity.cross(socket_w - com_w)
	var want := k * stretch - c * v_socket.dot(n)
	# Snaps only on a sustained overload (snap_after_s): a one-tick spike at the bottom of a hard
	# swing would make the cable a coin toss for the player.
	if want > float(def.get("cable_break_n", 170000.0)):
		_over_s += delta
		if _over_s >= float(_g.get("snap_after_s", 0.15)):
			_snap(socket_w)
			return
	else:
		_over_s = 0.0
	tension = maxf(want, 0.0)
	var arm := socket_w - mech.global_position  # the real socket: the pull turns the body as well
	mech.apply_force(n * tension, arm)
	if mech.get("is_player") and not Rumble.is_playing("grapple_tension"):
		Rumble.play("grapple_tension")


func _snap(socket_w: Vector3) -> void:
	CombatFx.sparks(mech.get_parent(), socket_w, (anchor_point - socket_w).normalized(), 24, 14.0)
	release()
	snapped.emit()


func _process(_delta: float) -> void:
	if mech == null or not is_instance_valid(mech) or state == State.IDLE:
		for seg in _rope:
			seg.visible = false
		_dart.visible = false
		return
	var from := mech.global_transform * socket_local
	var to := anchor_point if state == State.ATTACHED else _dart_pos
	var span := to - from
	var length := span.length()
	_dart.visible = true
	if length > 0.01:
		var up := span / length
		var x := up.cross(Vector3.UP if absf(up.y) < 0.95 else Vector3.RIGHT).normalized()
		_dart.global_transform = Transform3D(Basis(x, up, x.cross(up)), to)
	# A slack cable sags: a parabola whose arc length is the paid-out length (arc ~ d + 8 s^2 / 3d).
	var sag := 0.0
	if state == State.ATTACHED and rope_len > length:
		sag = sqrt(3.0 * length * (rope_len - length) / 8.0)
	var prev := from
	for i in ROPE_SEGMENTS:
		var t := float(i + 1) / ROPE_SEGMENTS
		var p := from.lerp(to, t) + Vector3.DOWN * sag * 4.0 * t * (1.0 - t)
		_place_segment(_rope[i], prev, p)
		prev = p


func _place_segment(seg: MeshInstance3D, a: Vector3, b: Vector3) -> void:
	var span := b - a
	var length := span.length()
	seg.visible = length > 0.02
	if not seg.visible:
		return
	var up := span / length
	var x := up.cross(Vector3.UP if absf(up.y) < 0.95 else Vector3.RIGHT).normalized()
	seg.global_transform = Transform3D(Basis(x, up, x.cross(up)).scaled_local(Vector3(1.0, length, 1.0)), a + span * 0.5)
