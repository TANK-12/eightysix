extends "res://tests/lib/test_case.gd"
## Lane A3's per-part damage on the real Juggernaut: armour decides ricochet or full damage, a lost
## armour panel comes off (hidden, flung, no longer colliding), a round finds a leg through its
## hitbox, a hurt leg limps, the cockpit or two legs destroy the mech, and with permanent damage
## off parts repair. tools/run_tests.sh runs at --fixed-fps 120 (120 physics frames = 1 s).

var ground: StaticBody3D
var mech: RigidBody3D
var combat: MechCombat


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
	combat = mech.get_node("Combat") as MechCombat


func after_each() -> void:
	for a: String in ["move_forward", "sprint"]:
		Input.action_release(a)
	mech.free()
	ground.free()
	for n: Node in tree.root.get_children():
		if n.name.begins_with("Round") or n is RigidBody3D:
			n.free()
	Settings.reset_all_quietly()


func test_armour_decides_ricochet_or_full_damage() -> void:
	var d := combat.damage
	var r := d.hit("leg_fr_upper", 1000.0, 5.0)
	assert_false(bool(r["penetrated"]), "5 mm cannot get through 12 mm")
	assert_almost_eq(float(r["dealt"]), 150.0, 0.01, "a ricochet does ricochet_fraction")
	r = d.hit("leg_fr_upper", 1000.0, 180.0)
	assert_true(bool(r["penetrated"]))
	assert_almost_eq(float(r["dealt"]), 1000.0, 0.01)
	assert_almost_eq(d.leg_health("fr"), 650.0 / 1800.0, 0.001, "a leg is its weakest segment")
	assert_almost_eq(d.leg_health("fl"), 1.0, 0.001)


func test_lost_armour_comes_off() -> void:
	await physics_frames(10)
	var key := "jg2_sidepanel_l"
	assert_true(combat.damage.detachable(key))
	var meshes: Array = combat._meshes.get(key, [])
	assert_gt(meshes.size(), 0, "the real panel mesh was found")
	var r := combat.take_hit({"key": key, "damage": 1200.0, "penetration_mm": 180.0, "point": mech.global_position, "dir": Vector3.FORWARD, "speed": 0.0})
	assert_true(bool(r["lost"]))
	await physics_frames(2)
	for mi: MeshInstance3D in meshes:
		assert_false(mi.visible, "the panel is gone from the mech")
	for cs: CollisionShape3D in combat._colliders[key]:
		assert_true(cs.disabled, "and no longer collides, so the next round reaches the internals")
	assert_gt(tree.root.find_children("Debris*", "RigidBody3D", false, false).size(), 0, "a flung copy of the panel")
	assert_false(combat.damage.is_destroyed)


func test_a_round_finds_the_leg_through_its_hitbox() -> void:
	await physics_frames(240)
	var leg: Dictionary = (mech.get("legs") as Array)[0]
	var hb := leg["lower_hitbox"] as CollisionShape3D
	var aim := hb.global_position
	var from := aim + Vector3(30.0, 0.3, 0.0) * signf((mech.to_local(aim)).x if absf(mech.to_local(aim).x) > 0.01 else 1.0)
	var round_def: Dictionary = (Registry.entry("weapons", "gun_57mm")["ammo"] as Dictionary)["apfsds"].duplicate()
	round_def["id"] = "apfsds"
	var skip: Array[RID] = []
	Projectile.spawn(tree.root, from, (aim - from).normalized() * 1550.0, round_def, null, 1.0, skip)
	var got: Array = []
	combat.hit_taken.connect(func(key: String, dealt: float, _i: Dictionary) -> void: got.append([key, dealt]))
	await physics_frames(10)
	assert_eq(got.size(), 1, "one hit")
	if got.size() == 1:
		assert_true(str(got[0][0]).begins_with("leg_%s_" % leg["name"]), "landed on leg %s, got %s" % [leg["name"], got[0][0]])
		assert_gt(float(got[0][1]), 800.0, "the dart penetrated")


func test_hurt_leg_limps_and_slows() -> void:
	await physics_frames(240)
	Settings.set_value("controls.sprint_mode", "hold", false)
	Input.action_press("move_forward", 1.0)
	Input.action_press("sprint", 1.0)
	await physics_frames(480)
	var healthy := Vector2(mech.linear_velocity.x, mech.linear_velocity.z).length()
	combat.damage.hit("leg_fl_lower", 1500.0 * 0.8, 999.0)
	assert_almost_eq(combat.limp_factor(), 0.2, 0.001)
	await physics_frames(360)
	var limping := Vector2(mech.linear_velocity.x, mech.linear_velocity.z).length()
	assert_gt(healthy, 5.0, "was running")
	assert_lt(limping, healthy * 0.75, "a leg at 20% slows the run (%.1f -> %.1f m/s)" % [healthy, limping])
	assert_gt(int(mech.get("grounded_legs")), 1, "still on its feet")


func test_cockpit_or_two_legs_destroy() -> void:
	var died: Array = []
	combat.destroyed.connect(func() -> void: died.append(true))
	combat.damage.hit("leg_fr_foot", 5000.0, 999.0)
	assert_false(combat.damage.is_destroyed, "one leg gone is not dead")
	combat.damage.hit("leg_rl_upper", 5000.0, 999.0)
	assert_true(combat.damage.is_destroyed, "two legs gone is")
	assert_eq(died.size(), 1)
	assert_false(combat.fire_main(), "a destroyed mech cannot fire")
	var d2 := DamageModel.new(Registry.entry("mechs", "juggernaut_m2"), Registry.tune("damage", {}))
	d2.hit("jg2_canopy", 5000.0, 999.0)
	assert_true(d2.is_destroyed, "the cockpit")


func test_repairs_when_damage_is_not_permanent() -> void:
	var d := DamageModel.new(Registry.entry("mechs", "juggernaut_m2"), Registry.tune("damage", {}))
	d.hit("jg2_sidepanel_r", 5000.0, 999.0)
	assert_true(d.is_lost("jg2_sidepanel_r"))
	var perm := DamageModel.new(Registry.entry("mechs", "juggernaut_m2"), Registry.tune("damage", {}))
	perm.hit("jg2_sidepanel_r", 5000.0, 999.0)
	var back: Array = []
	d.part_restored.connect(func(k: String) -> void: back.append(k))
	for i in 40 * 10:
		d.tick(0.1, false)
		perm.tick(0.1, true)
	assert_eq(back, ["jg2_sidepanel_r"], "the panel came back")
	assert_almost_eq(d.fraction("jg2_sidepanel_r"), 1.0, 0.001)
	assert_true(perm.is_lost("jg2_sidepanel_r"), "permanent damage stays")


func test_mech_meshes_sit_on_the_mech_layer() -> void:
	await physics_frames(2)
	var meshes := mech.find_children("*", "MeshInstance3D", true, false)
	assert_gt(meshes.size(), 0)
	for mi: MeshInstance3D in meshes:
		if mi.get_parent() == combat:
			continue
		assert_eq(mi.layers, CombatFx.MECH_LAYER, "%s is on the mech layer, so ground gouges skip it" % mi.name)
	var ground_mark := CombatFx.decal(tree.root, Vector3.ZERO, Vector3.UP, 0.7, true)
	assert_eq(ground_mark.cull_mask & CombatFx.MECH_LAYER, 0, "a ground gouge does not paint the mech")
	ground_mark.free()


func test_skid_fx_hidden_when_not_skidding() -> void:
	await physics_frames(200)
	for n: Node in combat.get_children():
		if n is CPUParticles3D:
			assert_false((n as CPUParticles3D).visible, "%s hidden at rest (idle particles draw black)" % n.name)
	for i in 10:
		mech.set("skidding", true)
		mech.linear_velocity = Vector3(0, 0, -10)
		await physics_frames(1)
	var shown := 0
	for n: Node in combat.get_children():
		if n is CPUParticles3D and (n as CPUParticles3D).visible:
			shown += 1
	assert_gt(shown, 0, "shown while skidding")
