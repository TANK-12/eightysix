extends "res://tests/lib/test_case.gd"
## Lane A3 part 4, ground movement (Emerson 2026-09-30: "I don't like how slow it is; there is no
## sliding yet"; then: the slide analog on L2, directional, "the momentum fights it a bit"). On flat
## ground: the gallop tops out near 70 km/h and 0-50 km/h is snappy but power-limited; the slide
## trigger at speed slides (kinetic friction, not a brake), the stick bends the path without turning
## the body, the turn input spins the body, a light squeeze is a light slide, and below slide speed the
## trigger is still the brake. --fixed-fps 120.

var ground: StaticBody3D
var mech: RigidBody3D


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(1200, 2, 1200)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	Settings.set_value("controls.sprint_mode", "hold", false)
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)


func after_each() -> void:
	for a: String in ["move_forward", "sprint", "brake", "turn_right", "strafe_right"]:
		Input.action_release(a)
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


func _planar() -> Vector3:
	return Vector3(mech.linear_velocity.x, 0.0, mech.linear_velocity.z)


func _heading() -> float:
	var f := -mech.global_transform.basis.z
	return rad_to_deg(atan2(-f.x, -f.z))


func _gallop(frames: int) -> void:
	await physics_frames(240)
	Input.action_press("move_forward", 1.0)
	Input.action_press("sprint", 1.0)
	await physics_frames(frames)


func test_gallop_is_fast_and_snappy() -> void:
	await physics_frames(240)
	Input.action_press("move_forward", 1.0)
	Input.action_press("sprint", 1.0)
	var to_50 := -1.0
	var top := 0.0
	for i in 600:
		await tree.physics_frame
		var v := _planar().length()
		top = maxf(top, v)
		if to_50 < 0.0 and v >= 50.0 / 3.6:
			to_50 = (i + 1) / 120.0
	print("  gallop: top %.1f km/h, 0-50 km/h %.2f s" % [top * 3.6, to_50])
	assert_between(top * 3.6, 66.0, 74.0, "gallop near 70 km/h (%.1f km/h)" % (top * 3.6))
	assert_between(to_50, 0.8, 1.8, "0-50 km/h in %.2f s: snappy, but no faster than 600 kW allows" % to_50)


func test_full_slide_skates_on_kinetic_friction() -> void:
	await _gallop(360)
	var v0 := _planar().length()
	var start := mech.global_position
	Input.action_press("brake", 1.0)
	await physics_frames(30)
	assert_true(bool(mech.get("skidding")), "sliding")
	var a := _planar().length()
	await physics_frames(60)
	var decel := (a - _planar().length()) / 0.5
	var mu := Settings.get_f("gameplay.slide_friction")
	assert_almost_eq(decel, mu * 9.81, 0.8, "slows at about mu x g (%.2f m/s^2)" % decel)
	while _planar().length() > 1.5:
		await tree.physics_frame
	var dist := Vector2(mech.global_position.x - start.x, mech.global_position.z - start.z).length()
	print("  slide: from %.1f km/h, %.1f m" % [v0 * 3.6, dist])
	assert_gt(dist, 25.0, "a long slide from a gallop (%.1f m)" % dist)


func test_stick_bends_the_path_without_turning_the_body() -> void:
	await _gallop(360)
	var h0 := _heading()
	var p0 := _planar().normalized()
	Input.action_press("brake", 1.0)
	Input.action_release("move_forward")
	Input.action_press("strafe_right", 1.0)
	await physics_frames(120)
	var bent := rad_to_deg(p0.signed_angle_to(_planar().normalized(), Vector3.UP))
	assert_lt(bent, -8.0, "the path bent right (%.1f deg in 1 s)" % bent)
	assert_gt(bent, -60.0, "but momentum fights it (%.1f deg)" % bent)
	assert_lt(absf(_heading() - h0), 5.0, "the body did not turn: a sideways drift")


func test_turn_input_spins_the_body_in_a_full_slide() -> void:
	await _gallop(360)
	Input.action_press("brake", 1.0)
	await physics_frames(20)
	var h0 := _heading()
	var p0 := _planar().normalized()
	Input.action_press("turn_right", 1.0)
	await physics_frames(120)
	var spun := _heading() - h0
	# Friction-limited: the skating feet give at most mu m g r of torque (~220 deg/s^2 at mu 0.4).
	assert_lt(spun, -50.0, "the body spun right (%.0f deg in 1 s)" % spun)
	var path := rad_to_deg(p0.signed_angle_to(_planar().normalized(), Vector3.UP))
	assert_gt(path, -15.0, "while the path carried on (%.1f deg)" % path)


func test_light_squeeze_is_a_light_slide_and_slow_is_a_brake() -> void:
	await _gallop(360)
	Input.action_press("brake", 0.3)
	await physics_frames(30)
	var s := float(mech.get("slide_amount"))
	assert_between(s, 0.15, 0.4, "slide depth follows the trigger (%.2f)" % s)
	Input.action_release("brake")
	Input.action_release("sprint")
	Input.action_release("move_forward")
	await physics_frames(360)
	assert_lt(_planar().length(), 1.0, "stopped")
	Input.action_press("move_forward", 1.0)
	await physics_frames(40)
	var v := _planar().length()
	assert_lt(v, 4.0, "slow (%.1f m/s)" % v)
	Input.action_release("move_forward")
	Input.action_press("brake", 1.0)
	await physics_frames(40)
	assert_almost_eq(float(mech.get("slide_amount")), 0.0, 0.001, "below slide speed the trigger brakes")
	assert_lt(_planar().length(), 0.5, "and stops it within a third of a second")
