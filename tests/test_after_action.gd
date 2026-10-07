extends "res://tests/lib/test_case.gd"
## After-action report (lane A7): the sortie log counts the player's shots, hits, parts shot off, kills and
## the longest one, and damage taken; the end card shows a grade and the personal bests a win beat.

const RIG := preload("res://tests/lib/mission_rig.gd")
const SORTIE_LOG := preload("res://scripts/mission/sortie_log.gd")

var rig: RefCounted


func before_each() -> void:
	rig = RIG.new(tree)


func after_each() -> void:
	rig.free_all()
	DirAccess.remove_absolute(ProjectSettings.globalize_path("user://test_records.cfg"))


func test_grade_from_win_armour_accuracy_and_time() -> void:
	assert_eq(SORTIE_LOG.score(true, 1.0, 0.6, 300.0, 600.0), 100, "a perfect win")
	assert_eq(SORTIE_LOG.grade_of(100), "S")
	assert_eq(SORTIE_LOG.grade_of(SORTIE_LOG.score(true, 0.5, 0.3, 900.0, 600.0)), "B", "a scrappy win: 40 + 12.5 + 10 + 10")
	assert_eq(SORTIE_LOG.grade_of(SORTIE_LOG.score(false, 0.0, 0.2, 100.0, 600.0)), "D", "a loss")
	assert_lt(SORTIE_LOG.score(false, 1.0, 0.6, 1.0, 600.0), 60, "a loss never reaches B")


func test_the_log_counts_what_the_player_did() -> void:
	var m: Mission = rig.mission([["ameise", "ameise"]], 200.0)
	await physics_frames(10)
	var combat := rig.level.mech.get_node("Combat") as MechCombat
	combat.shots_fired += 5  # five rounds fired; the kills below land as hits
	var a: LegionMech = m.units[0]
	var b: LegionMech = m.units[1]
	a.take_hit({"key": "leg_" + str(a.legs[0]["tag"]) if not a.legs.is_empty() else "arms", "damage": 99999.0, "penetration_mm": 900.0, "point": a.global_position, "shooter": rig.level.mech, "splash": false})
	rig.kill_as_player(a)
	await physics_frames(2)
	assert_eq(m.sortie.kills_by_you, 1, "the player's kill counts")
	assert_gt(m.sortie.parts_off.size(), 0, "the leg (or arms) shot off counts")
	var d := a.global_position.distance_to(rig.level.mech.global_position)
	assert_almost_eq(m.sortie.longest_kill_m, d, 30.0, "longest kill is the distance at the kill")
	# the other one dies to someone else's blast: no kill, no hit for the player
	for i in 12:
		if b.dead:
			break
		b.take_hit({"key": "hull", "damage": 5000.0, "penetration_mm": 900.0, "point": b.global_position, "splash": true})
	await physics_frames(5)
	assert_eq(m.state, "won")
	assert_eq(m.sortie.kills_by_you, 1, "a kill by someone else is not yours")
	var r: Dictionary = m.report
	assert_eq(int(r["shots"]), 5)
	assert_eq(int(r["hits"]), m.sortie.hits)
	assert_between(float(r["accuracy"]), 0.01, 1.0, "accuracy from hits over shots")
	assert_has(["S", "A", "B", "C", "D"], r["grade"])
	assert_eq(r["bests"], [], "a made-up mission id leaves the records alone")
	assert_eq(m.summary()["report"], r, "the summary carries the report to the end card")


func test_the_kill_that_ends_the_mission_counts() -> void:
	var m: Mission = rig.mission([["ameise"]], 300.0)
	await physics_frames(5)
	rig.kill_as_player(m.units[0])
	assert_eq(m.state, "won")
	assert_eq(int(m.report["kills_by_you"]), 1, "the last kill lands in the report built at that very kill")
	assert_gt(float(m.report["longest_kill_m"]), 0.0)


func test_damage_taken_is_summed() -> void:
	var m: Mission = rig.mission([["ameise"]], 600.0)
	await physics_frames(5)
	var combat := rig.level.mech.get_node("Combat") as MechCombat
	combat.take_hit({"key": "hull", "damage": 300.0, "penetration_mm": 900.0, "point": rig.level.mech.global_position, "splash": true})
	combat.take_hit({"key": "hull", "damage": 200.0, "penetration_mm": 900.0, "point": rig.level.mech.global_position, "splash": true})
	assert_gt(m.sortie.damage_taken, 100.0, "hits on the Juggernaut add up")
	assert_lt(m.sortie.armour_left(), 1.0, "and its armour drops")


func test_personal_bests_are_kept_per_mission() -> void:
	var log := SORTIE_LOG.new()
	log.records_file = "user://test_records.cfg"
	var first := log.finish("ashen_first_contact", true, 400.0)
	assert_true("score" in first["bests"] and "time_s" in first["bests"], "a first win sets the records")
	assert_false("accuracy" in first["bests"] or "longest_kill_m" in first["bests"], "a win with no hits holds no accuracy or longest-kill best")
	var slower := log.finish("ashen_first_contact", true, 500.0)
	assert_false("time_s" in slower["bests"], "a slower win is no time best")
	var faster := log.finish("ashen_first_contact", true, 300.0)
	assert_true("time_s" in faster["bests"], "a faster win is")
	assert_eq(float(log.best("ashen_first_contact", "time_s")), 300.0)
	assert_eq(int(log.best("ashen_first_contact", "wins")), 3)
	var lost := log.finish("ashen_first_contact", false, 100.0)
	assert_eq(lost["bests"], [], "a loss sets no records")


func test_end_card_shows_the_grade_and_bests() -> void:
	var end := MissionEnd.new()
	end.won = true
	var report := {"shots": 37, "hits": 14, "accuracy": 0.378, "parts_off": 4, "kills_by_you": 6, "longest_kill_m": 812.0, "damage_taken": 2450.0, "armour_left": 0.71, "score": 81, "grade": "A", "bests": ["time_s", "longest_kill_m"]}
	end.summary = {"mission": "ashen_first_contact", "kills": 9, "time_s": 312.0, "wave": 3, "waves": 3, "report": report}
	tree.root.add_child(end)
	end.show_now()
	var grade := end.find_child("Grade", true, false) as Label
	assert_not_null(grade, "a grade letter")
	assert_eq(grade.text, "A")
	var text := ""
	for l: Node in end.find_children("*", "Label", true, false):
		text += (l as Label).text + "\n"
	assert_true(text.contains("Accuracy 38 %  (14 of 37)"), text)
	assert_true(text.contains("Longest kill 812 m"))
	assert_true(text.contains("New best: time, longest kill"))
	tree.paused = false
	end.free()
