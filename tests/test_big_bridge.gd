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
		if sz.z < 0.5 and sz.y < 1.2:
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
