extends "res://tests/lib/test_case.gd"
## Settings: defaults, clamping, choices, saving and loading, page reset, generated audio rows.

var _saved_path := ""


func before_each() -> void:
	_saved_path = Settings.save_path
	Settings.save_path = "user://test_settings.cfg"
	Settings.reset_all_quietly()


func after_each() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path("user://test_settings.cfg"))
	Settings.save_path = _saved_path
	Settings.reset_all_quietly()
	Graphics.apply()


func test_every_item_has_a_default_or_is_an_action() -> void:
	for key: String in Settings.keys():
		var it := Settings.item(key)
		if str(it["type"]) in ["toggle", "slider", "choice"]:
			assert_true(it.has("default"), key)
			assert_eq(Settings.sanitise(key, it["default"]), it["default"], key + " default is valid")
			assert_true(str(it.get("help", "")) != "", key + " has help text")


## Lane A6 ("settings lined up"): every row reads like the rest, a label in sentence case and help that ends
## a sentence, and no work notes (lane names, sessions) leak into what the player sees.
func test_every_row_is_lined_up() -> void:
	var jargon := RegEx.create_from_string("\\b(lane [AB]?\\d|Relay|TODO|session)\\b")
	for key: String in Settings.keys():
		var it := Settings.item(key)
		var label := str(it.get("label", ""))
		assert_ne(label, "", key + " has a label")
		assert_eq(label.substr(0, 1), label.substr(0, 1).to_upper(), key + " label starts with a capital")
		var help := str(it.get("help", ""))
		if help != "":
			assert_true(help.strip_edges().right(1) in [".", ")", "?", "!"], key + " help ends a sentence")
		assert_true(jargon.search(label + " " + help) == null, key + " has no work notes in its text")


func test_slider_clamps_and_snaps() -> void:
	Settings.set_value("controls.move_inner", 0.9, false)
	assert_eq(Settings.get_value("controls.move_inner"), 0.4)
	Settings.set_value("graphics.shadow_distance", 123.0, false)
	assert_eq(Settings.get_value("graphics.shadow_distance"), 120.0)


func test_choice_rejects_unknown_values() -> void:
	assert_false(Settings.set_value("graphics.upscaler", "dlss", false))
	assert_eq(Settings.get_value("graphics.upscaler"), Settings.get_value("graphics.upscaler"))
	assert_true(Settings.set_value("graphics.fps_cap", 60, false))
	assert_eq(Settings.label_for("graphics.fps_cap", 60.0), "60")


func test_save_and_load_round_trip() -> void:
	Settings.set_value("controls.mouse_sensitivity", 1.75, false)
	Settings.set_value("interface.theme", "spearhead_field", false)
	Settings.save_now()
	Settings.reset_all_quietly()
	assert_eq(Settings.get_value("controls.mouse_sensitivity"), 1.0)
	Settings.load_saved()
	assert_eq(Settings.get_value("controls.mouse_sensitivity"), 1.75)
	assert_eq(Settings.get_value("interface.theme"), "spearhead_field")


func test_reset_page_restores_defaults() -> void:
	Settings.set_value("controls.move_inner", 0.3, false)
	Settings.set_value("controls.aim_curve", 2.5, false)
	Settings.reset_page("controls", "sticks")
	assert_true(Settings.is_default("controls.move_inner"))
	assert_true(Settings.is_default("controls.aim_curve"))


func test_registry_options_and_generated_rows() -> void:
	var preset_values := Settings.options_for("graphics.preset").map(func(o: Array) -> Variant: return o[0])
	for id in ["low", "medium", "high", "ultra", "custom"]:
		assert_has(preset_values, id)
	for bus: Dictionary in Registry.file("sounds")["buses"]:
		assert_true(Settings.has_key("audio." + str(bus["id"])), "volume row for " + str(bus["id"]))


func test_changed_signal_fires_once_per_real_change() -> void:
	var seen: Array = []
	var cb := func(key: String, _v: Variant) -> void: seen.append(key)
	Settings.changed.connect(cb)
	Settings.set_value("gameplay.camera_shake", 0.5, false)
	Settings.set_value("gameplay.camera_shake", 0.5, false)
	Settings.changed.disconnect(cb)
	assert_eq(seen.count("gameplay.camera_shake"), 1)
