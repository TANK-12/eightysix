extends "res://tests/lib/test_case.gd"
## Lane B5: walls and buildings that break (Destructible on top of the kit's pieces): broken pieces
## skipped by index, penetrators hole and high explosive breaks wide, unsupported floors fall, enough
## fire brings a building down, projectiles find the building, debris is capped.

var holder: Node3D


func before_each() -> void:
	holder = Node3D.new()
	tree.root.add_child(holder)


func after_each() -> void:
	holder.free()


func _shapes(n: Node) -> int:
	var c := 0
	for s: Node in n.find_children("*", "CollisionShape3D", true, false):
		if s.has_meta("piece"):
			c += 1
	return c


func test_broken_pieces_are_skipped_by_index_and_the_rest_stay_put() -> void:
	var full := Kit.build("ruin_house_two", 3)
	var cut := Kit.build("ruin_house_two", 3, {"gone": {0: true, 5: true}})
	var a: Array = full.get_meta("pieces")
	var b: Array = cut.get_meta("pieces")
	assert_eq(a.size(), b.size(), "same pieces listed")
	assert_eq(_shapes(cut), _shapes(full) - 2, "two colliders fewer")
	assert_true(bool(b[5]["gone"]), "piece 5 marked gone")
	assert_eq((b[9]["xf"] as Transform3D).origin, (a[9]["xf"] as Transform3D).origin, "the others are where they were")
	full.free()
	cut.free()


func _wall_hit(ammo: String, damage: float) -> Dictionary:
	var d := Destructible.make("wall_4m", 1)
	holder.add_child(d)
	var b: AABB = d._boxes[d.pieces.size() / 2]
	var r := d.take_hit({"point": d.to_global(b.get_center()), "dir": Vector3.FORWARD, "damage": damage, "ammo": ammo})
	r["integrity"] = d.integrity()
	return r


func test_a_penetrator_holes_a_wall_and_high_explosive_breaks_more() -> void:
	var ap := _wall_hit("apfsds", 900.0)
	var he := _wall_hit("he", 500.0)
	assert_gt(float(ap["broken"]), 0.0, "the 57 mm penetrator knocks a block out")
	assert_gt(float(ap["integrity"]), 0.5, "but leaves the wall standing")
	assert_gt(float(he["broken"]), float(ap["broken"]), "high explosive breaks more (%d vs %d)" % [he["broken"], ap["broken"]])
	var mg := _wall_hit("ball", 40.0)
	assert_eq(int(mg["broken"]), 0, "a 12.7 mm round only chips it")


func test_knocking_out_the_ground_floor_brings_the_floors_above_down() -> void:
	var d := Destructible.make("ruin_house_two", 3, {"damage": 0.0})
	holder.add_child(d)
	var base := INF
	for b: AABB in d._boxes:
		base = minf(base, b.position.y)
	var ground: Array[int] = []
	var upper := 0
	for p: Dictionary in d.pieces:
		var i := int(p["index"])
		if d.gone.has(i):
			continue
		if d._boxes[i].position.y <= base + Destructible.GROUND_EPS:
			ground.append(i)
		else:
			upper += 1
	assert_gt(upper, 5, "the house has an upper floor")
	var fell := [false]
	d.collapsed.connect(func() -> void: fell[0] = true)
	d._break(ground, Vector3.ZERO, 0.0)
	assert_true(fell[0], "with nothing under them the upper floors come down: the house collapses")
	assert_true(d.body == null, "nothing left standing")
	var left := d.get_children().filter(func(c: Node) -> bool: return not c.is_queued_for_deletion())
	assert_eq(left.size(), 1, "a rubble pile where it stood")
	assert_eq(str((left[0] as Node).get_meta("kit", "")), "rubble_pile")


func test_enough_fire_brings_a_building_down_and_debris_is_capped() -> void:
	var d := Destructible.make("ruin_house", 2, {"damage": 0.2})
	holder.add_child(d)
	var fell := [false]
	d.collapsed.connect(func() -> void: fell[0] = true)
	var shots := 0
	var rng := RandomNumberGenerator.new()
	rng.seed = 5
	while not fell[0] and shots < 40:
		var b: AABB = d._boxes[d._nearest(Vector3(rng.randf_range(-3, 3), rng.randf_range(0.2, 3.0), -4.0))]
		d.take_hit({"point": d.to_global(b.get_center()), "dir": Vector3.BACK, "damage": 500.0, "ammo": "he"})
		shots += 1
	print("    destruction: ruin_house down after %d HE rounds" % shots)
	assert_true(fell[0], "collapsed")
	assert_between(shots, 2, 30, "takes a few rounds, not one and not forever")
	assert_lt(Destructible._debris.size(), int(Registry.tune("destruction", {})["debris_cap"]) + 1, "debris capped")


func test_projectiles_find_the_building() -> void:
	var d := Destructible.make("ruin_house", 1)
	holder.add_child(d)
	assert_eq(CombatHits.receiver(d.body), d, "a shell striking the kit body reaches the Destructible")


func test_grapple_points_follow_a_building_as_it_breaks() -> void:
	var points: Array[Vector3] = []
	var d := Destructible.make("ruin_house_two", 3, {"damage": 0.0})
	holder.add_child(d)
	d.sync_anchors(points)
	d.broke.connect(d.sync_anchors.bind(points).unbind(1))
	d.collapsed.connect(d.sync_anchors.bind(points))
	assert_gt(points.size(), 0, "an intact house lists anchors")
	var first := points.duplicate()
	var top: AABB = d._boxes[0]
	for b: AABB in d._boxes:
		if b.end.y > top.end.y:
			top = b
	d.take_hit({"point": d.to_global(top.get_center()), "dir": Vector3.DOWN, "damage": 50000.0, "ammo": "he"})
	assert_gt(d.gone.size(), 0, "the top piece broke")
	if not d.is_collapsed:
		assert_eq(points.size(), d.anchors().size(), "the list holds only what the house still has")
		for p: Vector3 in points:
			assert_true(d.anchors().has(p), "no anchor left hanging where a piece used to be")
	d.collapse()
	assert_eq(points.size(), 0, "a collapsed house has no anchors")
	assert_gt(first.size(), 0, "(it had some before)")


func test_small_map_buildings_break_and_take_their_grapple_points_with_them() -> void:
	var level: Node3D = (load("res://scenes/levels/small_map.tscn") as PackedScene).instantiate()
	tree.root.add_child(level)
	var places: Node = level.get_node("Places")
	var houses: Array[Destructible] = []
	for n: Node in places.get_children():
		if n is Destructible and (n as Destructible).pieces.size() > 10:
			houses.append(n)
	assert_gt(houses.size(), 2, "the small map's buildings are Destructibles (%d)" % houses.size())
	var points: Array[Vector3] = level.get("grapple_points")
	var before := points.size()
	var d: Destructible = houses[0]
	assert_gt(d.listed.size(), 0, "a house lists its anchors")
	for k in 40:
		if d.is_collapsed:
			break
		var at: AABB = d._boxes[d._nearest(Vector3(0.0, 1.5, -3.0 + k * 0.15))]
		d.take_hit({"point": d.to_global(at.get_center()), "dir": Vector3.BACK, "damage": 900.0, "ammo": "he"})
	assert_true(d.is_collapsed, "enough fire brings the house down")
	assert_lt(points.size(), before, "its grapple points left the map's list (%d -> %d)" % [before, points.size()])
	level.free()
	Game.level = null


func test_a_burnt_out_truck_stands_and_comes_apart_under_fire() -> void:
	var d := Destructible.make("wreck_truck", 4)
	holder.add_child(d)
	assert_gt(d.pieces.size(), 5, "wheels, chassis, cab (%d pieces)" % d.pieces.size())
	assert_true(d._unsupported().is_empty(), "everything on it is held up as built")
	var shots := 0
	while d.integrity() > 0.5 and shots < 12:
		d.take_hit({"point": d.to_global(Vector3(0.0, 1.2, 0.0)), "dir": Vector3.RIGHT, "damage": 1500.0, "ammo": "he"})
		shots += 1
	assert_lt(d.integrity(), 0.6, "a few HE rounds wreck the wreck (%d)" % shots)


## Lane B5 part 3: street and depot props from the kit (a rail car, a power pole, crate stacks, a sandbag wall):
## each stands as built for every seed (nothing floats), and a rail car comes apart under HE.
func test_the_street_and_depot_props_stand_as_built() -> void:
	for id: String in ["rail_car", "power_pole", "crate_stack", "sandbag_wall"]:
		for seed_v in 8:
			var d := Destructible.make(id, seed_v)
			holder.add_child(d)
			assert_gt(d.pieces.size(), 1, "%s seed %d has pieces" % [id, seed_v])
			assert_true(d._unsupported().is_empty(), "%s seed %d: everything on it is held up as built" % [id, seed_v])
			d.free()


func test_a_rail_car_roof_comes_down_with_its_walls() -> void:
	var d := Destructible.make("rail_car", 2)
	holder.add_child(d)
	var shots := 0
	while d.integrity() > 0.6 and shots < 14:
		d.take_hit({"point": d.to_global(Vector3(0.0, 1.5, 0.0)), "dir": Vector3.RIGHT, "damage": 1500.0, "ammo": "he"})
		shots += 1
	assert_lt(d.integrity(), 0.7, "HE wrecks a rail car (%d rounds)" % shots)
	assert_true(d._unsupported().is_empty(), "nothing is left hanging")
