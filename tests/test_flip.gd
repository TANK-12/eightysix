extends "res://tests/lib/test_case.gd"
## Lane A4 (Emerson 2026-10-01, "let me flip in mid air"): flips from real physics only. Holding
## crouch as a charged jump is let go leans the same launch impulse onto the feet on one side, so it
## passes off the centre of mass and the body takes off spinning: stick forward = front flip (nose
## down), back = backflip. Without crouch the launch carries no spin. In the air, holding crouch
## tucks the legs: the inertia drops and the spin rises with the angular momentum conserved.

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
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)


func after_each() -> void:
	for a: String in ["jump", "crouch", "move_forward", "move_back"]:
		Input.action_release(a)
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


## Charges a full jump, then lets go with `stick` held (and crouch if `flip`); returns the body-frame
## angular velocity a few ticks after take-off.
func _launch(stick: String, flip: bool) -> Vector3:
	await physics_frames(360)
	Input.action_press("jump")
	await physics_frames(110)
	if stick != "":
		Input.action_press(stick, 1.0)
	if flip:
		Input.action_press("crouch")
	await physics_frames(40)
	Input.action_release("jump")
	await physics_frames(2)
	Input.action_release("crouch")
	await physics_frames(10)
	return mech.global_transform.basis.orthonormalized().inverse() * mech.angular_velocity


func test_front_flip_spins_nose_down() -> void:
	# At half lean the nose still rises at take-off; at full lean it spins fast enough that the
	# front of the body drops into the dirt before the feet are clear (real, and costs some spin).
	Settings.set_value("gameplay.flip_lean", 0.5)
	var w := await _launch("move_forward", true)
	assert_true(bool(mech.get("airborne")), "it left the ground")
	var off: Vector3 = mech.get("last_flip_offset")
	assert_gt(off.length(), 0.5, "the push moved off the centre of mass (%.2f m)" % off.length())
	assert_gt(off.dot(mech.global_transform.basis.z), 0.0, "behind it, onto the rear feet")
	assert_lt(w.x, -1.5, "pitching nose down fast enough to flip (%.2f rad/s)" % w.x)
	print("    front flip: offset %.2f m, spin %.2f rad/s" % [off.length(), w.x])
	# The spin is the launch impulse's moment about the centre of mass over the pitch inertia.
	var launch := float(mech.get("last_launch_speed")) * mech.mass
	var expect := launch * off.length() / mech.inertia.x
	assert_between(-w.x, expect * 0.8, expect * 1.2, "r x J / I = %.2f rad/s" % expect)


func test_backflip_spins_nose_up() -> void:
	Settings.set_value("gameplay.flip_lean", 1.0)
	var w := await _launch("move_back", true)
	assert_gt(w.x, 1.5, "pitching nose up (%.2f rad/s)" % w.x)


func test_no_crouch_no_spin() -> void:
	var w := await _launch("move_forward", false)
	assert_true(bool(mech.get("airborne")))
	assert_eq(mech.get("last_flip_offset"), Vector3.ZERO)
	assert_lt(absf(w.x), 0.6, "a plain running jump stays level (%.2f rad/s)" % w.x)


func test_tucking_spins_faster_and_keeps_angular_momentum() -> void:
	Settings.set_value("gameplay.flip_lean", 1.0)
	await _launch("move_forward", true)
	var b := mech.global_transform.basis.orthonormalized()
	var w0 := b.inverse() * mech.angular_velocity
	var l0 := w0.x * mech.inertia.x
	Input.action_press("crouch")
	await physics_frames(30)
	b = mech.global_transform.basis.orthonormalized()
	var w1 := b.inverse() * mech.angular_velocity
	assert_gt(float(mech.get("flip_tuck")), 0.99, "legs fully tucked")
	assert_gt(absf(w1.x), absf(w0.x) * 1.05, "spin rose from %.2f to %.2f rad/s" % [w0.x, w1.x])
	assert_almost_eq(w1.x * mech.inertia.x, l0, absf(l0) * 0.05, "pitch angular momentum kept")
	Input.action_release("crouch")
	await physics_frames(30)
	b = mech.global_transform.basis.orthonormalized()
	var w2 := b.inverse() * mech.angular_velocity
	assert_lt(absf(w2.x), absf(w1.x), "opening up slows it again")
