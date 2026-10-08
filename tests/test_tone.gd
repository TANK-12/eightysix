extends "res://tests/lib/test_case.gd"
## Lane LOOK2: the washed-out fix. AgX (the tonemapper every map uses) reads its own white point and contrast,
## not tonemap_white; its default white of 16.29 kept sunlit ground near 140 of 255.


func test_every_weather_drives_the_agx_tonemapper() -> void:
	var holder := Node.new()
	Engine.get_main_loop().root.add_child(holder)
	for id: String in Registry.ids("weather"):
		var w := Registry.entry("weather", id)
		var sky := SmallMapSky.new(holder, id)
		assert_eq(sky.env.tonemap_mode, Environment.TONE_MAPPER_AGX, id + " uses AgX")
		assert_true(w.has("agx_white") and w.has("agx_contrast"), id + " sets the AgX white point and contrast")
		assert_almost_eq(sky.env.tonemap_agx_white, float(w["agx_white"]), 0.001, id + " AgX white applied")
		assert_almost_eq(sky.env.tonemap_agx_contrast, float(w["agx_contrast"]), 0.001, id + " AgX contrast applied")
		assert_true(sky.env.tonemap_agx_white < 8.0, id + " white point within reach of a lit scene")
		assert_true(sky.env.volumetric_fog_ambient_inject <= 0.3, id + " fog does not pick up a milky veil of sky light")
		sky.disconnect_settings()
	holder.free()


func test_switching_weather_moves_the_tone_with_it() -> void:
	var holder := Node.new()
	Engine.get_main_loop().root.add_child(holder)
	var sky := SmallMapSky.new(holder, "golden_afternoon")
	sky.apply("storm_grey")
	var w := Registry.entry("weather", "storm_grey")
	assert_almost_eq(sky.env.tonemap_agx_white, float(w["agx_white"]), 0.001, "live switch sets the white point")
	assert_almost_eq(sky.env.tonemap_exposure, float(w["exposure"]), 0.001, "live switch sets the exposure")
	sky.disconnect_settings()
	holder.free()


## Alpha 0.1.1: a weather's contrast used to go to Environment.adjustment_contrast, a straight line about mid grey
## that clamps, so at 1.14 every shadow under 16 of 255 went to pure black. It is now a soft S-curve in the grade table.
func test_contrast_bends_into_black_and_white_instead_of_clipping() -> void:
	var k := 1.14
	assert_almost_eq(FilmGrade.contrast_curve(0.5, k), 0.5, 0.0001, "mid grey stays put")
	var slope := (FilmGrade.contrast_curve(0.52, k) - FilmGrade.contrast_curve(0.48, k)) / 0.04
	assert_almost_eq(slope, k, 0.001, "as much contrast in the mid tones as the straight line gave")
	assert_almost_eq(FilmGrade.contrast_curve(0.0, k), 0.0, 0.0001, "black stays black")
	assert_almost_eq(FilmGrade.contrast_curve(1.0, k), 1.0, 0.0001, "white stays white")
	assert_gt(FilmGrade.contrast_curve(8.0 / 255.0, k), 4.0 / 255.0, "a deep shadow keeps its detail (the line sent it to 0)")
	assert_gt(FilmGrade.contrast_curve(16.0 / 255.0, k), 9.0 / 255.0, "a shadow at 16 of 255 stays readable")
	assert_lt(FilmGrade.contrast_curve(0.96, k), 0.995, "a bright sky keeps a gradient (the line clipped it at 0.94)")
	assert_almost_eq(FilmGrade.contrast_curve(0.25, k), 0.5 + (0.25 - 0.5) * k, 0.002, "the lower mid tones as before")
	assert_almost_eq(FilmGrade.contrast_curve(0.85, k), 0.5 + (0.85 - 0.5) * k, 0.002, "the upper mid tones as before")
	var rising := true
	var last := -1.0
	for i in 256:
		var y := FilmGrade.contrast_curve(i / 255.0, k)
		rising = rising and y > last
		last = y
	assert_true(rising, "every step up in brightness stays a step up")
	assert_almost_eq(FilmGrade.contrast_curve(0.3, 1.0), 0.3, 0.0001, "contrast 1 changes nothing")


func test_the_environment_contrast_stays_flat_and_the_grade_table_carries_it() -> void:
	var holder := Node.new()
	Engine.get_main_loop().root.add_child(holder)
	for id: String in Registry.ids("weather"):
		var grade: Dictionary = Registry.entry("weather", id).get("grade", {})
		var sky := SmallMapSky.new(holder, id)
		assert_almost_eq(sky.env.adjustment_contrast, 1.0, 0.0001, id + ": no straight-line contrast that clips")
		if absf(float(grade.get("contrast", 1.0)) - 1.0) > 0.001:
			assert_not_null(sky.env.adjustment_color_correction, id + ": the grade table carries the contrast")
		sky.disconnect_settings()
	holder.free()


## Godot reads the 3D table at the colour itself with no half-texel offset, so texel i is what (i + 0.5) / SIZE gets;
## a table filled for i / (SIZE - 1) sent everything under 4 of 255 to black and added 3 % contrast.
func test_each_texel_holds_the_grade_of_the_colour_that_reads_it() -> void:
	var grade := {"contrast": 1.14, "shadow_shift": [-0.012, 0.002, 0.028], "highlight_shift": [0.018, 0.008, -0.012]}
	var slices := FilmGrade.slices(grade)
	assert_eq(slices.size(), FilmGrade.SIZE, "one slice per blue step")
	for i: int in [0, 1, 5, 16, 30, 31]:
		var x := (i + 0.5) / float(FilmGrade.SIZE)
		var want := FilmGrade.grade_colour(Color(x, x, x), grade)
		var got: Color = slices[i].get_pixel(i, i)
		assert_almost_eq(got.r, want.r, 1.0 / 255.0, "texel %d red" % i)
		assert_almost_eq(got.g, want.g, 1.0 / 255.0, "texel %d green" % i)
		assert_almost_eq(got.b, want.b, 1.0 / 255.0, "texel %d blue" % i)
