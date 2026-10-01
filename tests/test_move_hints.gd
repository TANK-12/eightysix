extends "res://tests/lib/test_case.gd"
## Lane A4 part 5 (the plan: "the first time a move is possible a small hint shows, and a setting turns hints
## off"). data/hints.json lists the hints; MoveHints picks the first one that is due and not yet seen.


func after_each() -> void:
	Settings.reset_all_quietly()


func _entries() -> Dictionary:
	return Registry.file("hints").get("entries", {})


func test_every_hint_is_well_formed() -> void:
	var entries := _entries()
	assert_gt(entries.size(), 5, "the moves are covered")
	var known := ["play_s", "speed_m_s", "running", "charging", "airborne", "skidding", "anchor_ready", "cockpit_view"]
	var orders := {}
	for id: String in entries:
		var e: Dictionary = entries[id]
		assert_ne(str(e.get("text", "")), "", "%s has text" % id)
		assert_false(orders.has(float(e.get("order", 0.0))), "%s has its own order" % id)
		orders[float(e.get("order", 0.0))] = true
		assert_gt((e.get("when", []) as Array).size(), 0, "%s says when it is due" % id)
		for item: Dictionary in e["when"]:
			assert_true(known.has(str(item["key"])), "%s tests a state key MoveHints builds (%s)" % [id, item["key"]])
		for m in RegEx.create_from_string("\\{([a-z_]+)\\}").search_all(str(e["text"])):
			assert_true(Controls.action_info(m.get_string(1)).size() > 0, "%s names a real action (%s)" % [id, m.get_string(1)])


func test_matches_numbers_and_flags() -> void:
	var state := {"speed_m_s": 5.0, "running": false}
	assert_true(MoveHints.matches([{"key": "speed_m_s", "min": 2.0}, {"key": "running", "is": false}], state))
	assert_false(MoveHints.matches([{"key": "speed_m_s", "max": 2.0}], state))
	assert_false(MoveHints.matches([{"key": "running", "is": true}], state))
	assert_false(MoveHints.matches([{"key": "no_such_key", "min": 0.0}], state), "an unknown key never matches")


func _state(over: Dictionary) -> Dictionary:
	var s := {"play_s": 0.0, "speed_m_s": 0.0, "running": false, "charging": false, "airborne": false, "skidding": false, "anchor_ready": false, "cockpit_view": false}
	s.merge(over, true)
	return s


func test_hints_come_when_the_move_is_possible_and_only_once() -> void:
	var e := _entries()
	assert_eq(MoveHints.pick(e, _state({}), []), "", "nothing at the very start")
	assert_eq(MoveHints.pick(e, _state({"play_s": 6.0}), []), "view", "the view switch first")
	assert_eq(MoveHints.pick(e, _state({"play_s": 6.0}), ["view"]), "", "a seen hint does not come again")
	assert_eq(MoveHints.pick(e, _state({"play_s": 9.0, "speed_m_s": 6.0}), ["view"]), "sprint", "walking and not running: the gallop")
	assert_eq(MoveHints.pick(e, _state({"play_s": 30.0, "speed_m_s": 15.0, "running": true}), ["view", "sprint", "jump"]), "slide", "at a gallop: the slide")
	assert_eq(MoveHints.pick(e, _state({"play_s": 30.0, "charging": true, "speed_m_s": 0.2}), ["view", "jump"]), "flip", "charging a jump: the flip")
	assert_eq(MoveHints.pick(e, _state({"play_s": 30.0, "anchor_ready": true}), ["view", "jump"]), "wire", "an anchor target: the wire")
	assert_eq(MoveHints.pick(e, _state({"play_s": 30.0, "airborne": true, "speed_m_s": 8.0}), ["view", "sprint", "jump", "slide", "flip", "wire"]), "air", "in the air: the legs")


func test_the_text_shows_the_players_own_keys() -> void:
	var text := MoveHints.bind_text("Hold {sprint} to gallop and {camera_view} for the cockpit.")
	assert_false(text.contains("{"), "every action is replaced (%s)" % text)
	assert_true(text.contains("Shift"), "the default run key is named")
	assert_true(text.contains("V"), "the default view key is named")


func test_the_setting_turns_hints_off() -> void:
	var hints := MoveHints.new()
	tree.root.add_child(hints)
	var mech := MechBuilder.build("juggernaut_m2")
	tree.root.add_child(mech)
	hints.watch(mech)
	hints.persist = false
	Settings.set_value("gameplay.move_hints", false, false)
	hints.set("_play_s", 100.0)
	hints.set("_gap_s", 0.0)
	await physics_frames(5)
	await tree.process_frame
	assert_eq(hints.current, "", "off: nothing is shown")
	Settings.set_value("gameplay.move_hints", true, false)
	hints.set("_gap_s", 0.0)
	await tree.process_frame
	await tree.process_frame
	assert_ne(hints.current, "", "on: the first due hint shows")
	assert_true(hints.seen.has(hints.current), "and is marked seen")
	mech.free()
	hints.free()
