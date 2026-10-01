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
## Lane A4 (Emerson 2026-10-01: "make the grapple have gravity and better aiming, and a stronger tug"):
## the dart is a real projectile. It leaves at anchor_speed_m_s, falls under gravity and pulls its
## line off the drum behind it, so it slows as more line moves with it ((m + lambda s) v is kept:
## v = v0 m / (m + lambda s)). The launcher's fire control elevates the sub-arms so that arc lands on
## the crosshair, and a dotted arc shows where it will go. The line is 20 mm Dyneema (stronger and a
## seventh the weight of steel) and the winch draws up to winch_power_w from the power pack.

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
var _rope_speed := 0.0  # the drum's cable speed, m/s: + paying out, - reeling in
var _input_reel := 0  # the player's reel buttons, which win while held
var _g: Dictionary = {}
var _dart_pos := Vector3.ZERO
var _dart_to := Vector3.ZERO
var _dart_vel := Vector3.ZERO
var _dart_s := 0.0  # line paid out behind the dart, m
var _miss := false
const ROPE_SEGMENTS := 10
const ARC_DOTS := 48
const ARC_STEP_S := 1.0 / 60.0

var _arc: MultiMeshInstance3D
var _arc_mat: StandardMaterial3D

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
	var dot := SphereMesh.new()
	dot.radius = 0.09
	dot.height = 0.18
	dot.radial_segments = 6
	dot.rings = 3
	_arc_mat = StandardMaterial3D.new()
	_arc_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_arc_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_arc_mat.no_depth_test = false
	dot.material = _arc_mat
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = dot
	mm.instance_count = ARC_DOTS
	mm.visible_instance_count = 0
	_arc = MultiMeshInstance3D.new()
	_arc.multimesh = mm
	_arc.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_arc)


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
## "clamped", "dir", "arc"}. "ok" bites a grapple surface; "surface" means the arc ends on something
## the dart cannot bite; "range" means the line runs out first (point is then where the dart would
## be). "dir" is the launch direction fire control picked, "arc" the dart's path.
func preview() -> Dictionary:
	if mech == null or not mech.is_inside_tree():
		return {"state": "range", "point": Vector3.ZERO, "socket": _mid_socket(), "clamped": false, "dir": Vector3.FORWARD, "arc": PackedVector3Array()}
	var xf := mech.global_transform
	var space := mech.get_world_3d().direct_space_state
	var from := xf * _mid_socket()
	var aim := _assist(from, aim_point(from, range_m()), space)
	var want := solve_launch(from, aim)
	var dir := arm_limit(want, xf.basis)
	var clamped := dir.angle_to(want) > 0.01
	var flight := fly(space, from, dir * launch_speed() + _carry(), range_m(), [mech.get_rid()])
	var out := {"state": "range", "point": flight["point"], "normal": Vector3.UP, "socket": _socket_towards(flight["point"]), "clamped": clamped, "dir": dir, "arc": flight["arc"]}
	if bool(flight["hit"]):
		var body := flight["collider"] as CollisionObject3D
		var ok := body != null and (body.collision_layer & SURFACE_MASK) != 0
		out["state"] = "ok" if ok else "surface"
		out["normal"] = flight["normal"]
	return out


func launch_speed() -> float:
	return float(def.get("anchor_speed_m_s", 140.0))


## The mech's own velocity rides along with the dart (it leaves a moving launcher).
func _carry() -> Vector3:
	return mech.linear_velocity if mech != null else Vector3.ZERO


## One step of the dart: gravity, and the line it drags off the drum (momentum (m + lambda s) v kept
## as line joins the moving part). Returns [position, velocity, line paid out].
static func dart_step(pos: Vector3, vel: Vector3, paid: float, dt: float, dart_kg: float, line_kg_m: float, g: float) -> Array:
	var speed := vel.length()
	if speed > 0.001:
		var slow := line_kg_m * speed * speed / maxf(dart_kg + line_kg_m * paid, 0.001)
		vel -= vel / speed * minf(slow * dt, speed)
	vel += Vector3.DOWN * g * dt
	var to := pos + vel * dt
	return [to, vel, paid + to.distance_to(pos)]


## Flies a dart from `from` at `vel` until it hits something on the world or grapple layers or its
## line runs out at `reach`. {"hit", "point", "normal", "collider", "arc", "time"}.
func fly(space: PhysicsDirectSpaceState3D, from: Vector3, vel: Vector3, reach: float, skip: Array[RID]) -> Dictionary:
	var arc := PackedVector3Array([from])
	var pos := from
	var paid := 0.0
	var t := 0.0
	var g := Registry.tune_f("physics.gravity_m_s2", 9.81)
	var m := float(def.get("dart_kg", 8.0))
	var lam := float(def.get("line_kg_per_m", 0.22))
	while paid < reach and t < 4.0:
		var step := dart_step(pos, vel, paid, ARC_STEP_S, m, lam, g)
		var to: Vector3 = step[0]
		var q := PhysicsRayQueryParameters3D.create(pos, to, 1 | SURFACE_MASK, skip)
		var hit := space.intersect_ray(q)
		if not hit.is_empty():
			arc.append(hit["position"])
			return {"hit": true, "point": hit["position"], "normal": hit["normal"], "collider": hit["collider"], "arc": arc, "time": t}
		pos = to
		vel = step[1]
		paid = float(step[2])
		t += ARC_STEP_S
		arc.append(pos)
	return {"hit": false, "point": pos, "normal": Vector3.UP, "collider": null, "arc": arc, "time": t}


## Fire control: the launch direction whose arc passes through `target` (gravity and line drag
## allowed for), by correcting the elevation a few times in the dart's own flight model.
func solve_launch(from: Vector3, target: Vector3) -> Vector3:
	var to := target - from
	var flat := Vector2(to.x, to.z)
	var dist := flat.length()
	if dist < 0.5:
		return to.normalized()
	var heading := Vector3(to.x, 0.0, to.z) / dist
	var pitch := atan2(to.y, dist)
	var g := Registry.tune_f("physics.gravity_m_s2", 9.81)
	var m := float(def.get("dart_kg", 8.0))
	var lam := float(def.get("line_kg_per_m", 0.22))
	var carry := _carry()
	for _i in 5:
		var dir := heading * cos(pitch) + Vector3.UP * sin(pitch)
		var pos := from
		var vel := dir * launch_speed() + carry
		var paid := 0.0
		var t := 0.0
		var prev := pos
		while Vector2(pos.x - from.x, pos.z - from.z).length() < dist and paid < range_m() * 1.5 and t < 4.0:
			prev = pos
			var step := dart_step(pos, vel, paid, ARC_STEP_S, m, lam, g)
			pos = step[0]
			vel = step[1]
			paid = float(step[2])
			t += ARC_STEP_S
		var a := Vector2(prev.x - from.x, prev.z - from.z).length()
		var b := Vector2(pos.x - from.x, pos.z - from.z).length()
		var y := lerpf(prev.y, pos.y, clampf((dist - a) / maxf(b - a, 0.001), 0.0, 1.0))
		var miss := target.y - y
		if absf(miss) < 0.05:
			break
		pitch = clampf(pitch + atan2(miss, dist), -PI * 0.45, PI * 0.45)
	return heading * cos(pitch) + Vector3.UP * sin(pitch)


## The crosshair's point: the first solid thing the aim ray meets within `reach` of `from` (plus the
## camera's distance), or that far along the ray. The sub-arm guns aim at it too.
func aim_point(from: Vector3, reach: float) -> Vector3:
	var ray := aim_ray()
	var o: Vector3 = ray[0]
	var d: Vector3 = (ray[1] as Vector3).normalized()
	var far := reach + o.distance_to(from)
	var q := PhysicsRayQueryParameters3D.create(o, o + d * far, 1 | 2 | SURFACE_MASK, [mech.get_rid()])
	var hit := mech.get_world_3d().direct_space_state.intersect_ray(q)
	return hit["position"] if not hit.is_empty() else o + d * far


## The grapple surface a shot would bite now ({"point", "normal", "socket"}), or {}.
func find_target() -> Dictionary:
	var p := preview()
	return p if str(p["state"]) == "ok" else {}


## The sub-arms elevate from grapple.arm_pitch_min_deg to arm_pitch_max_deg and swing
## arm_yaw_deg either side of the heading; a direction past that is pulled back inside.
func arm_limit(dir: Vector3, basis: Basis) -> Vector3:
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
	_dart_vel = (target["dir"] as Vector3) * launch_speed() + _carry()
	_dart_s = 0.0
	state = State.FLYING
	if mech.get("is_player"):
		Rumble.play("fire_sub")
	return not _miss


func release() -> void:
	if state == State.IDLE:
		return
	state = State.IDLE
	tension = 0.0
	_rope_speed = 0.0
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
		_fly_dart(delta)
	elif state == State.ATTACHED:
		_pull(delta)


## The dart in flight, stepped like the preview: it bites a grapple surface it hits, glances off
## anything else, and is stopped by its own line when that runs out.
func _fly_dart(delta: float) -> void:
	var step := dart_step(_dart_pos, _dart_vel, _dart_s, delta, float(def.get("dart_kg", 8.0)), float(def.get("line_kg_per_m", 0.22)), Registry.tune_f("physics.gravity_m_s2", 9.81))
	var to: Vector3 = step[0]
	var q := PhysicsRayQueryParameters3D.create(_dart_pos, to, 1 | SURFACE_MASK, [mech.get_rid()])
	var hit := mech.get_world_3d().direct_space_state.intersect_ray(q)
	if not hit.is_empty():
		_dart_pos = hit["position"]
		_dart_to = hit["position"]
		var body := hit["collider"] as CollisionObject3D
		if body != null and (body.collision_layer & SURFACE_MASK) != 0:
			_attach()
		else:
			CombatFx.sparks(mech.get_parent(), _dart_pos, hit["normal"], 8, 6.0)
			release()
		return
	_dart_pos = to
	_dart_vel = step[1]
	_dart_s = float(step[2])
	if _dart_s >= range_m():
		release()


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
	var want_speed := 0.0  # cable speed the winch is asked for: + pays out, - reels in
	if r < 0 and tension < cap * 0.98:
		want_speed = -minf(float(def.get("reel_in_m_s", 8.0)), float(def.get("winch_power_w", 120000.0)) / maxf(tension, 1.0))
	elif r > 0:
		# Free-spooling while the mech hangs on the cable would drop it and the catch would snap the
		# wire (3 m of fall is ~380 kN on this cable), so off the ground the winch lowers at lower_m_s,
		# a controlled abseil; on its feet the mech's weight is not on the cable and it free-spools.
		var off_ground := int(mech.get("grounded_legs")) == 0
		want_speed = float(def.get("lower_m_s", 4.0)) if off_ground else float(def.get("pay_out_m_s", 12.0))
	# The drum speeds up and brakes at winch_accel_m_s2: stopping a 4 m/s abseil dead would jerk the
	# 5.6 t mech to a stop on the cable (~235 kN, past its 170 kN), a ramped stop takes ~70 kN.
	# Reeling in under load already follows the power limit, so only the ramp from rest applies there;
	# on its feet (the cable carries no weight) the drum starts and stops at once.
	var hanging := int(mech.get("grounded_legs")) == 0
	var ramp := float(def.get("winch_accel_m_s2", 3.0)) * delta if hanging else INF
	if want_speed < 0.0 and _rope_speed <= 0.0:
		_rope_speed = maxf(_rope_speed - ramp, want_speed) if _rope_speed > want_speed else want_speed
	else:
		_rope_speed = move_toward(_rope_speed, want_speed, ramp)
	rope_len = clampf(rope_len + _rope_speed * delta, float(_g.get("min_len_m", 3.0)), range_m())
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
	_draw_arc()
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


## The dotted arc the dart would fly (player only, while the anchor is ready; Settings > Gameplay >
## "Show the wire anchor's arc"): pale where it will bite, red where it cannot.
func _draw_arc() -> void:
	var mm := _arc.multimesh
	var show := mech != null and is_instance_valid(mech) and state == State.IDLE and bool(mech.get("is_player")) and mech.is_inside_tree()
	show = show and Settings.get_b("gameplay.anchor_arc") and not Game.is_photo()
	if not show:
		mm.visible_instance_count = 0
		return
	var p := preview()
	var arc: PackedVector3Array = p["arc"]
	var ok := str(p["state"]) == "ok"
	_arc_mat.albedo_color = Color(0.85, 0.95, 1.0, 0.75) if ok else Color(1.0, 0.35, 0.3, 0.55)
	# A dot every ~2.5 m along the path, skipping the first few metres in front of the launcher.
	var count := 0
	var since := 0.0
	for i in range(1, arc.size()):
		since += arc[i].distance_to(arc[i - 1])
		if since < 2.5 or count >= ARC_DOTS:
			continue
		since = 0.0
		if arc[i].distance_to(arc[0]) < 4.0:
			continue
		mm.set_instance_transform(count, Transform3D(Basis.IDENTITY, arc[i]))
		count += 1
	mm.visible_instance_count = count

