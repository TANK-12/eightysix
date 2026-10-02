class_name Destructible
extends Node3D
## A kit wall or building that takes hits and breaks for real (lane B5). Every kit piece (Parts.piece)
## has hit points from its volume and material. A hit (the same take_hit route projectiles use on
## mechs: CombatHits.receiver finds this node above the kit body) damages the piece it strikes and,
## by the ammo's reach, pieces around it; a piece at zero breaks off as a loose debris body thrown
## along the shot. Then support: any piece with nothing left under it falls too, so knocking out a
## ground floor brings the floors above down by itself. Below collapse_below of its volume the whole
## building comes down into debris and a rubble pile. The kit node is rebuilt without the broken
## pieces (Kit.build "gone"), so what you see and what you hit stay the same. Figures in tuning.json
## "destruction".

signal broke(count: int)
signal collapsed

const GROUND_EPS := 0.35  # a piece whose bottom is this close to the base stands on the ground
const WEAK_GROUP := "weak_points"  # Destructibles with a part the HUD marks (the bridge's bearings)
const TOUCH_EPS := 0.25  # how near a piece's top must be to the bottom of the one it holds up

static var _debris: Array[RigidBody3D] = []

var kit_id := ""
var seed_value := 0
var over := {}
var body: Node3D  # the current kit node (rebuilt as pieces break)
var draw_range := 0.0  # visibility_range_end for the kit's geometry (0: unlimited)
var pieces: Array = []  # every piece from the first build: xf, size, material, index
var hp := PackedFloat32Array()
var gone := {}  # piece index -> true
var is_collapsed := false
var listed: Array[Vector3] = []  # the anchors this node has put into a level's grapple_points
var _boxes: Array[AABB] = []  # each piece's box in this node's space
var _volume := 0.0
var _base_y := INF  # the bottom of the lowest piece as built: the ground it stands on
var _cfg: Dictionary


## A kit piece wrapped so it can be destroyed. Not breakable kit entries come back wrapped too, with
## no pieces (hits do nothing).
static func make(id: String, seed_v: int, overrides: Dictionary = {}, range_m: float = 0.0) -> Destructible:
	var d := Destructible.new()
	d.name = id.to_pascal_case()
	d.kit_id = id
	d.seed_value = seed_v
	d.over = overrides.duplicate()
	d.draw_range = range_m
	d._cfg = Registry.tune("destruction", {})
	d._rebuild()
	for p: Dictionary in d.body.get_meta("pieces", []):
		d.pieces.append(p)
	var hp_m3: Dictionary = d._cfg.get("hp_per_m3", {})
	d.hp.resize(d.pieces.size())
	for p: Dictionary in d.pieces:
		var size: Vector3 = p["size"]
		var v := size.x * size.y * size.z
		var i := int(p["index"])
		d.hp[i] = v * float(hp_m3.get(str(p["material"]), hp_m3.get("_default", 1000.0)))
		if bool(p.get("weak", false)):
			d.hp[i] *= float(d._cfg.get("weak_hp_scale", 1.0))
		d._boxes.append((p["xf"] as Transform3D) * AABB(-size * 0.5, size))
		d._base_y = minf(d._base_y, d._boxes[-1].position.y)
		if p.get("gone", false):
			d.gone[i] = true
		else:
			d._volume += v
	if d.pieces.any(func(q: Dictionary) -> bool: return bool(q.get("weak", false))):
		d.add_to_group(WEAK_GROUP)
	return d


## Share of the starting volume still standing (1 intact, 0 gone).
func integrity() -> float:
	if _volume <= 0.0:
		return 1.0
	var left := 0.0
	for p: Dictionary in pieces:
		if not gone.has(int(p["index"])):
			var s: Vector3 = p["size"]
			left += s.x * s.y * s.z
	return left / _volume


## Whether every span (a piece that needs two supports under it, like a bridge deck) is still up: a bridge
## that can be walked over.
func spans_standing() -> bool:
	if is_collapsed:
		return false
	for p: Dictionary in pieces:
		if int(p.get("needs", 1)) > 1 and gone.has(int(p["index"])):
			return false
	return true


## World positions of the weak parts still standing (steel bearings): what the combat HUD marks.
func weak_points() -> Array[Vector3]:
	var out: Array[Vector3] = []
	if is_collapsed:
		return out
	for p: Dictionary in pieces:
		var i := int(p["index"])
		if bool(p.get("weak", false)) and not gone.has(i):
			out.append(to_global(_boxes[i].get_center()))
	return out


## Every weak point standing within `range_m` of `from`, in any Destructible in the tree.
static func weak_marks(tree: SceneTree, from: Vector3, range_m: float) -> Array[Vector3]:
	var out: Array[Vector3] = []
	for n: Node in tree.get_nodes_in_group(WEAK_GROUP):
		for q: Vector3 in (n as Destructible).weak_points():
			if q.distance_to(from) <= range_m:
				out.append(q)
	return out


## The kit anchors (grapple points) on the current pieces, in world space.
func anchors() -> Array[Vector3]:
	var out: Array[Vector3] = []
	if body != null:
		for p: Vector3 in body.get_meta("anchors", []):
			out.append(body.global_transform * p)
	return out


## Puts this node's current anchors into a level's `grapple_points`, taking out the ones it listed
## before (anchors on pieces that have since broken off). Call once after placing, and again on `broke`.
func sync_anchors(points: Array[Vector3]) -> void:
	for p: Vector3 in listed:
		var at := points.find(p)
		if at >= 0:
			points.remove_at(at)
	listed = anchors()
	points.append_array(listed)


## Projectile hits arrive here (CombatHits.receiver). info: point, dir, damage, ammo (as projectile.gd).
func take_hit(info: Dictionary) -> Dictionary:
	if pieces.is_empty() or is_collapsed:
		return {}
	var ammo: Dictionary = _cfg.get("ammo", {}).get(str(info.get("ammo", "")), _cfg.get("ammo", {}).get("_default", {}))
	var reach := float(ammo.get("radius_m", 0.8))
	var dmg := float(info.get("damage", 0.0)) * float(ammo.get("scale", 1.0))
	var at := to_local(info.get("point", global_position))
	var struck := _nearest(at)
	var broken: Array[int] = []
	for p: Dictionary in pieces:
		var i := int(p["index"])
		if gone.has(i):
			continue
		var d := _distance_to_box(at, _boxes[i])
		var share := 1.0 if i == struck else clampf(1.0 - d / maxf(reach, 0.01), 0.0, 1.0)
		if share <= 0.0:
			continue
		hp[i] -= dmg * share
		if hp[i] <= 0.0:
			broken.append(i)
	_break(broken, info.get("dir", Vector3.ZERO), float(_cfg.get("throw_m_s", 6.0)))
	return {"broken": broken.size(), "integrity": integrity()}


## Breaks the listed pieces (thrown along `dir`), then everything left without support, then
## collapses if too little stands.
func _break(indices: Array[int], dir: Vector3, throw_m_s: float) -> void:
	if indices.is_empty():
		return
	var count := 0
	for i in indices:
		if not gone.has(i):
			gone[i] = true
			_spawn_debris(i, dir * throw_m_s)
			count += 1
	for i in _unsupported():
		gone[i] = true
		if int(pieces[i].get("needs", 1)) > 1:
			_spawn_slab(i)
		else:
			_spawn_debris(i, Vector3.ZERO)
		count += 1
	if integrity() < float(_cfg.get("collapse_below", 0.35)):
		collapse()
		return
	_rebuild()
	broke.emit(count)


## Everything still standing comes down: debris, a rubble pile and a dust cloud.
func collapse() -> void:
	if is_collapsed:
		return
	is_collapsed = true
	for p: Dictionary in pieces:
		var i := int(p["index"])
		if not gone.has(i):
			gone[i] = true
			_spawn_debris(i, Vector3(randf_range(-1, 1), 0.5, randf_range(-1, 1)))
	if body != null:
		body.queue_free()
		body = null
	var span := Vector3.ZERO
	for b in _boxes:
		span = span.max(b.end)
	var pile := Kit.build("rubble_pile", seed_value, {"size": clampf(maxf(span.x, span.z) * 0.6, 3.0, 9.0)})
	add_child(pile)
	if is_inside_tree():
		var dust := CombatFx.hit_dust()
		CombatFx.smoke(get_parent(), global_position + Vector3.UP * 1.5, Vector3.UP, 10, 6.0 * dust, Color(0.55, 0.5, 0.44, 0.45), 6.0 * CombatFx.dust_linger(dust), 1.2)
	collapsed.emit()


## Indices of standing pieces that nothing holds up any more (bottom up: a piece is held when its
## bottom is on the ground or rests on enough held pieces (its "needs", usually 1) whose boxes it overlaps
## from above).
func _unsupported() -> Array[int]:
	var order: Array[int] = []
	for p: Dictionary in pieces:
		if not gone.has(int(p["index"])):
			order.append(int(p["index"]))
	order.sort_custom(func(a: int, b: int) -> bool: return _boxes[a].position.y < _boxes[b].position.y)
	var held := {}
	var out: Array[int] = []
	for i in order:
		var b := _boxes[i]
		var ok := b.position.y <= _base_y + GROUND_EPS
		if not ok:
			var need := int(pieces[i].get("needs", 1))
			var holding := 0
			for j: int in held:
				var u := _boxes[j]
				if absf(u.end.y - b.position.y) <= TOUCH_EPS and u.end.y <= b.end.y and _overlap_xz(u, b):
					holding += 1
					if holding >= need:
						ok = true
						break
		if ok:
			held[i] = true
		else:
			out.append(i)
	return out


## A heavy slab that lost a support (a bridge span): it tips over its long side as it comes down, so it slides
## off the pier caps it would otherwise only drop onto, one way or the other by index.
func _spawn_slab(i: int) -> void:
	var side := 1.0 if i % 2 == 0 else -1.0
	var xf: Transform3D = (pieces[i]["xf"] as Transform3D)
	var out := global_transform.basis * xf.basis.z * side
	var deb := _spawn_debris(i, out * float(_cfg.get("slab_slide_m_s", 2.5)))
	if deb != null:
		deb.angular_velocity = (global_transform.basis * xf.basis.x) * side * float(_cfg.get("slab_tip_rad_s", 0.9))
		var slick := PhysicsMaterial.new()  # it slides on the pier cap (crushed bearing, concrete dust)
		slick.friction = float(_cfg.get("slab_friction", 0.08))
		deb.physics_material_override = slick


func _spawn_debris(i: int, velocity: Vector3) -> RigidBody3D:
	if not is_inside_tree():
		return null
	var p: Dictionary = pieces[i]
	var deb := Kit.debris(get_parent(), global_transform * (p["xf"] as Transform3D), p)
	deb.linear_velocity = velocity + Vector3(randf_range(-0.5, 0.5), randf_range(0.0, 0.8), randf_range(-0.5, 0.5))
	deb.angular_velocity = Vector3(randf_range(-2, 2), randf_range(-2, 2), randf_range(-2, 2))
	_debris.append(deb)
	var cap := int(_cfg.get("debris_cap", 160))
	while _debris.size() > cap:
		var old: Variant = _debris.pop_front()  # may be freed already (level left)
		if is_instance_valid(old):
			(old as RigidBody3D).queue_free()
	return deb


func _rebuild() -> void:
	var o := over.duplicate()
	o["gone"] = gone.duplicate()
	var fresh := Kit.build(kit_id, seed_value, o)
	if body != null:
		body.queue_free()
	body = fresh
	add_child(body)
	if draw_range > 0.0:
		for gi: Node in body.find_children("*", "GeometryInstance3D", true, false):
			(gi as GeometryInstance3D).visibility_range_end = draw_range


func _nearest(at: Vector3) -> int:
	var best := -1
	var best_d := INF
	for p: Dictionary in pieces:
		var i := int(p["index"])
		if gone.has(i):
			continue
		var d := _distance_to_box(at, _boxes[i])
		if d < best_d:
			best_d = d
			best = i
	return best


static func _distance_to_box(p: Vector3, b: AABB) -> float:
	var q := p.clamp(b.position, b.end)
	return p.distance_to(q)


static func _overlap_xz(a: AABB, b: AABB) -> bool:
	return a.position.x < b.end.x - 0.02 and b.position.x < a.end.x - 0.02 and a.position.z < b.end.z - 0.02 and b.position.z < a.end.z - 0.02
