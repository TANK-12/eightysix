extends "res://tests/test_bench.gd"

func test_scratch() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 2, 400)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	mech = MechBuilder.build("standin")
	tree.root.add_child(mech)
	Settings.set_value("gameplay.physics_mode", "bench", false)
	await _frames(240)
	Input.action_press("move_forward", 1.0)
	for i in 6:
		await _frames(60)
		var d = _driver()
		print("    t %d: pos %s down %s lim %s forcecap %s drivecap %s pw %s" % [i, mech.global_position, str(d.rig.down()), str(d.rig.limit_nm(d.leg_joints["fl"].values()[0] if not d.leg_joints["fl"].is_empty() else "", 0.0)), str(d.call("leg_force_cap", mech.get("legs")[0])), str(d.call("drive_force_cap", Vector3(0,0,-1))), str(d.call("drive_power_w"))])
	print(d_dump())

func d_dump() -> String:
	var d = _driver()
	var out := ""
	for id in d.rig.joints:
		var j = d.rig.joints[id]
		out += "%s %s T%.0f dem%.0f lim%.0f om%.3f|" % [id, j["status"], j["torque_nm"], j["demand_nm"], j["limit_nm"], j["omega"]]
	return out + " speedf " + str(d.call("speed_factor")) + " minswing " + str(d.call("min_swing_s", 0.9, 3.0))
