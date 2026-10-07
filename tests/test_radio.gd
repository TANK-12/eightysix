extends "res://tests/lib/test_case.gd"
## Handler radio (lane A7): the Handler calls each wave with what it holds and its bearing, your kills,
## the parts you shoot off, and the end; lines cool down, once-only ones stay once, and the setting or
## the subtitles toggle silences it.

const RIG := preload("res://tests/lib/mission_rig.gd")


class FakeUnit:
	extends Node
	var enemy_id := ""

	func _init(id: String) -> void:
		enemy_id = id


var rig: RefCounted


func before_each() -> void:
	rig = RIG.new(tree)


func after_each() -> void:
	rig.free_all()
	for key: String in ["gameplay.handler_radio", "gameplay.kill_cam", "accessibility.subtitles"]:
		Settings.set_value(key, Settings.default_of(key), false)


func _hud(m: Mission) -> MissionHud:
	var hud := MissionHud.new()
	rig.level.add_child(hud)
	hud.watch(m)
	return hud


func test_describe_counts_each_kind() -> void:
	var units: Array = [FakeUnit.new("grauwolf"), FakeUnit.new("grauwolf"), FakeUnit.new("grauwolf"), FakeUnit.new("lowe")]
	assert_eq(HandlerRadio.describe(units), "three Grauwolf and a Löwe")
	assert_eq(HandlerRadio.describe([units[3]]), "a Löwe")
	for u: Node in units:
		u.free()


func test_waves_kills_parts_and_the_end_are_called() -> void:
	Settings.set_value("gameplay.kill_cam", false, false)
	var m: Mission = rig.mission([["ameise", "ameise"], ["grauwolf"]], 300.0)
	var hud := _hud(m)
	await physics_frames(10)
	var radio := hud.radio
	assert_gt(radio.said.size(), 0, "the first wave is called at once")
	var first := str(radio.said[0])
	assert_true(first.contains("two Ameise"), "with what it holds: " + first)
	assert_true(first.contains("bearing 3") or first.contains("bearing 0"), "and the bearing (north): " + first)
	var a: LegionMech = m.units[0]
	var leg := "leg_" + str(a.legs[0]["tag"])
	a.take_hit({"key": leg, "damage": 99999.0, "penetration_mm": 900.0, "point": a.global_position, "shooter": rig.level.mech, "splash": false})
	rig.kill_as_player(a)
	await physics_frames(2)
	var queued := " | ".join(radio._queue.map(func(q: Array) -> String: return str(q[1])))
	assert_true(queued.contains("leg") or queued.contains("Leg") or queued.contains("limping"), "the leg shot off is called: " + queued)
	assert_true(queued.contains("Ameise") or queued.contains("kill") or queued.contains("scrap"), "and the kill: " + queued)
	rig.kill_as_player(m.units[1])
	await physics_frames(60)
	rig.kill_as_player(m.units[0])
	await physics_frames(3)
	assert_eq(m.state, "won")
	await physics_frames(200)
	var all := " | ".join(radio.said)
	assert_true(all.contains("Undertaker") or all.contains("Handler One"), all)
	assert_true(radio.said.any(func(t: String) -> bool: return t.contains("Sector clear") or t.contains("All Legion destroyed")), "the win is called: " + all)


func test_cooldown_once_and_off() -> void:
	var radio := HandlerRadio.new()
	rig.level.add_child(radio)
	assert_ne(radio.say("kill", {"enemy": "Ameise"}), "", "a kill line")
	assert_eq(radio.say("kill", {"enemy": "Ameise"}), "", "cooling down right after")
	assert_ne(radio.say("armour_low"), "")
	radio._cool.clear()
	assert_eq(radio.say("armour_low"), "", "armour low is said once a mission")
	var line := radio.say("part.wp_rocket_pod")
	assert_true(line.contains("rockets"), "rocket pod line: " + line)
	Settings.set_value("gameplay.handler_radio", false, false)
	radio._cool.clear()
	assert_eq(radio.say("part.wp_rocket_pod"), "", "the setting silences it")
	Settings.set_value("gameplay.handler_radio", true, false)
	Settings.set_value("accessibility.subtitles", false, false)
	assert_eq(radio.say("part.wp_optic_sensor"), "", "so does Subtitles off")


func test_lines_show_one_at_a_time_and_type_out() -> void:
	var radio := HandlerRadio.new()
	rig.level.add_child(radio)
	radio.say("part.wp_rocket_pod")
	radio.say("part.wp_optic_sensor")
	await tree.process_frame
	await tree.process_frame
	assert_ne(radio.shown_line, "", "one line on screen")
	assert_eq(radio._queue.size(), 1, "the other waits")
	assert_lt(radio._text.visible_ratio, 1.0, "typed out, not all at once")
	await physics_frames(ceili(radio.shown_line.length() / HandlerRadio.TYPE_CHARS_S * 120.0) + 4)
	assert_eq(radio._text.visible_ratio, 1.0, "typed out at TYPE_CHARS_S")
