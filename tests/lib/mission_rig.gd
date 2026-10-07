extends RefCounted
## A flat 2.4 km ground, a level with the player's Juggernaut and a one-wave mission close by: what the
## lane A7 tests (after-action report, Handler radio, kill cam) share.


class FakeLevel:
	extends Node3D
	var mech: RigidBody3D

	func ground_height(_x: float, _z: float) -> float:
		return 0.0


var tree: SceneTree
var ground: StaticBody3D
var level: FakeLevel


func _init(scene_tree: SceneTree) -> void:
	tree = scene_tree
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
	level.mech.add_to_group("player_mech")
	level.add_child(level.mech)


## A mission of `waves` (each a list of enemy ids) whose areas sit `distance_m` north of the player.
func mission(waves: Array, distance_m: float = 300.0, mission_id: String = "test") -> Mission:
	var defs: Array = []
	for w: Array in waves:
		var groups: Array = []
		for e: String in w:
			groups.append({"enemy": e, "count": 1, "area": "a"})
		defs.append({"objective": "wave", "groups": groups, "delay_s": 0.2})
	var m := Mission.new()
	m.id = mission_id
	m.def = {"areas": {"a": {"at": [0.0, -distance_m], "radius_m": 20.0}}, "waves": defs}
	m.level = level
	level.add_child(m)
	return m


## Hits `u` as the player's round would (shooter set, not splash) until it is destroyed.
func kill_as_player(u: LegionMech, key: String = "hull") -> void:
	for i in 12:
		if u.dead:
			return
		u.take_hit({"key": key, "damage": 5000.0, "penetration_mm": 900.0, "point": u.global_position, "dir": Vector3.FORWARD, "shooter": level.mech, "splash": false})


func free_all() -> void:
	tree.paused = false
	Engine.time_scale = 1.0
	if is_instance_valid(level):
		level.free()
	if is_instance_valid(ground):
		ground.free()
	for n: Node in tree.root.get_children():
		if n.name.begins_with("Round") or n is GPUParticles3D or n is CPUParticles3D or n is Decal or n is OmniLight3D or n is MissionEnd:
			n.free()
	Settings.reset_all_quietly()
