extends "res://tests/lib/test_case.gd"
## Lane B5 part 3: the Legion's path-finding on the big map (scripts/ai/legion_nav.gd): a coarse grid over the
## whole map where steep ground and deep water are walls, fords are open, and a bridge is a corridor that is open
## while it stands. A hunting unit follows the path's waypoints instead of walking straight at its goal.

static var _terrain: BigTerrain
static var _nav: LegionNav


func _t() -> BigTerrain:
	if _terrain == null:
		_terrain = BigTerrain.new(Registry.entry("maps", "big_map"))
	return _terrain


func _n() -> LegionNav:
	if _nav == null:
		var e: Dictionary = Registry.entry("maps", "big_map")
		var terrain := _t()
		var t0 := Time.get_ticks_msec()
		_nav = LegionNav.build(terrain, float(e["legion_area_half_m"]))
		print("    nav: grid built in %d ms" % (Time.get_ticks_msec() - t0))
		var lay := BigBridges.layout(_t(), e, e["bridges"][0])
		_nav.add_corridor("ash_bridge", lay["from"], lay["to"])
	return _nav


func _length(p: PackedVector3Array) -> float:
	var total := 0.0
	for i in p.size() - 1:
		total += Vector2(p[i].x - p[i + 1].x, p[i].z - p[i + 1].z).length()
	return total


func test_a_path_over_open_hills_is_about_straight() -> void:
	var from := Vector3(-250.0, 0.0, 1480.0)
	var to := Vector3(-730.0, 0.0, 1390.0)
	var p := _n().path(from, to)
	assert_gt(p.size(), 3, "a path exists")
	var straight := Vector2(from.x - to.x, from.z - to.z).length()
	print("    nav: farm track to the spawn, %.0f m straight, %.0f m by path, %d waypoints" % [straight, _length(p), p.size()])
	assert_lt(_length(p), straight * 2.2, "not a huge detour")
	assert_lt(Vector2(p[p.size() - 1].x - to.x, p[p.size() - 1].z - to.z).length(), 40.0, "and it ends at the goal")


func test_a_path_never_goes_through_deep_water_or_up_a_cliff() -> void:
	var t := _t()
	var p := _n().path(Vector3(760.0, 0.0, 1080.0), Vector3(-730.0, 0.0, 1390.0))  # east shore to the spawn: across the river
	assert_gt(p.size(), 10, "a path exists across the river")
	var worst := 0.0
	for q: Vector3 in p:
		worst = maxf(worst, t.water_level - t.height_at(q.x, q.z))
	print("    nav: east shore to the spawn, %.0f m, deepest waypoint %.2f m under the water line" % [_length(p), worst])
	assert_lt(worst, 0.7, "every waypoint is dry or a ford")


func test_the_bridge_is_the_way_over_while_it_stands_and_not_when_it_is_down() -> void:
	var nav := _n()
	var from := Vector3(-300.0, 0.0, -400.0)
	var to := Vector3(300.0, 0.0, -250.0)
	nav.set_corridor_open("ash_bridge", true)
	var over := nav.path(from, to)
	assert_gt(over.size(), 5, "a path across the river exists")
	var near_bridge := false
	for q: Vector3 in over:
		if absf(q.x) < 30.0 and absf(q.z + 317.0) < 12.0:
			near_bridge = true
	assert_true(near_bridge, "it crosses at the bridge")
	nav.set_corridor_open("ash_bridge", false)
	var around := nav.path(from, to)
	nav.set_corridor_open("ash_bridge", true)
	print("    nav: across the Ash river %.0f m by the bridge, %s with the bridge down" % [_length(over), ("%.0f m" % _length(around)) if not around.is_empty() else "no path"])
	var still_on_it := false
	for q: Vector3 in around:
		if absf(q.x) < 30.0 and absf(q.z + 317.0) < 12.0:  # over the river where the deck is
			still_on_it = true
	assert_false(still_on_it, "with the bridge down no path crosses the deck")
	assert_true(around.is_empty() or _length(around) >= _length(over), "and the way round is no shorter")


func test_a_goal_on_a_cliff_goes_to_the_nearest_standable_ground() -> void:
	var t := _t()
	var steep := Vector3(1100.0, 0.0, -450.0)  # one of the steepest interior slopes (55-62 degrees)
	var p := _n().path(Vector3(900.0, 0.0, -300.0), steep)
	assert_gt(p.size(), 1, "it still gets as close as it can")
	var end := p[p.size() - 1]
	assert_lt(Vector2(end.x - steep.x, end.z - steep.z).length(), 120.0, "ends near it (%s)" % str(end.round()))
	assert_gt(t.height_at(end.x, end.z), t.water_level, "on dry ground")


class StubNav:
	extends LegionNav
	var asked := 0
	var way := PackedVector3Array()
	var closed: Array[Vector2] = []

	func block(x: float, z: float) -> bool:
		closed.append(Vector2(x, z))
		return true

	func path(_from: Vector3, _to: Vector3) -> PackedVector3Array:
		asked += 1
		return way


func test_a_far_goal_is_reached_by_the_paths_waypoints_and_a_near_one_directly() -> void:
	var ground := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(800, 2, 800)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	var u := LegionMech.build("grauwolf")
	u.position = Vector3(0, 0.3, 0)
	tree.root.add_child(u)
	var b := u.get_node("Brain") as LegionBrain
	var nav := StubNav.new()
	nav.way = PackedVector3Array([Vector3(60, 0, -50), Vector3(60, 0, -150), Vector3(60, 0, -250), Vector3(30, 0, -350), Vector3(0, 0, -400)])
	b.nav = nav
	var far := Vector3(0, 0, -400)
	assert_eq(b._nav_goal(far), nav.way[2], "steers two waypoints ahead of the next one, not straight at the goal")
	assert_eq(nav.asked, 1, "asked once")
	b._nav_goal(far)
	assert_eq(nav.asked, 1, "and keeps the path while the goal stays")
	u.global_position = Vector3(58, 0.3, -148)  # at the second waypoint
	assert_eq(b._nav_goal(far), nav.way[4], "passed waypoints are dropped: it looks two ahead from the next one")
	u.global_position = Vector3(0, 0.3, 0)
	assert_eq(b._nav_goal(Vector3(0, 0, -30)), Vector3(0, 0, -30), "a goal within 70 m is walked at directly")
	b.nav = null
	assert_eq(b._nav_goal(far), far, "no nav: straight at it")
	u.free()
	ground.free()


func test_a_unit_that_hardly_moved_along_its_path_closes_the_cell_ahead_and_asks_again() -> void:
	var ground := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(800, 2, 800)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	var u := LegionMech.build("lowe")
	u.position = Vector3(0, 0.3, 0)
	tree.root.add_child(u)
	var b := u.get_node("Brain") as LegionBrain
	var nav := StubNav.new()
	nav.way = PackedVector3Array([Vector3(0, 0, -50), Vector3(0, 0, -150), Vector3(0, 0, -250), Vector3(0, 0, -400)])
	b.nav = nav
	var far := Vector3(0, 0, -400)
	b._nav_goal(far)
	assert_eq(nav.closed.size(), 0, "nothing closed at first")
	b._bog_ms = Time.get_ticks_msec() - int(LegionBrain.NAV_BOGGED_S * 1000.0) - 500  # the last look was 10 s ago, here
	b._bog_pos = u.global_position + Vector3(3, 0, 0)
	b._nav_goal(far)
	assert_eq(nav.closed.size(), 2, "10 s and 3 m on: the cell ahead and the one under it are closed")
	assert_lt(absf(nav.closed[0].x), 1.0, "straight ahead of it")
	assert_lt(nav.closed[0].y, -5.0, "on its way to the next waypoint")
	assert_eq(nav.closed[1], Vector2(0, 0), "and its own")
	assert_eq(b.bogged, 1, "counted")
	assert_eq(nav.asked, 2, "and the path is asked for again")
	b._bog_ms = Time.get_ticks_msec() - int(LegionBrain.NAV_BOGGED_S * 1000.0) - 500
	b._bog_pos = u.global_position + Vector3(30, 0, 0)  # it did get somewhere
	b._nav_goal(far)
	assert_eq(nav.closed.size(), 2, "a unit that covered 30 m in that time is not bogged down")
	u.free()
	ground.free()


func test_a_narrow_crag_line_is_a_wall_on_the_grid() -> void:
	# The Frontier sweep's Löwe stalled at x -86 against a 35-41 degree band (x -101, z 1395-1435) about 8 m
	# wide that the grid's old 32 m averaged slope did not see.
	var nav := _n()
	var walls := 0
	for z in range(1395, 1436, 8):
		if nav.is_wall(-101.0, float(z)):
			walls += 1
	assert_gt(walls, 3, "most of the crag line is wall (%d of 6)" % walls)
