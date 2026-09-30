class_name WireAnchor
extends Node3D
## The Juggernaut's wire anchors (weapons.json "wire_anchor", fixed forward like every sub-arm).
## "Fire wire anchor" throws a dart along the chassis heading; it searches upward in a fan (launch
## pitches from the grapple tuning block) for the first grapple surface (physics layer 7) within
## range, flies there at anchor_speed_m_s and bites. Attached, the cable is a one-sided spring: slack
## does nothing, taut pulls the anchor socket towards the anchor, capped at max_tension_n (times the
## game-mode scale) and snapping above cable_break_n. Reel in shortens it (pull, climb a wall), pay
## out lengthens it; airborne on a taut cable the mech swings. Pressing fire again lets go.

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
var _rope: MeshInstance3D
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
	_rope = MeshInstance3D.new()
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
	_rope.mesh = cyl
	_rope.visible = false
	_rope.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_rope)
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


## The grapple surface the fan of launch pitches finds: {"point", "normal", "socket"} or {}. The
## first hit at least min_rise_m above the socket wins (something to swing from); ground ahead is
## only the fallback when nothing higher is in range.
func find_target() -> Dictionary:
	if mech == null or not mech.is_inside_tree():
		return {}
	var xf := mech.global_transform
	var fwd := -xf.basis.z
	var right := xf.basis.x
	var space := mech.get_world_3d().direct_space_state
	var lo := float(_g.get("launch_pitch_min_deg", 0.0))
	var hi := float(_g.get("launch_pitch_max_deg", 55.0))
	var step := maxf(float(_g.get("pitch_step_deg", 5.0)), 0.5)
	var from := xf * _mid_socket()
	var rise := float(_g.get("min_rise_m", 6.0))
	var fallback := {}
	var pitch := lo
	while pitch <= hi + 0.01:
		var dir := fwd.rotated(right, deg_to_rad(pitch))
		var q := PhysicsRayQueryParameters3D.create(from, from + dir * range_m(), SURFACE_MASK, [mech.get_rid()])
		var hit := space.intersect_ray(q)
		if not hit.is_empty():
			var found := {"point": hit["position"], "normal": hit["normal"], "socket": _socket_towards(hit["position"])}
			if (hit["position"] as Vector3).y >= from.y + rise:
				return found
			if fallback.is_empty():
				fallback = found
		pitch += step
	return fallback


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
	var target := find_target()
	var xf := mech.global_transform
	_miss = target.is_empty()
	if _miss:
		socket_local = _mid_socket()
		_dart_to = xf * socket_local + (-xf.basis.z).rotated(xf.basis.x, deg_to_rad(float(_g.get("launch_pitch_min_deg", 0.0)) + 10.0)) * range_m()
	else:
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


func game_scale() -> float:
	return 1.0 if mech.call("bench_mode") else float(_g.get("tension_game_scale", 2.5))


func _pull(delta: float) -> void:
	var xf := mech.global_transform
	var socket_w := xf * socket_local
	var d := anchor_point - socket_w
	var dist := d.length()
	var m := mech.mass
	var k := float(_g.get("stiffness_n_per_m_per_t", 60000.0)) * m / 1000.0
	var scale := game_scale()
	var r := _input_reel if _input_reel != 0 else reel
	# The winch stalls at max tension instead of reeling on: it cannot out-pull its own motor.
	if r < 0 and tension < float(def.get("max_tension_n", 180000.0)) * scale * 0.98:
		rope_len = maxf(rope_len - float(def.get("reel_in_m_s", 8.0)) * delta, float(_g.get("min_len_m", 3.0)))
	elif r > 0:
		rope_len = minf(rope_len + float(def.get("pay_out_m_s", 12.0)) * delta, range_m())
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
	if want > float(def.get("cable_break_n", 260000.0)) * scale:
		_over_s += delta
		if _over_s >= float(_g.get("snap_after_s", 0.15)):
			_snap(socket_w)
			return
	else:
		_over_s = 0.0
	tension = clampf(want, 0.0, float(def.get("max_tension_n", 180000.0)) * scale)
	var arm := (socket_w - mech.global_position) * float(_g.get("torque_share", 0.25))
	mech.apply_force(n * tension, arm)
	if mech.get("is_player") and not Rumble.is_playing("grapple_tension"):
		Rumble.play("grapple_tension")


func _snap(socket_w: Vector3) -> void:
	CombatFx.sparks(mech.get_parent(), socket_w, (anchor_point - socket_w).normalized(), 24, 14.0)
	release()
	snapped.emit()


func _process(_delta: float) -> void:
	if mech == null or not is_instance_valid(mech) or state == State.IDLE:
		_rope.visible = false
		_dart.visible = false
		return
	var from := mech.global_transform * socket_local
	var to := anchor_point if state == State.ATTACHED else _dart_pos
	var span := to - from
	var length := span.length()
	_rope.visible = length > 0.05
	_dart.visible = true
	if length > 0.05:
		var up := span / length
		var x := up.cross(Vector3.UP if absf(up.y) < 0.95 else Vector3.RIGHT).normalized()
		_rope.global_transform = Transform3D(Basis(x, up, x.cross(up)).scaled_local(Vector3(1.0, length, 1.0)), from + span * 0.5)
		_dart.global_transform = Transform3D(Basis(x, up, x.cross(up)), to)
