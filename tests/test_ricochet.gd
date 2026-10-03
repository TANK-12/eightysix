extends "res://tests/lib/test_case.gd"
## Version 015, Emerson's note 7 after 012: shells skip off the ground at shallow angles, and a round
## passing close cracks. Skips follow the angle and the ground's hardness and only ever lose energy;
## the crack comes from Whitham's N-wave and pushes the mech only if the numbers say so (they do not).

var holder: Node3D
var ground: StaticBody3D


func before_each() -> void:
	holder = Node3D.new()
	tree.root.add_child(holder)
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 2, 2000)
	cs.shape = box
	ground.add_child(cs)
	ground.position = Vector3(0, -1, 0)
	holder.add_child(ground)


func after_each() -> void:
	holder.free()


func _ammo(weapon: String, id: String) -> Dictionary:
	var a: Dictionary = Registry.entry("weapons", weapon)["ammo"][id].duplicate()
	a["id"] = id
	return a


## A round at `speed` meeting level ground `deg` below the horizontal.
func _vel(speed: float, deg: float) -> Vector3:
	return Vector3(0, -sin(deg_to_rad(deg)), -cos(deg_to_rad(deg))) * speed


func test_skip_depends_on_angle_and_ground() -> void:
	var rule: Dictionary = _ammo("gun_57mm", "apfsds")["ricochet"]
	var grounds: Dictionary = Registry.tune("combat.grounds", {})
	var dirt_limit := float(rule["max_deg"]) * float(grounds["dirt"]["hardness"])
	var rock_limit := float(rule["max_deg"]) * float(grounds["rock"]["hardness"])
	assert_gt(rock_limit, dirt_limit, "rock lets steeper hits skip than dirt (%.1f vs %.1f deg)" % [rock_limit, dirt_limit])
	assert_ne(Projectile.skip_velocity(_vel(1500, dirt_limit - 1.0), Vector3.UP, rule, grounds["dirt"]), Vector3.ZERO, "under the limit on dirt: skips")
	assert_eq(Projectile.skip_velocity(_vel(1500, dirt_limit + 1.0), Vector3.UP, rule, grounds["dirt"]), Vector3.ZERO, "over it on dirt: stops")
	assert_ne(Projectile.skip_velocity(_vel(1500, dirt_limit + 1.0), Vector3.UP, rule, grounds["rock"]), Vector3.ZERO, "the same hit on rock skips")
	assert_eq(Projectile.skip_velocity(_vel(1500, 3.0), Vector3.UP, {}, grounds["rock"]), Vector3.ZERO, "a round with no ricochet block (fuzed HE) never skips")


func test_a_skip_only_loses_energy() -> void:
	var rule: Dictionary = _ammo("gun_57mm", "apfsds")["ricochet"]
	for g: String in ["dirt", "rock", "metal"]:
		var ground: Dictionary = Registry.tune("combat.grounds", {})[g]
		var v := _vel(1500.0, 4.0)
		var out := Projectile.skip_velocity(v, Vector3.UP, rule, ground)
		var into := -v.y
		var e := float(ground["restitution"])
		assert_almost_eq(out.y, into * e, 0.01, "%s: comes up at restitution x the speed in" % g)
		var along_in := Vector2(v.x, v.z).length()
		var along_out := Vector2(out.x, out.z).length()
		assert_almost_eq(along_in - along_out, float(ground["friction"]) * (1.0 + e) * into, 0.01, "%s: friction takes its share of the speed along" % g)
		assert_lt(out.length(), v.length(), "%s: leaves slower (%.0f -> %.0f m/s)" % [g, v.length(), out.length()])
		assert_gt(out.length(), 1300.0, "%s: a grazing dart keeps most of its speed" % g)
	assert_eq(Projectile.skip_velocity(_vel(151.0, 4.0), Vector3.UP, rule, Registry.tune("combat.grounds", {})["dirt"]), Vector3.ZERO, "too slow to leave: it stops in the ground")


func test_a_grazing_dart_skips_on_and_a_steep_one_stops() -> void:
	var dart := _ammo("gun_57mm", "apfsds")
	var flat := Projectile.spawn(holder, Vector3(0, 3, 0), _vel(1550.0, 4.0), dart, null, 1.0, [])
	var skips: Array = []
	var hits: Array = []
	flat.skipped.connect(func(info: Dictionary) -> void: skips.append(info))
	flat.impacted.connect(func(info: Dictionary) -> void: hits.append(info))
	await physics_frames(10)
	assert_eq(skips.size(), 1, "4 deg onto dirt: it skipped")
	if not skips.is_empty():
		assert_lt(float(skips[0]["exit_speed"]), float(skips[0]["speed"]), "slower after (%.0f -> %.0f m/s)" % [skips[0]["speed"], skips[0]["exit_speed"]])
	if is_instance_valid(flat):
		assert_gt(flat.global_position.y, 0.0, "and flies on above the ground")
		assert_lt(flat.global_position.z, -60.0, "down range")
	var steep := Projectile.spawn(holder, Vector3(0, 3, 0), _vel(1550.0, 30.0), dart, null, 1.0, [])
	var steep_hits: Array = []
	steep.impacted.connect(func(info: Dictionary) -> void: steep_hits.append(info))
	steep.skipped.connect(func(_i: Dictionary) -> void: assert_true(false, "30 deg must not skip"))
	await physics_frames(4)
	assert_eq(steep_hits.size(), 1, "30 deg: it stops in the ground")
	var he := Projectile.spawn(holder, Vector3(0, 3, 0), _vel(800.0, 4.0), _ammo("gun_57mm", "he"), null, 1.0, [])
	var he_hits: Array = []
	he.impacted.connect(func(info: Dictionary) -> void: he_hits.append(info))
	await physics_frames(10)
	assert_eq(he_hits.size(), 1, "HE at 4 deg bursts on the ground (fuzed), no skip")


func test_whitham_nwave_matches_the_published_figure() -> void:
	var pa := Blast.nwave_pa(1650.0 / 343.0, 0.03, 0.7, 3.5)
	assert_almost_eq(pa, 1000.0, 300.0, "120 mm dart at 3.5 m: about 1 kPa (%.0f Pa)" % pa)
	assert_almost_eq(Blast.nwave_s(1650.0 / 343.0, 0.03, 0.7, 3.5) * 1000.0, 0.36, 0.08, "over about 0.36 ms")
	assert_eq(Blast.nwave_pa(300.0 / 343.0, 0.1, 1.0, 2.0), 0.0, "no crack under the speed of sound")


func test_a_close_pass_cracks_but_does_not_push() -> void:
	var mech := MechBuilder.build("juggernaut_m2")
	mech.position = Vector3(0, 3, 0)
	holder.add_child(mech)
	mech.add_to_group("player_mech")
	await physics_frames(240)
	var c := mech.global_transform * mech.center_of_mass
	var v0 := mech.linear_velocity
	var legion := Node3D.new()
	holder.add_child(legion)
	var dart := _ammo("lowe_120mm", "apfsds")
	var p := Projectile.spawn(holder, c + Vector3(3.0, 0.5, 400.0), Vector3(0, 0, -1650.0), dart, legion, 1.0, [])
	await physics_frames(30)
	var pa := float(p.cracked_pa) if is_instance_valid(p) else -1.0
	assert_gt(pa, 500.0, "the 120 mm dart passing 3 m off cracks (%.0f Pa)" % pa)
	assert_lt(pa, 3000.0, "at about a kilopascal")
	var push := Blast.nwave_push_pa_s(1650.0 / 343.0, 0.03, 0.7, 2.0) * float(Registry.tune("combat.near_miss.side_area_m2", 22.0))
	assert_lt(push, 5.0, "even at 2 m its push on the mech's side is a few N s (%.2f N s)" % push)
	assert_lt((mech.linear_velocity - v0).length(), 0.02, "so the mech is not shoved")
	var own := Projectile.spawn(holder, c + Vector3(3.0, 0.5, 400.0), Vector3(0, 0, -1650.0), dart, mech, 1.0, [])
	await physics_frames(30)
	assert_eq(float(own.cracked_pa) if is_instance_valid(own) else 0.0, 0.0, "his own rounds do not crack at him")
	var rocket := Projectile.spawn(holder, c + Vector3(3.0, 0.5, 60.0), Vector3(0, 0, -300.0), _ammo("grauwolf_rockets", "heat"), legion, 1.0, [])
	await physics_frames(30)
	assert_eq(float(rocket.cracked_pa) if is_instance_valid(rocket) else 0.0, 0.0, "a subsonic rocket does not crack")
