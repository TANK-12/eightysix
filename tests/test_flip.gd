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


## Lets a launched flip fly to the ground with no input; returns [turns about the spin axis while
## airborne, the lowest any foot or shin went below the ground (m, positive = under) until it
## stands again, seconds airborne].
func _fly_out(axis: int) -> Array:
	var turned := 0.0
	var under := 0.0
	var t := 0.0
	var left_ground := false
	var falling := false
	var landed := false
	for i in 900:
		await physics_frames(1)
		var b := mech.global_transform.basis.orthonormalized()
		var w := b.inverse() * mech.angular_velocity
		# In flight until the first touchdown stops the fall (a part-turn lands it on its side,
		# where it counts as airborne while it is righted).
		var vy := mech.linear_velocity.y
		falling = falling or vy < -2.0
		landed = landed or (falling and vy > -0.5)
		if bool(mech.get("airborne")) and not landed:
			turned += absf(w[axis]) / 120.0
			t += 1.0 / 120.0
		for leg: Dictionary in mech.get("legs"):
			for key: String in ["foot_mesh", "lower_mesh"]:
				var m := leg.get(key) as Node3D
				if m != null:
					under = maxf(under, -(m.global_position.y))
		if bool(mech.get("airborne")):
			left_ground = true
		elif left_ground and int(mech.get("grounded_legs")) >= 3:
			break
	return [turned / TAU, under, t]


## Emerson 2026-10-01: "side flip way way too fast, and still sometimes the feet clip". The same
## lean made 1.9 turns forwards, 2.3 backwards and 7.7 sideways (roll inertia is a fraction of
## pitch inertia), and the over-spun landings put feet 0.2-0.4 m into the ground. Now the flight
## computer aims the push for gameplay.flip_turns over the predicted flight, every way.
func _flip_turns(dir: String, axis: int, stick: float = 1.0) -> Array:
	var w := Vector3.ZERO
	if stick < 1.0:
		await physics_frames(360)
		Input.action_press("jump")
		await physics_frames(110)
		Input.action_press(dir, stick)
		Input.action_press("crouch")
		await physics_frames(40)
		Input.action_release("jump")
		await physics_frames(2)
		Input.action_release("crouch")
		Input.action_release(dir)
		await physics_frames(10)
	else:
		w = await _launch(dir, true)
		Input.action_release(dir)
	var r := await _fly_out(axis)
	print("    %s at %.0f%% stick: %.2f turns in %.2f s, deepest foot %.2f m under" % [dir, stick * 100.0, r[0], r[2], r[1]])
	return r


func test_front_flip_turns_once_and_lands_on_its_feet() -> void:
	var r := await _flip_turns("move_forward", 0)
	assert_between(float(r[0]), 0.8, 1.2, "about one turn (%.2f)" % r[0])
	assert_lt(float(r[1]), 0.05, "no foot in the ground (%.2f m)" % r[1])


func test_backflip_turns_once_and_lands_on_its_feet() -> void:
	var r := await _flip_turns("move_back", 0)
	assert_between(float(r[0]), 0.8, 1.2, "about one turn (%.2f)" % r[0])
	assert_lt(float(r[1]), 0.05, "no foot in the ground (%.2f m)" % r[1])


func test_side_flip_turns_once_not_seven_times() -> void:
	var r := await _flip_turns("strafe_left", 2)
	assert_between(float(r[0]), 0.8, 1.2, "about one roll (%.2f; was 7.7)" % r[0])
	assert_lt(float(r[1]), 0.05, "no foot in the ground (%.2f m)" % r[1])


func test_half_stick_half_a_flip() -> void:
	var r := await _flip_turns("strafe_left", 2, 0.5)
	assert_between(float(r[0]), 0.35, 0.7, "about half a roll (%.2f)" % r[0])


## Relay 38 (Emerson after 015, "when we roll over sideways or vertically it messes it up and we get clipping"):
## half a roll or half a flip lands it on its side or its back. Lying there it must not sink into the ground,
## no leg may pass under it, and it must not shake: back-and-forth changes of spin add up to under 1 rad/s
## over a second.
func _lands_and_lies_still(dir: String, axis: int) -> void:
	var r := await _flip_turns(dir, axis, 0.5)
	assert_lt(float(r[1]), 0.05, "no foot or shin in the ground in flight or landing (%.2f m)" % r[1])
	var jitter := 0.0
	var last := mech.angular_velocity
	var step := Vector3.ZERO
	var under := 0.0
	for i in 120:
		await physics_frames(1)
		# Shaking is the spin's change reversing tick to tick; tipping on over from its side onto its back
		# speeds the spin up smoothly and is not counted.
		var d := mech.angular_velocity - last
		if d.dot(step) < 0.0:
			jitter += minf(d.length(), step.length())
		step = d
		last = mech.angular_velocity
		for leg: Dictionary in mech.get("legs"):
			for key: String in ["foot_mesh", "lower_mesh"]:
				var m := leg.get(key) as Node3D
				if m != null:
					under = maxf(under, -(m.global_position.y))
	print("    %s half: up %.2f, hull at %.2f m, jitter %.2f rad/s per s, deepest leg %.2f m" % [dir, mech.global_transform.basis.y.y, mech.global_position.y, jitter, under])
	assert_gt(mech.global_position.y, 0.3, "the hull rests on the ground, not in it")
	assert_lt(jitter, 1.0, "it lies still (%.2f rad/s per s)" % jitter)
	assert_lt(under, 0.05, "no leg in the ground while it lies there (%.2f m)" % under)


func test_half_roll_sideways_lands_on_its_side_and_lies_still() -> void:
	await _lands_and_lies_still("strafe_left", 2)


func test_half_flip_end_over_end_lands_and_lies_still() -> void:
	await _lands_and_lies_still("move_forward", 0)
