extends "res://tests/lib/test_case.gd"
## Presets copy their values into the settings, a hand change turns the preset to Custom, and
## apply() reaches the window and the scene.


func after_each() -> void:
	Settings.reset_all_quietly()
	Graphics.copy_preset(Settings.get_s("graphics.preset"))
	Graphics.apply()


func test_picking_a_preset_copies_every_field() -> void:
	for id in Registry.ids("graphics_presets"):
		Settings.set_value("graphics.preset", id, false)
		assert_true(Graphics.preset_matches(id), id + " fields copied")
		var preset := Registry.entry("graphics_presets", id)
		assert_eq(Settings.get_value("graphics.shadow_size"), preset["shadow_size"], id)
		assert_eq(Settings.get_value("graphics.sdfgi"), preset["sdfgi"], id)


func test_changing_one_field_makes_it_custom() -> void:
	Settings.set_value("graphics.preset", "low", false)
	Settings.set_value("graphics.ssao", true, false)
	assert_eq(Settings.get_value("graphics.preset"), "custom")
	Settings.set_value("graphics.preset", "high", false)
	assert_true(Graphics.preset_matches("high"))


func test_apply_reaches_viewport_and_environment() -> void:
	var holder := WorldEnvironment.new()
	holder.environment = Environment.new()
	holder.add_to_group("world_environment")
	tree.root.add_child(holder)
	var cam := Camera3D.new()
	cam.add_to_group("game_camera")
	tree.root.add_child(cam)
	Settings.set_value("graphics.preset", "low", false)
	Graphics.apply()
	assert_almost_eq(tree.root.scaling_3d_scale, 0.67, 0.001)
	assert_false(holder.environment.volumetric_fog_enabled)
	assert_eq(cam.far, 600.0)
	Settings.set_value("graphics.preset", "ultra", false)
	Graphics.apply()
	assert_eq(tree.root.msaa_3d, Viewport.MSAA_2X)
	assert_true(holder.environment.sdfgi_enabled)
	assert_eq(cam.far, 2600.0)
	holder.free()
	cam.free()


func test_targets_are_in_the_plan() -> void:
	assert_eq(Registry.entry("graphics_presets", "low")["target_fps"], 60.0)
	assert_eq(Registry.entry("graphics_presets", "medium")["target_fps"], 45.0)
	assert_eq(Registry.entry("graphics_presets", "high")["target_fps"], 30.0)
	assert_eq(Registry.entry("graphics_presets", "ultra")["target_fps"], null)
