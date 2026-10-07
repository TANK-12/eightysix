extends "res://tests/lib/test_case.gd"
## The stand-up control (Emerson 2026-10-07: "add a way to flip the mech back upright when it ends up
## on its side or back"). The right_mech action (U), or jump while tipped, lifts the chassis and rolls
## it back level; upright it does nothing, and a tipped mech's jump button no longer charges a jump.

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
func _tip(roll_deg: float) -> float:
	Settings.set_value("gameplay.upright_assist", false)
	mech.position = Vector3(0, 3.0, 0)
	mech.rotation = Vector3(0, 0, deg_to_rad(roll_deg))
	tree.root.add_child(mech)
	await physics_frames(240)
	return _lean_deg()


## Presses `action` for a few ticks, then waits up to 4 s for it to stand; returns seconds taken (or -1).
func _press_and_wait(action: String) -> float:
	Input.action_press(action)
	await physics_frames(3)
	Input.action_release(action)
	for i in 480:
		await physics_frames(1)
		if _lean_deg() < 20.0 and int(mech.get("righting_s") * 1000) == 0:
			return (i + 3) / 120.0
	return -1.0


func test_u_stands_it_up_when_rolled_over_past_its_side() -> void:
	var lean := await _tip(115.0)
	assert_gt(lean, 55.0, "it lies rolled over first (%.0f deg)" % lean)
	var took := await _press_and_wait("right_mech")
	assert_between(took, 0.0, 3.0, "back on its feet in %.2f s" % took)
	await physics_frames(240)
	assert_lt(_lean_deg(), 20.0, "and it stays up (%.0f deg)" % _lean_deg())
	print("    rolled 115: lean %.0f deg, stood up in %.2f s, %.0f deg 2 s later" % [lean, took, _lean_deg()])


func test_u_stands_it_up_from_its_back() -> void:
	var lean := await _tip(180.0)
	assert_gt(lean, 120.0, "it lies on its back first (%.0f deg)" % lean)
	var took := await _press_and_wait("right_mech")
	assert_between(took, 0.0, 3.0, "back on its feet in %.2f s" % took)
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
