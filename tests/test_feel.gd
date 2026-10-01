extends "res://tests/lib/test_case.gd"
## Lane A4 part 3 (Emerson 2026-10-01: walking and running "feel too much like an animation, not
## physics"). The legs push on the ground, so the drive's moment about the centre of mass is the one
## a push at the feet would make (smoothed by the actuators' lag): the body squats back as it speeds
## up, dips its nose as it slows, and leans out of a turn, all through the leg springs.

var ground: StaticBody3D
var mech: RigidBody3D


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(900, 2, 900)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	mech = MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 3.0, 0)
	tree.root.add_child(mech)


func after_each() -> void:
	for a: String in ["move_forward", "sprint", "turn_right", "turn_left", "brake", "jump"]:
		Input.action_release(a)
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


## Pitch (nose up +) and roll (right side down +) of the body, degrees.
func _attitude() -> Vector2:
	var b := mech.global_transform.basis.orthonormalized()
	var fwd := -b.z
	var right := b.x
	return Vector2(rad_to_deg(asin(clampf(fwd.y, -1.0, 1.0))), rad_to_deg(asin(clampf(-right.y, -1.0, 1.0))))


## [most nose-up while speeding up, most nose-down while stopping, most outward roll in a run
## turn (+ = leaning out of a right turn), worst tilt anywhere].
func _drive_cycle() -> Array:
	await physics_frames(360)
	var level := _attitude()
	var squat := 0.0
	var dive := 0.0
	var lean := 0.0
	var worst := 0.0
	Input.action_press("move_forward", 1.0)
	Input.action_press("sprint")
	for i in 240:
		await physics_frames(1)
		var a := _attitude() - level
		squat = maxf(squat, a.x)
		worst = maxf(worst, maxf(absf(a.x), absf(a.y)))
	Input.action_press("turn_right", 1.0)
	for i in 180:
		await physics_frames(1)
		var a := _attitude() - level
		lean = maxf(lean, -a.y)
		worst = maxf(worst, maxf(absf(a.x), absf(a.y)))
	Input.action_release("turn_right")
	await physics_frames(120)
	Input.action_release("move_forward")
	Input.action_release("sprint")
	for i in 240:
		await physics_frames(1)
		var a := _attitude() - level
		dive = maxf(dive, -a.x)
		worst = maxf(worst, maxf(absf(a.x), absf(a.y)))
	return [squat, dive, lean, worst]


func test_the_body_answers_its_feet() -> void:
	var r := await _drive_cycle()
	print("    feel: squat %.2f deg speeding up, dive %.2f deg stopping, lean %.2f deg out of the turn, worst %.2f deg" % r)
	assert_gt(float(r[0]), 0.8, "a gallop start squats the body back (was 0.00 deg with the push at the centre of mass)")
	assert_gt(float(r[1]), 1.0, "stopping dips the nose")
	assert_gt(float(r[2]), 0.5, "a hard turn leans it out")
	assert_lt(float(r[3]), 6.0, "the legs hold it: it answers, it does not flail")


## The score route's jump turns in the air and lands moving sideways at about 100 km/h with the
## stick still forward: with the drive at the feet from the first tick, the legs' braking tipped
## it 35 deg onto its tail. Now the share fades in after touchdown.
func test_a_fast_sideways_landing_stays_on_its_feet() -> void:
	await physics_frames(240)
	mech.global_position += Vector3.UP * 3.0
	await physics_frames(1)
	mech.linear_velocity = mech.global_transform.basis.x * 25.0
	Input.action_press("move_forward", 1.0)
	Input.action_press("sprint")
	var worst := 0.0
	var landed := -1
	for i in 360:
		await physics_frames(1)
		if landed < 0 and not bool(mech.get("airborne")):
			landed = i
		if landed >= 0:
			worst = maxf(worst, rad_to_deg(mech.global_transform.basis.orthonormalized().y.angle_to(Vector3.UP)))
	assert_gt(landed, 0, "it came down")
	assert_lt(worst, 15.0, "lands sideways at 90 km/h and stays up (worst tilt %.1f deg)" % worst)
	print("    sideways landing at 90 km/h: worst tilt %.1f deg" % worst)


func test_a_hard_slide_keeps_its_feet_down() -> void:
	await physics_frames(360)
	Input.action_press("move_forward", 1.0)
	Input.action_press("sprint")
	await physics_frames(600)
	Input.action_release("move_forward")
	Input.action_release("sprint")
	Input.action_press("brake", 1.0)
	var air_ticks := 0
	for i in 420:
		await physics_frames(1)
		if i == 144:
			Input.action_press("turn_right", 1.0)
		if i == 264:
			Input.action_release("turn_right")
		air_ticks += 1 if bool(mech.get("airborne")) else 0
	assert_eq(air_ticks, 0, "the nose dips under braking but the rear feet stay loaded")


## The score route's jump: a full charge started 2.5 s into a gallop from a standstill (still
## speeding up), let go after 1 s. Returns [the largest pitch rate in the air (deg/s), the most
## the body pitched in the air (deg)].
func _route_jump() -> Array:
	await physics_frames(360)
	Input.action_press("move_forward", 1.0)
	Input.action_press("sprint")
	await physics_frames(300)
	Input.action_press("jump")
	await physics_frames(120)
	Input.action_release("jump")
	var rate := 0.0
	var pitch := 0.0
	for i in 300:
		await physics_frames(1)
		if bool(mech.get("airborne")):
			var b := mech.global_transform.basis.orthonormalized()
			rate = maxf(rate, absf(rad_to_deg((b.inverse() * mech.angular_velocity).x)))
			pitch = maxf(pitch, absf(rad_to_deg(asin(clampf(-b.z.y, -1.0, 1.0)))))
	return [rate, pitch]


func test_a_running_jump_leaves_level() -> void:
	var r := await _route_jump()
	assert_lt(float(r[0]), 5.0, "no pitch spin from the take-off (%.1f deg/s)" % r[0])
	assert_lt(float(r[1]), 5.0, "level in the air (%.1f deg)" % r[1])
