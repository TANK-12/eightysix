extends Node3D
## Lane B5's big map, "Sector 86 frontier": 4 km built from its maps.json entry. The ground streams
## (BigTerrain + BigStream: 1 m tiles with their own colliders around every mech and the camera, an
## 8 m overview beyond), the river and lake share one water plane, the towns are laid out from
## data/town_styles.json with the asset kit. The player's Juggernaut, chase camera and HUD are set up
## as on the small map; look_from("<viewpoint>") parks a camera for check screenshots.

const MAP_ID := "big_map"
const MECH_ID := "juggernaut_m2"
const HUD_SCRIPT := preload("res://scripts/ui/test_hud.gd")
const GROUND_SHADER := preload("res://assets/kit/shaders/ground.gdshader")
const WATER_SHADER := preload("res://assets/kit/shaders/water.gdshader")
const TEX := "res://assets/kit/textures/"
const SMALL_MAP := preload("res://scripts/world/small_map.gd")  # its noise textures are shared
const PLACE_RANGE_M := 900.0  # town pieces beyond this are not drawn

var entry: Dictionary
var terrain: BigTerrain
var stream: BigStream
var sky: SmallMapSky
var mech: RigidBody3D
var camera: Camera3D
var hud: CanvasLayer
var view_camera: Camera3D
var mission: Mission
## World positions a wire anchor holds on well (ruin corners and tops).
var grapple_points: Array[Vector3] = []
var places: Array = []  # every placed kit node
var build_ms := {}


func _ready() -> void:
	entry = Registry.entry("maps", MAP_ID)
	var t0 := Time.get_ticks_msec()
	sky = SmallMapSky.new(self, str(entry.get("weather", "golden_afternoon")))
	sky.fog_scale = float(entry.get("fog_scale", 1.0))
	sky.apply(sky.weather_id)
	Sfx.loop(str(entry.get("ambience", "wind_loop")), self)
	Sfx.clear_reverb_zones()
	terrain = BigTerrain.new(entry)
	build_ms["terrain"] = Time.get_ticks_msec() - t0
	t0 = Time.get_ticks_msec()
	stream = BigStream.new()
	stream.name = "Ground"
	add_child(stream)
	stream.setup(terrain, _ground_material())
	_build_water()
	Backdrop.build(self, entry, load(TEX + "rock/color.jpg"), terrain.overview_height)
	build_ms["ground"] = Time.get_ticks_msec() - t0
	t0 = Time.get_ticks_msec()
	_build_towns()
	_build_outcrops()
	build_ms["places"] = Time.get_ticks_msec() - t0
	_spawn_mech()
	camera = Camera3D.new()
	camera.set_script(load("res://scripts/camera/chase_camera.gd"))
	add_child(camera)
	camera.call("follow", mech)
	hud = HUD_SCRIPT.new()
	add_child(hud)
	hud.call("watch", mech)
	if not Bot.active and DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	Game.register_level(self)


func _exit_tree() -> void:
	if sky != null:
		sky.disconnect_settings()


## The map's own mission, if it has one (none yet: free roam). Bot runs call it.
func start_mission(mission_id: String = "") -> void:
	if mission_id == "":
		mission_id = Mission.for_map(MAP_ID)
	if mission_id == "" or mission != null:
		return
	mission = Mission.start_in(self, mission_id)


func ground_height(x: float, z: float) -> float:
	return terrain.height_at(x, z)


## Bot hook: record the game's sound to <bot out folder>/<name>.wav between two calls.
func record_audio(on: bool, name: String = "sound") -> void:
	Sfx.record(on, Bot.out_dir.path_join(name + ".wav") if Bot.out_dir != "" else "")


func set_weather(id: String) -> void:
	sky.apply(id)


## Park a still camera at one of the entry's viewpoints (for screenshots); follow_mech() ends it.
## The ground streams around the parked camera too.
func look_from(viewpoint: String) -> void:
	var v: Dictionary = entry.get("viewpoints", {}).get(viewpoint, {})
	if v.is_empty():
		push_warning("big_map: no viewpoint '%s'" % viewpoint)
		return
	if view_camera == null:
		view_camera = Camera3D.new()
		view_camera.fov = 62.0
		view_camera.far = 6000.0
		view_camera.add_to_group("game_camera")
		add_child(view_camera)
	var eye := _v3(v["eye"])
	var look := _v3(v["look"])
	eye.y = maxf(eye.y, terrain.overview_height(eye.x, eye.z) + 2.0)
	view_camera.global_position = eye
	view_camera.look_at(look, Vector3.UP)
	view_camera.current = true


func follow_mech() -> void:
	camera.current = true


func _ground_material() -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = GROUND_SHADER
	mat.set_shader_parameter("ground_col", load(TEX + "ground/color.jpg"))
	mat.set_shader_parameter("ground_nrm", load(TEX + "ground/normal.jpg"))
	mat.set_shader_parameter("rock_col", load(TEX + "rock/color.jpg"))
	mat.set_shader_parameter("rock_nrm", load(TEX + "rock/normal.jpg"))
	mat.set_shader_parameter("town_col", load(TEX + "concrete/color.jpg"))
	mat.set_shader_parameter("town_nrm", load(TEX + "concrete/normal.jpg"))
	mat.set_shader_parameter("macro", SMALL_MAP._noise(false, 0.01, 7))
	mat.set_shader_parameter("water_level", terrain.water_level)
	return mat


func _build_water() -> void:
	var mat := ShaderMaterial.new()
	mat.shader = WATER_SHADER
	mat.set_shader_parameter("wave_a", SMALL_MAP._noise(true, 0.02, 3))
	mat.set_shader_parameter("wave_b", SMALL_MAP._noise(true, 0.05, 4))
	sky.water_mats.append(mat)
	sky.apply(sky.weather_id)
	var plane := PlaneMesh.new()
	plane.size = Vector2(terrain.size_m, terrain.size_m)
	plane.subdivide_width = 32
	plane.subdivide_depth = 32
	var mi := MeshInstance3D.new()
	mi.name = "Water"
	mi.mesh = plane
	mi.material_override = mat
	mi.position.y = terrain.water_level
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)


## Every town's buildings and extras (BigTowns), standing on the town's level ground.
func _build_towns() -> void:
	var holder := Node3D.new()
	holder.name = "Towns"
	add_child(holder)
	for town: Dictionary in entry.get("towns", []):
		for spec: Dictionary in BigTowns.layout(terrain, town):
			var over := {}
			if spec.has("damage"):
				over["damage"] = float(spec["damage"])
			var x := float(spec["at"][0])
			var z := float(spec["at"][1])
			var node := Kit.build(str(spec["kit"]), int(spec["seed"]), over)
			node.position = Vector3(x, terrain.overview_height(x, z) - 0.15, z)
			node.rotation.y = deg_to_rad(float(spec["rot"]))
			node.set_meta("town", spec["town"])
			holder.add_child(node)
			for gi: Node in node.find_children("*", "GeometryInstance3D", true, false):
				(gi as GeometryInstance3D).visibility_range_end = PLACE_RANGE_M
			for p: Vector3 in node.get_meta("anchors", []):
				grapple_points.append(node.transform * p)
			places.append(node)


## Rock outcrops over the hills (the entry's "outcrops" block): climbable, grapple points on top.
func _build_outcrops() -> void:
	var cfg: Dictionary = entry.get("outcrops", {})
	var rng := RandomNumberGenerator.new()
	rng.seed = int(cfg.get("seed", 1))
	var holder := Node3D.new()
	holder.name = "Outcrops"
	add_child(holder)
	var inner := terrain.half - float(entry.get("terrain", {}).get("rim_width_m", 340.0)) * 0.6
	var sz: Array = cfg.get("size_m", [10.0, 26.0])
	var max_slope := cos(deg_to_rad(float(cfg.get("max_slope_deg", 28.0))))
	for i in int(cfg.get("count", 0)):
		var x := rng.randf_range(-inner, inner)
		var z := rng.randf_range(-inner, inner)
		var size := rng.randf_range(float(sz[0]), float(sz[1]))
		if terrain.road_edge_at(x, z) < size + 6.0 or terrain.water_edge_at(x, z) < size + 12.0:
			continue
		var e := 8.0
		var nrm := Vector3(terrain.overview_height(x - e, z) - terrain.overview_height(x + e, z), 2.0 * e, terrain.overview_height(x, z - e) - terrain.overview_height(x, z + e)).normalized()
		if nrm.y < max_slope or terrain.splat_at(x, z).a > 0.05:
			continue
		var low := terrain.overview_height(x, z)
		for d: Vector2 in [Vector2(1, 1), Vector2(-1, 1), Vector2(1, -1), Vector2(-1, -1)]:
			low = minf(low, terrain.overview_height(x + d.x * size * 0.4, z + d.y * size * 0.4))
		var node := Kit.build("outcrop", i, {"size": size})
		node.position = Vector3(x, low, z)
		node.rotation.y = rng.randf() * TAU
		holder.add_child(node)
		for gi: Node in node.find_children("*", "GeometryInstance3D", true, false):
			(gi as GeometryInstance3D).visibility_range_end = 1800.0
		for p: Vector3 in node.get_meta("anchors", []):
			grapple_points.append(node.transform * p)
		places.append(node)


func _spawn_mech() -> void:
	mech = MechBuilder.build(MECH_ID)
	var spawn: Dictionary = entry.get("spawn", {})
	var p: Array = spawn.get("position", [0.0, 0.0, 0.0])
	var x := float(p[0])
	var z := float(p[2])
	stream.prime(Vector3(x, 0.0, z))
	mech.position = Vector3(x, terrain.height_at(x, z) + 3.2, z)
	mech.rotation.y = deg_to_rad(-float(spawn.get("heading_deg", 0.0)))
	add_child(mech)


func _v3(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))
