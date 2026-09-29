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


func test_uncapped_estimate() -> void:
	# Each frame costs the slower of its GPU and CPU work: here 10, 10, 12 and 30 ms.
	var e := Bot.uncapped_estimate([10.0, 8.0, 12.0, 5.0], [4.0, 10.0, 6.0, 30.0])
	assert_almost_eq(e["gpu_ms_avg"], 8.75, 0.01)
	assert_almost_eq(e["cpu_ms_avg"], 12.5, 0.01)
	assert_eq(e["bound_by"], "cpu")
	assert_almost_eq(e["est_uncapped_fps"], 4.0 / 0.062, 0.1)
	assert_almost_eq(e["est_uncapped_p1_low_fps"], 1000.0 / 30.0, 0.1)
	assert_eq(Bot.uncapped_estimate([], []), {})


func test_paced_share() -> void:
	var at_60 := 1.0 / 60.0
	assert_eq(Bot.paced_share([at_60, at_60, at_60, 0.010], 60.0), 0.75)
	assert_eq(Bot.paced_share([0.012, 0.014], 60.0), 0.0)
	assert_eq(Bot.paced_share([], 60.0), 0.0)


func test_every_bot_script_parses() -> void:
	for f in DirAccess.get_files_at("res://tools/bot"):
		if f.ends_with(".json"):
			assert_not_null(Bot.parse_script(FileAccess.get_file_as_string("res://tools/bot/" + f)), f)
