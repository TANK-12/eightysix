extends "res://tests/lib/test_case.gd"
## The stand-up control (Emerson 2026-10-07: "add a way to flip the mech back upright when it ends up
## on its side or back", then "physical, not magic"). The right_mech action (U), or jump while tipped,
## has the legs plant on the ground and push it over until it is level: from its side, its back, its
## nose and on a slope, about 1-2 s on flat ground. Pinned it fails cleanly, with no leg strength it
## does nothing (so it is the legs doing it), upright it does nothing, and a tipped mech's jump button
## no longer charges a jump.

var ground: StaticBody3D
var mech: RigidBody3D


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(600, 2, 600)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	mech = MechBuilder.build("juggernaut_m2")


func after_each() -> void:
	for a: String in ["right_mech", "jump"]:
		Input.action_release(a)
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


func _lean_deg() -> float:
	return rad_to_deg(mech.global_transform.basis.y.angle_to(Vector3.UP))


## Drops the mech rolled `roll_deg` about its nose and lets it come to rest; returns the lean. Balance
## assist is off, because on flat ground its slow auto-recover would roll it off its side by itself
## (the button is for when that does not manage: rough ground, wedged, or on its back).
func _tip(roll_deg: float, pitch_deg: float = 0.0) -> float:
	Settings.set_value("gameplay.upright_assist", false)
	mech.position = Vector3(0, 3.0, 0)
	mech.rotation = Vector3(deg_to_rad(pitch_deg), 0, deg_to_rad(roll_deg))
	tree.root.add_child(mech)
	await physics_frames(240)
	return _lean_deg()




## Presses `action` for a few ticks, then waits up to 5 s for it to stand; returns seconds taken (or -1).
func _press_and_wait(action: String) -> float:
	Input.action_press(action)
	await physics_frames(3)
	Input.action_release(action)
	for i in 600:
		await physics_frames(1)
		if _lean_deg() < 20.0 and int(mech.get("righting_s") * 1000) == 0:
			return (i + 3) / 120.0
	return -1.0


func test_u_stands_it_up_when_rolled_over_past_its_side() -> void:
	var lean := await _tip(115.0)
	assert_gt(lean, 55.0, "it lies rolled over first (%.0f deg)" % lean)
	var took := await _press_and_wait("right_mech")
	assert_between(took, 0.0, 2.2, "back on its feet in %.2f s" % took)
	await physics_frames(240)
	assert_lt(_lean_deg(), 20.0, "and it stays up (%.0f deg)" % _lean_deg())
	print("    rolled 115: lean %.0f deg, stood up in %.2f s, %.0f deg 2 s later" % [lean, took, _lean_deg()])


func test_u_stands_it_up_from_its_back() -> void:
	var lean := await _tip(180.0)
	assert_gt(lean, 120.0, "it lies on its back first (%.0f deg)" % lean)
	var took := await _press_and_wait("right_mech")
	assert_between(took, 0.0, 2.5, "back on its feet in %.2f s" % took)
	await physics_frames(240)
	assert_lt(_lean_deg(), 20.0, "and it stays up (%.0f deg)" % _lean_deg())
	print("    back: lean %.0f deg, stood up in %.2f s, %.0f deg 2 s later" % [lean, took, _lean_deg()])


func test_jump_while_tipped_stands_it_up_instead_of_charging() -> void:
	await _tip(115.0)
	Input.action_press("jump")
	await physics_frames(30)
	assert_false(bool(mech.get("charging")), "no jump charge while on its side")
	Input.action_release("jump")
	for i in 480:
		await physics_frames(1)
		if _lean_deg() < 20.0:
			break
	assert_lt(_lean_deg(), 20.0, "jump stood it up (%.0f deg)" % _lean_deg())


func test_upright_does_nothing() -> void:
	var lean := await _tip(0.0)
	assert_lt(lean, 15.0)
	Input.action_press("right_mech")
	await physics_frames(3)
	Input.action_release("right_mech")
	assert_eq(float(mech.get("righting_s")), 0.0, "no stand-up when already upright")
	assert_false(mech.call("start_righting"), "start_righting refuses when upright")


func test_the_legs_do_it_with_no_strength_it_stays_down() -> void:
	(mech.get("_t")["righting"] as Dictionary)["leg_push_g"] = 0.0
	var lean := await _tip(180.0)
	await _press_and_wait("right_mech")
	assert_gt(_lean_deg(), 55.0, "no leg strength, no stand-up (%.0f -> %.0f deg)" % [lean, _lean_deg()])
	(mech.get("_t")["righting"] as Dictionary)["leg_push_g"] = 2.5


func test_legs_push_on_the_ground_while_it_stands() -> void:
	await _tip(180.0)
	Input.action_press("right_mech")
	await physics_frames(3)
	Input.action_release("right_mech")
	var most := 0
	var on_ground := true
	for i in 120:
		await physics_frames(1)
		var n := 0
		for leg: Dictionary in mech.get("legs"):
			if leg.get("pushing", false):
				n += 1
				on_ground = on_ground and (leg["push_at"] as Vector3).y < 0.2
		most = maxi(most, n)
	assert_gt(most, 0, "legs push (up to %d at once)" % most)
	assert_true(on_ground, "every pushing foot is on the ground")


func test_u_stands_it_up_from_its_nose() -> void:
	var lean := await _tip(0.0, -100.0)
	assert_gt(lean, 55.0, "it lies on its nose first (%.0f deg)" % lean)
	var took := await _press_and_wait("right_mech")
	assert_between(took, 0.0, 3.0, "back on its feet in %.2f s" % took)
	print("    nose: lean %.0f deg, stood up in %.2f s" % [lean, took])


## On a 20 degree slope the feet hold less and the climb is harder; a second press is allowed.
func test_u_stands_it_up_on_a_slope_maybe_at_the_second_try() -> void:
	ground.rotation = Vector3(0, 0, deg_to_rad(20.0))
	var lean := await _tip(180.0)
	assert_gt(lean, 55.0, "it lies on its back on the slope first (%.0f deg)" % lean)
	var took := await _press_and_wait("right_mech")
	var tries := 1
	if took < 0.0:
		tries = 2
		took = await _press_and_wait("right_mech")
	var tilt := rad_to_deg(mech.global_transform.basis.y.angle_to(Vector3.UP))
	assert_gt(took, 0.0, "up on the slope after %d tries (lean %.0f deg)" % [tries, tilt])
	print("    slope 20: lean %.0f deg, stood up in %.2f s at try %d" % [lean, took, tries])


func test_pinned_it_fails_cleanly() -> void:
	var lean := await _tip(180.0)
	var lid := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(30, 1, 30)
	cs.shape = box
	lid.add_child(cs)
	var aabb := _mech_top()
	lid.position = Vector3(mech.global_position.x, aabb + 0.55, mech.global_position.z)
	tree.root.add_child(lid)
	Input.action_press("right_mech")
	await physics_frames(3)
	Input.action_release("right_mech")
	var from := mech.global_position
	var top := 0.0
	var rise := 0.0
	for i in 480:
		await physics_frames(1)
		top = maxf(top, mech.linear_velocity.length())
		rise = maxf(rise, mech.linear_velocity.y)
	var moved := mech.global_position.distance_to(from)
	assert_gt(_lean_deg(), 55.0, "pinned under a slab it stays over (%.0f -> %.0f deg)" % [lean, _lean_deg()])
	assert_eq(float(mech.get("righting_s")), 0.0, "and it gives up after max_s")
	assert_lt(rise, 3.0, "nothing launches it (up at %.1f m/s at most)" % rise)
	assert_lt(top, 8.0, "the paddling legs shove it along, no faster than a walk (%.1f m/s)" % top)
	print("    pinned: stays at %.0f deg, shoved %.1f m along, top %.1f m/s" % [_lean_deg(), moved, top])
	lid.free()


func test_with_balance_assist_on_it_still_stands_from_its_back() -> void:
	await _tip(180.0)
	Settings.set_value("gameplay.upright_assist", true)
	var took := await _press_and_wait("right_mech")
	assert_between(took, 0.0, 2.5, "the assists stand aside while the legs work (%.2f s)" % took)


## The highest point of the mech's collision shapes, in world space.
func _mech_top() -> float:
	var top := -INF
	for c in mech.find_children("*", "CollisionShape3D", true, false):
		var shape := (c as CollisionShape3D).shape
		if shape == null:
			continue
		var debug := shape.get_debug_mesh()
		if debug == null:
			continue
		var box := (c as CollisionShape3D).global_transform * debug.get_aabb()
		top = maxf(top, box.end.y)
	return top


## A tumble that is neither a plain roll nor a plain pitch (the roll axis has to follow the body).
func test_u_stands_it_up_from_a_rolled_and_pitched_tumble() -> void:
	var lean := await _tip(140.0, 40.0)
	assert_gt(lean, 55.0, "it lies tumbled first (%.0f deg)" % lean)
	var took := await _press_and_wait("right_mech")
	assert_between(took, 0.0, 3.5, "back on its feet in %.2f s (2.2-3.1 s seen)" % took)
	print("    roll 140 + pitch 40: lean %.0f deg, stood up in %.2f s" % [lean, took])


## On a steep slope it can slide while it tries; a second press must still be taken (it lies on the
## ground, it is not flying), whatever the outcome.
func test_a_second_try_is_taken_while_it_slides_down_a_steep_slope() -> void:
	ground.rotation = Vector3(0, 0, deg_to_rad(-30.0))
	var lean := await _tip(180.0)
	var took := await _press_and_wait("right_mech")
	var second := "not needed"
	if took < 0.0:
		# Tumbling down it bounces clear of the slope for a second or more at a time (measured 2026-10-08),
		# and a press in the air is left alone by design; so press again as it touches the slope, the
		# way a pilot would. The speed rule (4 m/s) must not refuse it there.
		# (rolling over it passes upright for a moment: only "tipped and touching" counts)
		var speed := 0.0
		for i in 480:
			await physics_frames(1)
			if mech.call("is_tipped") and float(mech.get("_off_ground_s")) == 0.0:
				speed = mech.linear_velocity.length()
				Input.action_press("right_mech")
				await physics_frames(2)
				Input.action_release("right_mech")
				var taken := float(mech.get("righting_s")) > 0.0 or _lean_deg() < 20.0
				assert_true(taken, "the second press is taken (sliding at %.1f m/s)" % speed)
				second = "taken at %.1f m/s" % speed
				break
		if second == "not needed" and not mech.call("is_tipped"):
			second = "not needed (it came upright on its own)"
		assert_true(second != "not needed", "it touched the slope or came upright within 4 s")
		for i in 600:
			await physics_frames(1)
			if int(mech.get("righting_s") * 1000) == 0:
				break
	print("    slope 30: lean %.0f deg, first try %.2f s, second press %s, ends at %.0f deg" % [lean, took, second, _lean_deg()])
	assert_lt(_lean_deg(), 55.0, "it ends on its feet (%.0f deg, the slope is 30)" % _lean_deg())


## A flip in the air is left alone: tipped, falling fast with nothing under it for longer than
## righting.ground_window_s, a press does nothing; within the window of a touch (a bounce) it counts.
func test_a_flip_in_the_air_is_left_alone_but_a_bounce_is_not() -> void:
	Settings.set_value("gameplay.upright_assist", false)
	mech.position = Vector3(0, 60.0, 0)
	mech.rotation = Vector3(0, 0, deg_to_rad(170.0))
	tree.root.add_child(mech)
	mech.linear_velocity = Vector3(0, -8.0, 0)
	await physics_frames(84)  # 0.7 s in the air
	var off := float(mech.get("_off_ground_s"))
	assert_gt(off, 0.5, "it has been off the ground %.2f s" % off)
	assert_false(mech.call("start_righting"), "a press in the air is left alone (%.1f m/s)" % mech.linear_velocity.length())
	mech.set("_off_ground_s", 0.3)
	assert_true(mech.call("start_righting"), "a press 0.3 s after a touch counts")
	print("    in the air: off the ground %.2f s at %.1f m/s, refused; 0.3 s after a touch, taken" % [off, mech.linear_velocity.length()])


## Turning (spin about its own up) does not count as spin left over from the stand-up: before
## 2026-10-08 a held turn (95 deg/s) kept it going until max_s even on flat ground.
func test_turning_while_it_stands_up_does_not_keep_the_stand_up_going() -> void:
	var lean := await _tip(180.0)
	assert_gt(lean, 55.0, "it lies on its back first (%.0f deg)" % lean)
	Input.action_press("right_mech")
	await physics_frames(3)
	Input.action_release("right_mech")
	var turning := false
	var ended := -1.0
	for i in 600:
		await physics_frames(1)
		if not turning and _lean_deg() < 30.0:
			turning = true
		if turning:
			# a held turn: the yaw part of the spin is 95 deg/s, the tilting part is left to the legs
			var up := mech.global_transform.basis.y
			var w := mech.angular_velocity
			mech.angular_velocity = w - up * w.dot(up) + up * deg_to_rad(95.0)
		if float(mech.get("righting_s")) <= 0.0:
			ended = (i + 3) / 120.0
			break
	var max_s := float((mech.get("_t") as Dictionary)["righting"]["max_s"])
	assert_true(turning, "it came near level (%.0f deg)" % _lean_deg())
	assert_between(ended, 0.0, max_s - 0.5, "the stand-up ended after %.2f s while turning, before its %.1f s limit" % [ended, max_s])
	assert_lt(_lean_deg(), 15.0, "and it is level (%.0f deg)" % _lean_deg())
	print("    turning at 95 deg/s as it comes level: stand-up ended after %.2f s" % ended)
