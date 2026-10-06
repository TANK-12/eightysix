extends "res://tests/lib/test_case.gd"
## The look pass (lane B4): the film grade, the weather's fog and grade fields, the Juggernaut's
## paint finishes, and the preset fields that removed the grain and SSAO's cost.


func test_grade_without_shifts_changes_nothing() -> void:
	for c: Color in [Color(0, 0, 0), Color(0.2, 0.5, 0.8), Color(1, 1, 1), Color(0.5, 0.5, 0.5)]:
		var g := FilmGrade.grade_colour(c, {})
		assert_almost_eq(g.r, c.r, 0.001)
		assert_almost_eq(g.g, c.g, 0.001)
		assert_almost_eq(g.b, c.b, 0.001)


func test_split_tone_moves_shadows_and_highlights_apart() -> void:
	var grade := {"shadow_shift": [0, 0, 0.04], "highlight_shift": [0.04, 0, 0]}
	var dark := FilmGrade.grade_colour(Color(0.1, 0.1, 0.1), grade)
	var bright := FilmGrade.grade_colour(Color(0.9, 0.9, 0.9), grade)
	assert_gt(dark.b - dark.r, 0.02, "shadows go blue")
	assert_gt(bright.r - bright.b, 0.02, "highlights go warm")
	var lut := FilmGrade.lut(grade)
	assert_eq(lut.get_width(), FilmGrade.SIZE)
	assert_eq(lut.get_depth(), FilmGrade.SIZE)


func test_every_weather_builds_with_its_grade_and_fog() -> void:
	var holder := Node.new()
	Engine.get_main_loop().root.add_child(holder)
	for id: String in Registry.ids("weather"):
		var sky := SmallMapSky.new(holder, id)
		var w := Registry.entry("weather", id)
		assert_eq(sky.env.adjustment_color_correction != null, w.has("grade"), id + " grade table")
		assert_almost_eq(sky.env.fog_height_density, float(w.get("height_fog_density", 0.0)), 0.0001, id)
		sky.disconnect_settings()
	holder.free()
	var small := Registry.entry("maps", "small_map")
	assert_eq(str(small["weather"]), "golden_afternoon", "the small map opens on the golden afternoon")


func test_finish_paints_and_the_export_comes_back() -> void:
	var paint := StandardMaterial3D.new()
	paint.resource_name = "JG2_paint_001"
	paint.metallic = 1.0
	paint.roughness = 1.0
	var lens := StandardMaterial3D.new()
	lens.resource_name = "JG2_lens"
	lens.metallic = 0.3
	var changed := Finish.apply_to([paint, lens], "undertaker_field")
	assert_true(changed.has(paint), "paint changed")
	assert_almost_eq(paint.metallic, 1.0, 0.001, "metal where the surface's map shows chips")
	assert_almost_eq(paint.roughness, 0.64 / Finish.SURFACE_ROUGH_MEAN, 0.001)
	assert_true(paint.detail_enabled, "grime on")
	assert_lt(paint.albedo_color.r, 0.95, "tinted off the export's white")
	assert_almost_eq(lens.metallic, 0.3, 0.001, "a material the finish does not name stays as exported")
	Finish.apply_to([paint], "factory")
	assert_almost_eq(paint.metallic, 1.0, 0.001, "factory brings the export back")
	assert_false(paint.detail_enabled, "no grime on the bare export")
	assert_true(Registry.has_entry("finishes", Settings.item("mech.finish")["default"]), "default finish exists")


func test_presets_carry_sharpening_and_ssao_quality() -> void:
	for id: String in Registry.ids("graphics_presets"):
		var p := Registry.entry("graphics_presets", id)
		assert_true(p.has("sharpening") and p.has("ssao_quality"), id)
		assert_lt(float(p["sharpening"]), 0.3, id + ": strong FSR sharpening is the grain")
	assert_false(bool(Registry.entry("graphics_presets", "medium")["ssao"]), "Medium spends SSAO's 7 ms elsewhere")
	var before: Variant = Settings.get_value("graphics.sharpening")
	Settings.set_value("graphics.sharpening", 0.0, false)
	assert_almost_eq(Engine.get_main_loop().root.fsr_sharpness, 2.0, 0.001, "0% is Godot's softest")
	Settings.set_value("graphics.sharpening", 1.0, false)
	assert_almost_eq(Engine.get_main_loop().root.fsr_sharpness, 0.0, 0.001)
	Settings.set_value("graphics.sharpening", before, false)


func test_emblem_texture_is_chipped_and_mirrors() -> void:
	var clean := Emblem.coverage(Emblem.texture("undertaker", false, 0.0).get_image())
	var worn_tex := Emblem.texture("undertaker", false)
	var worn := Emblem.coverage(worn_tex.get_image())
	assert_gt(clean, 0.05, "the emblem draws something")
	assert_lt(worn, clean * 0.97, "wear chips paint off")
	assert_gt(worn, clean * 0.5, "but most of it is still there")
	var img := worn_tex.get_image()
	var mirrored := Emblem.texture("undertaker", true).get_image()
	var w := img.get_width()
	for p: Vector2i in [Vector2i(100, 200), Vector2i(382, 300), Vector2i(256, 140)]:
		assert_almost_eq(mirrored.get_pixel(w - 1 - p.x, p.y).a, img.get_pixel(p.x, p.y).a, 0.01, "mirror")
	assert_true(Registry.has_entry("emblems", Settings.item("mech.emblem")["default"]), "default emblem exists")


func test_emblem_decals_sit_on_the_logo_sockets_facing_out() -> void:
	var holder := Node3D.new()
	Engine.get_main_loop().root.add_child(holder)
	var sockets: Dictionary = Registry.entry("mechs", "juggernaut_m2")["sockets"]
	var decals := Emblem.attach(holder, sockets, "undertaker")
	assert_eq(decals.size(), 2, "both sides")
	for d: Decal in decals:
		var s: Dictionary = sockets[d.name.trim_prefix("Emblem_")]
		var at := Vector3(float(s["at"][0]), float(s["at"][1]), float(s["at"][2]))
		var out := Vector3(float(s["forward"][0]), float(s["forward"][1]), float(s["forward"][2]))
		assert_gt(d.transform.basis.y.normalized().dot(out), 0.99, d.name + " projects onto the panel")
		assert_gt(-d.transform.basis.z.normalized().dot(Vector3.UP), 0.99, d.name + " upright")
		var b := d.transform.basis
		assert_gt(b.determinant(), 0.0, d.name + " not turned inside out")
		var mirrored := b.x.dot(Vector3.FORWARD) < 0.0
		var picture_right := -b.x if mirrored else b.x
		assert_gt(picture_right.normalized().dot(Vector3.FORWARD), 0.99, d.name + " faces forward")
		var flipped := d.texture_albedo == Emblem.texture("undertaker", true)
		assert_eq(flipped, mirrored, d.name + " picture mirrored only where the box points backward")
		var box_in := (d.position - at).dot(out) - d.size.y * 0.5
		assert_lt(box_in, 0.0, d.name + " box starts inside the panel")
		assert_almost_eq(d.size.x, float(Registry.entry("emblems", "undertaker")["size_m"]), 0.001)
	assert_eq(Emblem.attach(holder, sockets, "none").size(), 0, "none paints nothing")
	assert_eq(holder.find_children("Emblem_*", "Decal", false, false).size(), 0, "and clears the old ones")
	holder.free()


func test_foot_dust_grows_with_speed_and_stays_off_hard_ground() -> void:
	var cfg: Dictionary = Registry.tune("foot_dust", {})
	var walk := float(cfg["min_speed_m_s"]) - 0.5
	assert_true(FootDust.plan(walk, "dirt").is_empty(), "no dust at a walk")
	var trot := FootDust.plan(float(cfg["min_speed_m_s"]) + 1.0, "dirt")
	var gallop := FootDust.plan(19.5, "dirt")
	assert_false(trot.is_empty(), "dust once running")
	assert_gt(float(gallop["size"]), float(trot["size"]), "bigger at a gallop")
	assert_gt(int(gallop["amount"]), int(trot["amount"]) - 1, "no fewer puffs")
	assert_true(FootDust.plan(19.5, "metal").is_empty(), "no dust off a steel deck")
	assert_lt(float(FootDust.plan(19.5, "rock")["colour"].a), float(gallop["colour"].a), "thinner on rock")


func test_foot_dust_puffs_land_behind_the_foot_and_are_capped() -> void:
	var holder := Node3D.new()
	Engine.get_main_loop().root.add_child(holder)
	var dust := FootDust.new()
	dust.level = holder
	var v := Vector3(0, 0, -15)  # galloping forward
	var p := dust.puff(Vector3(1, 0, 2), v, "dirt")
	assert_not_null(p, "a puff at a gallop")
	var cpu := p as CPUParticles3D
	assert_gt(cpu.global_transform.basis.y.dot(Vector3.BACK), 0.2, "kicked backward, away from the run")
	var made := 1
	for i in 100:
		if dust.puff(Vector3(1, 0, 2), v, "dirt") != null:
			made += 1
	assert_eq(made, int(Registry.tune("foot_dust", {})["max_live"]), "capped")
	holder.free()
	dust.free()


func test_foot_dust_material_fades_near_the_camera() -> void:
	var m := FootDust.material()
	assert_eq(m.distance_fade_mode, BaseMaterial3D.DISTANCE_FADE_PIXEL_ALPHA, "no blob in the camera's face")
	assert_true(m.proximity_fade_enabled, "soft where it meets the ground")
	var img := FootDust.cloud_texture(64).get_image()
	assert_almost_eq(img.get_pixel(0, 0).a, 0.0, 0.01, "clear at the corner")
	assert_gt(img.get_pixel(32, 32).a, 0.3, "thick in the middle")
	var ring: Array[float] = []
	for i in 16:
		var ang := TAU * i / 16.0
		ring.append(img.get_pixel(32 + int(cos(ang) * 18), 32 + int(sin(ang) * 18)).a)
	assert_gt(ring.max() - ring.min(), 0.1, "ragged edge, not a clean disc")


func _paint_and_frame() -> Array:
	var paint := StandardMaterial3D.new()
	paint.resource_name = "JG2_paint"
	var frame := StandardMaterial3D.new()
	frame.resource_name = "JG2_frame_001"
	Finish.apply_to([paint, frame], "undertaker_field")
	return [paint, frame]


func test_grime_builds_with_running_on_dirt_more_than_rock_and_none_on_steel() -> void:
	var dirt := GrimeBuildup.gain(1000.0, "dirt", 15.0)
	var rock := GrimeBuildup.gain(1000.0, "rock", 15.0)
	assert_gt(dirt, 0.05, "a kilometre run on dirt shows")
	assert_lt(rock, dirt * 0.6, "rock throws less dirt")
	assert_almost_eq(GrimeBuildup.gain(1000.0, "metal", 15.0), 0.0, 0.0001, "a steel deck adds none")
	assert_gt(GrimeBuildup.gain(1000.0, "dirt", 18.0), GrimeBuildup.gain(1000.0, "dirt", 4.0), "running throws more than walking")
	assert_gt(GrimeBuildup.landing_gain(12.0), GrimeBuildup.landing_gain(3.0), "a hard landing splashes more than a soft one")
	assert_gt(GrimeBuildup.skid_gain(2.0, "dirt"), 0.0, "a skid on dirt sprays the legs")


func test_grime_buildup_dirties_the_finish_and_mattes_it_capped() -> void:
	var mats := _paint_and_frame()
	var paint: StandardMaterial3D = mats[0]
	var clean_tex := paint.detail_albedo
	var clean_rough := paint.roughness
	var g := GrimeBuildup.new()
	g.mats = mats
	g.add(0.3)
	assert_ne(paint.detail_albedo, clean_tex, "a dirtier grime layer")
	assert_gt(paint.roughness, clean_rough, "dust is matte")
	g.add(50.0)
	var cap := float(Registry.tune("grime_buildup", {})["max_extra"])
	assert_almost_eq(g.extra, cap, 0.0001, "capped")
	assert_eq(paint.detail_albedo, Finish.grime_texture(Finish.GRIME_STEPS), "the heaviest grime at most")
	g.free()


func test_switching_finish_keeps_the_dirt_and_clearing_returns_the_finish() -> void:
	var mats := _paint_and_frame()
	var paint: StandardMaterial3D = mats[0]
	var g := GrimeBuildup.new()
	g.mats = mats
	g.add(0.4)
	Finish.apply_to(mats, "fresh_paint")
	assert_true(paint.detail_enabled, "fresh paint still carries the sortie's dirt")
	assert_gt(Finish.grime_of(paint), 0.4, "fresh paint's own 0.1 plus the dirt")
	g.reset()
	assert_almost_eq(Finish.grime_of(paint), 0.1, 0.0001, "back to the finish's own wear")
	var spec: Dictionary = Registry.entry("finishes", "fresh_paint")["materials"]["JG2_paint"]
	var mean := Finish.SURFACE_ROUGH_MEAN if spec.has("surface") else 1.0
	assert_almost_eq(paint.roughness, minf(float(spec["roughness"]) / mean, 1.0), 0.0001, "the finish's roughness on its surface's map")
	g.free()


func test_the_juggernaut_gets_dirty_running_and_the_setting_washes_it() -> void:
	var mech := MechBuilder.build("juggernaut_m2")
	Engine.get_main_loop().root.add_child(mech)
	var g := mech.get_node_or_null("GrimeBuildup") as GrimeBuildup
	assert_not_null(g, "every Juggernaut carries its grime")
	assert_gt(g.mats.size(), 0, "found the finish's materials")
	var paint: StandardMaterial3D
	for m: StandardMaterial3D in g.mats:
		if m.resource_name.begins_with("JG2_paint"):
			paint = m
	var before := Finish.grime_of(paint)
	g.travel(800.0, "dirt", 16.0)
	assert_gt(Finish.grime_of(paint), before + 0.05, "dirtier after a run")
	Settings.set_value("mech.grime_buildup", false, false)
	assert_almost_eq(Finish.grime_of(paint), before, 0.0001, "off: the finish's own wear")
	g.travel(800.0, "dirt", 16.0)
	assert_almost_eq(Finish.grime_of(paint), before, 0.0001, "off: no build-up")
	Settings.reset_all_quietly()
	mech.free()
