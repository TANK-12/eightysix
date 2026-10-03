extends "res://tests/lib/test_case.gd"
## Lane A3's wire anchor and ledge climb on the real Juggernaut: the dart goes where you look
## (lane A3 part 4) and bites only a grapple surface (physics layer 7); reeling in pulls the 5.4 t
## mech towards it no faster than the winch's power allows; paying out lowers a hanging mech; letting
## go works; a ledge in the legs' reach is found and hauled up. --fixed-fps 120.

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


## Look at `p`: the look pitch from the anchor sockets to it (the heading stays straight ahead).
func _aim_at(p: Vector3) -> void:
	var from: Vector3 = combat.anchor.aim_ray()[0]
	var d := p - from
	mech.set("look_pitch_deg", rad_to_deg(atan2(d.y, Vector2(d.x, d.z).length())))


func test_aims_where_you_look_and_bites_only_grapple_surfaces() -> void:
	await physics_frames(240)
	_block(Vector3(0, 12, -30), Vector3(20, 4, 4), 1)
	_block(Vector3(0, 24, -40), Vector3(20, 4, 4), 1 | 64)
	_block(Vector3(0, 0.5, -20), Vector3(20, 3, 4), 1 | 64)
	await physics_frames(2)
	_aim_at(Vector3(0, 12, -28))
	await physics_frames(30)
	_aim_at(Vector3(0, 12, -28))
	assert_eq(str(combat.anchor.preview()["state"]), "surface", "a plain wall (layer 1 only) cannot be bitten")
	assert_true(combat.anchor.find_target().is_empty())
	_aim_at(Vector3(0, 22, -38))
	await physics_frames(30)
	_aim_at(Vector3(0, 22, -38))
	var t := combat.anchor.find_target()
	assert_false(t.is_empty(), "the grapple slab up high is where you look")
	if not t.is_empty():
		assert_gt((t["point"] as Vector3).y, 20.0, "and it bites up there")
	_aim_at(Vector3(0, 1.5, -18))
	await physics_frames(30)
	_aim_at(Vector3(0, 1.5, -18))
	t = combat.anchor.find_target()
	assert_false(t.is_empty(), "looking low at the grapple-able rise")
	if not t.is_empty():
		assert_lt((t["point"] as Vector3).y, 3.0, "bites the rise, not the slab above: the crosshair decides")
	var up: Vector3 = combat.anchor.arm_limit(Vector3.UP, Basis.IDENTITY)
	assert_almost_eq(rad_to_deg(up.angle_to(Vector3.UP)), 10.0, 0.5, "straight up is pulled back to the arms' 80 deg")


func test_reel_in_lifts_the_mech_no_faster_than_the_winch_power() -> void:
	await physics_frames(240)
	# A roof ahead and above: a steep pull lifts (at a shallow angle the winch only drags the mech
	# along the ground, since the cable's vertical share is below its 53 kN weight).
	_block(Vector3(0, 22, -9), Vector3(20, 3, 8), 1 | 64)
	await physics_frames(2)
	_aim_at(Vector3(0, 20.4, -8))
	await physics_frames(30)
	_aim_at(Vector3(0, 20.4, -8))
	var start := mech.global_position
	assert_true(combat.anchor.fire(), "a dart left")
	await physics_frames(60)
	assert_eq(combat.anchor.state, WireAnchor.State.ATTACHED, "bit the slab")
	var len0 := combat.anchor.rope_len
	var peak := start.y
	var work := 0.0
	var loaded_s := 0.0
	for i in 480:
		combat.anchor.reel = -1
		var before := combat.anchor.rope_len
		var pull := combat.anchor.tension
		await physics_frames(1)
		if pull > 30000.0:
			work += (before - combat.anchor.rope_len) * pull
			loaded_s += 1.0 / 120.0
		peak = maxf(peak, mech.global_position.y)
	assert_lt(combat.anchor.rope_len, len0 - 6.0, "reeled in (%.1f m)" % (len0 - combat.anchor.rope_len))
	assert_gt(loaded_s, 1.0, "under load for a while (%.1f s)" % loaded_s)
	var kw := float(combat.anchor.def["winch_power_w"])
	assert_lt(work / maxf(loaded_s, 0.01), kw * 1.02, "under load the winch works at its %.0f kW at most (%.0f kW)" % [kw / 1000.0, work / maxf(loaded_s, 0.01) / 1000.0])
	assert_gt(peak - start.y, 3.0, "hauled up off the ground (%.1f m)" % (peak - start.y))
	assert_lt(mech.global_position.z, start.z - 3.0, "and towards the anchor")
	combat.anchor.fire()
	assert_eq(combat.anchor.state, WireAnchor.State.IDLE, "fire again lets go")


func test_pay_out_and_slack_do_not_pull() -> void:
	await physics_frames(240)
	_block(Vector3(0, 16, -25), Vector3(20, 3, 4), 1 | 64)
	await physics_frames(2)
	_aim_at(Vector3(0, 14.6, -24))
	await physics_frames(30)
	_aim_at(Vector3(0, 14.6, -24))
	combat.anchor.fire()
	await physics_frames(60)
	assert_eq(combat.anchor.state, WireAnchor.State.ATTACHED, "bit the slab")
	var len0 := combat.anchor.rope_len
	for i in 60:
		combat.anchor.reel = 1
		await physics_frames(1)
	assert_gt(combat.anchor.rope_len, len0 + 5.5, "paid out (12 m/s for 0.5 s)")
	assert_almost_eq(combat.anchor.tension, 0.0, 0.01, "a slack cable does nothing")


func test_pay_out_while_hanging_lowers_the_mech() -> void:
	await physics_frames(240)
	_block(Vector3(0, 40, -8), Vector3(20, 3, 20), 1 | 64)
	await physics_frames(2)
	_aim_at(Vector3(0, 38.4, -8))
	await physics_frames(30)
	_aim_at(Vector3(0, 38.4, -8))
	assert_true(combat.anchor.fire(), "a dart left for the roof")
	await physics_frames(60)
	assert_eq(combat.anchor.state, WireAnchor.State.ATTACHED, "bit the roof")
	for i in 1200:
		combat.anchor.reel = -1
		await physics_frames(1)
		if mech.global_position.y > 16.0:
			break
	combat.anchor.reel = 0
	await physics_frames(240)
	assert_eq(int(mech.get("grounded_legs")), 0, "hanging clear of the ground (y %.1f)" % mech.global_position.y)
	var y0 := mech.global_position.y
	var len0 := combat.anchor.rope_len
	for i in 180:
		combat.anchor.reel = 1
		await physics_frames(1)
	combat.anchor.reel = 0
	await physics_frames(300)
	var paid := combat.anchor.rope_len - len0
	var dropped := y0 - mech.global_position.y
	assert_eq(combat.anchor.state, WireAnchor.State.ATTACHED, "a controlled lower does not snap the wire")
	# 1.5 s held: the drum ramps up at 3 m/s^2 to 4 m/s, then brakes at 3 m/s^2 after letting go: ~6 m.
	assert_between(paid, 5.0, 7.0, "lowered at up to 4 m/s under load, ramped (%.1f m)" % paid)
	assert_almost_eq(dropped, paid, 1.0, "abseiled down by about what was paid out (%.1f m for %.1f m)" % [dropped, paid])


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


## Lane A4 (Emerson 2026-10-01: "make the grapple have gravity and better aiming"): the dart falls and
## slows as it pulls its line (v = v0 m / (m + lambda s)); fire control lifts the launch so the arc
## still lands on the crosshair; the arc it shows is the path it flies.
func test_dart_falls_and_fire_control_lands_it_on_the_crosshair() -> void:
	await physics_frames(240)
	var a := combat.anchor
	var space := mech.get_world_3d().direct_space_state
	var from: Vector3 = mech.global_transform * Vector3(0, 2, -2)
	var skip: Array[RID] = [mech.get_rid()]
	var flat := a.fly(space, from, Vector3.FORWARD * a.launch_speed(), 60.0, skip)
	var arc: PackedVector3Array = flat["arc"]
	var end := arc[arc.size() - 1]
	assert_lt(end.y, from.y - 2.0, "aimed level, 60 m of line later it has dropped (%.1f m)" % (from.y - end.y))
	var m := float(a.def["dart_kg"])
	var lam := float(a.def["line_kg_per_m"])
	var step := WireAnchor.dart_step(from, Vector3.FORWARD * 140.0, 40.0, 1.0 / 120.0, m, lam, 0.0)
	var slow := 140.0 - (step[1] as Vector3).length()
	assert_almost_eq(slow, lam * 140.0 * 140.0 / (m + lam * 40.0) / 120.0, 0.01, "line drag: lambda v^2 / (m + lambda s)")
	# A grapple slab 55 m out and 14 m up: the crosshair on it, the dart bites within a metre of it.
	_block(Vector3(0, 16, -58), Vector3(12, 4, 2), 1 | 64)
	await physics_frames(2)
	var spot := Vector3(0, 16, -57)
	_aim_at(spot)
	await physics_frames(30)
	_aim_at(spot)
	await physics_frames(1)
	var p := a.preview()
	assert_eq(str(p["state"]), "ok", "the arc reaches the slab")
	assert_lt((p["point"] as Vector3).distance_to(spot), 1.2, "and lands on the crosshair (%.2f m off)" % (p["point"] as Vector3).distance_to(spot))
	var dir: Vector3 = p["dir"]
	var straight := (spot - (mech.global_transform * a._mid_socket())).normalized()
	assert_gt(asin(dir.y) - asin(straight.y), 0.005, "fire control aims a little above the line to allow for the drop")
	print("    anchor: level shot drops %.1f m over 60 m of line; aim lifted %.2f deg; preview %.2f m off the crosshair" % [from.y - end.y, rad_to_deg(asin(dir.y) - asin(straight.y)), (p["point"] as Vector3).distance_to(spot)])
	assert_true(a.fire())
	for i in 120:
		await physics_frames(1)
		if a.state != WireAnchor.State.FLYING:
			break
	assert_eq(a.state, WireAnchor.State.ATTACHED, "the real flight bites where the preview said")
	assert_lt(a.anchor_point.distance_to(p["point"]), 1.5, "%.2f m from the preview" % a.anchor_point.distance_to(p["point"]))


func test_aim_assist_nudges_toward_a_marked_point_near_the_aim() -> void:
	await physics_frames(240)
	# A pole a little off the aim line, its tip marked as a grapple point.
	var tip := Vector3(-3, 18, -30)
	_block(Vector3(tip.x, 9, tip.z), Vector3(1.5, 18, 1.5), 1 | 64)
	await physics_frames(2)
	_aim_at(Vector3(0, 18, -30))
	await physics_frames(30)
	_aim_at(Vector3(0, 18, -30))
	var level := FakeLevel.new()
	tree.root.add_child(level)
	var before: Node = Game.level
	Game.level = level
	assert_true(combat.anchor.find_target().is_empty(), "aimed past the pole, nothing marked: no bite")
	level.grapple_points.append(tip)
	var t := combat.anchor.find_target()
	Game.level = before
	level.free()
	assert_false(t.is_empty(), "the marked point 6 deg off the aim is found")
	if not t.is_empty():
		assert_lt((t["point"] as Vector3).distance_to(tip), 1.6, "at the pole's tip")


func test_the_preview_arc_shows_screen_sized_dots_even_for_a_near_ledge() -> void:
	mech.set("is_player", true)
	await physics_frames(240)
	var a := combat.anchor
	# A grapple slab 14 m out and 5 m up: a short throw that used to show one dot at most.
	_block(Vector3(0, 6, -16), Vector3(12, 2, 2), 1 | 64)
	await physics_frames(2)
	_aim_at(Vector3(0, 6, -15))
	await physics_frames(10)
	_aim_at(Vector3(0, 6, -15))
	await physics_frames(2)
	assert_eq(str(a.preview()["state"]), "ok", "the arc reaches the near slab")
	var dots := a._arc.multimesh.visible_instance_count
	assert_gt(dots, 5, "a line of dots shows on a short throw (%d)" % dots)
	assert_true(a._arc_mat.fixed_size and a._arc_mat.billboard_mode == BaseMaterial3D.BILLBOARD_ENABLED, "dots face the camera at a fixed screen size")
	print("    anchor arc: %d dots on a 14 m throw" % dots)


## Emerson after 014: a 40 % stronger winch on a slider. The stall pull and power scale; the rope
## grows (break load and weight together) only when the stall pull would otherwise break it.
func test_winch_size_scales_the_winch_and_its_rope() -> void:
	var base: Dictionary = Registry.entry("weapons", "wire_anchor")
	assert_eq(Settings.get_f("gameplay.winch_size"), 1.4, "40 % stronger by default")
	assert_almost_eq(float(combat.anchor.def["max_tension_n"]), float(base["max_tension_n"]) * 1.4, 1.0, "stall pull x1.4")
	assert_almost_eq(float(combat.anchor.def["winch_power_w"]), float(base["winch_power_w"]) * 1.4, 1.0, "power x1.4")
	for size: float in [0.6, 1.0, 1.4, 2.0]:
		var d := WireAnchor.sized(base, size)
		assert_lt(float(d["max_tension_n"]), float(d["cable_break_n"]), "at %.1fx the stall pull stays under the rope's break load" % size)
	var d14 := WireAnchor.sized(base, 1.4)
	assert_almost_eq(float(d14["cable_break_n"]) / float(d14["max_tension_n"]), WireAnchor.ROPE_MARGIN, 0.001, "1.4x needs a bigger rope")
	assert_almost_eq(float(d14["line_kg_per_m"]) / float(base["line_kg_per_m"]), float(d14["cable_break_n"]) / float(base["cable_break_n"]), 0.001, "which weighs more in step with its strength")
	assert_eq(WireAnchor.sized(base, 1.0), base, "1x is the weapons.json winch and rope")
	assert_eq(float(WireAnchor.sized(base, 0.6)["cable_break_n"]), float(base["cable_break_n"]), "a smaller winch keeps the rope")
	Settings.set_value("gameplay.winch_size", 1.0, false)
	assert_almost_eq(float(combat.anchor.def["max_tension_n"]), float(base["max_tension_n"]), 1.0, "the slider changes it live")
	assert_almost_eq(float(combat.anchor.def["line_kg_per_m"]), float(base["line_kg_per_m"]), 0.0001, "and the rope with it")


## The bigger winch hauls the hanging mech up faster (same pull geometry, 2 s of reeling).
func test_bigger_winch_lifts_faster() -> void:
	var lifts: Array[float] = []
	for size: float in [1.0, 1.4]:
		if size != 1.0:
			after_each()
			before_each()
		Settings.set_value("gameplay.winch_size", size, false)
		await physics_frames(240)
		_block(Vector3(0, 22, -9), Vector3(20, 3, 8), 1 | 64)
		await physics_frames(2)
		_aim_at(Vector3(0, 20.4, -8))
		await physics_frames(30)
		_aim_at(Vector3(0, 20.4, -8))
		var y0 := mech.global_position.y
		assert_true(combat.anchor.fire(), "a dart left (%.1fx)" % size)
		await physics_frames(60)
		for i in 240:
			combat.anchor.reel = -1
			await physics_frames(1)
		lifts.append(mech.global_position.y - y0)
	assert_gt(lifts[1], lifts[0] * 1.1, "1.4x lifts more in 2 s (%.2f m vs %.2f m)" % [lifts[1], lifts[0]])
