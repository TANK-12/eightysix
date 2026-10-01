extends "res://tests/lib/test_case.gd"
## Lane A4 part 2: the Legion's brains (scripts/ai/) against the real Juggernaut, and the HE blast
## that replaced the draft supersonic "wake" (scripts/combat/blast.gd). --fixed-fps 120.

var ground: StaticBody3D
var player: RigidBody3D
var spawned: Array = []


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(2400, 2, 2400)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)


func after_each() -> void:
	for n: Node in spawned:
		if is_instance_valid(n):
			n.free()
	spawned.clear()
	if is_instance_valid(player):
		player.free()
	if is_instance_valid(ground):
		ground.free()
	for n: Node in tree.root.get_children():
		if n.name.begins_with("Round") or n is GPUParticles3D or n is CPUParticles3D or n is Decal or n is OmniLight3D:
			n.free()
	Settings.reset_all_quietly()


func _player(at: Vector3 = Vector3(0, 3.2, 0)) -> RigidBody3D:
	player = MechBuilder.build("juggernaut_m2")
	player.position = at
	tree.root.add_child(player)
	return player


func _unit(id: String, at: Vector3, facing: Vector3, members: Array = [], index: int = 0) -> LegionMech:
	var u := LegionMech.build(id)
	u.position = at + Vector3(0, 0.3, 0)
	u.basis = Basis.looking_at(facing.normalized(), Vector3.UP)
	var brain := u.get_node("Brain") as LegionBrain
	brain.setup(u.position, members, index, 7 + index)
	members.append(brain)
	tree.root.add_child(u)
	spawned.append(u)
	return u


func _brain(u: LegionMech) -> LegionBrain:
	return u.get_node("Brain") as LegionBrain


func _wall(at: Vector3, size: Vector3) -> StaticBody3D:
	var w := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	w.add_child(cs)
	w.position = at
	tree.root.add_child(w)
	spawned.append(w)
	return w


## Waits until `cond` holds or `seconds` pass; returns the seconds it took (INF when it never held).
func _until(cond: Callable, seconds: float) -> float:
	var t := 0.0
	while t < seconds:
		if cond.call():
			return t
		await physics_frames(12)
		t += 0.1
	return INF


# --- the blast ----------------------------------------------------------------------------------


func test_blast_figures_follow_the_published_fit() -> void:
	# Kinney-Graham side-on overpressure for 1 kg TNT: about 1 MPa at Z = 1, about 0.1 atm at Z = 10.
	assert_between(Blast.overpressure_pa(1.0, 1.0), 0.8e6, 1.2e6, "1 kg at 1 m")
	assert_between(Blast.overpressure_pa(10.0, 1.0), 7e3, 12e3, "1 kg at 10 m")
	# A weak wave reflects at twice its side-on pressure, a strong one up to eight times.
	assert_almost_eq(Blast.reflection(100.0), 2.0, 0.01)
	assert_between(Blast.reflection(5e6), 6.5, 8.0)
	var last := INF
	for r: float in [1.0, 2.0, 5.0, 10.0, 20.0]:
		var i := Blast.face_impulse(r, 3.6)
		assert_lt(i, last, "falls with distance")
		last = i
	print("    face impulse, 2.0 kg TNT on the ground: 2 m %.0f, 5 m %.0f, 15 m %.0f Pa s" % [Blast.face_impulse(2.0, 3.6), Blast.face_impulse(5.0, 3.6), Blast.face_impulse(15.0, 3.6)])


func test_an_he_burst_shoves_the_juggernaut_and_a_wall_shields_it() -> void:
	_player()
	await physics_frames(360)
	var space := player.get_world_3d().direct_space_state
	var com := player.global_transform * player.center_of_mass
	var side := player.global_transform.basis.x
	# Distances are from the widest collider's side (the hull or a splayed leg), at ground level.
	var half_w := 0.0
	for part: Array in Blast.body_parts(player):
		half_w = maxf(half_w, absf((part[1] as AABB).end.x))
	var figures := []
	for r: float in [2.0, 5.0, 15.0]:
		var at := Vector3(com.x, 0.1, com.z) + side * (half_w + r)
		var v0 := player.linear_velocity
		var pushed := Blast.push(space, at, 2.0, true)
		await physics_frames(1)
		var dv := player.linear_velocity - v0
		var j := 0.0
		for p: Dictionary in pushed:
			if p["body"] == player:
				j = float(p["impulse_ns"])
		figures.append([r, j, dv.length()])
		assert_gt(j, 0.0, "pushed at %.0f m" % r)
		assert_lt(dv.dot(side), 0.0, "away from the burst at %.0f m" % r)
		await physics_frames(240)
	assert_between(figures[0][1] / player.mass, 0.1, 1.5, "a 2 m near miss: a stagger, not a launch (%.2f m/s)" % (figures[0][1] / player.mass))
	assert_lt(figures[2][1], figures[0][1] * 0.2, "far less at 15 m")
	print("    120 mm HE beside a %.0f kg Juggernaut: 2 m %.0f N s (%.2f m/s), 5 m %.0f N s (%.2f m/s), 15 m %.0f N s (%.3f m/s)" % [player.mass, figures[0][1], figures[0][1] / player.mass, figures[1][1], figures[1][1] / player.mass, figures[2][1], figures[2][1] / player.mass])
	# A wall between the burst and the mech takes it.
	var at2 := Vector3(com.x, 0.1, com.z) + side * (half_w + 4.0)
	var wall := _wall(Vector3(com.x, 3.0, com.z) + side * (half_w + 2.0), Vector3(0.6, 8.0, 14.0))
	wall.basis = player.global_transform.basis
	await physics_frames(2)
	var shielded := Blast.push(space, at2, 2.0, true).filter(func(p: Dictionary) -> bool: return p["body"] == player)
	assert_eq(shielded.size(), 0, "a wall shields it")


func test_a_burst_off_centre_spins_a_body_in_the_air() -> void:
	var body := RigidBody3D.new()
	body.mass = 5400.0
	body.gravity_scale = 0.0
	body.collision_layer = 2
	for z: float in [-1.25, 1.25]:  # two halves, like a mech's parts
		var cs := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = Vector3(3.0, 2.0, 2.5)
		cs.shape = box
		cs.position.z = z
		body.add_child(cs)
	body.position = Vector3(0, 20, 0)
	tree.root.add_child(body)
	spawned.append(body)
	await physics_frames(2)
	Blast.push(body.get_world_3d().direct_space_state, Vector3(4.0, 20.0, 2.0), 2.0, false)
	await physics_frames(2)
	assert_gt(body.linear_velocity.length(), 0.01, "pushed")
	assert_gt(absf(body.angular_velocity.y), 0.001, "the near end pushed harder: it spins (%.3f rad/s)" % body.angular_velocity.y)
	print("    airborne 5.4 t box, 2 kg burst 4 m off its rear quarter: %.2f m/s, spin %.3f rad/s" % [body.linear_velocity.length(), body.angular_velocity.y])


# --- brains -------------------------------------------------------------------------------------


func test_every_unit_gets_its_brain() -> void:
	for id: String in ["ameise", "grauwolf", "lowe"]:
		var u := LegionMech.build(id)
		var brain := u.get_node_or_null("Brain")
		assert_not_null(brain, id + " has a brain")
		assert_true(brain is LegionBrain, id + " brain is a LegionBrain")
		assert_has(u.def, "ai", id + " has an ai block")
		u.free()


func test_scout_sees_calls_the_others_keeps_its_distance_and_shoots() -> void:
	_player()
	var scout := _unit("ameise", Vector3(0, 0, -320), Vector3(0, 0, 1))
	# A Grauwolf far behind the scout, facing away: it cannot see the Juggernaut, only hear the call.
	var wolf := _unit("grauwolf", Vector3(0, 0, -800), Vector3(0, 0, -1))
	var sb := _brain(scout)
	var wb := _brain(wolf)
	var t_seen := await _until(func() -> bool: return sb.state == "attack", 6.0)
	assert_lt(t_seen, 6.0, "the scout spots the Juggernaut at 320 m")
	assert_eq(int(sb.get("calls")), 1, "and calls once")
	assert_lt(wb.contact_age_s, 3.0, "the Grauwolf 480 m back got the call")
	assert_false(wb.sees, "without seeing it")
	await _until(func() -> bool: return wb.state == "alert", 2.0)
	assert_eq(wb.state, "alert", "and comes to look")
	await physics_frames(120 * 10)
	var d := scout.global_position.distance_to(player.global_position)
	assert_between(d, 120.0, 330.0, "the scout keeps its distance (%.0f m)" % d)
	assert_gt(sb.shots, 5, "and its guns fire (%d rounds)" % sb.shots)
	print("    scout: spotted in %.1f s, %d rounds, at %.0f m after 10 s; Grauwolf %s" % [t_seen, sb.shots, d, wb.state])


func test_hidden_behind_a_wall_it_is_heard_not_seen() -> void:
	_player()
	var scout := _unit("ameise", Vector3(0, 0, -120), Vector3(0, 0, 1))
	_wall(Vector3(0, 6, -40), Vector3(60, 12, 2))
	var sb := _brain(scout)
	await physics_frames(240)
	assert_eq(sb.state, "patrol", "the wall hides the Juggernaut")
	assert_false(sb.sees)
	var combat := player.get_node("Combat") as MechCombat
	combat.fire_main()
	await physics_frames(30)
	assert_lt(sb.contact_age_s, 1.0, "the 57 mm shot is heard")
	assert_false(sb.sees, "still not seen")
	assert_eq(sb.state, "alert", "it comes to look")


func test_a_hurt_scout_retreats() -> void:
	_player()
	var scout := _unit("ameise", Vector3(0, 0, -200), Vector3(0, 0, 1))
	var sb := _brain(scout)
	await _until(func() -> bool: return sb.state == "attack", 5.0)
	scout.take_hit({"key": "hull", "damage": scout.damage.parts["hull"]["max"] * 0.6, "penetration_mm": 100.0, "point": scout.global_position, "dir": Vector3.FORWARD, "splash": true})
	var d0 := scout.global_position.distance_to(player.global_position)
	await _until(func() -> bool: return sb.state == "retreat", 2.0)
	assert_eq(sb.state, "retreat", "under half health it runs")
	await physics_frames(120 * 4)
	var d1 := scout.global_position.distance_to(player.global_position)
	assert_gt(d1, d0 + 15.0, "away from the Juggernaut (%.0f -> %.0f m)" % [d0, d1])


func test_a_grauwolf_pack_spreads_to_flank_and_fires_rockets() -> void:
	_player()
	# This test is about where the pack goes, so its rockets must not end it: in about one run in
	# four they took two legs and the mech was destroyed, and a pack with no live target goes back
	# to patrol before it has spread. Armour no rocket gets through keeps the target standing.
	var dm := (player.get_node("Combat") as MechCombat).damage
	for key: String in dm.parts:
		dm.parts[key]["armour_mm"] = 1.0e6
	var members: Array = []
	var wolves: Array = []
	for i in 3:
		wolves.append(_unit("grauwolf", Vector3(-20 + i * 20, 0, -260), Vector3(0, 0, 1), members, i))
	await _until(func() -> bool: return (wolves[0] as LegionMech).get_node("Brain").get("state") == "attack", 6.0)
	# The widest the pack gets round the Juggernaut over 18 s (bearings from it, degrees).
	var spread := 0.0
	var bearings: Array = []
	for k in 36:
		await physics_frames(60)
		var now: Array = []
		for w: LegionMech in wolves:
			var to := w.global_position - player.global_position
			now.append(rad_to_deg(atan2(to.x, -to.z)))
		now.sort()
		if float(now[-1]) - float(now[0]) > spread:
			spread = float(now[-1]) - float(now[0])
			bearings = now
	var rockets := 0
	for w: LegionMech in wolves:
		rockets += _brain(w).shots
	assert_gt(spread, 90.0, "the pack spreads round the Juggernaut (widest: bearings %s)" % str(bearings))
	assert_gt(rockets, 2, "rockets fired (%d)" % rockets)
	print("    pack: bearings %s deg, %d rockets" % [str(bearings.map(func(b: float) -> int: return roundi(b))), rockets])


func test_a_grauwolf_closes_and_cuts_with_its_blade() -> void:
	_player()
	var wolf := _unit("grauwolf", Vector3(0, 0, -40), Vector3(0, 0, 1))
	var wb := _brain(wolf)
	var hp0 := (player.get_node("Combat") as MechCombat).damage.fraction("hull") if (player.get_node("Combat") as MechCombat).damage.has("hull") else 1.0
	await _until(func() -> bool: return wb.state == "attack", 4.0)
	wb.set("phase", "close")
	var t := await _until(func() -> bool: return int(wb.get("blade_hits")) > 0, 12.0)
	assert_lt(t, 12.0, "the blade lands")
	print("    blade: first cut after %.1f s (hull %.2f before)" % [t, hp0])


func test_lowe_turret_leads_and_ranges_onto_a_still_target() -> void:
	_player()
	var lowe := _unit("lowe", Vector3(0, 0, -300), Vector3(0.5, 0, 1))
	var hits: Array = []
	(player.get_node("Combat") as MechCombat).hit_taken.connect(func(key: String, dealt: float, info: Dictionary) -> void: hits.append([key, dealt, str(info.get("ammo", ""))]))
	# How close each 120 mm round's path came to the Juggernaut's centre, in metres. Not where it came
	# down: a round that skims just over the mech lands hundreds of metres behind it (a 284 m "miss"
	# in one run that had passed within a couple of metres). Back along the round's own flight line
	# from where it struck; a round that fell short is scored by the distance itself.
	var misses: Array = []
	var catch_round := func(n: Node) -> void:
		if n is Projectile and (n as Projectile).shooter == lowe and float((n as Projectile).ammo.get("projectile_kg", 0.0)) > 1.0:
			var round := n as Projectile
			round.impacted.connect(func(info: Dictionary) -> void:
				var c := player.global_transform * player.center_of_mass
				var to_c := c - (info["point"] as Vector3)
				var back := -round.velocity.normalized()
				var along := to_c.dot(back)
				misses.append(snappedf((to_c - back * along).length() if along > 0.0 else to_c.length(), 0.1)))
	tree.node_added.connect(catch_round)
	var big := func() -> Array: return hits.filter(func(h: Array) -> bool: return h[2] == "apfsds" or h[2] == "he")
	var t := await _until(func() -> bool: return not big.call().is_empty(), 24.0)
	tree.node_added.disconnect(catch_round)
	assert_lt(t, 24.0, "a 120 mm round hits the still Juggernaut at 300 m within three rounds (passed %s m off; hits %s)" % [str(misses), str(hits)])
	for m: float in misses:
		assert_lt(m, 8.0, "every round lands close: the lead is right and only the ranging error is left (%s)" % str(misses))
	print("    Löwe: first 120 mm hit after %.1f s, rounds passed %s m from the centre, hits %s" % [t, str(misses), str(big.call())])


func test_lowe_loads_he_for_a_moving_target() -> void:
	_player()
	var lowe := _unit("lowe", Vector3(0, 0, -300), Vector3(0, 0, 1))
	var lb := _brain(lowe)
	await physics_frames(10)
	lb.set("_target_v", Vector3.ZERO)
	assert_eq(lb.call("next_round"), "apfsds", "a still target at 300 m: the dart")
	lb.set("_target_v", Vector3(14, 0, 0))
	assert_eq(lb.call("next_round"), "he", "a target at 50 km/h: HE")


## Part 4 (Emerson after 010: "they climb the map's edge wall and shoot me from on top of it", "they
## walk on cliffs"): hunting a Juggernaut that stands on a high shelf past the Legion area's edge,
## a unit reads the face ahead as ground it cannot walk, stops inside the area and stays on the floor.
func test_a_hunting_unit_stays_inside_its_area_and_off_the_shelf() -> void:
	_wall(Vector3(0, 6, -90), Vector3(200, 12, 60))  # a shelf 12 m high, its face at z = -60
	var target := _player(Vector3(0, 15.2, -80))
	var u := _unit("grauwolf", Vector3(0, 0, 0), Vector3(0, 0, -1))
	var b := _brain(u)
	b.area_half_m = 50.0
	await physics_frames(60)
	b.hear_of(target.global_position)
	var fwd := Vector3(0, 0, -1)
	assert_false(b.walkable_ahead(fwd, 70.0), "the face ahead (and the area's edge) is not walkable")
	assert_true(b.walkable_ahead(-fwd, 30.0), "the open floor behind is")
	var top_y := 0.0
	var far_z := 0.0
	for i in 150:
		await physics_frames(12)
		b.hear_of(target.global_position)
		top_y = maxf(top_y, u.global_position.y)
		far_z = minf(far_z, u.global_position.z)
	print("    grauwolf hunting a target on a 12 m shelf past the area edge (z -50): highest %.2f m, furthest z %.1f, state %s" % [top_y, far_z, b.state])
	assert_lt(top_y, 4.0, "it stays on the floor")
	assert_gt(far_z, -50.0, "it stays inside its area")


## Part 4 (seen on screen after 010: a Löwe spawned beside a ruin climbed it nose-up): hunting a
## target behind a hip-high U of ruin walls it walks into, a Löwe stays on the ground and finds its
## way out and round (it gets closer to the target), not stuck in the U.
func test_a_lowe_does_not_climb_the_ruin_in_its_way() -> void:
	var h := 2.8
	_wall(Vector3(0, h * 0.5, -14), Vector3(16, h, 1.0))  # the back wall of the U
	_wall(Vector3(-8, h * 0.5, -8), Vector3(1.0, h, 12))
	_wall(Vector3(8, h * 0.5, -8), Vector3(1.0, h, 12))
	var target := _player(Vector3(0, 3.2, -700))  # past the Löwe's 500 m hold band, so it walks
	var u := _unit("lowe", Vector3(0, 0, 4), Vector3(0, 0, -1))
	var b := _brain(u)
	await physics_frames(60)
	var top_y := 0.0
	var worst_tilt := 0.0
	for i in 200:
		await physics_frames(12)
		b.hear_of(target.global_position)
		top_y = maxf(top_y, u.global_position.y)
		worst_tilt = maxf(worst_tilt, rad_to_deg(u.global_transform.basis.y.angle_to(Vector3.UP)))
	var gained := 704.0 - u.global_position.distance_to(target.global_position)
	print("    Löwe walking into a hip-high ruin: highest %.2f m, worst tilt %.1f deg, %.0f m closer to the target, ended at %s" % [top_y, worst_tilt, gained, u.global_position.snapped(Vector3.ONE * 0.1)])
	assert_lt(top_y, 1.0, "it stays on the ground")
	assert_gt(gained, 25.0, "it gets out and round the ruin")
	assert_lt(worst_tilt, 20.0, "and level")
