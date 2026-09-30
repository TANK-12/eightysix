class_name CombatHits
extends RefCounted
## Who and what a physics hit struck. Every mech collider (chassis part or leg hitbox) carries
## MechBuilder's "damage_key" meta; the receiver is the nearest node up the tree with a take_hit()
## method, or a node a body names with its "combat" meta (a mech's MechCombat child).


## The damage key on the CollisionShape3D a ray or shape query reported, or "".
static func key_of(collider: Object, shape_index: int) -> String:
	if not collider is CollisionObject3D:
		return ""
	var body := collider as CollisionObject3D
	var owner_id := body.shape_find_owner(shape_index)
	if owner_id < 0:
		return ""
	var node := body.shape_owner_get_owner(owner_id) as Node
	if node != null and node.has_meta("damage_key"):
		return str(node.get_meta("damage_key"))
	return ""


static func receiver(collider: Object) -> Object:
	var n := collider as Node
	while n != null:
		if n.has_meta("combat"):
			var c: Object = n.get_meta("combat")
			if is_instance_valid(c):
				return c
		if n.has_method("take_hit"):
			return n
		n = n.get_parent()
	return null


## Splash damage from a blast: every mech part within `radius` of `point` takes `damage` scaled
## down linearly with distance (each part once, the directly hit part excluded).
static func blast(space: PhysicsDirectSpaceState3D, point: Vector3, radius: float, info: Dictionary, skip_key: String) -> int:
	var sphere := SphereShape3D.new()
	sphere.radius = radius
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = sphere
	q.transform = Transform3D(Basis.IDENTITY, point)
	q.collision_mask = 2 | 4
	q.collide_with_areas = true
	var seen := {}
	var count := 0
	for r: Dictionary in space.intersect_shape(q, 64):
		var key := key_of(r["collider"], int(r["shape"]))
		var target := receiver(r["collider"])
		if key == "" or target == null or key == skip_key:
			continue
		var id := "%d/%s" % [target.get_instance_id(), key]
		if seen.has(id):
			continue
		seen[id] = true
		var body := r["collider"] as CollisionObject3D
		var owner := body.shape_owner_get_owner(body.shape_find_owner(int(r["shape"]))) as Node3D
		var d := owner.global_position.distance_to(point) if owner != null else radius
		var falloff := clampf(1.0 - d / radius, 0.0, 1.0)
		if falloff <= 0.0:
			continue
		var splash := info.duplicate()
		splash["key"] = key
		splash["damage"] = float(info.get("blast_damage", 0.0)) * falloff
		splash["penetration_mm"] = float(info.get("blast_penetration_mm", 8.0))
		splash["splash"] = true
		target.call("take_hit", splash)
		count += 1
	return count
