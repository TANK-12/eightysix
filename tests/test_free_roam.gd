extends "res://tests/lib/test_case.gd"
## Emerson's note 19 (2026-10-02): free roam (any map with no Legion) and playing on after beating every wave.


func after_each() -> void:
	Game.free_roam = false
	Game.pending_map = ""
	tree.paused = false


func _has_mission(free: bool) -> bool:
	Game.pending_map = "small_map"
	Game.free_roam = free
	var level: Node3D = (load("res://scenes/levels/small_map.tscn") as PackedScene).instantiate()
	tree.root.add_child(level)
	# The map builds over several frames; it registers itself (Game.level) once the player is in.
	for i in 600:
		if Game.level == level:
			break
		await physics_frames(1)
	assert_true(Game.level == level, "the map finished building")
	var has := level.get("mission") != null
	level.free()
	Game.level = null
	return has


func test_free_roam_starts_no_mission() -> void:
	assert_false(await _has_mission(true), "free roam: no mission, so no Legion")
	assert_true(await _has_mission(false), "a normal deploy still runs the map's mission")


func _card(won: bool) -> MissionEnd:
	var end := MissionEnd.new()
	end.won = won
	end.summary = {"mission": "ashen_first_contact", "time_s": 90.0, "kills": 6, "wave": 3, "waves": 3}
	tree.root.add_child(end)
	end.show_now()
	return end


static func _buttons(end: MissionEnd) -> Array:
	return end.find_children("*", "Button", true, false).map(func(b: Node) -> String: return (b as Button).text)


func test_a_win_offers_keep_exploring_and_it_plays_on() -> void:
	var end := _card(true)
	assert_eq(_buttons(end)[0], "Keep exploring", "first choice after a win")
	assert_true(tree.paused, "the card pauses the game")
	end.keep_exploring()
	assert_false(tree.paused, "keep exploring unpauses")
	await tree.process_frame
	assert_false(is_instance_valid(end), "and the card goes")


func test_a_loss_has_no_keep_exploring() -> void:
	var end := _card(false)
	assert_false(_buttons(end).has("Keep exploring"), "nothing to explore with a lost Juggernaut")
	end.free()
