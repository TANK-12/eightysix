extends Node3D
## Lane B3's small map, "Ashen valley": about 1 km of valley built from its maps.json entry and the
## asset kit. Ground chunks (a fine mesh near, a coarse one far) over one height-field collider, the
## river and lake, the ruined town, the broken bridge, the mast, tank-trap lines, outcrops to climb,
## scatter, mist over the water, and the weather. The player's Juggernaut, chase camera and HUD are
## set up the same way as the test range's. look_from("<viewpoint>") parks a camera at one of the
## entry's viewpoints (the bot uses it for check screenshots); follow_mech() goes back.

const MAP_ID := "small_map"
const MECH_ID := "juggernaut_m2"
const HUD_SCRIPT := preload("res://scripts/ui/test_hud.gd")
const GROUND_SHADER := preload("res://assets/kit/shaders/ground.gdshader")
const WATER_SHADER := preload("res://assets/kit/shaders/water.gdshader")
const TEX := "res://assets/kit/textures/"

var entry: Dictionary
var terrain: SmallMapTerrain
var sky: SmallMapSky
var scatter: SmallMapScatter
var mech: RigidBody3D
var camera: Camera3D
var hud: CanvasLayer
var view_camera: Camera3D
## World positions a wire anchor holds on well: outcrop tops, the mast, ruin corners, the bridge.
var grapple_points: Array[Vector3] = []
var build_ms := {}


func _ready() -> void:
	entry = Registry.entry("maps", MAP_ID)
	var t0 := Time.get_ticks_msec()
	sky = SmallMapSky.new(self, str(entry.get("weather", "overcast_morning")))
	terrain = SmallMapTerrain.new(entry)
	build_ms["terrain"] = Time.get_ticks_msec() - t0
	t0 = Time.get_ticks_msec()
	_build_ground()
	_build_water()
	build_ms["ground"] = Time.get_ticks_msec() - t0
	t0 = Time.get_ticks_msec()
	var avoid := _build_places()
	build_ms["places"] = Time.get_ticks_msec() - t0
	t0 = Time.get_ticks_msec()
	scatter = SmallMapScatter.new(self, terrain, entry, avoid)
	build_ms["scatter"] = Time.get_ticks_msec() - t0
	_build_mist()
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
	if sky != null:
		sky.disconnect_settings()
	if scatter != null:
		scatter.disconnect_settings()


func capture_mouse() -> void:
	if not Bot.active and DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func ground_height(x: float, z: float) -> float:
	return terrain.height_at(x, z)


func set_weather(id: String) -> void:
	sky.apply(id)


## Park a still camera at one of the entry's viewpoints (for screenshots); follow_mech() ends it.
func look_from(viewpoint: String) -> void:
	var v: Dictionary = entry.get("viewpoints", {}).get(viewpoint, {})
	if v.is_empty():
		push_warning("small_map: no viewpoint '%s'" % viewpoint)
		return
	if view_camera == null:
		view_camera = Camera3D.new()
		view_camera.fov = 62.0
		view_camera.add_to_group("game_camera")
		add_child(view_camera)
	var eye := _v3(v["eye"])
	var look := _v3(v["look"])
	eye.y = maxf(eye.y, ground_height(eye.x, eye.z) + 2.0)
	view_camera.global_position = eye
	view_camera.look_at(look, Vector3.UP)
	view_camera.current = true


## Measuring aid for frame-rate work (bot scripts call it): switch one part of the map on or off.
## Parts: ground_plain, mist, water, grass, shrubs, pebbles, solids, terrain_shadows, shrub_shadows, splits2.
func probe(part: String, on: bool) -> void:
	match part:
		"ground_plain":
			if not has_meta("ground_mat"):
				set_meta("ground_mat", (get_node("Ground").get_child(0) as GeometryInstance3D).material_override)
			var plain := StandardMaterial3D.new()
			plain.albedo_color = Color(0.4, 0.37, 0.3)
			for n in get_node("Ground").get_children():
				(n as GeometryInstance3D).material_override = get_meta("ground_mat") if on else plain
		"mist":
			for n in get_children():
				if n is FogVolume:
					n.visible = on
		"water":
			get_node("Water").visible = on
		"terrain_shadows":
			for n in get_node("Ground").get_children():
				(n as GeometryInstance3D).cast_shadow = (
					GeometryInstance3D.SHADOW_CASTING_SETTING_ON if on else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				)
		"splits2":
			sky.sun.directional_shadow_mode = (
				DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS if on else DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
			)
		_:
			for n in get_node("Scatter").get_children():
				if n.get_meta("kind", "") == part or (part == "solids" and n is StaticBody3D):
					n.visible = on
				elif part == "shrub_shadows" and n.get_meta("kind", "") == "shrub":
					(n as GeometryInstance3D).cast_shadow = (
						GeometryInstance3D.SHADOW_CASTING_SETTING_ON if on else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
					)


func follow_mech() -> void:
	camera.current = true


func _v3(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


# --- ground and water ------------------------------------------------------------------------


func _build_ground() -> void:
	var mat := ShaderMaterial.new()
	mat.shader = GROUND_SHADER
	mat.set_shader_parameter("splat", ImageTexture.create_from_image(terrain.splat))
	mat.set_shader_parameter("splat_half", terrain.half)
	mat.set_shader_parameter("splat_n", float(terrain.n))
	mat.set_shader_parameter("ground_col", load(TEX + "ground/color.jpg"))
	mat.set_shader_parameter("ground_nrm", load(TEX + "ground/normal.jpg"))
	mat.set_shader_parameter("rock_col", load(TEX + "rock/color.jpg"))
	mat.set_shader_parameter("rock_nrm", load(TEX + "rock/normal.jpg"))
	mat.set_shader_parameter("town_col", load(TEX + "concrete/color.jpg"))
	mat.set_shader_parameter("town_nrm", load(TEX + "concrete/normal.jpg"))
	mat.set_shader_parameter("macro", _noise(false, 0.01, 7))
	mat.set_shader_parameter("water_level", terrain.water_level)
	var holder := Node3D.new()
	holder.name = "Ground"
	add_child(holder)
	var chunks := terrain.chunk_count()
	var c := SmallMapTerrain.CHUNK_M
	for cz in chunks:
		for cx in chunks:
			var begin := 0.0
			for lod: Array in SmallMapTerrain.LODS:
				# neighbouring rings overlap by 8 m: the skirts move a coarse chunk's box centre down a
				# little, and without the overlap a chunk could fall between two rings (a hole to the water)
				var mi := MeshInstance3D.new()
				mi.mesh = terrain.chunk_mesh(cx * c, cz * c, int(lod[0]))
				mi.material_override = mat
				mi.visibility_range_begin = maxf(begin - 8.0, 0.0) if begin > 0.0 else 0.0
				mi.visibility_range_end = float(lod[1]) + 8.0 if float(lod[1]) > 0.0 else 0.0
				if begin > 0.0:
					mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if int(lod[0]) > 2 else GeometryInstance3D.SHADOW_CASTING_SETTING_ON
				holder.add_child(mi)
				begin = float(lod[1])
	var body := StaticBody3D.new()
	body.name = "GroundBody"
	body.collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	shape.shape = terrain.build_shape()
	body.add_child(shape)
	add_child(body)


func _build_water() -> void:
	var mat := ShaderMaterial.new()
	mat.shader = WATER_SHADER
	mat.set_shader_parameter("wave_a", _noise(true, 0.02, 3))
	mat.set_shader_parameter("wave_b", _noise(true, 0.05, 4))
	var plane := PlaneMesh.new()
	plane.size = Vector2(terrain.size_m, terrain.size_m)
	plane.subdivide_width = 8
	plane.subdivide_depth = 8
	var mi := MeshInstance3D.new()
	mi.name = "Water"
	mi.mesh = plane
	mi.material_override = mat
	mi.position.y = terrain.water_level
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)


# --- places from the entry -------------------------------------------------------------------


## Buildings, structures, the bridge, tank traps and outcrops. Returns the footprints scatter avoids.
func _build_places() -> Array[Rect2]:
	var avoid: Array[Rect2] = []
	var holder := Node3D.new()
	holder.name = "Places"
	add_child(holder)
	for b: Dictionary in entry.get("buildings", []):
		var node := _place(holder, b, {"damage": float(b.get("damage", 0.4))}, true)
		var fp: Array = Kit.entry(str(b["kit"])).get("footprint_m", [8, 8])
		var r := maxf(float(fp[0]), float(fp[1])) * 0.75
		var at: Array = b["at"]
		avoid.append(Rect2(float(at[0]) - r, float(at[1]) - r, r * 2.0, r * 2.0))
		_anchors_of(node)
	for s: Dictionary in entry.get("structures", []):
		var over := {}
		if s.has("damage"):
			over["damage"] = float(s["damage"])
		var node := _place(holder, s, over, false)
		var at: Array = s["at"]
		avoid.append(Rect2(float(at[0]) - 4.0, float(at[1]) - 4.0, 8.0, 8.0))
		_anchors_of(node)
	for br: Dictionary in entry.get("bridges", []):
		_bridge(holder, br, avoid)
	for line: Dictionary in entry.get("tank_trap_lines", []):
		var a := _v2(line["from"])
		var b := _v2(line["to"])
		var cnt := int(line.get("count", 6))
		for i in cnt:
			var p := a.lerp(b, (i + 0.5) / cnt)
			var node := Kit.build("tank_trap", i)
			node.position = Vector3(p.x, ground_height(p.x, p.y), p.y)
			node.rotation.y = float(i) * 0.9
			holder.add_child(node)
	for o: Array in entry.get("outcrops", []):
		var x := float(o[0])
		var z := float(o[1])
		var node := Kit.build("outcrop", int(x * 7 + z), {"size": float(o[2])})
		node.position = Vector3(x, _lowest(x, z, float(o[2]) * 0.4), z)
		node.rotation.y = fmod(x * 0.37 + z * 0.11, TAU)
		holder.add_child(node)
		avoid.append(Rect2(x - o[2] * 0.6, z - o[2] * 0.6, o[2] * 1.2, o[2] * 1.2))
		_anchors_of(node)
	return avoid


func _place(holder: Node3D, spec: Dictionary, over: Dictionary, flat: bool) -> Node3D:
	var at: Array = spec["at"]
	var x := float(at[0])
	var z := float(at[1])
	var node := Kit.build(str(spec["kit"]), int(spec.get("seed", x * 13 + z)), over)
	var y := _lowest(x, z, 4.0) - 0.15 if flat else ground_height(x, z)
	node.position = Vector3(x, y, z)
	node.rotation.y = deg_to_rad(float(spec.get("rot", 0.0)))
	holder.add_child(node)
	return node


func _bridge(holder: Node3D, br: Dictionary, avoid: Array[Rect2]) -> void:
	var a := _v2(br["from"])
	var b := _v2(br["to"])
	var ha := ground_height(a.x, a.y) + 0.4
	var hb := ground_height(b.x, b.y) + 0.4
	var over := {
		"length_m": a.distance_to(b),
		"end_heights": [0.0, hb - ha],
		"broken_spans": br.get("broken_spans", []),
		"fallen": bool(br.get("fallen", false)),
		"pillar_drop_m": maxf(ha - terrain.water_level + 4.0, 6.0),
	}
	var node := Kit.build(str(br.get("kit", "bridge")), 1, over)
	node.position = Vector3(a.x, ha, a.y)
	node.rotation.y = -atan2(b.y - a.y, b.x - a.x)
	holder.add_child(node)
	_anchors_of(node)
	var mid := (a + b) * 0.5
	avoid.append(Rect2(mid.x - 10.0, mid.y - 10.0, 20.0, 20.0))


func _anchors_of(node: Node3D) -> void:
	for p: Vector3 in node.get_meta("anchors", []):
		grapple_points.append(node.transform * p)


func _lowest(x: float, z: float, r: float) -> float:
	var h := ground_height(x, z)
	for d: Vector2 in [Vector2(r, r), Vector2(-r, r), Vector2(r, -r), Vector2(-r, -r)]:
		h = minf(h, ground_height(x + d.x, z + d.y))
	return h


func _v2(a: Array) -> Vector2:
	return Vector2(float(a[0]), float(a[1]))


func _build_mist() -> void:
	for m: Dictionary in entry.get("mist", []):
		var at := _v2(m["at"])
		var size: Array = m.get("size_m", [60, 10, 60])
		var fog := FogVolume.new()
		fog.size = Vector3(float(size[0]), float(size[1]), float(size[2]))
		fog.shape = RenderingServer.FOG_VOLUME_SHAPE_ELLIPSOID
		var mat := FogMaterial.new()
		mat.density = 0.05
		mat.albedo = Color(0.85, 0.87, 0.88)
		mat.edge_fade = 0.6
		fog.material = mat
		fog.position = Vector3(at.x, terrain.water_level + float(size[1]) * 0.25, at.y)
		add_child(fog)


func _spawn_mech() -> void:
	mech = MechBuilder.build(MECH_ID)
	var spawn: Dictionary = entry.get("spawn", {})
	var p: Array = spawn.get("position", [0.0, 0.0, 0.0])
	var x := float(p[0])
	var z := float(p[2])
	mech.position = Vector3(x, ground_height(x, z) + 3.2, z)
	mech.rotation.y = deg_to_rad(-float(spawn.get("heading_deg", 0.0)))
	add_child(mech)


static func _noise(normal: bool, frequency: float, seed_value: int) -> NoiseTexture2D:
	var noise := FastNoiseLite.new()
	noise.seed = seed_value
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
		tex.bump_strength = 4.0
	return tex
