extends "res://tests/lib/test_case.gd"
## Relay 38 (Emerson 2026-10-03): "camera and legs keep slipping through the floor, and when we roll over
## sideways or vertically it messes it up and we get clipping also." Each case plays one move on one ground
## and checks every physics tick: the lowest foot, ankle and knee point under the ground the player sees,
## the hull's lowest point under it, and the chase camera and cockpit eye above it. Grounds: flat, a flat
## run into a 25 degree ramp, and the Palouse survey ground (heightmap tiles with their real colliders,
## measured against the drawn mesh, not the collider). Moves: a side roll, an end-over-end flip at a run,
## a running jump's landing, and a gallop into a full slide.

const UNDER_M := 0.03  # a bone point this far under the drawn ground counts as clipping
const CAM_CLEAR_M := 0.1  # the camera's near plane needs this much air above the drawn ground
const RAMP_DEG := 25.0
const PALOUSE_AT := Vector2(0.0, 0.0)  # the map's spawn, where four tiles meet

var world: Node3D
var mech: RigidBody3D
var cam: Camera3D
var ground_kind := ""
var _terrain: BigTerrain
var _tiles := {}  # Vector2i -> tile data at 1 m


func after_each() -> void:
	for a: String in ["jump", "crouch", "move_forward", "move_back", "strafe_left", "strafe_right", "sprint", "brake"]:
		Input.action_release(a)
	if world != null:
		world.free()
	world = null
	Settings.reset_all_quietly()


func _box(size: Vector3, at: Vector3, tilt_deg: float = 0.0) -> void:
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	body.add_child(cs)
	world.add_child(body)
	body.rotation.x = deg_to_rad(tilt_deg)
	body.global_position = at


## Builds the ground and returns where the mech starts (on the ground, facing -z).
func _ground(kind: String, start_z: float) -> Vector3:
	ground_kind = kind
	world = Node3D.new()
	tree.root.add_child(world)
	if kind == "flat":
		_box(Vector3(600, 2, 600), Vector3(0, -1, 0))
	elif kind == "ramp":
		# flat for z > 0, then rising RAMP_DEG towards -z; the ramp's top face passes through the origin
		_box(Vector3(600, 2, 600), Vector3(0, -1, 0))
		var a := deg_to_rad(RAMP_DEG)
		_box(Vector3(600, 2, 400), Vector3(0, -cos(a), -sin(a)) * 1.0 + Vector3(0, 0, 0), RAMP_DEG)
	else:
		if _terrain == null:
			_terrain = BigTerrain.new(Registry.entry("maps", "palouse"))
		var c := _terrain.tile_of(PALOUSE_AT.x + 1.0, PALOUSE_AT.y + 1.0)
		for dz in [-1, 0]:
			for dx in [-1, 0]:
				var key := Vector2i(c.x + dx, c.y + dz)
				if not _tiles.has(key):
					_tiles[key] = _terrain.tile(key.x, key.y, 1)
				var o := _terrain.tile_origin(key.x, key.y)
				var body := StaticBody3D.new()
				body.collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE
				body.collision_mask = 0
				var cs := CollisionShape3D.new()
				cs.shape = BigTerrain.tile_shape(_tiles[key])
				cs.position = Vector3(o.x + BigTerrain.TILE_M * 0.5, 0.0, o.y + BigTerrain.TILE_M * 0.5)
				body.add_child(cs)
				world.add_child(body)
	var p := Vector3(PALOUSE_AT.x, 0.0, PALOUSE_AT.y + start_z) if kind == "palouse" else Vector3(0.0, 0.0, start_z)
	p.y = surface(p.x, p.z)
	return p


## The drawn ground's height at (x, z): what the player sees, not what the collider holds.
func surface(x: float, z: float) -> float:
	if ground_kind == "flat":
		return 0.0
	if ground_kind == "ramp":
		return maxf(0.0, -tan(deg_to_rad(RAMP_DEG)) * z)
	var key := _terrain.tile_of(x, z)
	if not _tiles.has(key):
		return _terrain.height_at(x, z)
	return drawn_height(_tiles[key], _terrain.tile_origin(key.x, key.y), x, z)


## A 1 m tile's mesh height at world (x, z): BigTerrain.mesh_arrays splits each square along the
## (i + 1, j) - (i, j + 1) diagonal.
static func drawn_height(t: Dictionary, o: Vector2, x: float, z: float) -> float:
	var n := int(t["n"])
	var h: PackedFloat32Array = t["heights"]
	var lx := clampf(x - o.x, 0.0, n - 1.001)
	var lz := clampf(z - o.y, 0.0, n - 1.001)
	var i := int(lx)
	var j := int(lz)
	var fx := lx - i
	var fz := lz - j
	var h00 := h[j * n + i]
	var h10 := h[j * n + i + 1]
	var h01 := h[(j + 1) * n + i]
	var h11 := h[(j + 1) * n + i + 1]
	if fx + fz <= 1.0:
		return h00 + fx * (h10 - h00) + fz * (h01 - h00)
	return h11 + (1.0 - fx) * (h01 - h11) + (1.0 - fz) * (h10 - h11)


func _spawn(at: Vector3) -> void:
	Settings.set_value("controls.sprint_mode", "hold", false)
	mech = MechBuilder.build("juggernaut_m2")
	world.add_child(mech)
	mech.global_position = at + Vector3.UP * 3.0
	cam = Camera3D.new()
	cam.set_script(load("res://scripts/camera/chase_camera.gd"))
	world.add_child(cam)
	cam.call("follow", mech)
	cam.set("view", "third")


## The worst of this tick: [deepest foot/ankle/knee under the drawn ground, which, hull's deepest point,
## chase camera clearance, cockpit eye clearance].
func _tick() -> Array:
	var xf := mech.global_transform
	var deep := -INF
	var which := ""
	for leg: Dictionary in mech.get("legs"):
		# the sole as drawn: the foot mesh's frame (ankle, foot tilt) less the sole-to-ankle offset
		var sole := xf * ((leg["foot_mesh"] as Node3D).transform * -(leg["end_offset"] as Vector3))
		var pts := {"foot": sole, "ankle": xf * (leg["ankle_local"] as Vector3), "knee": xf * (leg["knee_local"] as Vector3)}
		for k: String in pts:
			var p: Vector3 = pts[k]
			var d := surface(p.x, p.z) - p.y
			if d > deep:
				deep = d
				which = "%s %s" % [leg["name"], k]
	var hull := -INF
	for cs: Node in mech.get_children():
		if cs is CollisionShape3D and (cs as CollisionShape3D).shape is ConvexPolygonShape3D:
			var sxf := xf * (cs as CollisionShape3D).transform
			for q: Vector3 in ((cs as CollisionShape3D).shape as ConvexPolygonShape3D).points:
				var w := sxf * q
				hull = maxf(hull, surface(w.x, w.z) - w.y)
	var c := cam.global_position
	var eye: Vector3 = xf * cam.call("eye_point", mech)
	return [deep, which, hull, c.y - surface(c.x, c.z), eye.y - surface(eye.x, eye.z)]


## Plays `moves` ([[tick, action, strength or 0 to release]]) and watches for `ticks`; returns the counts.
func _play(moves: Array, ticks: int) -> Dictionary:
	var r := {"leg_frames": 0, "deepest": 0.0, "where": "", "hull": 0.0, "cam_frames": 0, "cam_min": INF, "eye_frames": 0, "eye_min": INF, "up_end": 0.0, "spin_end": 0.0}
	await physics_frames(360)
	for i in ticks:
		for m: Array in moves:
			if int(m[0]) == i:
				if float(m[2]) > 0.0:
					Input.action_press(str(m[1]), float(m[2]))
				else:
					Input.action_release(str(m[1]))
		await physics_frames(1)
		var t := _tick()
		if float(t[0]) > UNDER_M:
			r["leg_frames"] += 1
		if float(t[0]) > float(r["deepest"]):
			r["deepest"] = t[0]
			r["where"] = "%s at tick %d" % [t[1], i]
		r["hull"] = maxf(float(r["hull"]), float(t[2]))
		if float(t[3]) < CAM_CLEAR_M:
			r["cam_frames"] += 1
		r["cam_min"] = minf(float(r["cam_min"]), float(t[3]))
		if float(t[4]) < CAM_CLEAR_M:
			r["eye_frames"] += 1
		r["eye_min"] = minf(float(r["eye_min"]), float(t[4]))
		if i >= ticks - 120:
			# the last second: jitter is the spin's change reversing tick to tick (shaking), not a steady
			# roll down a slope or tipping on over from its side onto its back
			var w := mech.angular_velocity
			var d := w - (r.get("w_last", w) as Vector3)
			var step: Vector3 = r.get("step", Vector3.ZERO)
			if d.dot(step) < 0.0:
				r["jitter"] = float(r.get("jitter", 0.0)) + minf(d.length(), step.length())
			r["step"] = d
			r["w_last"] = w
			r["spin_change"] = float(r.get("spin_change", 0.0)) + d.length()
	r["up_end"] = mech.global_transform.basis.y.normalized().y
	r["spin_end"] = mech.angular_velocity.length()
	return r


## A charged jump let go with `stick` held (and crouch for a flip), after `run` ticks of `run_with`.
static func _jump_moves(stick: String, flip: bool, run: int, run_with: Array, strength: float = 1.0) -> Array:
	var out: Array = []
	for a: String in run_with:
		out.append([0, a, 1.0])
	out.append([run, "jump", 1.0])
	if stick != "":
		out.append([run + 110, stick, strength])
	if flip:
		out.append([run + 110, "crouch", 1.0])
	out.append([run + 150, "jump", 0.0])
	out.append([run + 152, "crouch", 0.0])
	for a: String in run_with + [stick]:
		if a != "":
			out.append([run + 160, a, 0.0])
	return out


func _scenario(kind: String, move: String) -> Dictionary:
	var start_z := 0.0
	if kind == "ramp":
		start_z = 30.0 if move == "slide" else -10.0
	var at := _ground(kind, start_z)
	_spawn(at)
	var moves: Array = []
	match move:
		"side_roll":
			moves = _jump_moves("strafe_left", true, 0, [])
		"half_roll":
			moves = _jump_moves("strafe_left", true, 0, [], 0.5)
		"half_flip":
			moves = _jump_moves("move_back", true, 0, [], 0.5)
		"flip_at_speed":
			moves = _jump_moves("move_forward", true, 180, ["move_forward", "sprint"])
		"landing":
			moves = _jump_moves("move_forward", false, 180, ["move_forward", "sprint"])
		"slide":
			moves = [[0, "move_forward", 1.0], [0, "sprint", 1.0], [240, "move_forward", 0.0], [240, "sprint", 0.0], [240, "brake", 1.0], [520, "brake", 0.0]]
	var r := await _play(moves, 1000)
	print(
		(
			"    %-8s %-13s legs under %3d ticks (deepest %.2f m, %s), hull %.2f m, camera low %3d (min %.2f m), cockpit eye low %3d (min %.2f m), up %.2f, spin %.2f rad/s, jitter %.2f rad/s per s (all spin change %.2f)"
			% [kind, move, r["leg_frames"], r["deepest"], r["where"], r["hull"], r["cam_frames"], r["cam_min"], r["eye_frames"], r["eye_min"], r["up_end"], r["spin_end"], r.get("jitter", 0.0), r["spin_change"]]
		)
	)
	return r


func _check(r: Dictionary, upright: bool = true) -> void:
	assert_eq(int(r["leg_frames"]), 0, "no foot, ankle or knee under the ground (deepest %.2f m, %s)" % [r["deepest"], r["where"]])
	assert_eq(int(r["cam_frames"]), 0, "the chase camera never at or under the ground (min %.2f m)" % r["cam_min"])
	assert_eq(int(r["eye_frames"]), 0, "the cockpit eye never at or under the ground (min %.2f m)" % r["eye_min"])
	assert_lt(float(r["hull"]), 0.1, "the hull does not sink into the ground (%.2f m)" % r["hull"])
	if upright:
		assert_gt(float(r["up_end"]), 0.8, "it ends on its feet (up %.2f)" % r["up_end"])
	assert_lt(float(r.get("jitter", 0.0)), 1.0, "no jitter: back-and-forth spin changes add up to under 1 rad/s over the last second (%.2f)" % r.get("jitter", 0.0))


func test_flat_side_roll() -> void:
	_check(await _scenario("flat", "side_roll"))


func test_flat_flip_at_speed() -> void:
	_check(await _scenario("flat", "flip_at_speed"))


func test_flat_landing() -> void:
	_check(await _scenario("flat", "landing"))


func test_flat_slide() -> void:
	_check(await _scenario("flat", "slide"))


func test_ramp_side_roll() -> void:
	_check(await _scenario("ramp", "side_roll"), false)  # a one-turn roll aimed for flat ground lands on its side here


func test_ramp_flip_at_speed() -> void:
	_check(await _scenario("ramp", "flip_at_speed"))


func test_ramp_landing() -> void:
	_check(await _scenario("ramp", "landing"))


func test_ramp_slide() -> void:
	_check(await _scenario("ramp", "slide"))


func test_palouse_side_roll() -> void:
	_check(await _scenario("palouse", "side_roll"))


func test_palouse_flip_at_speed() -> void:
	_check(await _scenario("palouse", "flip_at_speed"))


func test_palouse_landing() -> void:
	_check(await _scenario("palouse", "landing"))


func test_palouse_slide() -> void:
	_check(await _scenario("palouse", "slide"))


func test_flat_half_roll() -> void:
	_check(await _scenario("flat", "half_roll"), false)


func test_flat_half_flip() -> void:
	_check(await _scenario("flat", "half_flip"), false)


func test_ramp_half_roll() -> void:
	_check(await _scenario("ramp", "half_roll"), false)


func test_ramp_half_flip() -> void:
	_check(await _scenario("ramp", "half_flip"), false)


func test_palouse_half_roll() -> void:
	_check(await _scenario("palouse", "half_roll"), false)


func test_palouse_half_flip() -> void:
	_check(await _scenario("palouse", "half_flip"), false)


## The heightmap collider must hold the same surface the mesh draws, or feet planted on the collider
## float over or sink into the ground the player sees.
func test_palouse_collider_matches_the_drawn_ground() -> void:
	_ground("palouse", 0.0)
	await physics_frames(2)
	var space := world.get_world_3d().direct_space_state
	var worst := 0.0
	var worst_at := Vector2.ZERO
	var rng := RandomNumberGenerator.new()
	rng.seed = 38
	for i in 400:
		var x := PALOUSE_AT.x + rng.randf_range(-120.0, 120.0)
		var z := PALOUSE_AT.y + rng.randf_range(-120.0, 120.0)
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(x, 2000, z), Vector3(x, -2000, z), 1))
		if hit.is_empty():
			continue
		var d := absf((hit["position"] as Vector3).y - surface(x, z))
		if d > worst:
			worst = d
			worst_at = Vector2(x, z)
	print("    collider vs drawn ground: worst %.3f m at %s" % [worst, str(worst_at)])
	assert_lt(worst, 0.02, "collider within 2 cm of the drawn mesh (%.3f m)" % worst)


## Probe: the mech frozen in rolled poses resting on the ground, the chase camera at every aim pitch and
## free-look orbit; counts camera placements under the drawn ground or inside a collider.
func test_camera_poses() -> void:
	var bad := 0
	var total := 0
	var worst := ""
	var worst_c := INF
	for kind: String in ["flat", "ramp", "palouse"]:
		var at := _ground(kind, -10.0 if kind == "ramp" else 0.0)
		_spawn(at)
		await physics_frames(240)
		mech.freeze = true
		Settings.set_value("controls.mouse_mode", "camera", false)
		var poses := {"upright": Basis.IDENTITY, "side": Basis(Vector3.BACK, PI * 0.5), "back": Basis(Vector3.BACK, PI), "nose_down": Basis(Vector3.RIGHT, -PI * 0.5), "tail_down": Basis(Vector3.RIGHT, PI * 0.5)}
		for pose: String in poses:
			for yaw: float in [0.0, PI * 0.5, PI, PI * 1.5]:
				var b: Basis = Basis(Vector3.UP, yaw) * poses[pose]
				mech.global_transform = Transform3D(b, at + Vector3.UP * 3.0)
				# rest it on the ground: lift so the hull's deepest point is on the drawn surface
				var deepest := -INF
				for cs: Node in mech.get_children():
					if cs is CollisionShape3D and (cs as CollisionShape3D).shape is ConvexPolygonShape3D:
						var sxf := mech.global_transform * (cs as CollisionShape3D).transform
						for q: Vector3 in ((cs as CollisionShape3D).shape as ConvexPolygonShape3D).points:
							var w := sxf * q
							deepest = maxf(deepest, surface(w.x, w.z) - w.y)
				mech.global_position += Vector3.UP * (deepest + 0.02)
				for pitch: float in [-30.0, 0.0, 40.0, 75.0]:
					for orbit: Vector2 in [Vector2(0, 0), Vector2(0, -0.5), Vector2(PI * 0.5, -0.5), Vector2(PI, -0.5), Vector2(0, 0.9)]:
						mech.set("look_pitch_deg", pitch)
						cam.call("follow", mech)
						cam.set("_orbit", orbit)
						await physics_frames(20)
						mech.set("look_pitch_deg", pitch)
						var c := cam.global_position
						var clear := c.y - surface(c.x, c.z)
						var probe := PhysicsShapeQueryParameters3D.new()
						var ball := SphereShape3D.new()
						ball.radius = 0.1
						probe.shape = ball
						probe.transform = Transform3D(Basis.IDENTITY, c)
						probe.collision_mask = 1
						var inside := not world.get_world_3d().direct_space_state.intersect_shape(probe, 1).is_empty()
						total += 1
						if clear < CAM_CLEAR_M or inside:
							bad += 1
							if clear < worst_c:
								worst_c = clear
								worst = "%s %s yaw %.0f pitch %.0f orbit %s: clear %.2f inside %s" % [kind, pose, rad_to_deg(yaw), pitch, str(orbit), clear, inside]
		world.free()
		world = null
	print("    camera poses: %d of %d bad; worst %s" % [bad, total, worst])
	assert_eq(bad, 0, "camera never under the ground (%s)" % worst)


