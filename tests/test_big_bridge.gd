extends "res://tests/lib/test_case.gd"
## Lane B5 part 2: the bridge on the big map's west road (BigBridges). The road is "bridged": no ford,
## the river stays deep and its banks steepen there; the bridge is laid from bank to bank on a flat
## deck, stands on pillars and abutments, and breaks under fire without taking the rest with it.

static var _terrain: BigTerrain
var holder: Node3D


func _t() -> BigTerrain:
	if _terrain == null:
		_terrain = BigTerrain.new(Registry.entry("maps", "big_map"))
	return _terrain


func _lay() -> Dictionary:
	var e: Dictionary = Registry.entry("maps", "big_map")
	return BigBridges.layout(_t(), e, e["bridges"][0])


func before_each() -> void:
	holder = Node3D.new()
	tree.root.add_child(holder)


func after_each() -> void:
	holder.free()


func test_the_bridged_road_crosses_deep_water_dry() -> void:
	var t := _t()
	var lay := _lay()
	assert_false(lay.is_empty(), "the west road crosses the river, so there is a bridge")
	var a: Vector2 = lay["from"]
	var b: Vector2 = lay["to"]
	var deepest := 0.0
	for k in 41:
		var q := a.lerp(b, k / 40.0)
		deepest = maxf(deepest, t.water_level - t.height_at(q.x, q.y))
	print("    bridge: %.0f m long, deck %.2f m, river bed %.2f m under the water line" % [a.distance_to(b), lay["at"].y, deepest])
	assert_gt(deepest, 2.0, "the river is deep under the bridge, not a ford")
	assert_gt(lay["at"].y - t.water_level, 2.0, "the deck is well above the water")
	assert_between(a.distance_to(b), 40.0, 140.0, "a sensible length")


func test_the_deck_meets_the_ground_at_both_ends() -> void:
	var t := _t()
	var lay := _lay()
	var a: Vector2 = lay["from"]
	var b: Vector2 = lay["to"]
	var dir := (b - a).normalized()
	for end: Vector2 in [a + dir * 3.0, b - dir * 3.0]:
		var gap: float = lay["at"].y - t.height_at(end.x, end.y)
		print("    bridge end at %s: deck %.2f m above the ground" % [str(end.round()), gap])
		assert_between(gap, -0.2, 1.0, "the deck is not floating or buried at %s" % str(end.round()))


func test_the_other_road_still_fords() -> void:
	var t := _t()
	var depth := t.water_level - t.height_at(636.0, 1194.0)
	assert_between(depth, 0.0, 0.8, "the farm track's ford is still shallow")


func test_the_bridge_stands_and_a_shot_deck_span_stays_out() -> void:
	var lay := _lay()
	var d := Destructible.make(str(lay["kit"]), 1, lay["over"])
	holder.add_child(d)
	assert_gt(d.pieces.size(), 20, "a bridge of many pieces")
	assert_true(d._unsupported().is_empty(), "everything on a new bridge is held up")
	var deck := -1
	for p: Dictionary in d.pieces:
		var s: Vector3 = p["size"]
		if s.y < 1.0 and s.x > 3.0 and s.z > 5.0:
			deck = int(p["index"])
			if deck > d.pieces.size() / 3:
				break
	assert_gt(deck, -1, "found a deck span")
	var left := d.integrity()
	d._break([deck] as Array[int], Vector3.ZERO, 0.0)
	assert_true(d.gone.has(deck), "the span is gone")
	assert_false(d.is_collapsed, "the rest of the bridge stands (the pillars hold most of it)")
	assert_gt(d.integrity(), 0.6, "most of it is still there")
	assert_lt(d.integrity(), left, "but a gap")


func test_parapets_chip_under_he_but_a_concrete_span_does_not_fall_to_a_few_rounds() -> void:
	var lay := _lay()
	var d := Destructible.make(str(lay["kit"]), 1, lay["over"])
	holder.add_child(d)
	var parapet := -1
	var deck := -1
	for p: Dictionary in d.pieces:
		var sz: Vector3 = p["size"]
		if sz.z < 0.5 and sz.y < 1.8:
			parapet = int(p["index"])
		elif sz.y < 1.0 and sz.z > 5.0 and sz.x > 3.0:
			deck = int(p["index"])
	assert_gt(parapet, -1, "found a parapet")
	assert_gt(deck, -1, "found a deck span")
	for k in 3:
		d.take_hit({"point": d.to_global(d._boxes[parapet].get_center()), "dir": Vector3.RIGHT, "damage": 1100.0, "ammo": "he"})
	assert_true(d.gone.has(parapet), "three HE rounds break a parapet")
	assert_false(d.gone.has(deck), "but the concrete deck under it stands")
	for k in 8:
		d.take_hit({"point": d.to_global(d._boxes[deck].get_center()), "dir": Vector3.DOWN, "damage": 1100.0, "ammo": "he"})
	assert_false(d.gone.has(deck), "and eight rounds do not bring a 56 cubic metre span down")


func test_a_span_that_goes_takes_its_parapets_with_it() -> void:
	var lay := _lay()
	var d := Destructible.make(str(lay["kit"]), 1, lay["over"])
	holder.add_child(d)
	var deck := -1
	for p: Dictionary in d.pieces:
		var sz: Vector3 = p["size"]
		if sz.y < 1.0 and sz.z > 5.0 and sz.x > 3.0:
			deck = int(p["index"])
			break
	var top := d._boxes[deck].end.y
	var on_it := 0
	for i in d.pieces.size():
		var b := d._boxes[i]
		if i != deck and absf(b.position.y - top) < 0.1 and Destructible._overlap_xz(b, d._boxes[deck]):
			on_it += 1
	assert_gt(on_it, 1, "the span carries parapets (%d)" % on_it)
	d._break([deck] as Array[int], Vector3.ZERO, 0.0)
	assert_gt(d.gone.size(), on_it, "the span and what stood on it are gone (%d pieces)" % d.gone.size())


func _bearings(d: Destructible) -> Array[int]:
	var out: Array[int] = []
	for p: Dictionary in d.pieces:
		if str(p["material"]) == "steel_rust":
			out.append(int(p["index"]))
	return out


func _span_with_bearings(d: Destructible) -> Dictionary:
	# a deck span (needs 2) and the two bearings under it
	for p: Dictionary in d.pieces:
		if int(p.get("needs", 1)) == 2:
			var i := int(p["index"])
			var under: Array[int] = []
			for b in _bearings(d):
				var u := d._boxes[b]
				if absf(u.end.y - d._boxes[i].position.y) <= Destructible.TOUCH_EPS and Destructible._overlap_xz(u, d._boxes[i]):
					under.append(b)
			if under.size() == 2:
				return {"span": i, "bearings": under}
	return {}


func test_a_span_needs_both_bearings_so_one_shot_out_drops_the_two_it_carried() -> void:
	var lay := _lay()
	var d := Destructible.make(str(lay["kit"]), 1, lay["over"])
	holder.add_child(d)
	assert_gt(_bearings(d).size(), 4, "steel bearings under the deck")
	var s := _span_with_bearings(d)
	assert_false(s.is_empty(), "a span rests on two bearings")
	var bs: Array = s["bearings"]
	var before := d.pieces.size() - d.gone.size()
	d._break([bs[0]] as Array[int], Vector3.ZERO, 0.0)
	assert_true(d.gone.has(int(bs[0])), "the bearing is gone")
	assert_true(d.gone.has(int(s["span"])), "the span lost one of its two bearings and fell")
	var spans_gone := 0
	for p: Dictionary in d.pieces:
		if int(p.get("needs", 1)) == 2 and d.gone.has(int(p["index"])):
			spans_gone += 1
	assert_eq(spans_gone, 2, "a bearing carries two spans (one each side) and both come down")
	assert_false(d.is_collapsed, "the rest of the bridge stands")
	assert_true(d._unsupported().is_empty(), "nothing else is left hanging")
	var slabs := 0
	for deb: Variant in Destructible._debris:
		if is_instance_valid(deb) and (deb as RigidBody3D).physics_material_override != null and (deb as RigidBody3D).get_parent() == holder:
			slabs += 1
			assert_gt((deb as RigidBody3D).linear_velocity.length(), 2.0, "a falling slab is sent sliding")
	assert_eq(slabs, 2, "the two spans came down as slick slabs that slide off the pier caps")
	print("    bridge: one bearing out took %d pieces of %d" % [before - (d.pieces.size() - d.gone.size()), before])


func test_a_direct_he_round_at_a_bearing_breaks_it_in_one_or_two() -> void:
	var lay := _lay()
	var d := Destructible.make(str(lay["kit"]), 1, lay["over"])
	holder.add_child(d)
	var b := _bearings(d)[2]
	var rounds := 0
	while not d.gone.has(b) and rounds < 6:
		d.take_hit({"point": d.to_global(d._boxes[b].get_center()), "dir": Vector3.UP, "damage": 1100.0, "ammo": "he"})
		rounds += 1
	print("    bridge: a bearing breaks after %d HE rounds" % rounds)
	assert_between(float(rounds), 1.0, 3.0, "a few rounds at the weak point, not one and not many")


## Part 5: a fired HE shell (500 damage) bursts on the deck beside a bearing (bearings sit under it) and gives it a share of its 800,
## measured 150-620 a hit on the live bridge, so a bearing's hit points are tuned down (tuning "destruction" weak_hp_scale):
## shells at the deck beside it, not scripted hits on it, break it in a few.
func test_a_few_shells_bursting_beside_a_bearing_break_it() -> void:
	var lay := _lay()
	var d := Destructible.make(str(lay["kit"]), 1, lay["over"])
	holder.add_child(d)
	var b := _bearings(d)[2]
	var size: Vector3 = d.pieces[b]["size"]
	var scale := float(Registry.tune("destruction", {}).get("weak_hp_scale", 1.0))
	assert_almost_eq(d.hp[b], size.x * size.y * size.z * 2500.0 * scale, 1.0, "a bearing has the weak share of its steel's hit points")
	var at := d._boxes[b].get_center() + Vector3(0.0, 0.0, size.z * 0.5 + 1.2)  # 1.2 m beside the bearing, at the deck's side
	var rounds := 0
	while not d.gone.has(b) and rounds < 10:
		d.take_hit({"point": d.to_global(at), "dir": Vector3.UP, "damage": 500.0, "ammo": "he"})
		rounds += 1
	print("    bridge: a bearing breaks after %d HE shells bursting 1.2 m beside it" % rounds)
	assert_between(float(rounds), 2.0, 6.0, "a few shells, not one and not many")


func test_the_bearings_are_marked_weak_points_a_player_can_be_shown() -> void:
	var lay := _lay()
	var d := Destructible.make(str(lay["kit"]), 1, lay["over"])
	holder.add_child(d)
	var pts := d.weak_points()
	assert_eq(pts.size(), _bearings(d).size(), "one weak point per standing bearing")
	var b := _bearings(d)[2]
	assert_true(pts.has(d.to_global(d._boxes[b].get_center())), "at the bearing's centre, in world space")
	var near := Destructible.weak_marks(tree, pts[0], 20.0)
	assert_gt(near.size(), 0, "marks within range of the player")
	assert_lt(near.size(), pts.size(), "marks out of range are left out")
	assert_eq(Destructible.weak_marks(tree, pts[0] + Vector3(5000.0, 0.0, 0.0), 300.0).size(), 0, "none from far away")
	d._break([b] as Array[int], Vector3.ZERO, 0.0)
	assert_eq(d.weak_points().size(), pts.size() - 1, "a broken bearing is no longer marked")
	var plain := Destructible.make("ruin_house", 1)
	holder.add_child(plain)
	assert_eq(plain.weak_points().size(), 0, "a building has none")
