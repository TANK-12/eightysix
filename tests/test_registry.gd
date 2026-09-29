extends "res://tests/lib/test_case.gd"
## Every registry loads, cross-references resolve, and "inherits" merges as documented.

const FILES := ["mechs", "parts", "weapons", "enemies", "maps", "graphics_presets", "themes", "input",
	"sounds", "music", "tuning", "rumble", "settings", "tips"]


func test_all_files_load_without_errors() -> void:
	assert_eq(Registry.errors.size(), 0, ", ".join(Registry.errors))
	for name: String in FILES:
		assert_true(Registry.has_file(name), name + ".json missing")
		assert_has(Registry.file(name), "_about", name + " has no _about line")


func test_inherits_deep_merges_and_abstract_is_hidden() -> void:
	var knee := Registry.entry("parts", "standin_knee_fl")
	assert_eq(knee["bench"]["peak_force_n"], 220000.0, "own figure wins")
	assert_eq(knee["bench"]["stroke_m"], 0.6, "inherited from act_linear_heavy")
	assert_false(knee.has("inherits"))
	assert_false(knee.has("abstract"))
	assert_false("act_linear_heavy" in Registry.ids("parts"))
	var blades := Registry.entry("mechs", "juggernaut_m2_blades")
	assert_eq(blades["loadout"]["main_gun"], "gun_57mm", "variant keeps the other slots")
	assert_eq(blades["loadout"]["sub_left"], "hf_blade")


func test_mech_parts_actuators_and_loadouts_exist() -> void:
	var motors: Dictionary = Registry.tune("motors", {})
	for id in Registry.ids("mechs"):
		var m := Registry.entry("mechs", id)
		for p: Dictionary in m.get("parts", []):
			assert_true(Registry.has_entry("parts", str(p["part"])), "%s: part %s" % [id, p["part"]])
		for leg_name: String in m.get("legs", {}):
			var leg: Dictionary = m["legs"][leg_name]
			for seg: String in ["upper", "lower", "foot"]:
				assert_true(Registry.has_entry("parts", str(leg[seg])), "%s leg %s %s" % [id, leg_name, seg])
			for act: String in leg.get("actuators", []):
				var a := Registry.entry("parts", act)
				assert_eq(a.get("kind"), "actuator", act)
				assert_has(motors, str(a.get("game_motor", "")), act + " game motor")
				for field: String in ["peak_force_n", "no_load_speed_m_s", "stroke_m", "lever_arm_m", "rated_power_w", "thermal_mass_j_per_k"]:
					assert_has(a.get("bench", {}), field, act + " bench " + field)
		for slot: String in m.get("loadout", {}):
			assert_true(Registry.has_entry("weapons", str(m["loadout"][slot])), "%s loadout %s" % [id, slot])


func test_main_gun_is_fixed_forward() -> void:
	var gun := Registry.entry("weapons", "gun_57mm")
	assert_eq(gun["mount"], "fixed_forward")
	assert_eq(gun["traverse_deg"], 0.0, "supplement point 2: no independent traverse")
	assert_has(Registry.entry("weapons", "lowe_120mm"), "wake", "supplement point 4")


func test_enemies_weapons_and_maps_resolve() -> void:
	for id in Registry.ids("enemies"):
		for w: String in Registry.entry("enemies", id).get("weapons", []):
			assert_true(Registry.has_entry("weapons", w), id + " weapon " + w)
	for id in Registry.ids("maps"):
		var map := Registry.entry("maps", id)
		if map.get("status") != "planned":
			assert_true(ResourceLoader.exists(str(map["scene"])), id + " scene exists")


func test_themes_complete_and_fonts_exist() -> void:
	var colour_keys := Registry.entry("themes", "handler_console")["colors"].keys()
	for id in Registry.ids("themes"):
		var t := Registry.entry("themes", id)
		for key: String in colour_keys:
			assert_has(t["colors"], key, id + " colour " + key)
		for role: String in t["fonts"]:
			assert_true(ResourceLoader.exists(str(t["fonts"][role])), id + " font " + role)


func test_presets_cover_every_preset_setting() -> void:
	for key: String in Settings.keys():
		var field := str(Settings.item(key).get("preset_field", ""))
		if field == "":
			continue
		for id in Registry.ids("graphics_presets"):
			var preset := Registry.entry("graphics_presets", id)
			assert_has(preset, field, id + " lacks " + field)
			assert_not_null(Settings.sanitise(key, preset[field]), "%s.%s = %s is not a valid %s" % [id, field, str(preset[field]), key])


func test_rumble_categories_have_sliders() -> void:
	for id in Registry.ids("rumble"):
		var cat := "rumble." + str(Registry.entry("rumble", id).get("category", ""))
		assert_true(Settings.has_key(cat), id + " category " + cat)


func test_tune_reads_dotted_paths() -> void:
	assert_eq(Registry.tune("standin.drive.walk_m_s"), 7.0)
	assert_eq(Registry.tune("no.such.path", 3), 3)
