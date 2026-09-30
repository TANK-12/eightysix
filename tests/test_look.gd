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
	assert_almost_eq(paint.metallic, 0.0, 0.001, "paint is not metal")
	assert_almost_eq(paint.roughness, 0.64, 0.001)
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
