extends "res://tests/lib/test_case.gd"
## Lane A6 (the plan: "a tutorial only as a stub that is off by default; he decides after testing").
## data/tutorial.json lists the steps; Tutorial shows one at a time and moves on when its done_when holds.

const TUTORIAL := preload("res://scripts/ui/tutorial.gd")


func after_each() -> void:
	Settings.reset_all_quietly()


func _entries() -> Dictionary:
	return Registry.file("tutorial").get("entries", {})


func _state(over: Dictionary) -> Dictionary:
	var s := {"play_s": 0.0, "step_s": 0.0, "speed_m_s": 0.0, "running": false, "charging": false, "airborne": false, "skidding": false, "anchor_ready": false, "cockpit_view": false}
	s.merge(over, true)
	return s


func test_off_by_default() -> void:
	assert_false(Settings.get_b("gameplay.tutorial"), "the tutorial stub is off until Emerson decides")


func test_every_step_is_well_formed() -> void:
	var entries := _entries()
	assert_gt(entries.size(), 3, "a few steps")
	var known := ["step_s", "play_s", "speed_m_s", "running", "charging", "airborne", "skidding", "anchor_ready", "cockpit_view", "squad"]
	var orders := {}
	for id: String in entries:
		var e: Dictionary = entries[id]
		assert_ne(str(e.get("text", "")), "", "%s has text" % id)
		assert_false(orders.has(float(e.get("order", 0.0))), "%s has its own order" % id)
		orders[float(e.get("order", 0.0))] = true
		assert_gt((e.get("done_when", []) as Array).size(), 0, "%s says when it is done" % id)
		for item: Dictionary in e["done_when"]:
			assert_true(known.has(str(item["key"])), "%s tests a known state key (%s)" % [id, item["key"]])
		for m in RegEx.create_from_string("\\{([a-z_]+)\\}").search_all(str(e["text"])):
			assert_true(Controls.action_info(m.get_string(1)).size() > 0, "%s names a real action (%s)" % [id, m.get_string(1)])


func test_steps_advance_in_order() -> void:
	var e := _entries()
	var ids: Array = TUTORIAL.ordered(e)
	assert_eq(ids[0], "welcome", "welcome first")
	assert_eq(TUTORIAL.advance(ids, e, 0, _state({"step_s": 1.0})), 0, "the welcome stays a few seconds")
	assert_eq(TUTORIAL.advance(ids, e, 0, _state({"step_s": 6.5})), 1, "then the walk")
	var walk := ids.find("walk")
	assert_eq(TUTORIAL.advance(ids, e, walk, _state({"step_s": 3.0})), walk, "standing still does not finish the walk")
	assert_eq(TUTORIAL.advance(ids, e, walk, _state({"step_s": 3.0, "speed_m_s": 3.0})), walk + 1, "walking does")
	var view := ids.find("view")
	assert_eq(TUTORIAL.advance(ids, e, view, _state({"cockpit_view": true})), view + 1, "the cockpit view")
	assert_eq(TUTORIAL.advance(ids, e, ids.size(), _state({})), ids.size(), "past the last step it stays finished")


func test_shows_only_when_switched_on() -> void:
	var hints := MoveHints.new()
	hints.persist = false
	tree.root.add_child(hints)
	var mech := MechBuilder.build("juggernaut_m2")
	tree.root.add_child(mech)
	hints.watch(mech)
	var tut: Control = TUTORIAL.new()
	tree.root.add_child(tut)
	tut.call("watch", hints)
	await tree.process_frame
	await tree.process_frame
	assert_eq(str(tut.get("_text")), "", "off: nothing shown")
	assert_eq(int(tut.get("step_s") * 1000.0), 0, "off: the clock does not run")
	Settings.set_value("gameplay.tutorial", true, false)
	await tree.process_frame
	await tree.process_frame
	assert_eq(str(tut.call("current_id")), "welcome", "on: the first step")
	assert_true(str(tut.get("_text")).contains("Tutorial"), "its text is drawn")
	tut.set("step_s", 7.0)
	await tree.process_frame
	assert_eq(str(tut.call("current_id")), "walk", "the welcome moves on by itself")
	assert_false(str(tut.get("_text")).contains("{"), "the keys are named")
	tut.free()
	mech.free()
	hints.free()
