extends "res://tests/lib/test_case.gd"
## LOOK3 Half B (2026-10-06): the forest and Brilon get their own light, the firs their own look, and
## shell marks a ragged scorch, wall cracks and a cap per graphics preset.


func test_the_real_place_maps_have_their_own_weather_with_their_own_fog() -> void:
	var holder := Node.new()
	Engine.get_main_loop().root.add_child(holder)
	for map_id: String in ["allegheny", "brilon"]:
		var entry := Registry.entry("maps", map_id)
		var id := str(entry["weather"])
		assert_true(id != "overcast_morning" and Registry.has_entry("weather", id), map_id + " has a weather of its own")
		var w := Registry.entry("weather", id)
		assert_true(bool(w.get("fog_unscaled", false)), id + " is written for its map's size")
		var sky := SmallMapSky.new(holder, id)
		sky.fog_scale = float(entry.get("fog_scale", 1.0))
		sky.apply(id)
		assert_true(sky.fog_scale < 1.0, map_id + " still thins the shared weathers")
		assert_almost_eq(sky.env.volumetric_fog_density, float(w["volumetric_density"]), 1e-6, id + " volumetric fog not thinned again")
		assert_almost_eq(sky.env.fog_height_density, float(w["height_fog_density"]), 1e-6, id + " pooled mist not thinned again")
		assert_almost_eq(float(sky.sky_mat.get_shader_parameter("cloud_scale")), float(w["cloud_scale"]), 0.001, id + " cloud size reaches the sky")
		# a shared weather on the same map is still thinned by the map's fog_scale
		sky.apply("overcast_morning")
		var o := Registry.entry("weather", "overcast_morning")
		assert_almost_eq(sky.env.volumetric_fog_density, float(o["volumetric_density"]) * sky.fog_scale, 1e-6, "shared weather thinned on " + map_id)
		assert_almost_eq(float(sky.sky_mat.get_shader_parameter("cloud_scale")), 1.0, 0.001, "shared weather keeps the old cloud size")
		sky.disconnect_settings()
	holder.free()


func test_the_forest_mist_pools_in_the_hollows_below_the_ridges() -> void:
	var w := Registry.entry("weather", str(Registry.entry("maps", "allegheny")["weather"]))
	# the spawn road lies at 64 m, the ridges at 170-220 m (assets/maps/allegheny/height.f32)
	var top := float(w["height_fog_top_m"])
	assert_true(top > 64.0 and top < 170.0, "mist top %.0f m between the spawn hollow and the ridges" % top)
	assert_true(float(w["sun_elevation_deg"]) < 25.0, "a low morning sun slants through the firs")
	assert_true(float(w["volumetric_anisotropy"]) >= 0.5, "fog scatters forward, so light shafts show toward the sun")


func test_the_firs_take_their_look_from_the_map_entry() -> void:
	var forest := BigForest.new()
	forest.cfg = Registry.entry("maps", "allegheny")["forest"]
	var look: Dictionary = forest.cfg["look"]
	for part: int in [1, 2]:
		var m := forest._material(part, "branch.png" if part == 1 else "far.png", "")
		for key: String in ["variation", "crown_ao", "translucency"]:
			assert_almost_eq(float(m.get_shader_parameter(key)), float(look[key]), 0.001, "part %d %s" % [part, key])
		assert_almost_eq(float(m.get_shader_parameter("tree_h")), BigForest.TREE_H, 0.001, "part %d knows the tree height" % part)
	forest.free()


func test_tree_cards_are_mipmapped_so_far_firs_do_not_sparkle() -> void:
	for file: String in ["branch.png", "far.png"]:
		var tex := load(BigForest.TEX + file) as Texture2D
		assert_true(tex.get_image().has_mipmaps(), file + " has mipmaps")


func test_scorch_has_a_ragged_edge_and_walls_crack() -> void:
	var img := CombatFx.scorch_texture().get_image()
	if img.is_compressed():
		img.decompress()
	var n := img.get_width()
	var ring := PackedFloat32Array()
	for i in 48:
		var p := Vector2(0.5, 0.5) + Vector2.from_angle(TAU * i / 48.0) * 0.21
		ring.append(img.get_pixel(int(p.x * n), int(p.y * n)).a)
	var mean := 0.0
	for a in ring:
		mean += a / ring.size()
	var spread := 0.0
	for a in ring:
		spread += absf(a - mean) / ring.size()
	assert_true(spread > 0.05, "alpha round the scorch ring varies (%.3f), not a smooth disc" % spread)
	assert_true(img.get_pixel(n / 2, n / 2).a > 0.8, "the centre is charred")
	var holder := Node3D.new()
	Engine.get_main_loop().root.add_child(holder)
	var ground := CombatFx.decal(holder, Vector3.ZERO, Vector3.UP, 2.0)
	var wall := CombatFx.decal(holder, Vector3(0, 2, 0), Vector3.RIGHT, 2.0)
	assert_eq(ground.texture_albedo, CombatFx.scorch_texture(), "the ground scorches")
	assert_eq(wall.texture_albedo, CombatFx.crack_texture(), "a wall cracks")
	assert_true(wall.texture_normal != null and ground.texture_normal != null, "both marks have relief")
	holder.free()


func test_scorch_marks_kept_follow_the_preset() -> void:
	var limits := []
	for id: String in ["low", "medium", "high", "ultra"]:
		limits.append(int(Registry.entry("graphics_presets", id)["decal_limit"]))
	for i in range(1, limits.size()):
		assert_true(limits[i] >= limits[i - 1], "a higher preset keeps at least as many marks")
	var preset := Settings.get_s("graphics.preset")
	var before := Settings.get_f("graphics.decal_limit")
	Settings.set_value("graphics.decal_limit", 24, false)
	var holder := Node3D.new()
	Engine.get_main_loop().root.add_child(holder)
	var made: Array = []
	for i in 30:
		made.append(CombatFx.decal(holder, Vector3(i * 3.0, 0, 0), Vector3.UP, 2.0))
	var live := 0
	for d: Decal in made:
		if is_instance_valid(d) and not d.is_queued_for_deletion():
			live += 1
	assert_eq(live, 24, "the 24 newest marks stay")
	Settings.set_value("graphics.decal_limit", before, false)
	Settings.set_value("graphics.preset", preset, false)
	holder.free()
