extends "res://tests/lib/test_case.gd"
## Lane A4 part 5 (Emerson's note 3 after 010: aiming modes as settings, analog first). Settings > Gameplay >
## Physics > Aiming: "rate" (the stick moves the aim at a rate, the aim stays) or "angle" (the stick's
## deflection is the angle and letting go springs level). The 57 mm never moves: the body tilts to aim in
## both, within its own range, and only turns as far as the legs can in the air (tests/test_air.gd).

var ground: StaticBody3D
var mech: RigidBody3D


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 2, 400)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)
	await physics_frames(300)


func after_each() -> void:
	Input.action_release("aim_up")
	Input.action_release("aim_down")
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


func test_rate_mode_keeps_climbing_while_held_and_stays_when_let_go() -> void:
	Settings.set_value("gameplay.aim_mode", "rate", false)
	Input.action_press("aim_up", 0.3)
	await physics_frames(120)
	var early: float = mech.get("look_pitch_deg")
	await physics_frames(120)
	var later: float = mech.get("look_pitch_deg")
	assert_gt(later, early + 2.0, "held at a third of the stick the aim keeps rising (%.1f then %.1f deg)" % [early, later])
	Input.action_release("aim_up")
	await physics_frames(120)
	assert_almost_eq(float(mech.get("look_pitch_deg")), later, 0.5, "the aim stays where it was left")


func test_angle_mode_follows_the_deflection_and_springs_back() -> void:
	Settings.set_value("gameplay.aim_mode", "angle", false)
	var look_max := Registry.tune_f("aim.look_max_deg", 75.0)
	var tilt_max := Registry.tune_f("aim.pitch_max_deg", 18.0)
	Input.action_press("aim_up", 0.5)
	await physics_frames(120)
	var half: float = mech.get("look_pitch_deg")
	var deflection: float = mech.get("_aim_deflection")
	assert_between(deflection, 0.1, 0.9, "half a push is a part-deflection after the stick's response curve (%.2f)" % deflection)
	assert_almost_eq(half, look_max * deflection, 1.0, "the angle is the deflection times the range (%.1f of %.0f deg)" % [half, look_max])
	await physics_frames(120)
	assert_almost_eq(float(mech.get("look_pitch_deg")), half, 0.5, "held, it stays put instead of climbing")
	assert_almost_eq(float(mech.get("aim_pitch_deg")), tilt_max * deflection, 1.0, "the body tilts in proportion, inside its own range")
	Input.action_release("aim_up")
	await physics_frames(180)
	assert_lt(absf(float(mech.get("look_pitch_deg"))), 1.0, "let go, it springs back level")
	assert_lt(absf(float(mech.get("aim_pitch_deg"))), 1.0, "and so does the body")


func test_angle_mode_full_stick_reaches_the_top_of_the_range_and_down_the_bottom() -> void:
	Settings.set_value("gameplay.aim_mode", "angle", false)
	Input.action_press("aim_up", 1.0)
	await physics_frames(150)
	assert_almost_eq(float(mech.get("look_pitch_deg")), Registry.tune_f("aim.look_max_deg", 75.0), 1.0, "full up")
	assert_almost_eq(float(mech.get("aim_pitch_deg")), Registry.tune_f("aim.pitch_max_deg", 18.0), 0.5, "the body at its limit")
	Input.action_release("aim_up")
	Input.action_press("aim_down", 1.0)
	await physics_frames(180)
	assert_almost_eq(float(mech.get("look_pitch_deg")), Registry.tune_f("aim.look_min_deg", -25.0), 1.0, "full down")


func test_the_aim_tilt_toggle_still_keeps_the_body_level_in_both_modes() -> void:
	Settings.set_value("gameplay.aim_tilt", false, false)
	for mode: String in ["rate", "angle"]:
		Settings.set_value("gameplay.aim_mode", mode, false)
		Input.action_press("aim_up", 1.0)
		await physics_frames(120)
		assert_lt(absf(float(mech.get("aim_pitch_deg"))), 0.5, "%s: the body stays level with Body tilts to aim off" % mode)
		assert_gt(float(mech.get("look_pitch_deg")), 5.0, "%s: the aim line still moves" % mode)
		Input.action_release("aim_up")
		await physics_frames(200)
