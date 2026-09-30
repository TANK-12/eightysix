extends "res://tests/lib/test_case.gd"
## Lane A3 part 4: air movement from real physics only (Emerson 2026-09-30). Dropped from high up,
## the real Juggernaut is airborne. The move stick does not push it (nothing outside touches the
## centre of mass); the aim turns and pitches it only by swinging the legs (sweep outstretched, return
## tucked), with the angular momentum of body + legs conserved; with gameplay.air_control off the
## legs stay still and nothing turns.

var mech: RigidBody3D


func before_each() -> void:
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 800.0, 0)
	tree.root.add_child(mech)


func after_each() -> void:
	for a: String in ["move_forward", "turn_right", "aim_up"]:
		Input.action_release(a)
	mech.free()
	Settings.reset_all_quietly()


func _planar_speed() -> float:
	return Vector2(mech.linear_velocity.x, mech.linear_velocity.z).length()


func _yaw() -> float:
	var f := -mech.global_transform.basis.z
	return rad_to_deg(atan2(-f.x, -f.z))


## Angular momentum of the body (world inertia x angular velocity) plus what the swinging legs carry.
func _total_l() -> Vector3:
	var b := mech.global_transform.basis.orthonormalized()
	var i_world := b * Basis.from_scale(mech.inertia) * b.transposed()
	return i_world * mech.angular_velocity + (mech.get("leg_momentum") as Vector3)


func test_stick_does_not_push_in_the_air() -> void:
	await physics_frames(30)
	assert_true(bool(mech.get("airborne")), "falling from 800 m")
	var before := _planar_speed()
	Input.action_press("move_forward", 1.0)
	await physics_frames(120)
	assert_lt(absf(_planar_speed() - before), 0.05, "a second of stick forward changes nothing (%.3f m/s)" % _planar_speed())


func test_swinging_legs_turn_the_body_and_conserve_angular_momentum() -> void:
	await physics_frames(30)
	var yaw0 := _yaw()
	var worst := 0.0
	var biggest := 0.0
	var swung := 0.0
	var tucked := false
	Input.action_press("turn_right", 1.0)
	for i in 240:
		await tree.physics_frame
		worst = maxf(worst, _total_l().length())
		biggest = maxf(biggest, (Basis.from_scale(mech.inertia) * mech.angular_velocity).length())
		swung = maxf(swung, absf((mech.get("air_swing") as Vector2).x))
		tucked = tucked or float(mech.get("air_tuck")) > 0.9
	var turned := _yaw() - yaw0
	assert_lt(turned, -10.0, "two seconds of legs swinging turned it right (%.1f deg)" % turned)
	assert_gt(rad_to_deg(swung), 20.0, "the legs really swung (%.0f deg)" % rad_to_deg(swung))
	assert_true(tucked, "and tucked in to come back")
	assert_gt(biggest, 500.0, "the body really spun (peak %.0f kg m^2/s)" % biggest)
	assert_lt(worst, biggest * 0.02, "body + legs angular momentum stays zero (worst %.1f vs peak %.0f)" % [worst, biggest])


func test_aim_up_pitches_the_body_with_the_legs() -> void:
	await physics_frames(30)
	Input.action_press("aim_up", 1.0)
	await physics_frames(240)
	var f := -mech.global_transform.basis.z
	var pitch := rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
	# Small by nature: the legs' fore-aft inertia is about 6% of the body's pitch inertia (the long gun).
	assert_gt(pitch, 0.5, "nose pitched up by swinging the legs (%.1f deg)" % pitch)


func test_off_nothing_turns() -> void:
	Settings.set_value("gameplay.air_control", false, false)
	await physics_frames(30)
	var yaw0 := _yaw()
	Input.action_press("move_forward", 1.0)
	Input.action_press("turn_right", 1.0)
	await physics_frames(120)
	assert_lt(_planar_speed(), 0.05, "no push")
	assert_lt(absf(_yaw() - yaw0), 0.5, "and no turn")
	assert_eq((mech.get("air_swing") as Vector2), Vector2.ZERO, "legs still")
