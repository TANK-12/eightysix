extends "res://tests/lib/test_case.gd"
## The bot's script reader and frame statistics.


func test_script_steps_sorted() -> void:
	var s: Dictionary = Bot.parse_script('{"name": "x", "steps": [{"at": 2, "shot": "b"}, {"at": 1, "shot": "a"}]}')
	assert_eq(s["steps"][0]["shot"], "a")
	assert_eq(Bot.parse_script("not json"), null)
	assert_eq(Bot.parse_script('{"name": "no steps"}'), null)


func test_frame_stats() -> void:
	var frames: Array = []
	for i in 99:
		frames.append(1.0 / 60.0)
	frames.append(1.0 / 20.0)
	var st := Bot.frame_stats(frames, "t")
	assert_eq(st["frames"], 100)
	assert_almost_eq(st["avg_fps"], 100.0 / (99.0 / 60.0 + 1.0 / 20.0), 0.1)
	assert_almost_eq(st["min_fps"], 20.0, 0.1)
	assert_almost_eq(st["p1_low_fps"], 20.0, 0.1)


func test_every_bot_script_parses() -> void:
	for f in DirAccess.get_files_at("res://tools/bot"):
		if f.ends_with(".json"):
			assert_not_null(Bot.parse_script(FileAccess.get_file_as_string("res://tools/bot/" + f)), f)
