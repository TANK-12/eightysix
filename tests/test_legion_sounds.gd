extends "res://tests/lib/test_case.gd"
## Legion sounds (lane A4 part 7): a Legion mech's own signals make sound through MechSounds, with the
## step, servo and gun sounds named per enemy in data/enemies.json "sounds".

var cam: Camera3D
var mechs: Array = []


func before_each() -> void:
	cam = Camera3D.new()
	tree.root.add_child(cam)
	cam.make_current()
	mechs = []


func after_each() -> void:
	for m: Node in mechs:
		m.free()
	cam.free()


func _legion(id: String) -> LegionMech:
	var m := LegionMech.build(id)
	m.position = Vector3(0, 400, -30)
	m.freeze = true
	tree.root.add_child(m)
	mechs.append(m)
	return m


func test_every_enemy_names_real_sounds() -> void:
	for id in Registry.ids("enemies"):
		var def := Registry.entry("enemies", id)
		var s: Dictionary = def.get("sounds", {})
		assert_false(s.is_empty(), id + " has a sounds block")
		for key in ["step", "servo"]:
			assert_true(Sfx.has(str(s.get(key, ""))), "%s %s names a sound in sounds.json" % [id, key])
		for w in def.get("weapons", []):
			assert_true(Registry.file("sounds").get("weapons", {}).has(str(w)), "%s: weapon %s has a sound" % [id, w])


func test_a_legion_step_and_shot_make_sound() -> void:
	var m := _legion("ameise")
	await physics_frames(4)
	assert_true(m.has_node("MechSounds"), "Sfx attached MechSounds to the Legion")
	var legs: Array = m.legs
	assert_gt(legs.size(), 0)
	var before := Sfx.played
	var steps := int(Sfx.counts.get("legion_step_light", 0))
	m.emit_signal("stepped", str(legs[0]["tag"]))
	assert_eq(Sfx.played, before + 1, "a step makes a sound")
	assert_eq(int(Sfx.counts.get("legion_step_light", 0)), steps + 1, "the Legion's own step sound, not the Juggernaut's")
	var shots := int(Sfx.counts.get("mg_12_7_fire", 0))
	m.emit_signal("fired", "ameise_mg", "ball")
	assert_eq(int(Sfx.counts.get("mg_12_7_fire", 0)), shots + 1, "its machine gun is heard")


func test_the_heavy_steps_louder_and_lower_than_the_scout() -> void:
	var a := Registry.entry("enemies", "ameise")["sounds"] as Dictionary
	var l := Registry.entry("enemies", "lowe")["sounds"] as Dictionary
	assert_gt(float(l["step_db"]), float(a["step_db"]), "the Loewe's step is louder")
	assert_lt(float(l["step_pitch"]), float(a["step_pitch"]), "and lower")


func test_the_loewe_gun_and_the_pack_weapons_are_heard() -> void:
	var m := _legion("lowe")
	await physics_frames(4)
	var shots := int(Sfx.counts.get("lowe_fire", 0))
	m.emit_signal("fired", "lowe_120mm", "he")
	assert_eq(int(Sfx.counts.get("lowe_fire", 0)), shots + 1, "the 120 mm is heard")
	var g := _legion("grauwolf")
	await physics_frames(4)
	var hiss := int(Sfx.counts.get("hydraulic_hiss", 0))
	g.emit_signal("fired", "grauwolf_rockets", "heat")
	assert_eq(int(Sfx.counts.get("hydraulic_hiss", 0)), hiss + 1, "a rocket launch is heard")


func test_the_servo_loop_follows_the_legion() -> void:
	var m := _legion("grauwolf")
	await physics_frames(4)
	var ms := m.get_node("MechSounds")
	assert_true(ms.get("_servo") != null, "a servo loop rides the Legion mech")
