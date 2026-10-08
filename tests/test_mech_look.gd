extends "res://tests/lib/test_case.gd"
## LOOK3 Half A (2026-10-06): the mechs wear real CC0 surfaces (projected three ways, the exports
## have no UV maps), grime rises from the feet, and the Legion get their liveries from looks.py.


func _mat(n: String) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.resource_name = n
	m.metallic = 1.0
	m.roughness = 1.0
	return m


func test_every_named_surface_has_its_maps() -> void:
	for id: String in Registry.ids("mech_surfaces"):
		for tex: String in ["albedo.jpg", "normal.jpg", "orm.jpg"]:
			assert_true(load(Finish.SURFACE_DIR.path_join(id).path_join(tex)) is Texture2D, id + " " + tex)
	for reg: String in ["finishes", "legion_finishes"]:
		for id: String in Registry.ids(reg):
			for key: String in Registry.entry(reg, id).get("materials", {}):
				var s := str(Registry.entry(reg, id)["materials"][key].get("surface", ""))
				assert_true(s == "" or Registry.has_entry("mech_surfaces", s), "%s %s %s: surface %s exists" % [reg, id, key, s])


func test_a_surface_lays_real_maps_and_the_export_comes_back() -> void:
	var paint := _mat("JG2_paint_001")
	Finish.apply_to([paint], "undertaker_field")
	assert_eq(str(paint.get_meta("finish_surface")), "chipped_paint")
	assert_true(paint.uv1_triplanar and not paint.uv1_world_triplanar, "projected in the part's own space")
	assert_true(paint.normal_enabled and paint.normal_texture != null, "normal map on")
	assert_true(paint.ao_enabled and paint.ao_texture_channel == BaseMaterial3D.TEXTURE_CHANNEL_RED, "cavities from the occlusion map")
	assert_eq(paint.metallic_texture_channel, BaseMaterial3D.TEXTURE_CHANNEL_BLUE)
	assert_almost_eq(paint.metallic, 1.0, 0.001, "metal only where the map shows chips")
	var rough := float(Registry.entry("finishes", "undertaker_field")["materials"]["JG2_paint"]["roughness"])
	assert_almost_eq(paint.roughness, rough / Finish.SURFACE_ROUGH_MEAN, 0.001, "the map's mean brings it back to the finish's")
	Finish.apply_to([paint], "factory")
	assert_false(paint.uv1_triplanar or paint.ao_enabled, "factory takes the surface off")
	assert_true(paint.normal_texture == null, "the export had no normal map")


func test_grime_rises_from_the_feet() -> void:
	var root := Node3D.new()
	var shared := _mat("JG2_paint")
	for y: float in [0.1, 0.55, 2.4]:
		var mi := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = Vector3.ONE * 0.2
		box.material = shared
		mi.mesh = box
		mi.position.y = y
		root.add_child(mi)
	var cache := {}
	var made := Finish.band_copies(root, cache, func(_m: StandardMaterial3D) -> bool: return true)
	assert_eq(made.size(), 3, "one copy per band")
	assert_eq(Finish.band_copies(root, cache, func(_m: StandardMaterial3D) -> bool: return true).size(), 0, "copies are shared")
	Finish.apply_to(made, "undertaker_field")
	var g: Array = []
	for mi: MeshInstance3D in root.get_children():
		var m := mi.get_active_material(0) as StandardMaterial3D
		assert_ne(m, shared, "the part wears its band's copy")
		g.append(Finish.grime_of(m))
	var spec: Dictionary = Registry.entry("finishes", "undertaker_field")["materials"]["JG2_paint"]
	assert_almost_eq(float(g[2]), float(spec["grime"]), 0.001, "the hull has the finish's own grime")
	assert_gt(float(g[0]), float(g[1]), "feet dirtier than the lower legs")
	assert_gt(float(g[1]), float(g[2]), "lower legs dirtier than the hull")
	root.free()


func test_the_legion_wear_the_livery_and_switch_live() -> void:
	var before: Variant = Settings.get_value("legion.livery")
	Settings.set_value("legion.livery", "legion_field", false)
	var a := LegionMech.build("ameise")
	var b := LegionMech.build("ameise")
	var shells: Array = []
	for unit: LegionMech in [a, b]:
		for n: Node in unit.model.find_children("*", "MeshInstance3D", true, false):
			var mi := n as MeshInstance3D
			for i in mi.mesh.get_surface_count():
				var m := mi.get_active_material(i) as StandardMaterial3D
				if m != null and m.resource_name.begins_with("LG_shell_night"):
					shells.append(m)
	assert_gt(shells.size(), 0, "the shell has a livery copy")
	var shell := shells[0] as StandardMaterial3D
	assert_eq(str(shell.get_meta("finish_surface")), "chipped_paint")
	assert_gt(shell.albedo_color.r, shell.albedo_color.b + 0.04, "field cream, not the export's white")
	var lite_has := false
	for n: Node in a.lite.find_children("*", "MeshInstance3D", true, false):
		var m := (n as MeshInstance3D).get_active_material(0) as StandardMaterial3D
		lite_has = lite_has or (m != null and m.has_meta("finish_band"))
	assert_true(lite_has, "the lite twin wears it too")
	var copies := {}
	for m: StandardMaterial3D in shells:
		copies[m] = true
	assert_lt(copies.size(), shells.size(), "both units share the copies")
	Settings.set_value("legion.livery", "legion_night", false)
	assert_gt(shell.albedo_color.b, shell.albedo_color.r + 0.05, "night is silver-blue, switched live")
	Settings.set_value("legion.livery", before, false)
	a.free()
	b.free()
