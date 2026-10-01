extends "res://tests/lib/test_case.gd"
## Lane A4 part 5 (Emerson's note 8 after 010: "the legs cross over and pass through each other"). The
## Juggernaut's four legs must keep clear of each other whatever it does. The gap measured here is the
## closest approach between the leg bones (hip to knee to ankle, in the body frame) of any two legs.
## The leg meshes reach at most 0.21 m from their bone (measured on the model: thigh p90 0.18, shin 0.13),
## so two bones 0.5 m apart leave about 8 cm of daylight; touching bones are 0.42 m apart.
## Before: a gallop put the same-side legs' bones 0.000-0.002 m apart (also in version 009, 57eb7f2) and a
## front flip 0.009 m. The cause was the feet only ever being placed by their own leg: a front foot gathered
## back and a rear foot gathered forward passed each other (standin_mech.gd _keep_apart), and in a tuck or
## yawed air swing two knees folded into the same spot (_knee_swivel).

const CLEAR_M := 0.5

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
	for a: String in ["move_forward", "move_back", "jump", "strafe_right", "strafe_left", "turn_right", "turn_left", "sprint", "crouch"]:
		Input.action_release(a)
	mech.free()
	ground.free()
	Settings.reset_all_quietly()


## The closest any two legs' bones are this tick: [distance, "fr-rr"].
func leg_gap() -> Array:
	var legs: Array = mech.get("legs")
	var best: Array = [INF, ""]
	for i in legs.size():
		for j in range(i + 1, legs.size()):
			var a: Dictionary = legs[i]
			var b: Dictionary = legs[j]
			var bones_a: Array = [[a["pivot"], a["knee_local"]], [a["knee_local"], a["ankle_local"]]]
			var bones_b: Array = [[b["pivot"], b["knee_local"]], [b["knee_local"], b["ankle_local"]]]
			for sa: Array in bones_a:
				for sb: Array in bones_b:
					var d := LegIK.segment_distance(sa[0], sa[1], sb[0], sb[1])
					if d < best[0]:
						best = [d, "%s-%s" % [a["name"], b["name"]]]
	return best


## Runs `steps` ([[at second, action, strength or -1 to release]]) for `seconds` after the mech has settled;
## returns the closest the legs came.
func run_scenario(label: String, steps: Array, seconds: float) -> float:
	await physics_frames(360)
	var worst: Array = [INF, ""]
	var worst_t := 0.0
	var top := 0.0
	var next := 0
	var frames := int(seconds * 120.0)
	for i in frames:
		while next < steps.size() and float(steps[next][0]) * 120.0 <= i:
			var s: Array = steps[next]
			if float(s[2]) < 0.0:
				Input.action_release(str(s[1]))
			else:
				Input.action_press(str(s[1]), float(s[2]))
			next += 1
		await physics_frames(1)
		top = maxf(top, mech.linear_velocity.length())
		var g := leg_gap()
		if g[0] < worst[0]:
			worst = g
			worst_t = i / 120.0
	print("    %-28s closest %.3f m (%s at %.1f s), top %.1f m/s" % [label, worst[0], worst[1], worst_t, top])
	return worst[0]


func _hold(actions: Dictionary) -> Array:
	var steps: Array = []
	for a: String in actions:
		steps.append([0.0, a, actions[a]])
	return steps


func test_standing_and_walking() -> void:
	assert_gt(await run_scenario("stand", [], 1.0), CLEAR_M, "standing")
	assert_gt(await run_scenario("walk", _hold({"move_forward": 1.0}), 5.0), CLEAR_M, "walking")


func test_gallop_forward() -> void:
	assert_gt(await run_scenario("gallop", _hold({"move_forward": 1.0, "sprint": 1.0}), 8.0), CLEAR_M, "a straight gallop")


func test_gallop_turning() -> void:
	var easy := await run_scenario("gallop + turn 0.22", _hold({"move_forward": 1.0, "sprint": 1.0, "turn_left": 0.22}), 10.0)
	assert_gt(easy, CLEAR_M, "a gallop in a wide curve (the b4_grime route that ended on its back)")


func test_gallop_hard_turn() -> void:
	assert_gt(await run_scenario("gallop + turn 1.0", _hold({"move_forward": 1.0, "sprint": 1.0, "turn_left": 1.0}), 8.0), CLEAR_M, "a gallop turning flat out")


func test_gallop_slalom() -> void:
	var steps: Array = _hold({"move_forward": 1.0, "sprint": 1.0})
	for k in 8:
		steps.append([1.0 + k * 1.2, "turn_left" if k % 2 == 0 else "turn_right", 1.0])
		steps.append([1.0 + k * 1.2 + 0.6, "turn_left" if k % 2 == 0 else "turn_right", -1.0])
	assert_gt(await run_scenario("gallop slalom", steps, 11.0), CLEAR_M, "swerving left and right at a gallop")


func test_gallop_sideways_and_back() -> void:
	assert_gt(await run_scenario("gallop sideways", _hold({"strafe_right": 1.0, "sprint": 1.0}), 6.0), CLEAR_M, "sideways")
	assert_gt(await run_scenario("gallop backwards", _hold({"move_back": 1.0, "sprint": 1.0}), 6.0), CLEAR_M, "backwards")


func test_stop_and_start() -> void:
	var steps: Array = [[0.0, "move_forward", 1.0], [0.0, "sprint", 1.0], [3.0, "move_forward", -1.0], [3.0, "sprint", -1.0], [5.0, "move_back", 1.0], [5.0, "sprint", 1.0], [7.0, "move_back", -1.0], [7.0, "sprint", -1.0], [8.0, "move_forward", 1.0]]
	assert_gt(await run_scenario("stop and start", steps, 10.0), CLEAR_M, "braking and reversing")


func test_turn_on_the_spot() -> void:
	assert_gt(await run_scenario("turn on the spot", _hold({"turn_right": 1.0}), 5.0), CLEAR_M, "turning with no speed")


## A charged jump: crouch tucks in the air; `stick` is held from the launch, `flip` holds crouch for the flip.
func jump_scenario(label: String, stick: String, flip: bool, run: bool = false) -> float:
	await physics_frames(360)
	if run:
		Input.action_press("move_forward", 1.0)
		Input.action_press("sprint", 1.0)
		await physics_frames(240)
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
	var worst: Array = [INF, ""]
	var left := false
	for i in 900:
		await physics_frames(1)
		var g := leg_gap()
		if g[0] < worst[0]:
			worst = g
		if bool(mech.get("airborne")):
			left = true
		elif left and int(mech.get("grounded_legs")) >= 3 and i > 60:
			break
	print("    %-28s closest %.3f m (%s)" % [label, worst[0], worst[1]])
	return worst[0]


func test_jump_and_landing() -> void:
	assert_gt(await jump_scenario("standing jump", "", false), CLEAR_M, "a charged jump and the landing")


func test_running_jump() -> void:
	assert_gt(await jump_scenario("running jump", "", false, true), CLEAR_M, "a jump from a gallop")


func test_flips() -> void:
	assert_gt(await jump_scenario("front flip", "move_forward", true), CLEAR_M, "a front flip's tuck (the legs' yawed swing put two knees together)")


func test_back_and_side_flips() -> void:
	assert_gt(await jump_scenario("backflip", "move_back", true), CLEAR_M, "backflip")
	assert_gt(await jump_scenario("side flip", "strafe_right", true), CLEAR_M, "side flip")


func test_the_swivel_is_off_when_nothing_is_close() -> void:
	await physics_frames(360)
	for leg: Dictionary in mech.get("legs"):
		assert_almost_eq(float(leg.get("swivel", 0.0)), 0.0, 0.001, "%s stands with its knee unswivelled" % leg["name"])


func test_segment_distance() -> void:
	assert_almost_eq(LegIK.segment_distance(Vector3.ZERO, Vector3(1, 0, 0), Vector3(0, 1, 0), Vector3(1, 1, 0)), 1.0, 0.0001, "parallel segments")
	assert_almost_eq(LegIK.segment_distance(Vector3.ZERO, Vector3(2, 0, 0), Vector3(1, -1, 1), Vector3(1, 1, 1)), 1.0, 0.0001, "crossing segments a metre apart")
	assert_almost_eq(LegIK.segment_distance(Vector3.ZERO, Vector3(1, 0, 0), Vector3(3, 0, 0), Vector3(4, 0, 0)), 2.0, 0.0001, "end to end")
	assert_almost_eq(LegIK.segment_distance(Vector3.ZERO, Vector3(1, 0, 0), Vector3(1, 1, 0), Vector3(1, 2, 0)), 1.0, 0.0001, "end to a perpendicular end")
