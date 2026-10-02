extends "res://tests/lib/test_case.gd"
## The world look pass (lane LOOK): each map's palette names real shader uniforms and real kit materials, the
## two maps are painted differently, the ground and wall shaders get all their textures, and the look-pass bots
## only ask for viewpoints that exist.

const MAPS := ["small_map", "big_map"]


## The uniform names a shader file declares (read from its source: no GPU needed).
func _uniforms(path: String) -> PackedStringArray:
	var out := PackedStringArray()
	var re := RegEx.new()
	re.compile("(?m)^uniform\\s+[\\w]+\\s+(\\w+)")
	for m in re.search_all(FileAccess.get_file_as_string(path)):
		out.append(m.get_string(1))
	return out


func test_palette_names_real_uniforms_and_materials() -> void:
	var ground := _uniforms("res://assets/kit/shaders/ground.gdshader")
	var kit_materials: Dictionary = Registry.file("kit").get("materials", {})
	for id: String in MAPS:
		var palette: Dictionary = Registry.entry("maps", id).get("palette", {})
		assert_false(palette.is_empty(), id + " has a palette")
		for u: String in palette.get("ground", {}):
			assert_true(u in ground, "%s palette: ground has no uniform %s" % [id, u])
		for mat_id: String in palette.get("kit", {}):
			assert_true(kit_materials.has(mat_id), "%s palette: no kit material %s" % [id, mat_id])
			var spec: Dictionary = kit_materials.get(mat_id, {})
			assert_true(spec.has("shader"), "%s palette: %s is not a shader material" % [id, mat_id])
			var names := _uniforms("res://assets/kit/shaders/%s.gdshader" % str(spec.get("shader", "none")))
			for u: String in palette["kit"][mat_id]:
				assert_true(u in names, "%s palette: %s has no uniform %s" % [id, mat_id, u])


func test_the_two_maps_are_painted_differently() -> void:
	var a: Dictionary = Registry.entry("maps", "small_map")["palette"]
	var b: Dictionary = Registry.entry("maps", "big_map")["palette"]
	assert_ne(a["ground"]["grass_tint"], b["ground"]["grass_tint"], "turf colour")
	assert_ne(a["kit"]["brick"]["coat_a"], b["kit"]["brick"]["coat_a"], "plaster colour")
	assert_ne(Registry.entry("maps", "small_map")["weather"], Registry.entry("maps", "big_map")["weather"], "light")


func test_ground_material_has_every_texture_and_the_palette() -> void:
	for id: String in MAPS:
		var entry := Registry.entry("maps", id)
		var mat := GroundLook.material(entry, 0.0)
		for prefix: String in GroundLook.SETS:
			assert_not_null(mat.get_shader_parameter(prefix + "_col"), id + " " + prefix + "_col")
			assert_not_null(mat.get_shader_parameter(prefix + "_nrm"), id + " " + prefix + "_nrm")
		var want: Array = entry["palette"]["ground"]["grass_tint"]
		var got: Color = mat.get_shader_parameter("grass_tint")
		assert_almost_eq(got.r, float(want[0]), 0.001, id + " grass tint reaches the shader")
		assert_almost_eq(got.b, float(want[2]), 0.001)


func test_walls_are_masonry_and_the_palette_repaints_them() -> void:
	var brick := Kit.material("brick")
	assert_true(brick is ShaderMaterial, "brick is a shader material")
	for uniform: String in ["base_col", "base_nrm", "coat_col", "macro"]:
		assert_not_null((brick as ShaderMaterial).get_shader_parameter(uniform), "brick " + uniform)
	Kit.apply_palette({"brick": {"coat_a": [0.1, 0.2, 0.3]}})
	var c: Color = (brick as ShaderMaterial).get_shader_parameter("coat_a")
	assert_almost_eq(c.g, 0.2, 0.001, "palette sets the plaster colour")
	Kit.apply_palette(Registry.entry("maps", "small_map")["palette"]["kit"])


func test_every_kit_texture_and_source_is_listed() -> void:
	var sources := FileAccess.get_file_as_string("res://assets/SOURCES.md")
	for id: String in Registry.file("kit")["materials"]:
		var spec: Dictionary = Registry.file("kit")["materials"][id]
		var paths: Array = spec.get("tex", {}).values()
		if spec.has("textures"):
			paths.append(str(spec["textures"]) + "/color.jpg")
		for p: String in paths:
			assert_true(ResourceLoader.exists("res://assets/kit/textures/" + p), "%s: %s exists" % [id, p])
			var folder := p.get_base_dir()
			assert_true(("textures/%s/" % folder) in sources, "%s is credited in assets/SOURCES.md" % folder)
	for prefix: String in GroundLook.SETS:
		var folder := str(GroundLook.SETS[prefix])
		assert_true(("textures/%s/" % folder) in sources, "%s is credited in assets/SOURCES.md" % folder)


# The kit's textures were imported as uncompressed images with no mipmaps (detect_3d never fires for a texture
# loaded from script): the ground shader then cost 30 ms a frame on Low and shimmered. Every one is VRAM
# compressed with mipmaps now.
func test_every_kit_texture_is_compressed_and_mipmapped() -> void:
	var n := 0
	for folder in DirAccess.get_directories_at("res://assets/kit/textures"):
		for file in DirAccess.get_files_at("res://assets/kit/textures/" + folder):
			if not file.ends_with(".jpg.import"):
				continue
			var cfg := ConfigFile.new()
			assert_eq(cfg.load("res://assets/kit/textures/%s/%s" % [folder, file]), OK)
			var where := "%s/%s" % [folder, file]
			assert_eq(cfg.get_value("params", "compress/mode"), 2, where + " is VRAM compressed")
			assert_eq(cfg.get_value("params", "mipmaps/generate"), true, where + " has mipmaps")
			n += 1
	assert_true(n >= 40, "found the kit's textures (%d)" % n)


func test_look_bots_ask_only_for_known_viewpoints() -> void:
	for pair: Array in [["look_small", "small_map"], ["look_big", "big_map"]]:
		var bot: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tools/bot/%s.json" % pair[0]))
		var views: Dictionary = Registry.entry("maps", str(pair[1])).get("viewpoints", {})
		var n := 0
		for step: Dictionary in bot["steps"]:
			if step.get("call", "") == "look_from":
				n += 1
				assert_true(views.has(str(step["args"][0])), "%s: viewpoint %s" % [pair[0], step["args"][0]])
		assert_gt(n, 8, pair[0] + " has at least nine views")


func test_shrub_keeps_its_leaf_clusters() -> void:
	var shrub := Kit.build("shrub", 3)
	var mesh: ArrayMesh = (shrub.get_node("Mesh") as MeshInstance3D).mesh
	var verts: PackedVector3Array = mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	assert_gt(verts.size(), 600, "a shrub is made of many leaf clusters")
	shrub.free()
