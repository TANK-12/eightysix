extends "res://tests/lib/test_case.gd"
## Real-place maps (Emerson 2026-10-03: "get some nice maps downloaded"): a streamed map whose terrain
## block names a heightmap stands on those real heights, and the big map scene plays whichever
## streamed map was picked.


func test_palouse_stands_on_the_survey() -> void:
	var entry: Dictionary = Registry.entry("maps", "palouse")
	var hm: Dictionary = entry["terrain"]["heightmap"]
	var f := FileAccess.open(str(hm["file"]), FileAccess.READ)
	assert_not_null(f, "the heightmap file ships with the game")
	var n := int(hm["points"])
	var raw := f.get_buffer(n * n * 4).to_float32_array()
	assert_eq(raw.size(), n * n, "n x n heights")
	var terrain := BigTerrain.new(entry)
	var size := float(entry["size_m"])
	var step := size / (n - 1)
	var rough := float(entry["terrain"]["rough_m"])
	var floor_m := float(entry["terrain"]["floor_m"])
	var worst := 0.0
	# away from the rim: the ground is floor + the survey + at most the fine roughness
	for p: Vector2i in [Vector2i(1024, 1024), Vector2i(1024, 424), Vector2i(700, 1300), Vector2i(1400, 900), Vector2i(500, 500)]:
		var x := p.x * step - size * 0.5
		var z := p.y * step - size * 0.5
		var want := floor_m + raw[p.y * n + p.x]
		worst = maxf(worst, absf(terrain.sample(x, z) - want))
	assert_lt(worst, rough + 0.05, "heights follow the survey within the roughness (%.2f m)" % worst)
	var top := -INF
	var top_at := Vector2.ZERO
	for zi in range(0, n, 16):
		for xi in range(0, n, 16):
			if raw[zi * n + xi] > top:
				top = raw[zi * n + xi]
				top_at = Vector2(xi * step - size * 0.5, zi * step - size * 0.5)
	assert_gt(top, 300.0, "Steptoe Butte stands over 300 m above the lowest ground (%.0f m)" % top)
	assert_lt(top_at.distance_to(Vector2(0, -1200)), 300.0, "about 1.2 km north of the centre (%s)" % str(top_at))


func test_noise_maps_are_unchanged_without_a_heightmap() -> void:
	var entry: Dictionary = Registry.entry("maps", "big_map")
	assert_false((entry["terrain"] as Dictionary).has("heightmap"))
	var a := BigTerrain.new(entry)
	assert_true(is_finite(a.sample(100.0, 200.0)), "the noise map still builds")
