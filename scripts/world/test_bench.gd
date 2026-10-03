extends "res://scripts/world/test_range.gd"
## Lane B6: the two test bench grounds. Same sky, chase camera and test HUD as the test range, but the
## ground is a measuring surface: "flat" is a level concrete pad with painted marks every few metres
## and two ramps, "rough" is a noise rock field with steps and boulders. The mech on it is whatever
## Settings bench.design says, and the physics mode is switched to the test bench for as long as the
## map is open (the setting you had comes back when you leave). Sizes and counts: data/bench.json "grounds".

const GROUND_COLOUR := Color(0.72, 0.72, 0.7)

@export var map_id := "test_bench_flat"

var spec: Dictionary = {}
var size_m := 400
var _mode_before := ""


func _ready() -> void:
	spec = Registry.file("bench").get("grounds", {}).get(map_id.trim_prefix("test_bench_"), {})
	size_m = int(spec.get("size_m", 400.0))
	_mode_before = Settings.get_s("gameplay.physics_mode")
	Settings.set_value("gameplay.physics_mode", "bench", false)
	_build_environment()
	if map_id == "test_bench_rough":
		_build_rough()
	else:
		_build_flat()
	_spawn_mech()
	camera = Camera3D.new()
	camera.set_script(load("res://scripts/camera/chase_camera.gd"))
	add_child(camera)
	camera.call("follow", mech)
	hud = HUD_SCRIPT.new()
	add_child(hud)
	hud.call("watch", mech)
	capture_mouse()
	Game.register_level(self)


func _exit_tree() -> void:
	if _mode_before != "":
		Settings.set_value("gameplay.physics_mode", _mode_before, false)


func _map_id() -> String:
	return map_id


func ground_height(x: float, z: float) -> float:
	if map_id == "test_bench_rough":
		return TerrainGen.height_at(grid, size_m, x, z)
	return 0.0


func _spawn_mech() -> void:
	mech = MechBuilder.build(Settings.get_s("bench.design"))
	var spawn: Dictionary = Registry.entry("maps", map_id).get("spawn", {})
	var p: Array = spawn.get("position", [0.0, 0.0, 0.0])
	mech.position = Vector3(float(p[0]), ground_height(float(p[0]), float(p[2])) + 3.2, float(p[2]))
	mech.rotation.y = deg_to_rad(-float(spawn.get("heading_deg", 0.0)))
	add_child(mech)


## A kit texture set (assets/kit/textures/<folder>) projected from all three sides, `tile_m` metres a tile.
func _surface_material(folder: String, tint: Color, tile_m: float) -> StandardMaterial3D:
	var dir := "res://assets/kit/textures/" + folder + "/"
	var mat := StandardMaterial3D.new()
	mat.albedo_color = tint
	mat.albedo_texture = load(dir + "color.jpg")
	mat.normal_enabled = true
	mat.normal_texture = load(dir + "normal.jpg")
	mat.roughness = 1.0
	mat.uv1_triplanar = true
	mat.uv1_world_triplanar = true
	mat.uv1_scale = Vector3.ONE / tile_m
	mat.uv1_triplanar_sharpness = 4.0
	return mat


func _solid(at: Vector3, size: Vector3, rot: Vector3, mat: Material, layer: int = 1 | 64) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = layer
	body.position = at
	body.rotation = rot
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mi.mesh = box
	mi.material_override = mat
	body.add_child(mi)
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	cs.shape = shape
	body.add_child(cs)
	add_child(body)
	return body


## A level pad (top at y 0), a painted line every mark_every_m along and across it (a long one every
## fifth), and two ramps of ramp_deg, one up and one down, ahead of the spawn.
func _build_flat() -> void:
	var slab := Vector3(size_m, 2.0, size_m)
	_solid(Vector3(0.0, -1.0, 0.0), slab, Vector3.ZERO, _surface_material("concrete_stained", GROUND_COLOUR, 4.0))
	var paint := StandardMaterial3D.new()
	paint.albedo_color = Color(0.92, 0.9, 0.82)
	paint.roughness = 0.8
	var step := float(spec.get("mark_every_m", 10.0))
	var half := size_m * 0.5
	var n := int(half / step)
	for i in range(-n, n + 1):
		var long_mark := i % 5 == 0
		var width := 0.5 if long_mark else 0.25
		var at := i * step
		_paint_strip(Vector3(0.0, 0.01, at), Vector3(size_m if long_mark else 12.0, 0.02, width), paint)
		_paint_strip(Vector3(at, 0.01, 0.0), Vector3(width, 0.02, size_m if long_mark else 12.0), paint)
	var ramp_deg := float(spec.get("ramp_deg", 8.0))
	var ramp_len := 40.0
	var rise := sin(deg_to_rad(ramp_deg)) * ramp_len
	var ramp_mat := _surface_material("concrete_stained", Color(0.8, 0.7, 0.52), 3.0)
	_solid(Vector3(-24.0, rise * 0.5 - 0.1, -60.0), Vector3(16.0, 1.0, ramp_len), Vector3(deg_to_rad(ramp_deg), 0.0, 0.0), ramp_mat)
	_solid(Vector3(24.0, rise * 0.5 - 0.1, -60.0), Vector3(16.0, 1.0, ramp_len), Vector3(-deg_to_rad(ramp_deg), 0.0, 0.0), ramp_mat)


func _paint_strip(at: Vector3, size: Vector3, mat: Material) -> void:
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mi.mesh = box
	mi.material_override = mat
	mi.position = at
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)


## The same height grid and mesh as the test range, scaled to amplitude_m peak to peak and flattened
## to a pad round the spawn, then five steps of step_height_m ahead of it and `boulders` loose-looking rocks.
func _build_rough() -> void:
	grid = TerrainGen.heights(size_m, int(spec.get("seed", 8620)))
	var n := size_m + 1
	var half := size_m * 0.5
	var lo := INF
	var hi := -INF
	for zi in n:
		for xi in n:
			if Vector2(xi - half, zi - half).length() < 150.0:
				var h0: float = grid[zi * n + xi]
				lo = minf(lo, h0)
				hi = maxf(hi, h0)
	var scale_to := float(spec.get("amplitude_m", 1.6)) / maxf(hi - lo, 0.001)
	var spawn_h := grid[n * (n / 2) + n / 2] * scale_to
	for zi in n:
		for xi in n:
			var r := Vector2(xi - half, zi - half).length()
			var h := grid[zi * n + xi] * scale_to
			grid[zi * n + xi] = lerpf(spawn_h, h, smoothstep(16.0, 40.0, r)) - spawn_h
	var mesh_node := MeshInstance3D.new()
	mesh_node.name = "Terrain"
	mesh_node.mesh = TerrainGen.build_mesh(grid, size_m)
	mesh_node.material_override = GroundLook.material(Registry.entry("maps", map_id), -1000.0)
	add_child(mesh_node)
	var body := StaticBody3D.new()
	body.name = "TerrainBody"
	body.collision_layer = 1 | 64
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	shape.shape = TerrainGen.build_shape(grid, size_m)
	body.add_child(shape)
	add_child(body)
	_build_steps()
	_build_boulders()


func _build_steps() -> void:
	var count := int(spec.get("steps", 5))
	var rise := float(spec.get("step_height_m", 0.35))
	var mat := _surface_material("concrete_stained", Color(0.78, 0.76, 0.72), 3.0)
	for i in count:
		var top := rise * (i + 1)
		var z := -50.0 - 6.0 * i
		_solid(Vector3(0.0, ground_height(0.0, z) + top * 0.5 - 0.05, z), Vector3(14.0, top, 6.0), Vector3.ZERO, mat)


func _build_boulders() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = int(spec.get("seed", 8620))
	var mat := _surface_material("rock", Color(0.7, 0.68, 0.64), 3.0)
	var count := int(spec.get("boulders", 40))
	var placed := 0
	while placed < count:
		var x := rng.randf_range(-size_m * 0.42, size_m * 0.42)
		var z := rng.randf_range(-size_m * 0.42, size_m * 0.42)
		if Vector2(x, z).length() < 24.0:
			continue
		var s := rng.randf_range(0.6, 2.6)
		var size := Vector3(s * rng.randf_range(0.9, 1.5), s * rng.randf_range(0.55, 0.9), s * rng.randf_range(0.9, 1.4))
		var rock := TerrainGen.rock_mesh(8620 + placed, size)
		var rb := StaticBody3D.new()
		rb.collision_layer = 1 | 64
		rb.position = Vector3(x, ground_height(x, z) + size.y * 0.18, z)
		rb.rotation = Vector3(rng.randf_range(-0.2, 0.2), rng.randf_range(0.0, TAU), rng.randf_range(-0.2, 0.2))
		var mi := MeshInstance3D.new()
		mi.mesh = rock
		mi.material_override = mat
		rb.add_child(mi)
		var cs := CollisionShape3D.new()
		cs.shape = rock.create_convex_shape(true, true)
		rb.add_child(cs)
		add_child(rb)
		placed += 1
