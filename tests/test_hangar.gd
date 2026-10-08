extends "res://tests/lib/test_case.gd"
## The Hangar (lane A4 part 7): the light presets are valid data, the Juggernaut stands in the room
## under real physics, the camera orbits within its limits, a point on the picture picks a part with its
## name and realistic mass, the Hangar screen and the main-menu Juggernaut build from the data.

const HANGAR_SCENE := "res://scenes/ui/hangar.tscn"
const MENU_SCENE := "res://scenes/ui/main_menu.tscn"

var stage: HangarStage
var _saved := {}


func before_each() -> void:
	stage = null
	_saved = {}


func after_each() -> void:
	if stage != null and is_instance_valid(stage):
		stage.free()
	for key: String in _saved:
		Settings.set_value(key, _saved[key], false)


func _make_stage(showcase: bool = false) -> void:
	stage = HangarStage.new()
	stage.showcase = showcase
	tree.root.add_child(stage)
	stage.set_mech("juggernaut_m2")


func assert_gte(got: float, want: float, msg: String = "") -> void:
	assert_true(got >= want, "%s: %s is not >= %s" % [msg, got, want])


func assert_lte(got: float, want: float, msg: String = "") -> void:
	assert_true(got <= want, "%s: %s is not <= %s" % [msg, got, want])


func _remember(key: String) -> void:
	if not _saved.has(key):
		_saved[key] = Settings.get_value(key)


# --- the data ----------------------------------------------------------------------------------


func test_light_presets_are_valid_data() -> void:
	var ids := Registry.ids("hangar")
	assert_gte(ids.size(), 4, "at least four light presets")
	for id in ids:
		var def := Registry.entry("hangar", id)
		assert_ne(str(def.get("label", "")), "", id + " has a label")
		assert_true(Color(str(def.get("background", "#zzzzzz"))) != Color(), id + " background is a colour")
		var lights: Array = def.get("lights", [])
		assert_gte(lights.size(), 1, id + " has lights")
		var shadows := 0
		for spec: Dictionary in lights:
			assert_true(str(spec.get("kind", "")) in ["spot", "omni", "sun"], "%s: light kind %s" % [id, spec.get("kind")])
			assert_gt(float(spec.get("energy", 0.0)), 0.0, id + " light energy")
			assert_eq((spec.get("at", []) as Array).size(), 3, id + " light position")
			if str(spec.get("kind")) != "omni":
				assert_eq((spec.get("look", []) as Array).size(), 3, id + " light looks at something")
			if bool(spec.get("shadow", false)):
				shadows += 1
		assert_lte(shadows, 2, id + " keeps shadows to two lights (the Iris Xe pays for each)")
	assert_true(Settings.get_s("hangar.light") in ids, "the default light setting is one of the presets")


func test_every_part_lands_in_a_group() -> void:
	_make_stage()
	var rows := stage.part_rows()
	assert_gt(rows.size(), 40, "the Juggernaut has many weighed parts (%d)" % rows.size())
	for r: Dictionary in rows:
		assert_ne(str(r["group"]), "other", "%s (%s) needs a group in hangar.json" % [r["id"], r["kind"]])
		assert_gt(float(r["mass_kg"]), 0.0)
		assert_ne(str(r["label"]), "")


func test_part_masses_add_up_to_the_mechs_mass() -> void:
	_make_stage()
	var sum := 0.0
	for r: Dictionary in stage.part_rows():
		sum += float(r["mass_kg"])
	assert_almost_eq(sum, stage.total_mass_kg(), 0.5, "the parts list is the mass the physics body carries")
	assert_gt(stage.total_mass_kg(), 4000.0, "a realistic Juggernaut, not a toy")


func test_labels_and_masses_read_cleanly() -> void:
	assert_eq(HangarStage.short_label("Juggernaut Model 2: canopy"), "Canopy")
	assert_eq(HangarStage.short_label("Juggernaut Model 2 thigh (FR)"), "Thigh (FR)")
	assert_eq(HangarStage.short_label("Juggernaut Model 2: sidepanel.R"), "Sidepanel (R)")
	assert_eq(HangarStage.short_label("Juggernaut Model 2: pod_tub"), "Pod tub")
	assert_eq(HangarStage.short_label("57 mm gun"), "57 mm gun")
	var hangar := load("res://scripts/ui/hangar.gd")
	assert_eq(hangar.kg(468.84), "469 kg")
	assert_eq(hangar.kg(35.74), "35.7 kg")
	assert_eq(hangar.kg(5563.7), "5,564 kg")


# --- the stage ---------------------------------------------------------------------------------


func test_the_juggernaut_stands_on_the_floor_and_shows_after_settling() -> void:
	_make_stage()
	assert_false(stage.mech.visible, "hidden while it drops onto its legs")
	await physics_frames(240)
	assert_true(stage.settled())
	assert_true(stage.mech.visible, "shown once settled")
	var p := stage.mech.global_position
	assert_gt(p.y, 1.3, "standing, not fallen through (y %.2f)" % p.y)
	assert_lt(p.y, 2.2, "standing, not floating (y %.2f)" % p.y)
	assert_lt(Vector2(p.x, p.z).length(), 0.4, "stays where it was put")
	await physics_frames(240)
	assert_almost_eq(stage.mech.global_position.y, p.y, 0.05, "no drift while standing")
	var size := stage.model_size()
	assert_gt(size.z, 6.0, "about eight metres long (%.1f)" % size.z)
	assert_gt(size.y, 2.5, "about three and a half metres high (%.1f)" % size.y)


func test_camera_orbit_zoom_and_pan_stay_in_limits() -> void:
	_make_stage()
	var f := stage.focus_point()
	var d0 := stage.camera.global_position.distance_to(f)
	stage.orbit(1.1, -0.2)
	assert_almost_eq(stage.camera.global_position.distance_to(f), d0, 0.01, "orbiting keeps the distance")
	for i in 60:
		stage.zoom(0.8)
	assert_almost_eq(stage.distance, 3.5, 0.001, "zoom in stops")
	for i in 60:
		stage.zoom(1.3)
	assert_almost_eq(stage.distance, 24.0, 0.001, "zoom out stops")
	stage.pan(100.0, 100.0)
	assert_almost_eq(stage.focus_offset.length(), 4.0, 0.01, "the focus stays near the mech")
	stage.orbit(0.0, -10.0)
	assert_almost_eq(rad_to_deg(stage.pitch), -80.0, 0.01, "pitch stops above the mech")
	stage.orbit(0.0, 10.0)
	assert_almost_eq(rad_to_deg(stage.pitch), 25.0, 0.01, "and below the chin")
	stage.reset_view()
	assert_eq(stage.focus_offset, Vector3.ZERO)
	assert_almost_eq(stage.distance, 12.5, 0.001, "reset gives the start view back")


func test_the_menu_camera_sways_and_keeps_the_mech_right_of_centre() -> void:
	_make_stage(true)
	await physics_frames(60)
	var f := stage.focus_point()
	assert_lt(stage.shift_x, 0.5)
	stage.shift_x = 0.2
	stage.age_s = 5.0
	var y0 := stage.yaw
	await physics_frames(240)
	assert_ne(snappedf(stage.yaw, 0.001), snappedf(y0, 0.001), "the camera sways by itself")
	assert_lt(absf(rad_to_deg(stage.yaw) - 150.0), 27.0, "within the sway")
	var on_screen := stage.camera.unproject_position(f)
	assert_gt(on_screen.x, stage.get_viewport().get_visible_rect().size.x * 0.55, "the mech is right of centre, clear of the buttons")


func test_a_point_on_the_picture_picks_a_part_with_its_mass() -> void:
	_make_stage()
	await physics_frames(240)
	var seen := {}
	var size := stage.get_viewport().get_visible_rect().size
	for ix in 24:
		for iy in 14:
			var hit := stage.pick(Vector2((ix + 0.5) * size.x / 24.0, (iy + 0.5) * size.y / 14.0))
			if hit.is_empty():
				continue
			seen[hit["id"]] = hit
	assert_gte(seen.size(), 8, "many different parts can be pointed at (%d)" % seen.size())
	for id: String in seen:
		var part := Registry.entry("parts", id)
		assert_almost_eq(float(seen[id]["mass_kg"]), float(part["mass_kg"]), 0.001, id + " shows the data's mass")
		assert_ne(str(seen[id]["label"]), "", id + " has a name")
	assert_true(stage.pick(Vector2(2, 2)).is_empty(), "the corner of the room is not a part")


func test_highlight_lights_every_copy_of_a_part() -> void:
	_make_stage()
	await physics_frames(10)
	assert_eq(stage.highlight("jg2_canopy"), 1, "the canopy")
	assert_eq(stage.highlighted_count(), 1)
	assert_gte(stage.highlight("jg2_thigh_FR"), 1, "a leg's thigh (its mesh is a detached node)")
	stage.clear_highlight()
	assert_eq(stage.highlighted_count(), 0)
	assert_eq(stage.highlight("jg2_int_pilot"), 0, "a point mass has no mesh to light")


func test_lights_switch_and_follow_the_preset() -> void:
	_make_stage()
	var ids := stage.light_ids()
	for id in ids:
		assert_eq(stage.set_light(id), id)
		var def := Registry.entry("hangar", id)
		assert_eq(stage.get_node("Lights").get_children().filter(func(n: Node) -> bool: return n is Light3D).size(), (def["lights"] as Array).size(), id + " builds its lights")
	assert_eq(stage.set_light("no_such_preset"), ids[0], "an unknown id falls back to the first preset")


## Catches the engine's warnings while it is added (OS.add_logger).
class WarningCatcher extends Logger:
	var warnings: PackedStringArray = []

	func _log_error(_function: String, _file: String, _line: int, code: String, rationale: String, _editor_notify: bool, error_type: int, _script_backtraces: Array[ScriptBacktrace]) -> void:
		if error_type == ERROR_TYPE_WARNING:
			warnings.append(code + " " + rationale)


func test_lamps_straight_above_their_mark_hang_level_without_a_warning() -> void:
	_make_stage()
	var catcher := WarningCatcher.new()
	OS.add_logger(catcher)
	var lamps := 0
	for id in stage.light_ids():
		stage.set_light(id)
		for n in stage.get_node("Lights").get_children():
			if n is MeshInstance3D:
				lamps += 1
				var long_side: Vector3 = (n as MeshInstance3D).global_basis.x.normalized()
				assert_lte(absf(long_side.y), 0.01, id + ": a lamp fixture hangs level")
	OS.remove_logger(catcher)
	assert_gte(lamps, 1, "some preset hangs a lamp (Showroom's ceiling lamps look straight down)")
	var colinear := Array(catcher.warnings).filter(func(w: String) -> bool: return w.contains("colinear"))
	assert_eq(colinear.size(), 0, "look_at warned while the lights were built: %s" % [colinear])


func test_the_blades_variant_builds_too() -> void:
	_make_stage()
	assert_true(stage.set_mech("juggernaut_m2_blades"))
	assert_eq(stage.mech_id, "juggernaut_m2_blades")
	assert_gt(stage.total_mass_kg(), 4000.0)
	assert_false(stage.set_mech("standin_not_here"), "an unknown mech is refused and the old one stays")
	assert_eq(stage.mech_id, "juggernaut_m2_blades")


# --- the screens -------------------------------------------------------------------------------


func test_the_hangar_screen_builds_from_the_data() -> void:
	_remember("hangar.light")
	var hangar := (load(HANGAR_SCENE) as PackedScene).instantiate() as Control
	tree.root.add_child(hangar)
	await physics_frames(200)
	var variants: PackedStringArray = hangar.get_script().call("_variant_ids")
	assert_true("juggernaut_m2" in variants)
	assert_true("juggernaut_m2_blades" in variants)
	assert_false("standin" in variants, "the test stand-in is not shown")
	assert_eq((hangar.get("_variant_buttons") as Dictionary).size(), variants.size())
	var light_button := hangar.get("_light_button") as Button
	assert_true(light_button.text.begins_with("Lighting:"), "the lighting selector shows the current preset")
	light_button.pressed.emit()
	assert_eq((hangar.get("stage") as HangarStage).light_id, Settings.get_s("hangar.light"), "pressing it steps to the next preset")
	assert_true((hangar.get("_total_label") as Label).text.ends_with(" kg"), "the total mass is shown")
	assert_gte((hangar.get("_group_rows") as Dictionary).size(), 3, "parts are grouped")
	assert_gt((hangar.get("_part_buttons") as Dictionary).size(), 40, "every weighed part has a row")
	assert_true(str((hangar.get("_size_label") as Label).text).contains("long"), "the size shows once it stands")
	assert_gte((hangar.get("_loadout_box") as Control).get_child_count(), 3, "the loadout slots are listed")
	hangar.free()


func test_pinning_a_part_opens_its_card_and_group() -> void:
	var hangar := (load(HANGAR_SCENE) as PackedScene).instantiate() as Control
	tree.root.add_child(hangar)
	await physics_frames(60)
	hangar.call("pin_part", "jg2_canopy")
	var s: HangarStage = hangar.get("stage")
	assert_eq(str((hangar.get("_card_title") as Label).text), "Canopy")
	assert_true(str((hangar.get("_card_body") as Label).text).contains("kg"), "the card shows the mass")
	assert_eq(s.highlighted_count(), 1, "and lights the part")
	var rows: Dictionary = hangar.get("_group_rows")
	assert_true((rows[hangar.get("pinned")["group"]]["rows"] as Control).visible, "its group opens in the list")
	hangar.call("pin_part", "")
	assert_eq(s.highlighted_count(), 0, "unpinning clears the light")
	hangar.free()


func test_pointing_at_a_part_shows_its_name_and_mass_in_a_tip() -> void:
	var hangar := (load(HANGAR_SCENE) as PackedScene).instantiate() as Control
	tree.root.add_child(hangar)
	await physics_frames(200)
	hangar.call("_update_hover", true)  # the pad's pointer: the centre of the picture
	var tip := hangar.get("_tip") as Control
	assert_true(tip.visible, "something is under the centre of the picture")
	var text := str((hangar.get("_tip_label") as Label).text)
	assert_true(text.ends_with("kg"), "the tip shows a mass: " + text)
	assert_eq(str((hangar.get("_card_title") as Label).text), str(hangar.get("hovered")["label"]), "and the card follows the pointer")
	assert_eq((hangar.get("stage") as HangarStage).highlighted_count() > 0, true, "the part under it is lit")
	hangar.free()


func test_the_hangar_changes_light_variant_and_hides_its_panels() -> void:
	_remember("hangar.light")
	var hangar := (load(HANGAR_SCENE) as PackedScene).instantiate() as Control
	tree.root.add_child(hangar)
	await physics_frames(30)
	hangar.call("show_light", "work_lights")
	assert_eq((hangar.get("stage") as HangarStage).light_id, "work_lights")
	assert_eq(Settings.get_s("hangar.light"), "work_lights", "the choice is remembered for the menu")
	hangar.call("cycle_light", 1)
	assert_ne((hangar.get("stage") as HangarStage).light_id, "work_lights")
	hangar.call("show_variant", "juggernaut_m2_blades")
	assert_eq((hangar.get("stage") as HangarStage).mech_id, "juggernaut_m2_blades")
	hangar.call("set_panels_hidden", true)
	assert_false((hangar.get("_ui") as Control).visible)
	hangar.call("set_panels_hidden", false)
	assert_true((hangar.get("_ui") as Control).visible)
	hangar.free()


func test_the_main_menu_shows_the_juggernaut_behind_the_buttons() -> void:
	_remember("interface.menu_showcase")
	Settings.set_value("interface.menu_showcase", true, false)
	var menu := (load(MENU_SCENE) as PackedScene).instantiate() as Control
	tree.root.add_child(menu)
	await physics_frames(30)
	var s: HangarStage = menu.get("_stage")
	assert_true(s != null, "the stage is there")
	assert_true(s.showcase, "swaying by itself")
	assert_false((menu.get("_backdrop") as Control).visible, "the plain backdrop steps aside")
	var hangar_button: Button = null
	for b: Node in (menu.get("_menu") as Control).get_children():
		if b is Button and (b as Button).text == "Hangar":
			hangar_button = b as Button
	assert_true(hangar_button != null and not hangar_button.disabled, "the Hangar entry is live")
	Settings.set_value("interface.menu_showcase", false, false)
	await physics_frames(5)
	assert_true(menu.get("_stage") == null, "off removes it")
	assert_true((menu.get("_backdrop") as Control).visible, "and gives the backdrop back")
	Settings.set_value("interface.menu_showcase", true, false)
	await physics_frames(5)
	assert_true(menu.get("_stage") != null, "on brings it back")
	menu.free()


func test_the_game_can_open_the_hangar() -> void:
	assert_true(ResourceLoader.exists(Game.HANGAR))
	assert_true(Game.has_method("goto_hangar"))
