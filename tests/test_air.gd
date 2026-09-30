extends "res://tests/lib/test_case.gd"
## Lane A3's air control (Emerson 2026-09-30: movement and aiming in mid-air): dropped from high up,
## the real Juggernaut is airborne; the move stick pushes it along its heading, the aim stick swings
## the chassis round and pitches it up, and with gameplay.air_control off none of that happens.

var mech: RigidBody3D


func before_each() -> void:
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 400.0, 0)
	tree.root.add_child(mech)


func after_each() -> void:
	for a: String in ["move_forward", "turn_right", "aim_up"]:
		Input.action_release(a)
	mech.free()
	Settings.reset_all_quietly()


func _planar_speed() -> float:
	return Vector2(mech.linear_velocity.x, mech.linear_velocity.z).length()


func test_stick_pushes_in_the_air() -> void:
	await physics_frames(30)
	assert_true(bool(mech.get("airborne")), "falling from 400 m")
	Input.action_press("move_forward", 1.0)
	await physics_frames(120)
	var v := mech.linear_velocity
	assert_gt(-v.z, 4.0, "a second of stick forward pushes it forward (%.1f m/s)" % -v.z)
	assert_lt(_planar_speed(), 14.5, "capped near air.max_m_s")


func test_aim_turns_and_pitches_the_chassis() -> void:
	await physics_frames(30)
	Input.action_press("turn_right", 1.0)
	Input.action_press("aim_up", 1.0)
	await physics_frames(60)
	Input.action_release("turn_right")
	await physics_frames(60)
	var f := -mech.global_transform.basis.z
	var yaw := rad_to_deg(atan2(-f.x, -f.z))
	assert_lt(yaw, -30.0, "swung to the right in the air (yaw %.0f°)" % yaw)
	var pitch := rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
	assert_gt(pitch, 8.0, "nose pitched up to aim (%.0f°)" % pitch)


func test_off_is_a_ballistic_arc() -> void:
	Settings.set_value("gameplay.air_control", false, false)
	await physics_frames(30)
	Input.action_press("move_forward", 1.0)
	Input.action_press("turn_right", 1.0)
	await physics_frames(120)
	assert_lt(_planar_speed(), 0.5, "no push without air control")
	var f := -mech.global_transform.basis.z
	assert_gt(rad_to_deg(atan2(-f.x, -f.z)), -10.0, "and no swing")
