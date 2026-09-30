extends "res://tests/lib/test_case.gd"
## The stand-in on real Jolt physics, headless: it stands, walks, charge-jumps with no air control,
## lands, and does not fall through the test range's terrain. tools/run_tests.sh passes
## --fixed-fps 120, so 120 physics frames are exactly 1 s of game time at the game's own step.

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
	mech = MechBuilder.build("standin")
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)


func after_each() -> void:
	for a: String in ["move_forward", "jump", "strafe_right", "brake", "turn_right"]:
		Input.action_release(a)
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


func test_stands_at_ride_height() -> void:
	await physics_frames(360)
	var t: Dictionary = mech.call("telemetry")
	assert_eq(t["grounded_legs"], 4)
	assert_between(mech.global_position.y, 2.0, 2.6, "chassis centre near stance height 2.3 m")
	assert_lt(mech.linear_velocity.length(), 0.3, "settled")
	assert_lt(absf(t["roll_deg"]), 2.0)


func test_walks_forward() -> void:
	await physics_frames(240)
	var start := mech.global_position
	Input.action_press("move_forward", 1.0)
	await physics_frames(360)
	var moved := mech.global_position - start
	assert_lt(moved.z, -8.0, "walked forward (-z) at least 8 m in 3 s")
	assert_lt(absf(moved.x), 1.5, "kept straight")


func test_charge_jump_then_no_air_control() -> void:
	Settings.set_value("gameplay.air_control", false, false)  # the supplement's pure ballistic jump
	await physics_frames(240)
	Input.action_press("jump")
	await physics_frames(144)
	assert_true(bool(mech.get("charging")))
	assert_gt(float(mech.get("crouch")), 0.5, "crouches while charging")
	Input.action_release("jump")
	await physics_frames(12)
	assert_true(bool(mech.get("airborne")), "left the ground")
	var vx_before := mech.linear_velocity.x
	Input.action_press("strafe_right", 1.0)
	var peak := 0.0
	for i in 60:
		await tree.physics_frame
		peak = maxf(peak, mech.global_position.y)
	assert_almost_eq(mech.linear_velocity.x, vx_before, 0.2, "no mid-air steering")
	assert_gt(peak, 5.0, "a full charge clears a few metres")
	Input.action_release("strafe_right")
	await physics_frames(480)
	assert_eq(int(mech.call("telemetry")["grounded_legs"]), 4, "landed on its feet")


func test_bench_mode_is_slow() -> void:
	Settings.set_value("gameplay.physics_mode", "bench", false)
	await physics_frames(240)
	var start := mech.global_position
	Input.action_press("move_forward", 1.0)
	await physics_frames(360)
	var moved := _flat(mech.global_position - start)
	var cap := float(mech.get("_bench_speed_cap"))
	assert_between(cap, 0.3, 2.0, "bench speed cap comes from the actuators")
	assert_lt(moved, cap * 3.0 + 0.2, "real actuators walk at a crawl")
	assert_gt(moved, 0.5, "but they do walk")


func test_test_range_holds_the_mech_up() -> void:
	mech.free()
	ground.free()
	var level: Node3D = (load("res://scenes/levels/test_range.tscn") as PackedScene).instantiate()
	tree.root.add_child(level)
	mech = level.get("mech")
	Input.action_press("move_forward", 1.0)
	await physics_frames(720)
	var p := mech.global_position
	var floor_y := float(level.call("ground_height", p.x, p.z))
	assert_gt(p.y, floor_y + 0.8, "above the terrain after 6 s of walking")
	assert_false(is_nan(p.y))
	Input.action_release("move_forward")
	level.free()
	mech = MechBuilder.build("standin")
	ground = StaticBody3D.new()
	tree.root.add_child(ground)
	tree.root.add_child(mech)
	Game.level = null


func _flat(v: Vector3) -> float:
	return Vector2(v.x, v.z).length()
