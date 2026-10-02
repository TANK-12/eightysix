extends "res://tests/lib/test_case.gd"
## Lane A5 part 1: the squad (scripts/ai/squad.gd), its pilots (scripts/ai/squad_pilot.gd) on real
## Juggernauts, the Legion picking the nearest Juggernaut, and the Handler view. --fixed-fps 120.

var ground: StaticBody3D
var world: Node3D
var player: RigidBody3D
var squad: Squad
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
	world = Node3D.new()
	world.name = "SquadTestWorld"
	tree.root.add_child(world)


func after_each() -> void:
	for n: Node in spawned:
		if is_instance_valid(n):
			n.free()
	spawned.clear()
	if is_instance_valid(world):
		world.free()
	if is_instance_valid(ground):
		ground.free()
	for n: Node in tree.root.get_children():
		if n.name.begins_with("Round") or n is GPUParticles3D or n is CPUParticles3D or n is Decal or n is OmniLight3D:
			n.free()
	Settings.reset_all_quietly()


## The player's mech (standing still: no input in a headless run) and a squad of `count` round it.
func _squad(count: int, at: Vector3 = Vector3(0, 3.2, 0)) -> Squad:
	player = MechBuilder.build("juggernaut_m2")
	player.position = at
	world.add_child(player)
	squad = Squad.new()
	squad.leader = player
	squad.level = world
	world.add_child(squad)
	squad.spawn(count)
	return squad


func _legion(id: String, at: Vector3, facing: Vector3, thinking: bool) -> LegionMech:
	var u := LegionMech.build(id)
	u.position = at + Vector3(0, 0.3, 0)
	u.basis = Basis.looking_at(facing.normalized(), Vector3.UP)
	var brain := u.get_node("Brain") as LegionBrain
	brain.setup(u.position, [], 0, 7)
	if not thinking:
		brain.process_mode = Node.PROCESS_MODE_DISABLED
	world.add_child(u)
	spawned.append(u)
	return u


func _until(cond: Callable, seconds: float) -> float:
	var t := 0.0
	while t < seconds:
		if cond.call():
			return t
		await physics_frames(12)
		t += 0.1
	return INF


func _flat_dist(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()


# --- data and setup -------------------------------------------------------------------------------


func test_the_squad_registry_builds() -> void:
	var ids := Registry.ids("squad")
	assert_eq(Array(ids), ["werewolf", "laughing_fox", "gunslinger", "snow_witch"], "spawn order")
	for id in ids:
		var e := Registry.entry("squad", id)
		assert_true(MechBuilder.can_build(str(e["mech"])), id + "'s mech builds")
		assert_eq((e["slot"] as Array).size(), 3, id + " slot")
	assert_eq(Settings.get_f("gameplay.squad_size"), 2.0, "two wingmen by default")
	for map_id: String in ["test_bench_flat", "test_bench_rough", "test_range"]:
		assert_false(bool(Registry.entry("maps", map_id).get("squad", true)), map_id + " has no squad")


func test_attach_follows_the_setting() -> void:
	var level := Node3D.new()
	level.set_script(load("res://tests/lib/fake_level.gd"))
	world.add_child(level)
	player = MechBuilder.build("juggernaut_m2")
	player.position = Vector3(0, 3.2, 0)
	level.add_child(player)
	level.set("mech", player)
	Settings.set_value("gameplay.squad_size", 0.0, false)
	assert_eq(Squad.attach(level), null, "size 0: no squad")
	Settings.set_value("gameplay.squad_size", 3.0, false)
	var s := Squad.attach(level)
	assert_not_null(s, "size 3: a squad")
	assert_eq(s.members.size(), 3)
	for m: RigidBody3D in s.members:
		assert_false(bool(m.get("is_player")), m.name + " is not a player")
		assert_true(m.is_in_group("squad_mech"))
		assert_false(m.is_in_group("player_mech"))
		assert_between(_flat_dist(m.global_position, player.global_position), 10.0, 50.0, m.name + " beside the leader")
	assert_eq(tree.get_nodes_in_group("player_mech").size(), 1, "still one player")


func test_select_and_address() -> void:
	_squad(2)
	assert_eq(squad.selected, -1)
	squad.select_next(1)
	assert_eq(squad.selected, 0)
	squad.select_next(1)
	assert_eq(squad.selected, 1)
	squad.select_next(1)
	assert_eq(squad.selected, -1, "wraps to the whole squad")
	squad.select_next(-1)
	assert_eq(squad.selected, 1, "and back")
	var rows := squad.report()
	assert_eq(rows.size(), 2)
	assert_eq(str(rows[0]["callsign"]), "Werewolf")
	assert_true(bool(rows[0]["alive"]))
	var lines := MissionEnd.squad_lines([{"callsign": "Werewolf", "alive": true, "armour": 0.82, "shots": 14}, {"callsign": "Laughing Fox", "alive": false}])
	assert_eq(lines, "\nWerewolf  armour 82 %  ·  14 shots\nLaughing Fox  lost", "the end screen's squad lines")
	squad.selected = 0
	squad.give_order("hold")
	assert_eq(squad.pilots[0].order, "hold")
	assert_eq(squad.pilots[1].order, "follow", "only the picked one")


# --- driving --------------------------------------------------------------------------------------


func test_a_wingman_walks_to_a_point_and_back_into_formation() -> void:
	_squad(1)
	await physics_frames(120)
	var p := squad.pilots[0]
	var m := squad.members[0]
	var start := m.global_position
	var point := start + Vector3(-70.0, 0.0, -50.0)  # 86 m off, behind its left shoulder
	squad.give_order("move", point)
	var took := await _until(func() -> bool: return _flat_dist(m.global_position, point) < 8.0, 40.0)
	print("    move 86 m: %.1f s" % took)
	assert_lt(took, 30.0, "got to the marked point")
	assert_gt(m.global_position.y, -1.0, "still on its feet above the ground")
	squad.give_order("follow")
	var back := await _until(func() -> bool: return _flat_dist(m.global_position, p.goal()) < 8.0, 40.0)
	print("    back in its slot: %.1f s" % back)
	assert_lt(back, 30.0, "back in its formation slot")
	assert_gt(m.global_transform.basis.y.dot(Vector3.UP), 0.8, "upright")


func test_hold_stays_put() -> void:
	_squad(1)
	await physics_frames(120)
	var m := squad.members[0]
	squad.give_order("hold")
	var at := m.global_position
	await physics_frames(600)
	assert_lt(_flat_dist(m.global_position, at), 4.0, "held its ground for 5 s")


func test_it_walks_round_a_wall() -> void:
	_squad(1)
	await physics_frames(120)
	var m := squad.members[0]
	var start := m.global_position
	var point := start + Vector3(0.0, 0.0, -90.0)
	# A 40 m wide, 10 m high wall square across the way, 40 m ahead.
	var w := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(40.0, 10.0, 2.0)
	cs.shape = box
	w.add_child(cs)
	w.position = Vector3(start.x, 5.0, start.z - 40.0)
	world.add_child(w)
	squad.give_order("move", point)
	var took := await _until(func() -> bool: return _flat_dist(m.global_position, point) < 8.0, 60.0)
	print("    round a 40 m wall to a point 90 m off: %.1f s" % took)
	assert_lt(took, 45.0, "found its way round")
	assert_gt(m.global_transform.basis.y.dot(Vector3.UP), 0.8, "upright")


# --- fighting -------------------------------------------------------------------------------------


func test_it_turns_onto_a_legion_and_hits_it() -> void:
	_squad(1)
	await physics_frames(120)
	var p := squad.pilots[0]
	var m := squad.members[0]
	squad.give_order("hold")
	var fwd := -m.global_transform.basis.z
	var off := fwd.rotated(Vector3.UP, deg_to_rad(55.0))  # well off its nose, away from the player: it must turn the body
	var u := _legion("grauwolf", m.global_position + off * 160.0 - Vector3(0, m.global_position.y, 0), -off, false)
	var hp := u.health_fraction()
	var took := await _until(func() -> bool: return p.shots > 0, 20.0)
	print("    turned 55 deg and fired: %.1f s" % took)
	assert_lt(took, 15.0, "fired the 57 mm")
	assert_eq(p.target, u, "fighting the Grauwolf")
	await _until(func() -> bool: return u.health_fraction() < hp, 3.0)
	assert_lt(u.health_fraction(), hp, "the round hit it")
	# It keeps firing at the breech's own rate (0.9 s cycle), not a reload after every shot.
	var first := p.shots
	await physics_frames(480)
	print("    shots in the next 4 s: %d (Grauwolf health %.2f)" % [p.shots - first, u.health_fraction()])
	assert_true(p.shots - first >= 3 or u.dead, "kept firing, or it is already down")


func test_no_shot_through_a_friendly() -> void:
	_squad(1)
	await physics_frames(120)
	var p := squad.pilots[0]
	var m := squad.members[0]
	squad.give_order("hold")
	# The Grauwolf straight down the line from the wingman through the player's mech.
	var dir := (player.global_position - m.global_position)
	dir.y = 0.0
	dir = dir.normalized()
	var at := player.global_position + dir * 150.0
	at.y = 0.0
	_legion("grauwolf", at, -dir, false)
	await physics_frames(840)
	assert_not_null(p.target, "it sees the Legion")
	assert_eq(p.shots, 0, "it never fired through the player")


func test_the_legion_hunts_the_nearest_juggernaut() -> void:
	_squad(1)
	var m := squad.members[0]
	# Wingman sent far out on the right; a Legion beyond it.
	m.global_position = Vector3(400.0, 3.2, 0.0)
	await physics_frames(60)
	var u := _legion("ameise", Vector3(520.0, 0.0, 0.0), Vector3.LEFT, true)
	var brain := u.get_node("Brain") as LegionBrain
	await physics_frames(240)
	assert_eq(brain.target, m, "the nearer Juggernaut is the target")
	m.global_position = Vector3(-300.0, 3.2, 0.0)
	await physics_frames(240)
	assert_eq(brain.target, player, "switches when the player is nearer")


# --- the Handler view -----------------------------------------------------------------------------


func test_the_handler_view_opens_shows_and_orders() -> void:
	_squad(2)
	await physics_frames(60)
	var field_cam := Camera3D.new()
	world.add_child(field_cam)
	field_cam.make_current()
	var u := _legion("ameise", Vector3(0.0, 0.0, -200.0), Vector3.BACK, false)
	var hud := CanvasLayer.new()
	hud.layer = 12  # where the mission HUD sits
	world.add_child(hud)
	var h := squad.handler
	h.open()
	assert_true(h.is_open)
	assert_eq(world.get_viewport().get_camera_3d(), h.camera, "the tactical camera is live")
	assert_gt(h.camera.global_position.y, 100.0, "high above the squad")
	assert_has(h.seen_legion, u, "the Legion the squad sees is on the board")
	assert_false(hud.visible, "the field HUD hides")
	var mid: Vector3 = h.centre()[0]
	var screen := h.camera.unproject_position(mid + Vector3(30.0, 0.0, 0.0))
	assert_true(h.order_move_at(screen), "a click on the ground gives a move order")
	for p: SquadPilot in squad.pilots:
		assert_eq(p.order, "move")
		assert_lt(_flat_dist(p.order_point, mid + Vector3(30.0, 0.0, 0.0)), 3.0, "to the clicked point")
	assert_eq(h.click_at(h.camera.unproject_position(u.global_position) + Vector2(6, 4)), "attack", "a click on the red marker")
	for p: SquadPilot in squad.pilots:
		assert_eq(p.order, "attack")
		assert_eq(p.order_target, u, "that Legion")
	h.close()
	assert_false(h.is_open)
	assert_eq(world.get_viewport().get_camera_3d(), field_cam, "the field camera is back")
	assert_true(hud.visible, "and the field HUD")


func test_the_squad_has_hints_and_tips() -> void:
	_squad(1)
	var hints := MoveHints.new()
	world.add_child(hints)
	var state := hints.state()
	assert_eq(int(state["squad"]), 1, "the hint state counts the squad")
	state["play_s"] = 30.0
	var seen: Array = []
	for id in Registry.ids("hints"):
		if not id in ["squad_orders", "handler_view"]:
			seen.append(id)
	assert_eq(MoveHints.pick(Registry.file("hints")["entries"], state, seen), "squad_orders", "the squad hint comes up")
	for id: String in ["squad_orders", "handler_view"]:
		assert_true(Registry.has_entry("hints", id), id + " hint")
		assert_true(Registry.has_entry("tips", id), id + " tip")
	hints.free()
