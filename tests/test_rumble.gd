extends "res://tests/lib/test_case.gd"
## Rumble patterns scale with the settings and loop or end as written.


func after_each() -> void:
	Settings.reset_all_quietly()
	Rumble.stop_all()


func test_scaling_by_settings() -> void:
	var full := Rumble.scaled_steps("fire_main")
	assert_eq(full[0]["strong"], 1.0)
	Settings.set_value("rumble.weapons", 0.5, false)
	assert_almost_eq(Rumble.scaled_steps("fire_main")[0]["strong"], 0.5, 0.0001)
	Settings.set_value("rumble.intensity", 0.5, false)
	assert_almost_eq(Rumble.scaled_steps("fire_main")[0]["strong"], 0.25, 0.0001)
	Settings.set_value("rumble.enabled", false, false)
	assert_eq(Rumble.scaled_steps("fire_main")[0]["strong"], 0.0)
	assert_eq(Rumble.scaled_steps("no_such_event"), [])


func test_values_are_clamped() -> void:
	Settings.set_value("rumble.intensity", 1.5, false)
	Settings.set_value("rumble.weapons", 1.5, false)
	for step: Dictionary in Rumble.scaled_steps("fire_main"):
		assert_between(step["strong"], 0.0, 1.0)
		assert_between(step["weak"], 0.0, 1.0)


func test_one_shot_ends_and_loop_keeps_going() -> void:
	Rumble.play("ui_confirm")
	Rumble.play("skid")
	for i in 30:
		await tree.process_frame
	await tree.create_timer(0.2).timeout
	assert_false(Rumble.is_playing("ui_confirm"), "25 ms pattern is over")
	assert_true(Rumble.is_playing("skid"), "looping pattern still going")
	Rumble.stop("skid")
	assert_false(Rumble.is_playing("skid"))
