extends "res://tests/lib/test_case.gd"
## Mass from parts, per-part colliders, the leg solver and the charge jump maths.


func test_mass_sum_centre_and_inertia() -> void:
	var two := MechMass.sum([
		{"mass": 100.0, "position": Vector3(-1, 0, 0), "size": Vector3(1, 1, 1)},
		{"mass": 100.0, "position": Vector3(1, 0, 0), "size": Vector3(1, 1, 1)},
	])
	assert_eq(two["mass"], 200.0)
	assert_almost_eq(two["com"], Vector3.ZERO, 0.0001)
	var box := MechMass.box_inertia(100.0, Vector3(1, 1, 1))
	assert_almost_eq(box.x, 100.0 / 6.0, 0.0001)
	var inertia: Vector3 = two["inertia"]
	assert_almost_eq(inertia.x, 2.0 * box.x, 0.0001, "no offset along x")
	assert_almost_eq(inertia.y, 2.0 * (box.y + 100.0), 0.0001, "parallel axis 1 m")


func test_standin_mass_is_the_sum_of_its_parts() -> void:
	var def := Registry.entry("mechs", "standin")
	var expected := 0.0
	for p: Dictionary in def["parts"]:
		expected += float(Registry.entry("parts", str(p["part"]))["mass_kg"])
	for leg_name: String in def["legs"]:
		var leg: Dictionary = def["legs"][leg_name]
		for seg: String in ["upper", "lower", "foot"]:
			expected += float(Registry.entry("parts", str(leg[seg]))["mass_kg"])
		for act: String in leg["actuators"]:
			expected += float(Registry.entry("parts", act)["mass_kg"])
	var body := MechBuilder.build("standin")
	assert_not_null(body)
	assert_almost_eq(body.mass, expected, 0.01)
	assert_between(body.mass, 9000.0, 13000.0, "about ten tonnes")
	assert_almost_eq(body.center_of_mass.x, 0.0, 0.001, "left-right symmetric")
	assert_gt(body.inertia.y, 1000.0)
	body.free()


func test_every_part_has_its_own_collider() -> void:
	var body := MechBuilder.build("standin")
	var body_shapes := body.get_children().filter(func(n: Node) -> bool: return n is CollisionShape3D)
	assert_eq(body_shapes.size(), Registry.entry("mechs", "standin")["parts"].size(), "one per chassis part")
	for cs: CollisionShape3D in body_shapes:
		assert_true(cs.has_meta("part_id"))
		assert_false(cs.shape is CapsuleShape3D, "no capsules")
	var hitboxes := body.get_node("LegHitboxes")
	assert_eq(hitboxes.get_child_count(), 12, "upper, lower and foot on four legs")
	assert_eq((hitboxes as Area3D).collision_layer, MechBuilder.LAYER_HITBOX)
	body.free()


func test_planned_mechs_are_not_built() -> void:
	assert_false(MechBuilder.can_build("juggernaut_m2"), "waits for B1's export and A2's controller")
	assert_true(MechBuilder.can_build("standin"))


func test_leg_ik_keeps_lengths_and_bends_to_pole() -> void:
	var hip := Vector3(-1.2, -0.35, -1.4)
	var foot := Vector3(-2.3, -2.3, -1.6)
	var knee := LegIK.knee(hip, foot, 1.7, 2.1, Vector3(-1, 1.4, 0))
	assert_almost_eq(hip.distance_to(knee), 1.7, 0.001)
	assert_almost_eq(knee.distance_to(foot), 2.1, 0.001)
	assert_gt(knee.y, hip.y - 0.5, "knee rides high like a spider's")
	var far := LegIK.reachable(hip, hip + Vector3(0, -10, 0), 1.7, 2.1)
	assert_almost_eq(hip.distance_to(far), 3.798, 0.01)


func test_charge_jump_curve() -> void:
	var p: Dictionary = Registry.tune("standin.jump", {})
	assert_eq(JumpCharge.game_speed(0.05, p), 0.0, "a tap does not jump")
	assert_almost_eq(JumpCharge.game_speed(float(p["min_hold_s"]), p), float(p["min_launch_m_s"]), 0.001)
	assert_almost_eq(JumpCharge.game_speed(5.0, p), float(p["max_launch_m_s"]), 0.001, "caps at full charge")
	var body := MechBuilder.build("standin")
	var acts: Array = body.get("actuators")
	var bench := JumpCharge.bench_speed(5.0, body.mass, acts, 3.8, p, Registry.tune("jump_bench", {}))
	assert_gt(bench, 0.0)
	assert_lt(bench, JumpCharge.game_speed(5.0, p) * 0.5, "real actuators jump far lower than magic motors")
	body.free()
