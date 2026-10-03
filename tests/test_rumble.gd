extends "res://tests/lib/test_case.gd"
## Rumble patterns scale with the settings and loop or end as written.


const FRAME_S := 1.0 / 120.0


func before_each() -> void:
	Settings.reset_all_quietly()  # the player's own saved Rumble sliders must not leak into the checks
	Rumble.stop_all()
	Rumble.test_pads = [0]
	Rumble.record = true
	Rumble.log.clear()


func after_each() -> void:
	Settings.reset_all_quietly()
	tree.paused = false
	Rumble.stop_all()
	Rumble.record = false
	Rumble.test_pads = []
	Rumble.log.clear()


func _frames(n: int) -> void:
	for i in n:
		await tree.process_frame


func _starts() -> Array:
	return Rumble.log.filter(func(e: Dictionary) -> bool: return e["kind"] == "start")


func _last_kind() -> String:
	return "" if Rumble.log.is_empty() else str(Rumble.log[-1]["kind"])


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
	for i in 40:
		Rumble.play("skid")
		await tree.process_frame
	assert_false(Rumble.is_playing("ui_confirm"), "25 ms pattern is over")
	assert_true(Rumble.is_playing("skid"), "looping pattern still going")
	Rumble.stop("skid")
	assert_false(Rumble.is_playing("skid"))


func test_a_one_shot_stops_at_its_length_plus_a_frame() -> void:
	var t0 := Rumble._clock
	Rumble.play("fire_main")
	await _frames(60)
	var length := 0.07 + 0.11 + 0.16
	assert_eq(_last_kind(), "stop", "motors told to stop")
	var stop_at: float = Rumble.log[-1]["t"] - t0
	assert_between(stop_at, length - FRAME_S, length + 2.0 * FRAME_S, "stop time %.3f s vs %.3f s" % [stop_at, length])
	assert_false(Rumble.is_playing("fire_main"))


func test_every_effect_sent_to_the_pad_has_a_finite_length() -> void:
	Rumble.play("fire_main")
	Rumble.play("grapple_tension")
	for i in 120:
		Rumble.play("grapple_tension")
		await tree.process_frame
	Rumble.stop("grapple_tension")
	await _frames(60)
	assert_gt(_starts().size(), 2)
	for e: Dictionary in _starts():
		assert_between(e["duration"], 0.01, Rumble.SEND_CEIL_S + Rumble.SEND_SLACK_S + 0.001, "duration of a send")


func test_a_step_is_not_handed_to_the_pad_longer_than_it_lasts_plus_slack() -> void:
	var t0 := Rumble._clock
	Rumble.play("fire_main")
	await _frames(60)
	for e: Dictionary in _starts():
		var ends: float = e["t"] - t0 + e["duration"]
		assert_lt(ends, 0.34 + Rumble.SEND_SLACK_S + 2.0 * FRAME_S, "a hitch cannot extend it past the pattern + slack")


func test_a_start_reaches_the_pad_on_the_frame_of_its_event() -> void:
	await tree.process_frame
	var frame := Engine.get_process_frames()
	Rumble.play("hit_heavy")
	await tree.process_frame
	assert_eq(_starts().size(), 1)
	assert_eq(int(_starts()[0]["frame"]), frame, "same frame, not the next")


func test_a_loop_dies_when_nothing_refreshes_it() -> void:
	for i in 30:
		Rumble.play("skid")
		await tree.process_frame
	assert_true(Rumble.is_playing("skid"))
	await _frames(int(ceil((0.25 + 0.05) / FRAME_S)))
	assert_false(Rumble.is_playing("skid"), "lapsed after hold_ms")
	assert_eq(_last_kind(), "stop")


func test_a_loop_stops_on_the_same_frame_its_cause_ends() -> void:
	for i in 10:
		Rumble.play("skid")
		await tree.process_frame
	var frame := Engine.get_process_frames()
	Rumble.stop("skid")
	await tree.process_frame
	assert_eq(_last_kind(), "stop")
	assert_eq(int(Rumble.log[-1]["frame"]), frame)


class Owner:
	extends Node

	func _process(_delta: float) -> void:
		Rumble.play("skid")
		Rumble.play("grapple_tension")


func test_freeing_the_owner_stops_its_loops() -> void:
	var owner_node := Owner.new()
	tree.root.add_child(owner_node)
	await _frames(20)
	assert_true(Rumble.is_playing("skid"))
	assert_true(Rumble.is_playing("grapple_tension"))
	owner_node.queue_free()
	await _frames(int(ceil((0.25 + 0.05) / FRAME_S)))
	assert_false(Rumble.is_playing("skid"))
	assert_false(Rumble.is_playing("grapple_tension"))
	assert_eq(_last_kind(), "stop")


func test_pausing_stops_loops_even_if_the_owner_keeps_calling() -> void:
	var owner_node := Owner.new()
	owner_node.process_mode = Node.PROCESS_MODE_ALWAYS
	tree.root.add_child(owner_node)
	await _frames(10)
	assert_eq(_last_kind(), "start")
	tree.paused = true
	await _frames(3)
	assert_eq(_last_kind(), "stop", "silent within a few frames of pausing")
	assert_false(Rumble.is_playing("skid"))
	tree.paused = false
	owner_node.queue_free()
	await _frames(5)


func test_a_menu_tick_still_plays_while_paused() -> void:
	tree.paused = true
	await tree.process_frame
	Rumble.play("ui_confirm")
	await tree.process_frame
	assert_eq(_starts().size(), 1)
	await _frames(10)
	assert_eq(_last_kind(), "stop")


func test_leaving_the_level_silences_everything() -> void:
	Rumble.play("fire_main")
	Rumble.play("skid")
	await _frames(3)
	assert_eq(_last_kind(), "start")
	Game._leave_level()
	assert_eq(_last_kind(), "stop", "at once, not a frame later")
	assert_false(Rumble.is_playing("fire_main"))
	assert_false(Rumble.is_playing("skid"))


func test_a_loop_that_is_refreshed_forever_still_ends_at_its_ceiling() -> void:
	Rumble.play("skid")
	(Rumble._playing["skid"] as Dictionary)["max"] = 0.3
	for i in 90:
		Rumble.play("skid")
		await tree.process_frame
	assert_true(Rumble.is_playing("skid"), "the owner still thinks it is skidding")
	assert_eq(_last_kind(), "stop", "but the motors are off past max_s")
	var stop_at: float = Rumble.log[-1]["t"]
	assert_lt(stop_at - (Rumble._clock - 90.0 * FRAME_S), 0.3 + 3.0 * FRAME_S)


func test_the_same_event_sixty_times_a_second_does_not_restart_the_motor_every_frame() -> void:
	for i in 120:
		Rumble.play("hit_light")
		await tree.process_frame
	var n := _starts().size()
	assert_lt(n, 8, "%d starts in one second of re-fires" % n)
	Rumble.log.clear()
	for i in 120:
		Rumble.play("grapple_tension")
		await tree.process_frame
	n = _starts().size()
	assert_lt(n, 8, "%d starts in one second of a held loop" % n)
	assert_gt(n, 3, "but it is refreshed before the effect on the pad runs out")


func test_changing_values_are_sent_once_each() -> void:
	Rumble.play("fire_main")
	await _frames(60)
	assert_eq(_starts().size(), 3, "one send per step")


func test_turning_rumble_off_mid_loop_goes_quiet() -> void:
	for i in 10:
		Rumble.play("skid")
		await tree.process_frame
	assert_eq(_last_kind(), "start")
	Settings.set_value("rumble.enabled", false, false)
	for i in 40:
		Rumble.play("skid")
		await tree.process_frame
	assert_eq(_last_kind(), "stop")


func test_losing_window_focus_keeps_the_pad_quiet_while_the_cause_goes_on() -> void:
	var owner_node := Owner.new()
	tree.root.add_child(owner_node)
	await _frames(10)
	assert_eq(_last_kind(), "start")
	Rumble.notification(Node.NOTIFICATION_APPLICATION_FOCUS_OUT)
	await _frames(30)
	assert_eq(_last_kind(), "stop", "a skid or a taut wire in the background must not buzz the pad")
	Rumble.log.clear()
	Rumble.play("fire_main")
	await _frames(10)
	assert_eq(_starts().size(), 0, "nothing reaches the pad while unfocused")
	Rumble.notification(Node.NOTIFICATION_APPLICATION_FOCUS_IN)
	await _frames(3)
	assert_eq(_last_kind(), "start", "back on focus")
	owner_node.queue_free()
	await _frames(5)
