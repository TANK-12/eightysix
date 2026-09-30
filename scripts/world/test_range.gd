extends Node3D
## Lane A1's throwaway test range: rocky noise terrain with real collision, loose boulders, a few
## concrete slabs to climb and jump at, a sky, sun and fog that follow the graphics presets, the
## stand-in walker, the chase camera and a test HUD. Proves the loop runs end to end and gives the
## frame-rate logger something to draw.

const SIZE_M := 320
const SEED := 8606
const ROCKS := 46
const MECH_ID := "juggernaut_m2"
const HUD_SCRIPT := preload("res://scripts/ui/test_hud.gd")
const TERRAIN_SHADER := preload("res://assets/shaders/terrain.gdshader")

var grid := PackedFloat32Array()
var mech: RigidBody3D
var camera: Camera3D
var hud: CanvasLayer


func _ready() -> void:
	_build_environment()
	grid = TerrainGen.heights(SIZE_M, SEED)
	_build_terrain()
	_build_rocks()
	_build_slabs()
	_build_targets()
	_build_gantry()
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


func capture_mouse() -> void:
	if not Bot.active and DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func ground_height(x: float, z: float) -> float:
	return TerrainGen.height_at(grid, SIZE_M, x, z)


func _build_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.19, 0.31, 0.47)
	sky_mat.sky_horizon_color = Color(0.63, 0.66, 0.68)
	sky_mat.sky_curve = 0.11
	sky_mat.ground_horizon_color = Color(0.5, 0.5, 0.47)
	sky_mat.ground_bottom_color = Color(0.13, 0.12, 0.1)
	sky_mat.sun_angle_max = 24.0
	var sky := Sky.new()
	sky.sky_material = sky_mat
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.9
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.05
	env.fog_enabled = true
	env.fog_light_color = Color(0.58, 0.62, 0.66)
	env.fog_density = 0.0009
	env.fog_aerial_perspective = 0.45
	env.fog_sky_affect = 0.25
	env.volumetric_fog_density = 0.008
	env.volumetric_fog_albedo = Color(0.82, 0.84, 0.87)
	env.volumetric_fog_length = 160.0
	env.volumetric_fog_ambient_inject = 0.35
	env.ssao_radius = 1.6
	env.ssao_intensity = 1.6
	env.glow_intensity = 0.55
	env.glow_bloom = 0.04
	env.sdfgi_use_occlusion = true
	env.sdfgi_cascades = 4
	var world_env := WorldEnvironment.new()
	world_env.environment = env
	world_env.add_to_group("world_environment")
	add_child(world_env)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-36.0, 38.0, 0.0)
	sun.light_energy = 1.2
	sun.light_color = Color(1.0, 0.95, 0.87)
	sun.light_angular_distance = 0.6
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.add_to_group("sun")
	add_child(sun)


func _build_terrain() -> void:
	var mesh_node := MeshInstance3D.new()
	mesh_node.name = "Terrain"
	mesh_node.mesh = TerrainGen.build_mesh(grid, SIZE_M)
	var mat := ShaderMaterial.new()
	mat.shader = TERRAIN_SHADER
	mat.set_shader_parameter("noise_tex", _noise_texture(false, 0.012))
	mat.set_shader_parameter("noise_normal", _noise_texture(true, 0.03))
	mesh_node.material_override = mat
	add_child(mesh_node)
	var body := StaticBody3D.new()
	body.name = "TerrainBody"
	body.collision_layer = 1 | 64
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	shape.shape = TerrainGen.build_shape(grid, SIZE_M)
	body.add_child(shape)
	add_child(body)


func _build_rocks() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = SEED
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.46, 0.44, 0.41)
	mat.albedo_texture = _noise_texture(false, 0.05)
	mat.normal_enabled = true
	mat.normal_texture = _noise_texture(true, 0.09)
	mat.normal_scale = 1.4
	mat.roughness = 0.9
	mat.uv1_triplanar = true
	mat.uv1_scale = Vector3(0.6, 0.6, 0.6)
	var placed := 0
	while placed < ROCKS:
		var x := rng.randf_range(-SIZE_M * 0.42, SIZE_M * 0.42)
		var z := rng.randf_range(-SIZE_M * 0.42, SIZE_M * 0.42)
		if Vector2(x, z).length() < 22.0:
			continue
		var s := rng.randf_range(0.8, 4.2)
		var size := Vector3(s * rng.randf_range(0.9, 1.5), s * rng.randf_range(0.55, 0.9), s * rng.randf_range(0.9, 1.4))
		var mesh := TerrainGen.rock_mesh(SEED + placed, size)
		var body := StaticBody3D.new()
		body.collision_layer = 1 | 64
		body.collision_mask = 0
		body.position = Vector3(x, ground_height(x, z) + size.y * 0.18, z)
		body.rotation = Vector3(rng.randf_range(-0.2, 0.2), rng.randf_range(0.0, TAU), rng.randf_range(-0.2, 0.2))
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = mat
		body.add_child(mi)
		var cs := CollisionShape3D.new()
		cs.shape = mesh.create_convex_shape(true, true)
		body.add_child(cs)
		add_child(body)
		placed += 1


func _build_slabs() -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.56, 0.55, 0.52)
	mat.albedo_texture = _noise_texture(false, 0.2)
	mat.roughness = 0.85
	mat.uv1_triplanar = true
	mat.uv1_scale = Vector3(0.3, 0.3, 0.3)
	var slabs := [
		[Vector3(34.0, 0.0, -30.0), Vector3(14.0, 2.4, 14.0), 0.0, 0.0],
		[Vector3(-40.0, 0.0, -24.0), Vector3(22.0, 4.5, 2.0), 0.3, 0.0],
		[Vector3(10.0, 0.0, 44.0), Vector3(10.0, 1.2, 26.0), -0.1, 12.0],
		[Vector3(-26.0, 0.0, 40.0), Vector3(6.0, 7.0, 6.0), 0.8, 0.0],
	]
	for s: Array in slabs:
		var at: Vector3 = s[0]
		var size: Vector3 = s[1]
		var body := StaticBody3D.new()
		body.collision_layer = 1 | 64
		body.position = Vector3(at.x, ground_height(at.x, at.z) + size.y * 0.5 - 0.6, at.z)
		body.rotation = Vector3(deg_to_rad(float(s[3])), float(s[2]), 0.0)
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


## Lane A3's firing line: loose steel plates 70-145 m downrange of the spawn; a round's momentum
## knocks them flat.
func _build_targets() -> void:
	var steel := StandardMaterial3D.new()
	steel.albedo_color = Color(0.72, 0.2, 0.12)
	steel.metallic = 0.6
	steel.roughness = 0.45
	var plates := [Vector2(-10.0, -70.0), Vector2(6.0, -90.0), Vector2(-4.0, -110.0), Vector2(16.0, -130.0), Vector2(-18.0, -145.0)]
	for i in plates.size():
		var at: Vector2 = plates[i]
		var body := RigidBody3D.new()
		body.name = "Target%d" % i
		body.mass = 400.0
		body.collision_layer = 1
		body.collision_mask = 1 | 16
		var size := Vector3(2.4, 4.5, 0.25)  # taller than the muzzle (2.9 m) so a level shot hits
		body.position = Vector3(at.x, ground_height(at.x, at.y) + size.y * 0.5 + 0.2, at.y)
		var mi := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = size
		mi.mesh = box
		mi.material_override = steel
		body.add_child(mi)
		var cs := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = size
		cs.shape = shape
		body.add_child(cs)
		add_child(body)


## Lane A3's wire-anchor gantry ahead of the spawn: two pillars and a beam 20 m up. Only the beam
## is a grapple surface (layer 64), so the anchor's upward fan skips the pillars and bites the beam.
func _build_gantry() -> void:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.3, 0.31, 0.3)
	mat.metallic = 0.7
	mat.roughness = 0.5
	var z := -38.0
	var base := ground_height(0.0, z)
	var parts := [
		[Vector3(-9.0, base + 10.0, z), Vector3(1.6, 22.0, 1.6), 1],
		[Vector3(9.0, base + 10.0, z), Vector3(1.6, 22.0, 1.6), 1],
		[Vector3(0.0, base + 20.0, z), Vector3(20.0, 1.6, 2.0), 1 | 64],
	]
	for part: Array in parts:
		var body := StaticBody3D.new()
		body.collision_layer = int(part[2])
		body.position = part[0]
		var mi := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = part[1]
		mi.mesh = box
		mi.material_override = mat
		body.add_child(mi)
		var cs := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = part[1]
		cs.shape = shape
		body.add_child(cs)
		add_child(body)


func _spawn_mech() -> void:
	mech = MechBuilder.build(MECH_ID)
	var spawn: Dictionary = Registry.entry("maps", "test_range").get("spawn", {})
	var p: Array = spawn.get("position", [0.0, 10.0, 0.0])
	var x := float(p[0])
	var z := float(p[2])
	mech.position = Vector3(x, ground_height(x, z) + 3.2, z)
	mech.rotation.y = deg_to_rad(-float(spawn.get("heading_deg", 0.0)))
	add_child(mech)


static func _noise_texture(normal: bool, frequency: float) -> NoiseTexture2D:
	var noise := FastNoiseLite.new()
	noise.frequency = frequency
	noise.fractal_octaves = 5
	var tex := NoiseTexture2D.new()
	tex.width = 512
	tex.height = 512
	tex.seamless = true
	tex.noise = noise
	tex.generate_mipmaps = true
	if normal:
		tex.as_normal_map = true
		tex.bump_strength = 6.0
	return tex
