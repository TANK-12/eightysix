extends "res://tests/lib/test_case.gd"
## Lane B5's big map: the streamed ground (BigTerrain, BigStream) and its towns (BigTowns). The
## height function is checked where tiles meet, against the overview, and at its features; the
## stream is checked for building fine ground around mechs, dropping it behind them, and for never
## letting a body fall through where tiles meet.

static var _terrain: BigTerrain


func _t() -> BigTerrain:
	if _terrain == null:
		_terrain = BigTerrain.new(Registry.entry("maps", "big_map"))
	return _terrain


func test_neighbouring_tiles_share_their_edges_exactly() -> void:
	var t := _t()
	for pair: Array in [[Vector2i(15, 15), Vector2i(16, 15)], [Vector2i(16, 15), Vector2i(16, 16)], [Vector2i(3, 20), Vector2i(4, 20)]]:
		var a := t.tile(pair[0].x, pair[0].y, 1)
		var b := t.tile(pair[1].x, pair[1].y, 1)
		var n := int(a["n"])
		var ha: PackedFloat32Array = a["heights"]
		var hb: PackedFloat32Array = b["heights"]
		var worst := 0.0
		var nworst := 0.0
		var na: PackedVector3Array = a["normals"]
		var nb: PackedVector3Array = b["normals"]
		for k in n:
			var ia := k * n + (n - 1) if pair[1].x > pair[0].x else (n - 1) * n + k
			var ib := k * n if pair[1].x > pair[0].x else k
			worst = maxf(worst, absf(ha[ia] - hb[ib]))
			nworst = maxf(nworst, na[ia].angle_to(nb[ib]))
		assert_lt(worst, 0.0001, "edge heights match %s" % str(pair))
		assert_lt(nworst, 0.001, "edge normals match %s" % str(pair))


func test_tiles_and_overview_come_from_one_function() -> void:
	var t := _t()
	var d := t.tile(9, 22, 1)
	var o := t.tile_origin(9, 22)
	var h: PackedFloat32Array = d["heights"]
	for p: Vector2i in [Vector2i(0, 0), Vector2i(37, 90), Vector2i(128, 128), Vector2i(64, 3)]:
		assert_almost_eq(h[p.y * 129 + p.x], t.sample(o.x + p.x, o.y + p.y), 0.0001, "tile point %s" % str(p))
	var ov := t.overview_tile(9, 22)
	var oh: PackedFloat32Array = ov["heights"]
	assert_almost_eq(oh[5 * 17 + 7], t.sample(o.x + 56.0, o.y + 40.0), 0.0001, "overview point")
	var c := t.coarsen(d)
	assert_eq(int(c["n"]), 65)
	assert_almost_eq((c["heights"] as PackedFloat32Array)[3 * 65 + 5], h[6 * 129 + 10], 0.0001, "2 m from 1 m")


func test_towns_are_level_and_roads_follow_a_smooth_bed() -> void:
	var t := _t()
	for town: Dictionary in Registry.entry("maps", "big_map")["towns"]:
		var c := Vector2(float(town["center"][0]), float(town["center"][1]))
		var reach := minf(float(town["size_m"][0]), float(town["size_m"][1])) * 0.4
		var lo := INF
		var hi := -INF
		for k in 40:
			var p := c + Vector2(cos(k * 2.4), sin(k * 2.4)) * (reach * k / 40.0)
			var h := t.height_at(p.x, p.y)
			lo = minf(lo, h)
			hi = maxf(hi, h)
		assert_lt(hi - lo, 1.2, "%s: the town square is level (%.2f m)" % [town["id"], hi - lo])
	# across a road, 4 m either side of its middle, away from towns and water
	var road: Array = Registry.entry("maps", "big_map")["roads"][1]["points"]
	var a := Vector2(float(road[1][0]), float(road[1][1]))
	var b := Vector2(float(road[2][0]), float(road[2][1]))
	var mid := a.lerp(b, 0.5)
	var across := (b - a).normalized().orthogonal()
	assert_lt(t.road_edge_at(mid.x, mid.y), 0.0, "on the road")
	assert_lt(absf(t.height_at(mid.x + across.x * 4.0, mid.y + across.y * 4.0) - t.height_at(mid.x - across.x * 4.0, mid.y - across.y * 4.0)), 0.6, "the road is not tilted sideways")
	assert_gt(t.splat_at(mid.x, mid.y).r, 0.8, "painted as road")


func test_river_and_lake_hold_water_and_roads_ford_it() -> void:
	var t := _t()
	var e: Dictionary = Registry.entry("maps", "big_map")
	var lake: Dictionary = e["lakes"][0]
	assert_lt(t.height_at(float(lake["center"][0]), float(lake["center"][1])), t.water_level - 3.0, "the lake is deep in the middle")
	var river: Array = e["rivers"][0]["points"]
	var p := Vector2(float(river[3][0]), float(river[3][1]))
	assert_lt(t.height_at(p.x, p.y), t.water_level - 1.5, "the river runs below the water line")
	assert_gt(t.splat_at(p.x + 14.0, p.y).g, 0.3, "muddy bank")
	# find where the west road crosses the river: the water there is ford-shallow
	var fords := 0
	for road: Dictionary in e["roads"]:
		var pts: Array = road["points"]
		for i in pts.size() - 1:
			var a := Vector2(float(pts[i][0]), float(pts[i][1]))
			var b := Vector2(float(pts[i + 1][0]), float(pts[i + 1][1]))
			for k in 400:
				var q := a.lerp(b, k / 400.0)
				if t.water_edge_at(q.x, q.y) < -6.0:
					var depth := t.water_level - t.height_at(q.x, q.y)
					if road.get("bridged", false):
						assert_gt(depth, 1.5, "%s is bridged at %s: the river stays deep (%.2f m)" % [road["id"], str(q), depth])
					else:
						assert_between(depth, 0.0, 0.8, "%s fords at %s, %.2f m deep" % [road["id"], str(q), depth])
						fords += 1
					break
	assert_gt(fords, 0, "roads cross the river at fords (the main road has a bridge)")


func test_towns_lay_out_buildings_clear_of_roads_and_water() -> void:
	var t := _t()
	var total := 0
	for town: Dictionary in Registry.entry("maps", "big_map")["towns"]:
		var specs := BigTowns.layout(t, town)
		var buildings := 0
		for s: Dictionary in specs:
			assert_true(Registry.has_entry("kit", str(s["kit"])), "kit %s exists" % s["kit"])
			var x := float(s["at"][0])
			var z := float(s["at"][1])
			assert_gt(t.road_edge_at(x, z), 1.0, "%s off the road" % s["kit"])
			assert_gt(t.water_edge_at(x, z), 4.0, "%s out of the water" % s["kit"])
			if s.has("damage"):
				buildings += 1
		assert_gt(buildings, 3, "%s has buildings (%d)" % [town["id"], buildings])
		total += specs.size()
		assert_eq(BigTowns.layout(t, town).size(), specs.size(), "%s lays out the same every time" % town["id"])
	assert_between(total, 40, 400, "a sensible number of pieces (%d)" % total)


func _stream() -> BigStream:
	var s := BigStream.new()
	tree.root.add_child(s)
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://assets/kit/shaders/ground.gdshader")
	s.setup(_t(), mat)
	return s


## Runs the stream until it has nothing left to make (or `frames` run out).
func _settle(s: BigStream, frames: int) -> void:
	for i in frames:
		s.update()
		await tree.process_frame
		if i > 2 and not s.busy():
			return
		OS.delay_msec(10)


func test_stream_builds_fine_ground_around_mechs_and_drops_it_behind() -> void:
	var s := _stream()
	assert_not_null(s, "BigStream compiles and builds")
	if s == null:
		return
	var focus := Node3D.new()
	tree.root.add_child(focus)
	s.focus = focus
	var mech := Node3D.new()
	mech.add_to_group("mechs")
	tree.root.add_child(mech)
	mech.global_position = Vector3(-560, 40, 1480)
	focus.global_position = mech.global_position
	await _settle(s, 900)
	var key := _t().tile_of(-560, 1480)
	assert_true(s.has_fine(key), "fine ground under the mech")
	assert_eq(s.near_count(), 25, "the camera's two rings (5 x 5)")
	mech.global_position = Vector3(1200, 40, -1000)
	focus.global_position = mech.global_position
	await _settle(s, 900)
	assert_false(s.has_fine(key), "dropped behind")
	assert_true(s.has_fine(_t().tile_of(1200, -1000)), "built ahead")
	assert_eq(s.near_count(), 25, "no more than the rings")
	mech.free()
	focus.free()
	s.free()


func test_bodies_dropped_where_tiles_meet_never_fall_through() -> void:
	var s := _stream()
	assert_not_null(s, "BigStream compiles and builds")
	if s == null:
		return
	var o := _t().tile_origin(12, 12)
	var points: Array[Vector2] = [o, o + Vector2(0.5, 64), o + Vector2(64, 0.3), o + Vector2(128, 128), o + Vector2(127.8, 40)]
	var anchor := Node3D.new()
	anchor.add_to_group("mechs")
	tree.root.add_child(anchor)
	anchor.global_position = Vector3(o.x, 0, o.y)
	s.focus = anchor
	s.prime(anchor.global_position)
	await _settle(s, 40)
	var balls: Array[RigidBody3D] = []
	for p in points:
		var b := RigidBody3D.new()
		var cs := CollisionShape3D.new()
		var sphere := SphereShape3D.new()
		sphere.radius = 0.3
		cs.shape = sphere
		b.add_child(cs)
		b.collision_mask = Kit.LAYER_WORLD
		tree.root.add_child(b)
		b.global_position = Vector3(p.x, _t().height_at(p.x, p.y) + 6.0, p.y)
		b.linear_velocity = Vector3(0, -25, 0)
		balls.append(b)
	await physics_frames(240)
	for i in balls.size():
		# a ball may roll downhill: compare with the ground under where it ended up
		var at := balls[i].global_position
		var ground := _t().height_at(at.x, at.z)
		assert_gt(at.y, ground - 0.1, "ball dropped at %s is on the ground at %s (%.2f vs %.2f)" % [str(points[i]), str(at), at.y, ground])
		balls[i].free()
	anchor.free()
	s.free()
