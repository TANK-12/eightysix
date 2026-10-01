extends "res://tests/lib/test_case.gd"
## Input: binding strings, the InputMap per scheme, rebinding and clashes, dead zones and curves.

var _saved_path := ""


func before_each() -> void:
	_saved_path = Controls.save_path
	Controls.save_path = "user://test_bindings.cfg"
	Controls.reset_scheme("standard")
	Controls.reset_scheme("hardcore")
	Controls.apply_scheme("standard")


func after_each() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path("user://test_bindings.cfg"))
	Controls.save_path = _saved_path
	Controls.load_overrides()
	Controls.apply_scheme("standard")


func test_binding_strings_round_trip() -> void:
	for s: String in ["key:W", "key:Space", "key:Shift", "mouse:left", "mouse:wheel_up", "joy:cross",
			"joy:touchpad", "joy:left_y-", "joy:right_x+", "joy:r2", "joy:l2"]:
		var ev := Controls.parse_binding(s)
		assert_not_null(ev, s)
		assert_eq(Controls.binding_of(ev), s, s)
	assert_eq(Controls.parse_binding("key:NotAKey"), null)
	assert_eq(Controls.binding_label("joy:cross"), "Cross")
	assert_eq(Controls.binding_label("joy:left_y-"), "Left stick up")


func test_every_registry_binding_parses() -> void:
	for action in Controls.actions():
		for scheme: String in ["standard", "hardcore"]:
			var b := Controls.bindings(action, scheme)
			for s: String in b["keys"] + b["pad"]:
				assert_not_null(Controls.parse_binding(s), "%s %s %s" % [scheme, action, s])


func test_menus_answer_the_pad() -> void:
	for scheme_name: String in ["standard", "hardcore"]:
		Controls.apply_scheme(scheme_name)
		for pair: Array in [["ui_accept", "joy:cross"], ["ui_accept", "key:Enter"],
				["ui_cancel", "joy:circle"], ["ui_cancel", "key:Escape"],
				["ui_up", "joy:dpad_up"], ["ui_up", "joy:left_y-"], ["ui_down", "joy:left_y+"],
				["ui_left", "joy:left_x-"], ["ui_right", "joy:left_x+"], ["ui_right", "key:Right"]]:
			var ev := Controls.parse_binding(pair[1])
			if ev is InputEventJoypadMotion:
				(ev as InputEventJoypadMotion).axis_value *= 0.8
			else:
				ev.set("pressed", true)
			assert_true(ev.is_action_pressed(pair[0]), "%s %s %s" % [scheme_name, pair[0], pair[1]])


func test_schemes_swap_the_input_map() -> void:
	assert_true(InputMap.has_action("move_forward"))
	assert_gt(InputMap.action_get_events("move_forward").size(), 1)
	assert_eq(InputMap.action_get_events("leg_lift_fl").size(), 0, "hardcore actions empty in standard")
	Controls.apply_scheme("hardcore")
	assert_gt(InputMap.action_get_events("leg_lift_fl").size(), 0)
	var fire_pad: Array = Controls.bindings("fire_main", "hardcore")["pad"]
	assert_eq(fire_pad, ["joy:square"], "shoulders belong to the legs in hardcore")
	assert_eq(InputMap.action_get_events("move_forward").size(), 0)


func test_rebind_saves_loads_and_reports_clashes() -> void:
	Controls.set_binding("move_forward", "standard", "keys", 0, "key:S")
	assert_has(Controls.conflicts("move_forward", "standard", "key:S"), "move_back")
	assert_false("order_follow" in Controls.conflicts("fire_sub", "standard", "joy:r1"), "handler-only action does not clash")
	Controls.load_overrides()
	assert_eq(Controls.bindings("move_forward", "standard")["keys"], ["key:S"])
	Controls.set_binding("move_forward", "standard", "keys", 1, "key:Up")
	assert_eq(Controls.bindings("move_forward", "standard")["keys"], ["key:S", "key:Up"])
	Controls.reset_scheme("standard")
	assert_eq(Controls.bindings("move_forward", "standard")["keys"], ["key:W"])


func test_shape_dead_zone_curve_and_sign() -> void:
	assert_eq(Controls.shape(0.1, 0.12, 0.95, 1.5), 0.0, "inside the dead zone")
	assert_eq(Controls.shape(0.97, 0.12, 0.95, 1.5), 1.0, "past the outer zone")
	assert_eq(Controls.shape(-0.97, 0.12, 0.95, 1.5), -1.0, "keeps sign")
	assert_almost_eq(Controls.shape(0.535, 0.12, 0.95, 1.0), 0.5, 0.001, "linear midpoint")
	assert_lt(Controls.shape(0.535, 0.12, 0.95, 2.0), 0.26, "curve softens the middle")
	var last := -1.0
	for i in 101:
		var v := Controls.shape(i / 100.0, 0.1, 0.9, 1.7)
		assert_true(v >= last, "monotonic")
		last = v


func test_stick_dead_zone_is_radial() -> void:
	var diag := Controls.shape_stick(Vector2(0.7, 0.7), 0.1, 0.95, 1.0)
	assert_almost_eq(diag.x, diag.y, 0.0001, "diagonal stays diagonal")
	assert_eq(Controls.shape_stick(Vector2(0.05, 0.05), 0.1, 0.95, 1.0), Vector2.ZERO)
	assert_almost_eq(Controls.shape_stick(Vector2(1.0, 0.0), 0.1, 0.95, 1.5).length(), 1.0, 0.0001)


func test_trigger_and_fire_threshold() -> void:
	Input.action_press("fire_main", 0.3)
	assert_false(Controls.held("fire_main"), "below the fire point")
	Input.action_press("fire_main", 0.8)
	assert_true(Controls.held("fire_main"))
	Input.action_release("fire_main")
