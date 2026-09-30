extends "res://tests/lib/test_case.gd"
## The small map (lane B3): the ground is built as maps.json says (water below the line in the river
## and lake, roads level across, the town flat, the rim high, the spawn dry), the collider is the
## drawn surface, and the whole level loads with the Juggernaut standing on it.

static var _terrain: SmallMapTerrain


func _t() -> SmallMapTerrain:
	if _terrain == null:
		_terrain = SmallMapTerrain.new(Registry.entry("maps", "small_map"))
	return _terrain


func test_registry_entry_is_consistent() -> void:
	var e := Registry.entry("maps", "small_map")
	assert_true(Game.can_start("small_map"), "startable")
	assert_true(Registry.has_entry("weather", str(e["weather"])), "weather exists")
	var half := float(e["size_m"]) * 0.5
	for key in ["buildings", "structures"]:
		for b: Dictionary in e[key]:
			assert_true(Registry.has_entry("kit", str(b["kit"])), "kit " + str(b["kit"]))
			assert_between(float(b["at"][0]), -half, half)
			assert_between(float(b["at"][1]), -half, half)
	for v: String in e["viewpoints"]:
		assert_eq((e["viewpoints"][v]["eye"] as Array).size(), 3, v)


func test_river_and_lake_are_under_water() -> void:
	var t := _t()
	var e := Registry.entry("maps", "small_map")
	var pts: Array = e["river"]["points"]
	for k in range(1, pts.size() - 1):
		var x := float(pts[k][0])
		var z := float(pts[k][1])
		assert_lt(t.height_at(x, z), t.water_level - 1.0, "river bed at %s" % [pts[k]])
	var c: Array = e["lake"]["center"]
	assert_lt(t.height_at(float(c[0]), float(c[1])), t.water_level - 3.0, "lake middle is deep")


func test_land_stays_above_water_away_from_it() -> void:
	var t := _t()
	var rng := RandomNumberGenerator.new()
	rng.seed = 5
	var wet := 0
	for i in 400:
		var x := rng.randf_range(-500, 500)
		var z := rng.randf_range(-500, 500)
		if t.water_edge_at(x, z) > 45.0 and t.height_at(x, z) < t.water_level + 0.3:
			wet += 1
	assert_eq(wet, 0, "no puddles of sea level far from the river and lake")


func test_roads_are_level_across() -> void:
	var t := _t()
	for road: Dictionary in Registry.entry("maps", "small_map")["roads"]:
		var pts: Array = road["points"]
		for k in pts.size() - 1:
			var a := Vector2(float(pts[k][0]), float(pts[k][1]))
			var b := Vector2(float(pts[k + 1][0]), float(pts[k + 1][1]))
			var m := (a + b) * 0.5
			if t.water_edge_at(m.x, m.y) < 12.0 or absf(m.x) > 440 or absf(m.y) > 440:
				continue
			var across := (b - a).orthogonal().normalized() * float(road["width_m"]) * 0.4
			var dh := absf(t.height_at(m.x + across.x, m.y + across.y) - t.height_at(m.x - across.x, m.y - across.y))
			assert_lt(dh, 0.6, "road %s level across at %s" % [road["id"], m])


func test_town_is_flat_and_rim_is_high() -> void:
	var t := _t()
	var lo := 1.0e9
	var hi := -1.0e9
	for i in 9:
		for k in 9:
			var h := t.height_at(10 - 100 + i * 25, -170 - 80 + k * 20)
			lo = minf(lo, h)
			hi = maxf(hi, h)
	assert_lt(hi - lo, 2.0, "town plateau within 2 m")
	assert_gt(t.height_at(0, 505) - t.height_at(0, 300), 25.0, "rim rises at the edge")


func test_spawn_is_dry_and_walkable() -> void:
	var t := _t()
	var p: Array = Registry.entry("maps", "small_map")["spawn"]["position"]
	var x := float(p[0])
	var z := float(p[2])
	assert_gt(t.height_at(x, z), t.water_level + 1.0, "spawn is dry")
	assert_gt(t.normal_at(x, z).y, 0.9, "spawn is under about 25 degrees")


func test_collider_matches_drawn_ground() -> void:
	var t := _t()
	var body := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	cs.shape = t.build_shape()
	body.add_child(cs)
	tree.root.add_child(body)
	await physics_frames(2)
	var space := body.get_world_3d().direct_space_state
	var rng := RandomNumberGenerator.new()
	rng.seed = 9
	var worst := 0.0
	for i in 60:
		var x := rng.randf_range(-500, 500)
		var z := rng.randf_range(-500, 500)
		var q := PhysicsRayQueryParameters3D.create(Vector3(x, 400, z), Vector3(x, -100, z))
		var hit := space.intersect_ray(q)
		assert_false(hit.is_empty(), "ray hits the ground at %d,%d" % [x, z])
		if not hit.is_empty():
			worst = maxf(worst, absf((hit["position"] as Vector3).y - t.height_at(x, z)))
	assert_lt(worst, 0.05, "collider within 5 cm of the drawn height")
	body.free()


func test_grapple_points_have_a_surface_to_hold() -> void:
	var level: Node3D = (load("res://scenes/levels/small_map.tscn") as PackedScene).instantiate()
	tree.root.add_child(level)
	await physics_frames(2)
	var space := level.get_world_3d().direct_space_state
	var missing: Array = []
	for p: Vector3 in level.get("grapple_points"):
		var found := false
		for dir: Vector3 in [Vector3.DOWN, Vector3.LEFT, Vector3.RIGHT, Vector3.FORWARD, Vector3.BACK]:
			var q := PhysicsRayQueryParameters3D.create(p - dir * 2.0, p + dir * 2.5, Kit.LAYER_GRAPPLE)
			if not space.intersect_ray(q).is_empty():
				found = true
				break
		if not found:
			missing.append(p)
	assert_eq(missing, [], "every grapple point is within 2.5 m of a grapple surface")
	level.free()
	Game.level = null


func test_level_loads_and_the_mech_stands() -> void:
	var level: Node3D = (load("res://scenes/levels/small_map.tscn") as PackedScene).instantiate()
	tree.root.add_child(level)
	var mech: RigidBody3D = level.get("mech")
	assert_not_null(mech)
	assert_gt((level.get("grapple_points") as Array).size(), 20, "grapple points listed")
	await physics_frames(480)
	var p := mech.global_position
	var floor_y := float(level.call("ground_height", p.x, p.z))
	assert_gt(p.y, floor_y + 0.8, "the Juggernaut stands on the valley floor")
	assert_false(is_nan(p.y))
	print("small_map build ms: ", level.get("build_ms"))
	level.free()
	Game.level = null
