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
