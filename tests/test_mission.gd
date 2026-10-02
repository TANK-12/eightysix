extends "res://tests/lib/test_case.gd"
## Lane A4 part 2: the mission loop (scripts/mission/mission.gd, data/missions.json): waves spawn on
## open ground at their areas, the next wave follows a cleared one, the last cleared wins, the
## player's Juggernaut destroyed loses, and the end screen pauses with Restart and Main menu.


class FakeLevel:
	extends Node3D
	var mech: RigidBody3D

	func ground_height(_x: float, _z: float) -> float:
		return 0.0


var ground: StaticBody3D
var level: FakeLevel


func before_each() -> void:
	ground = StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(2400, 2, 2400)
	cs.shape = box
	cs.position.y = -1.0
	ground.add_child(cs)
	tree.root.add_child(ground)
	level = FakeLevel.new()
	tree.root.add_child(level)
	level.mech = MechBuilder.build("juggernaut_m2")
	level.mech.position = Vector3(0, 3.2, 0)
	level.add_child(level.mech)


func after_each() -> void:
	tree.paused = false
	if is_instance_valid(level):
		level.free()
	if is_instance_valid(ground):
		ground.free()
	for n: Node in tree.root.get_children():
		if n.name.begins_with("Round") or n is GPUParticles3D or n is CPUParticles3D or n is Decal or n is OmniLight3D or n is MissionEnd:
			n.free()
	Settings.reset_all_quietly()


func _mission(def: Dictionary) -> Mission:
	var m := Mission.new()
	m.id = "test"
	m.def = def
	m.level = level
	level.add_child(m)
	return m


func _two_waves() -> Dictionary:
	return {
		"areas": {"a": {"at": [0.0, -400.0], "radius_m": 30.0}, "b": {"at": [300.0, -300.0], "radius_m": 30.0}},
		"waves": [
			{"objective": "first", "groups": [{"enemy": "ameise", "count": 2, "area": "a"}], "delay_s": 0.5},
			{"objective": "second", "groups": [{"enemy": "grauwolf", "count": 1, "area": "b"}], "alerted": true, "delay_s": 0.0},
		],
	}


func _kill(u: LegionMech) -> void:
	for i in 10:
		if u.dead:
			return
		u.take_hit({"key": "hull", "damage": 5000.0, "penetration_mm": 500.0, "point": u.global_position, "dir": Vector3.FORWARD, "splash": true})


func test_missions_resolve_against_the_registries() -> void:
	assert_true(Registry.has_file("missions"))
	for id: String in Registry.ids("missions"):
		var m := Registry.entry("missions", id)
		assert_true(Registry.has_entry("maps", str(m["map"])), id + " map exists")
		for w: Dictionary in m["waves"]:
			for g: Dictionary in w["groups"]:
				assert_true(Registry.has_entry("enemies", str(g["enemy"])), id + " enemy " + str(g["enemy"]))
				assert_has(m["areas"], str(g["area"]), id + " area " + str(g["area"]))
				for stop: Variant in g.get("route", []):
					if stop is Array:
						assert_eq((stop as Array).size(), 2, id + " route point is [x, z]")
					else:
						assert_has(m["areas"], str(stop), id + " route stop " + str(stop))
	assert_eq(Mission.for_map("small_map"), "ashen_first_contact", "Ashen valley has its mission")
	assert_eq(Mission.for_map("test_range"), "", "the test range has none")


func test_waves_spawn_follow_each_other_and_the_last_wins() -> void:
	var m := _mission(_two_waves())
	var texts: Array = []
	var result: Array = []
	m.objective_changed.connect(func(t: String) -> void: texts.append(t))
	m.ended.connect(func(won: bool) -> void: result.append(won))
	await physics_frames(10)
	assert_eq(m.wave, 0)
	assert_eq(m.objective, "first", "wave 1's objective")
	assert_eq(m.units.size(), 2, "wave 1: two Ameise")
	for u: LegionMech in m.units:
		var flat := Vector2(u.global_position.x, u.global_position.z)
		assert_lt(flat.distance_to(Vector2(0, -400)), 31.0, "spawned in its area")
		assert_true(u.get_node("Brain") is LegionBrain, "with its brain")
	var a: LegionMech = m.units[0]
	var b: LegionMech = m.units[1]
	assert_gt(a.global_position.distance_to(b.global_position), 11.0, "not on top of each other")
	assert_eq((a.get_node("Brain") as LegionBrain).pack.size(), 2, "the two share a pack")
	await physics_frames(120)
	_kill(a)
	await physics_frames(5)
	assert_eq(m.wave, 0, "one left: still wave 1")
	_kill(b)
	await physics_frames(30)
	assert_eq(m.wave, 0, "the next wave waits its delay")
	await physics_frames(60)
	assert_eq(m.wave, 1, "wave 2 after the delay")
	assert_eq(m.alive(), 1)
	var called := (m.units[0] as LegionMech).get_node("Brain") as LegionBrain
	assert_lt(called.contact_age_s, 2.0, "a called-in wave knows roughly where the Juggernaut is")
	assert_lt(Vector2(called.last_known.x, called.last_known.z).length(), 80.0, "within its 10 %% error (%s)" % str(called.last_known))
	_kill(m.units[0])
	await physics_frames(5)
	assert_eq(m.state, "won")
	assert_eq(result, [true], "ended won")
	assert_eq(m.kills, 3)
	assert_has(texts, "second")
	assert_has(texts, "Mission complete")


func test_losing_the_juggernaut_loses_the_mission() -> void:
	var m := _mission(_two_waves())
	var result: Array = []
	m.ended.connect(func(won: bool) -> void: result.append(won))
	await physics_frames(10)
	var combat := level.mech.get_node("Combat") as MechCombat
	var cockpit := ""
	for key: String in combat.damage.parts:
		if str(combat.damage.parts[key]["kind"]) in DamageModel.CRITICAL:
			cockpit = key
	assert_ne(cockpit, "", "the Juggernaut has a critical part")
	for i in 20:
		if combat.damage.is_destroyed:
			break
		combat.take_hit({"key": cockpit, "damage": 5000.0, "penetration_mm": 900.0, "point": level.mech.global_position, "splash": true})
	await physics_frames(2)
	assert_eq(m.state, "lost")
	assert_eq(result, [false], "ended lost")


func test_end_screen_pauses_with_restart_and_main_menu() -> void:
	var end := MissionEnd.new()
	end.won = true
	end.summary = {"mission": "ashen_first_contact", "kills": 9, "time_s": 312.0, "wave": 3, "waves": 3}
	tree.root.add_child(end)
	end.show_now()
	assert_true(tree.paused, "the game pauses")
	var texts: Array = []
	for b: Node in end.find_children("*", "Button", true, false):
		texts.append((b as Button).text)
	assert_eq(texts, ["Restart mission", "Main menu"])
	var labels: Array = []
	for l: Node in end.find_children("*", "Label", true, false):
		labels.append((l as Label).text)
	assert_has(labels, "Mission complete")
	assert_true(" ".join(labels).contains("5:12"), "time shown as minutes (%s)" % str(labels))
	tree.paused = false
	end.free()


## Lane B5 part 2: an alerted wave with "track_s" keeps hearing where the Juggernaut is, so on a 4 km
## map it can walk the whole way; without it the call-in fades after perception.memory_s.
func _alerted_wave(track_s: float) -> Dictionary:
	var w := {"objective": "pack", "groups": [{"enemy": "grauwolf", "count": 1, "area": "a"}], "alerted": true, "delay_s": 0.0}
	if track_s > 0.0:
		w["track_s"] = track_s
	return {"areas": {"a": {"at": [0.0, -900.0], "radius_m": 30.0}}, "waves": [w]}


func test_an_alerted_wave_with_track_s_keeps_hearing_of_the_player() -> void:
	var m := _mission(_alerted_wave(60.0))
	await physics_frames(2400)  # 20 s at 120 Hz: past memory_s (15 s)
	var brain := (m.units[0] as LegionMech).get_node("Brain") as LegionBrain
	assert_lt(brain.contact_age_s, 6.0, "told again every few seconds (contact age %.1f s)" % brain.contact_age_s)


func test_an_alerted_wave_without_track_s_forgets_after_its_memory() -> void:
	var m := _mission(_alerted_wave(0.0))
	await physics_frames(2400)
	var brain := (m.units[0] as LegionMech).get_node("Brain") as LegionBrain
	assert_gt(brain.contact_age_s, 15.0, "the call-in fades (contact age %.1f s)" % brain.contact_age_s)


func test_a_group_with_a_route_patrols_between_its_stops() -> void:
	level.mech.global_position = Vector3(0.0, 3.2, 1100.0)  # far out of sight: they patrol, not hunt
	var m := _mission(
		{
			"areas": {"start": {"at": [0.0, -400.0], "radius_m": 10.0}, "mid": {"at": [60.0, -420.0], "radius_m": 5.0}, "end": {"at": [120.0, -400.0], "radius_m": 5.0}},
			"waves": [{"objective": "column", "groups": [{"enemy": "ameise", "count": 2, "area": "start", "route": ["mid", [120.0, -400.0]]}]}],
		}
	)
	await physics_frames(10)
	for u: LegionMech in m.units:
		var brain := u.get_node("Brain") as LegionBrain
		assert_eq(brain._route.size(), 2, "the route is the two stops, not a random loop")
		assert_almost_eq(brain._route[0].x, 60.0, 0.01, "first stop: the middle area's centre")
		assert_almost_eq(brain._route[1].z, -400.0, 0.01, "second stop: an [x, z] point")
	await physics_frames(3000)  # 25 s at 120 Hz
	var a: LegionMech = m.units[0]
	assert_gt(a.global_position.x, 15.0, "walking along it (x %.0f)" % a.global_position.x)


func _column(extra: Dictionary) -> Mission:
	var g := {"enemy": "ameise", "count": 1, "area": "start", "route": [[60.0, -400.0], [120.0, -400.0]]}
	g.merge(extra)
	return _mission({"areas": {"start": {"at": [0.0, -400.0], "radius_m": 0.5}}, "waves": [{"objective": "column", "groups": [g]}]})


func test_a_column_with_trigger_m_waits_until_the_juggernaut_is_near() -> void:
	level.mech.global_position = Vector3(0.0, 3.2, 1100.0)
	var m := _column({"trigger_m": 300.0})
	await physics_frames(1200)  # 10 s
	var u: LegionMech = m.units[0]
	assert_lt(absf(u.global_position.x), 5.0, "it stands on the road while the Juggernaut is 1500 m away (x %.0f)" % u.global_position.x)
	level.mech.global_position = Vector3(0.0, 3.2, -300.0)  # 100 m off
	await physics_frames(1500)
	assert_gt(u.global_position.x, 15.0, "and marches once it is near (x %.0f)" % u.global_position.x)


func test_a_once_route_stops_at_its_last_stop() -> void:
	level.mech.global_position = Vector3(0.0, 3.2, 1100.0)
	var m := _column({"once": true})
	await physics_frames(5700)  # 47 s: 120 m at 4 m/s takes 30, a loop back would have it near x 60 by now
	var u: LegionMech = m.units[0]
	assert_between(u.global_position.x, 110.0, 130.0, "it ends up at the last stop and stays (x %.0f)" % u.global_position.x)


func test_a_marching_column_ignores_the_juggernaut_until_the_end_of_its_route() -> void:
	level.mech.global_position = Vector3(60.0, 3.2, -330.0)  # 70 m off the road, well inside sight
	var m := _column({"once": true, "trigger_m": 500.0})
	await physics_frames(1800)  # 15 s
	var u: LegionMech = m.units[0]
	var brain := u.get_node("Brain") as LegionBrain
	assert_eq(brain.state, "patrol", "on the march it does not attack what it sees")
	assert_gt(u.global_position.x, 15.0, "and keeps walking (x %.0f)" % u.global_position.x)
	await physics_frames(3600)  # to the end of the route
	assert_ne(brain.state, "patrol", "at the end of the route it fights")


func test_the_guide_points_at_the_nearest_legion_of_the_wave() -> void:
	var m := _mission(
		{
			"areas": {"east": {"at": [400.0, 0.0], "radius_m": 0.5}, "north": {"at": [0.0, -900.0], "radius_m": 0.5}},
			"waves": [{"objective": "two", "groups": [{"enemy": "ameise", "count": 1, "area": "east"}, {"enemy": "ameise", "count": 1, "area": "north"}]}],
		}
	)
	await physics_frames(5)
	var g := m.guide()
	assert_false(g.is_empty(), "a wave with Legion alive has a guide")
	assert_between(float(g["distance_m"]), 380.0, 420.0, "the nearer one, 400 m east")
	assert_between(float(g["bearing_deg"]), 85.0, 95.0, "due east is 090 (%.0f)" % float(g["bearing_deg"]))
	for u: LegionMech in m.units:
		_kill(u)
	assert_true(m.guide().is_empty(), "nothing alive, no guide")
