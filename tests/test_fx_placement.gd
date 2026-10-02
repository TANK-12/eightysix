extends "res://tests/lib/test_case.gd"
## Emerson's note 11 (2026-10-02): sparks and smoke also showed at the map's spawn point (the world origin)
## when he fired. A Juggernaut far from the origin fires both guns; nothing new may appear near (0,0,0).

const FAR := Vector3(300, 0, 300)

var world: Node3D
var mech: RigidBody3D


func before_each() -> void:
	world = Node3D.new()
	tree.root.add_child(world)
	var ground := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(400, 2, 400)
	cs.shape = box
	ground.add_child(cs)
	world.add_child(ground)
	ground.global_position = FAR + Vector3(0, -1, 0)
	mech = MechBuilder.build("juggernaut_m2")
	world.add_child(mech)
	mech.global_position = FAR + Vector3(0, 3, 0)
	await physics_frames(30)


func after_each() -> void:
	world.free()
	Settings.reset_all_quietly()


func _near_origin(before: Array) -> Array:
	var out: Array = []
	for n: Node in world.find_children("*", "Node3D", true, false):
		var n3 := n as Node3D
		if not before.has(n3) and n3.is_visible_in_tree() and n3.global_position.length() < 20.0:
			out.append("%s %s at %s (parent %s)" % [n3.get_class(), n3.name, n3.global_position, n3.get_parent().name])
	return out


func test_firing_makes_nothing_at_the_origin() -> void:
	var combat := mech.get_node_or_null("Combat")
	assert_true(combat != null, "the mech has its combat node")
	# What was there before firing (the wire anchor's world-space aim-arc dots sit at the origin on purpose).
	var before := world.find_children("*", "Node3D", true, false)
	var seen: Array = []
	for i in 40:
		if i % 20 == 0:
			combat.call("fire_main")
		if i % 3 == 0:
			combat.call("fire_sub")
		await physics_frames(1)
		await tree.process_frame
		for s: String in _near_origin(before):
			if not seen.has(s):
				seen.append(s)
	assert_eq(seen.size(), 0, "nothing near the origin: %s" % ", ".join(seen))


## The same on the real small map (spawn at the origin): the player walks off 150 m, then fires.
func test_firing_on_the_small_map_makes_nothing_at_the_spawn() -> void:
	Settings.set_value("gameplay.squad_size", 0.0, false)
	var level: Node3D = (load("res://scenes/levels/small_map.tscn") as PackedScene).instantiate()
	tree.root.add_child(level)
	var player: RigidBody3D = level.get("mech")
	await physics_frames(60)
	var x := 150.0
	var z := -150.0
	player.global_position = Vector3(x, float(level.call("ground_height", x, z)) + 3.5, z)
	player.linear_velocity = Vector3.ZERO
	await physics_frames(120)
	var before := level.find_children("*", "Node3D", true, false)
	var combat := player.get_node("Combat")
	var seen: Array = []
	for i in 60:
		if i % 20 == 0:
			combat.call("fire_main")
		if i % 3 == 0:
			combat.call("fire_sub")
		await physics_frames(1)
		await tree.process_frame
		for n: Node in level.find_children("*", "Node3D", true, false):
			var n3 := n as Node3D
			if not before.has(n3) and n3.is_visible_in_tree() and n3.global_position.length() < 20.0:
				var s := "%s %s at %s (parent %s)" % [n3.get_class(), n3.name, n3.global_position, n3.get_parent().name]
				if not seen.has(s):
					seen.append(s)
	assert_eq(seen.size(), 0, "nothing new at the spawn: %s" % ", ".join(seen))
	level.free()
	Game.level = null
