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


## Part 2 (2026-10-03): the forest (Allegheny, USGS) and the city (Brilon, DGM1 NRW + OpenStreetMap).
## Away from roads and the rim, the ground is floor + the survey + at most the fine roughness.
func _follows_survey(id: String) -> void:
	var entry: Dictionary = Registry.entry("maps", id)
	var hm: Dictionary = entry["terrain"]["heightmap"]
	var f := FileAccess.open(str(hm["file"]), FileAccess.READ)
	assert_not_null(f, "%s: the heightmap file ships with the game" % id)
	var n := int(hm["points"])
	var raw := f.get_buffer(n * n * 4).to_float32_array()
	assert_eq(raw.size(), n * n, "%s: n x n heights" % id)
	var terrain := BigTerrain.new(entry)
	var size := float(entry["size_m"])
	var step := size / (n - 1)
	var rough := float(entry["terrain"]["rough_m"])
	var floor_m := float(entry["terrain"]["floor_m"])
	var inner := size * 0.5 - float(entry["terrain"]["rim_width_m"]) * 1.6
	var worst := 0.0
	var checked := 0
	for zi in range(0, n, n / 16):
		for xi in range(0, n, n / 16):
			var x := xi * step - size * 0.5
			var z := zi * step - size * 0.5
			if absf(x) > inner or absf(z) > inner or terrain.road_edge_at(x, z) < BigTerrain.ROAD_SHOULDER_M + 2.0:
				continue
			worst = maxf(worst, absf(terrain.sample(x, z) - (floor_m + raw[zi * n + xi])))
			checked += 1
	assert_gt(checked, 60.0, "%s: enough survey points away from roads (%d)" % [id, checked])
	assert_lt(worst, rough + 0.05, "%s: heights follow the survey within the roughness (%.2f m)" % [id, worst])


func test_forest_and_city_stand_on_their_surveys() -> void:
	_follows_survey("allegheny")
	_follows_survey("brilon")


func test_forest_leaves_lanes_for_a_mech() -> void:
	var entry: Dictionary = Registry.entry("maps", "allegheny")
	var cfg: Dictionary = entry["forest"]
	var terrain := BigTerrain.new(entry)
	var trees := BigForest.plan(terrain, cfg)
	var count := 0
	for key: Vector2i in trees:
		count += (trees[key] as PackedFloat32Array).size() / 5
	assert_gt(count, 50000.0, "a real forest: tens of thousands of trees (%d)" % count)
	# trunk to trunk at least cell * (1 - 2 jitter): wider than the Juggernaut's 4.9 m stance plus two trunks
	var lane := float(cfg["cell_m"]) * (1.0 - 2.0 * float(cfg["jitter"]))
	assert_gt(lane - 2.0 * BigForest.TRUNK_HIT_R, 4.9, "the narrowest gap clears the Juggernaut's feet")
	var nearest := INF
	var on_road := 0
	for key: Vector2i in [Vector2i(10, 10), Vector2i(16, 16), Vector2i(20, 12)]:
		var a: PackedFloat32Array = trees.get(key, PackedFloat32Array())
		for i in range(0, a.size(), 5):
			for j in range(i + 5, a.size(), 5):
				nearest = minf(nearest, Vector2(a[i], a[i + 2]).distance_to(Vector2(a[j], a[j + 2])))
			if terrain.road_edge_at(a[i], a[i + 2]) < float(cfg["road_clear_m"]) - 0.01:
				on_road += 1
	assert_gt(nearest, lane - 0.01, "no two trunks closer than %.1f m (nearest %.2f m)" % [lane, nearest])
	assert_eq(on_road, 0, "no tree on a road")
	var spawn: Array = entry["spawn"]["position"]
	var forest := BigForest.new()
	forest.terrain = terrain
	forest.trees = trees
	assert_false(forest.trunk_near(float(spawn[0]), float(spawn[2]), float(cfg["spawn_clear_m"]) - 1.0), "the spawn is clear of trees")
	forest.free()


func test_city_raises_the_osm_buildings() -> void:
	var entry: Dictionary = Registry.entry("maps", "brilon")
	var terrain := BigTerrain.new(entry)
	var osm := BigTerrain.osm(str(entry["osm"]["file"]))
	assert_gt((osm["roads"] as Array).size(), 300.0, "the town's streets")
	assert_almost_eq(float(osm["road_scale"]), 1.3, 0.001, "streets 1.3x their real width (Emerson: slightly wider)")
	var city := BigCity.new()
	city.setup(terrain)
	var n := city.buildings.size()
	assert_gt(n, (osm["buildings"] as Array).size() * 0.97, "nearly every mapped building stands (%d)" % n)
	var ruined := 0
	var floating := 0
	for b: Dictionary in city.buildings:
		if float(b["ruin"]) > 0.0:
			ruined += 1
		for p: Vector2 in b["poly"]:
			if float(b["foot"]) > terrain.sample(p.x, p.y):
				floating += 1
	assert_eq(floating, 0, "every wall starts at or under the ground at its corners")
	assert_between(float(ruined) / n, 0.2, 0.7, "part of the town is in ruins (%d of %d)" % [ruined, n])
	var spawn: Array = entry["spawn"]["position"]
	assert_false(city.blocked(float(spawn[0]), float(spawn[2]), 3.0), "the spawn is on an open street")
	assert_gt(city.chunks.size(), 4.0, "the town is split into chunks (%d)" % city.chunks.size())
	# walls wear the facade shader (crew note 750): UV runs along the wall, CUSTOM0 says how long it is
	var facades := 0
	var bad_uv := 0
	for key: Vector2i in city.chunks:
		var mesh: ArrayMesh = (city.chunks[key]["mesh"] as MeshInstance3D).mesh
		for s in mesh.get_surface_count():
			var mat := mesh.surface_get_material(s) as ShaderMaterial
			if mat == null or not mat.shader.resource_path.ends_with("facade.gdshader"):
				continue
			facades += 1
			assert_ne(mesh.surface_get_format(s) & Mesh.ARRAY_FORMAT_TANGENT, 0, "a facade surface has tangents for its normal map")
			var arr := mesh.surface_get_arrays(s)
			var uv: PackedVector2Array = arr[Mesh.ARRAY_TEX_UV]
			var info: PackedFloat32Array = arr[Mesh.ARRAY_CUSTOM0]
			assert_eq(info.size(), uv.size() * 4, "one CUSTOM0 (length, storey, ruin, storeys+seed) per vertex")
			for v in mini(uv.size(), info.size() / 4):
				if uv[v].x < -0.01 or uv[v].x > info[v * 4] + 0.01 or uv[v].y < -0.01:
					bad_uv += 1
	assert_gt(facades, city.chunks.size() * 0.9, "every chunk has facade walls (%d surfaces)" % facades)
	assert_eq(bad_uv, 0, "wall UVs run from 0 to the wall's length, upward from its foot")
	# mid-size props along the streets and in the ruins, never through a wall
	var kinds := {}
	var in_house := 0
	for prop: Node3D in city.props:
		kinds[str(prop.get_meta("kit", ""))] = true
		if str(prop.get_meta("kit", "")) == "power_pole" and city.blocked(prop.position.x, prop.position.z):
			in_house += 1
	assert_gt(city.props.size(), 400.0, "the town has props (%d)" % city.props.size())
	assert_eq(kinds.keys().size(), 3, "poles, wrecks and rubble piles (%s)" % [kinds.keys()])
	assert_eq(in_house, 0, "no pole stands inside a house")
	city.free()


func after_each() -> void:
	Game.pending_map = ""
	Game.free_roam = false


## The map plays: the Juggernaut lands on the ground, with colliders under it, and the map's buildings
## and trunks are solid.
func _plays(id: String) -> Node3D:
	Game.pending_map = id
	Game.free_roam = true
	var level: Node3D = (load("res://scenes/levels/big_map.tscn") as PackedScene).instantiate()
	tree.root.add_child(level)
	for i in 600:
		if Game.level == level:
			break
		await physics_frames(1)
	assert_true(Game.level == level, "%s: the map finished building" % id)
	assert_eq(str(level.get("map_id")), id, "%s: the scene plays the picked map" % id)
	await physics_frames(360)
	var mech: Node3D = level.get("mech")
	var terrain: BigTerrain = level.get("terrain")
	var p := mech.global_position
	var space := mech.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(p + Vector3(0, 2, 0), p - Vector3(0, 30, 0), Kit.LAYER_WORLD, [(mech as CollisionObject3D).get_rid()])
	var hit := space.intersect_ray(q)
	assert_false(hit.is_empty(), "%s: a collider under the Juggernaut" % id)
	if not hit.is_empty():
		assert_lt(absf((hit["position"] as Vector3).y - terrain.height_at(p.x, p.z)), 1.0, "%s: it stands on the ground (%.2f vs %.2f)" % [id, (hit["position"] as Vector3).y, terrain.height_at(p.x, p.z)])
	assert_lt(p.y - terrain.height_at(p.x, p.z), 8.0, "%s: the Juggernaut is down on the ground, not stuck above it" % id)
	return level


func test_forest_map_plays_with_solid_trunks() -> void:
	var level := await _plays("allegheny")
	var forest: Node3D = level.get("forest")
	assert_not_null(forest, "the forest is built")
	assert_gt(float(forest.get("count")), 50000.0, "the whole forest stands")
	assert_gt(float(forest.call("body_tiles")), 3.0, "trunk colliders round the Juggernaut")
	# a level ray at chest height through the nearest trunk hits it
	var mech: Node3D = level.get("mech")
	var trees: Dictionary = forest.get("trees")
	var terrain: BigTerrain = level.get("terrain")
	var a: PackedFloat32Array = trees.get(terrain.tile_of(mech.global_position.x, mech.global_position.z), PackedFloat32Array())
	if a.is_empty():
		for k: Vector2i in forest.get("_bodies"):
			a = trees[k]
			break
	assert_gt(float(a.size()), 0.0, "trees near the Juggernaut")
	var t := Vector3(a[0], a[1] + 3.0, a[2])
	var q := PhysicsRayQueryParameters3D.create(t + Vector3(6, 0, 0), t, Kit.LAYER_WORLD)
	assert_false(mech.get_world_3d().direct_space_state.intersect_ray(q).is_empty(), "a trunk blocks a mech")
	level.free()
	Game.level = null


func test_city_map_plays_with_solid_buildings() -> void:
	var level := await _plays("brilon")
	var city: Node3D = level.get("city")
	assert_not_null(city, "the town is built")
	var space := level.get_world_3d().direct_space_state
	var solid := 0
	var tried := 0
	for b: Dictionary in city.get("buildings"):
		if float(b["ruin"]) > 0.0 or tried >= 20:
			continue
		var c: Vector2 = b["c"]
		var poly: PackedVector2Array = b["poly"]
		if not Geometry2D.is_point_in_polygon(c, poly):
			continue
		tried += 1
		var q := PhysicsRayQueryParameters3D.create(Vector3(c.x, float(b["top"]) + 40.0, c.y), Vector3(c.x, float(b["foot"]), c.y), Kit.LAYER_WORLD)
		var hit := space.intersect_ray(q)
		if not hit.is_empty() and (hit["position"] as Vector3).y > float(b["top"]) - 0.5:
			solid += 1
	assert_eq(solid, tried, "intact houses have solid roofs (%d of %d)" % [solid, tried])
	level.free()
	Game.level = null
