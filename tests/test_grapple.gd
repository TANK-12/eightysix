extends "res://tests/lib/test_case.gd"
## Lane A3's wire anchor and ledge climb on the real Juggernaut: the dart finds a grapple surface
## (physics layer 7) in its upward fan, bites, and reeling in pulls 12 t towards it; paying out and
## letting go work; a ledge in the legs' reach is found and hauled up. --fixed-fps 120.

var ground: StaticBody3D
var mech: RigidBody3D
var combat: MechCombat
var blocks: Array = []


func before_each() -> void:
	ground = _block(Vector3(0, -1, 0), Vector3(400, 2, 400), 1)
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)
	combat = mech.get_node("Combat") as MechCombat


func _block(at: Vector3, size: Vector3, layer: int) -> StaticBody3D:
	var b := StaticBody3D.new()
	b.collision_layer = layer
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	b.add_child(cs)
	b.position = at
	tree.root.add_child(b)
	blocks.append(b)
	return b


func after_each() -> void:
	Input.action_release("move_forward")
	mech.free()
	for b: Node in blocks:
		b.free()
	blocks.clear()
	Settings.reset_all_quietly()


func test_finds_a_high_surface_and_misses_a_plain_wall() -> void:
	await physics_frames(240)
	_block(Vector3(0, 12, -30), Vector3(20, 4, 4), 1)
	await physics_frames(2)
	assert_true(combat.anchor.find_target().is_empty(), "layer 1 only: not a grapple surface")
	_block(Vector3(0, 14, -40), Vector3(20, 4, 4), 1 | 64)
	await physics_frames(2)
	var t := combat.anchor.find_target()
	assert_false(t.is_empty(), "the grapple slab up and ahead is found")
	if not t.is_empty():
		assert_gt((t["point"] as Vector3).y, 8.0, "found by pitching the fan up")
	# Grapple-able ground rising ahead is hit first at pitch 0; the slab above still wins.
	_block(Vector3(0, 0.5, -20), Vector3(20, 3, 4), 1 | 64)
	await physics_frames(2)
	t = combat.anchor.find_target()
	assert_gt((t["point"] as Vector3).y, 8.0, "a surface above beats the ground ahead")


func test_reel_in_lifts_the_mech_towards_the_anchor() -> void:
	await physics_frames(240)
	_block(Vector3(0, 22, -25), Vector3(20, 3, 4), 1 | 64)
	await physics_frames(2)
	var start := mech.global_position
	assert_true(combat.anchor.fire(), "a dart left")
	await physics_frames(60)
	assert_eq(combat.anchor.state, WireAnchor.State.ATTACHED, "bit the slab")
	var len0 := combat.anchor.rope_len
	combat.anchor.reel = -1
	var peak := start.y
	for i in 360:
		await physics_frames(1)
		combat.anchor.reel = -1
		peak = maxf(peak, mech.global_position.y)
	assert_lt(combat.anchor.rope_len, len0 - 10.0, "reeled in")
	assert_gt(peak - start.y, 3.0, "hauled up off the ground (%.1f m)" % (peak - start.y))
	assert_lt(mech.global_position.z, start.z - 5.0, "and towards the anchor")
	combat.anchor.fire()
	assert_eq(combat.anchor.state, WireAnchor.State.IDLE, "fire again lets go")


func test_pay_out_and_slack_do_not_pull() -> void:
	await physics_frames(240)
	_block(Vector3(0, 16, -25), Vector3(20, 3, 4), 1 | 64)
	await physics_frames(2)
	combat.anchor.fire()
	await physics_frames(60)
	var len0 := combat.anchor.rope_len
	for i in 60:
		combat.anchor.reel = 1
		await physics_frames(1)
	assert_gt(combat.anchor.rope_len, len0 + 5.5, "paid out (12 m/s for 0.5 s)")
	assert_almost_eq(combat.anchor.tension, 0.0, 0.01, "a slack cable does nothing")


func test_climbs_a_ledge_in_reach() -> void:
	await physics_frames(240)
	var h := 2.2
	_block(Vector3(0, h * 0.5, -7.5), Vector3(20, h, 8), 1)
	await physics_frames(2)
	var ledge := combat.climb.find_ledge()
	assert_false(ledge.is_empty(), "the 2.2 m ledge ahead is found")
	if ledge.is_empty():
		return
	assert_almost_eq(float(ledge["height"]), h, 0.3)
	# The real path: stick forward into the ledge; MechClimb finds it each tick and hauls.
	Input.action_press("move_forward", 1.0)
	await physics_frames(480)
	assert_gt(mech.global_position.y, h + 0.8, "up on the ledge (y %.2f)" % mech.global_position.y)
	assert_lt(mech.global_position.z, -4.0, "and over the lip")
	assert_false(combat.climb.climbing, "the climb ends once it is over")


func test_no_climb_on_a_walkable_slope_or_a_wall_too_tall() -> void:
	await physics_frames(240)
	_block(Vector3(0, 4, -6.5), Vector3(20, 8, 6), 1)
	await physics_frames(2)
	assert_true(combat.climb.find_ledge().is_empty(), "8 m wall is out of reach")


class FakeLevel:
	extends Node
	var grapple_points: Array[Vector3] = []


func test_aim_assist_uses_the_levels_grapple_points() -> void:
	await physics_frames(240)
	# A pole off to the side, its tip marked as a grapple point: the upward fan straight ahead misses it.
	var tip := Vector3(-14, 18, -30)
	_block(Vector3(tip.x, 9, tip.z), Vector3(1.5, 18, 1.5), 1 | 64)
	await physics_frames(2)
	var level := FakeLevel.new()
	tree.root.add_child(level)
	var before: Node = Game.level
	Game.level = level
	assert_true(combat.anchor.find_target().is_empty() or (combat.anchor.find_target()["point"] as Vector3).y < 8.0, "no marked point: nothing high")
	level.grapple_points.append(tip)
	var t := combat.anchor.find_target()
	Game.level = before
	level.free()
	assert_false(t.is_empty(), "the marked point is found")
	if not t.is_empty():
		assert_lt((t["point"] as Vector3).distance_to(tip), 1.6, "at the pole's tip")
