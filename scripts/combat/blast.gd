class_name Blast
extends RefCounted
## The air blast of a high-explosive burst, from published fits (lane A4 part 2), so a near miss
## shoves a mech only as hard as a real shell could. Kinney & Graham's free-air fits ("Explosive
## Shocks in Air", 1985) give the side-on peak overpressure and positive-phase impulse at scaled
## distance Z = R / W^(1/3) (m / kg^(1/3), W in kg of TNT); they sit close to the Kingery-Bulmash
## charts the military manuals use. A burst on the ground reflects off it, so it acts like a free-air
## charge "surface_factor" (1.8, soil) times heavier. A surface facing the burst feels the reflected
## pressure: Pr = 2 Ps (7 P0 + 4 Ps) / (7 P0 + Ps) (Rankine-Hugoniot, air); the same factor scales
## the impulse. A body takes that impulse times the area it shows the burst, so the push follows from
## the shell's filler and the distance alone: no typed-in "wake" force.
##
## What it gives (2.0 kg TNT on the ground, a 120 mm HEAT-MP shell, tests/test_ai.gd): about 6.3 kN s
## on the 5.6 t Juggernaut 2 m off its side (1.1 m/s), 2.8 kN s at 5 m (0.5 m/s), 1.0 kN s at 15 m
## (0.18 m/s). A near miss staggers, a close one shoves hard; the 57 mm's own recoil is 5.6 kN s.
## The supersonic wake of a passing round (Whitham's N-wave; a 120 mm dart at 3.5 m: about 1 kPa
## over 0.36 ms) pushes then pulls by the same amount; the push half is about 0.1 Pa s, under 1 N s
## on the Juggernaut's whole side: a crack you hear, no shove at all.

const P0 := 101325.0  # Pa, sea-level air
const SURFACE_FACTOR := 1.8
## Beyond this scaled distance the push is too small to matter (about 10 kPa side-on).
const Z_MAX := 12.0


## Side-on peak overpressure, Pa, at `r_m` from `tnt_kg` in free air.
static func overpressure_pa(r_m: float, tnt_kg: float) -> float:
	var z := scaled(r_m, tnt_kg)
	var num := 808.0 * (1.0 + pow(z / 4.5, 2.0))
	var den := sqrt((1.0 + pow(z / 0.048, 2.0)) * (1.0 + pow(z / 0.32, 2.0)) * (1.0 + pow(z / 1.35, 2.0)))
	return P0 * num / den


## Side-on positive-phase impulse, Pa s, at `r_m` from `tnt_kg` in free air.
static func impulse_pa_s(r_m: float, tnt_kg: float) -> float:
	var w3 := pow(maxf(tnt_kg, 1e-6), 1.0 / 3.0)
	var z := scaled(r_m, tnt_kg)
	var bar_ms := 0.067 * sqrt(1.0 + pow(z / 0.23, 4.0)) / (z * z * pow(1.0 + pow(z / 1.55, 3.0), 1.0 / 3.0))
	return bar_ms * 100.0 * w3  # 1 bar ms = 100 Pa s


## How much harder a face-on surface is pushed than the side-on figure (2 for a weak wave, up to 8).
static func reflection(ps_pa: float) -> float:
	return 2.0 * (7.0 * P0 + 4.0 * ps_pa) / (7.0 * P0 + ps_pa)


static func scaled(r_m: float, tnt_kg: float) -> float:
	return maxf(r_m, 0.05) / pow(maxf(tnt_kg, 1e-6), 1.0 / 3.0)


## The furthest a burst of `tnt_kg` (already surface-scaled) pushes anything worth counting.
static func reach_m(tnt_kg: float) -> float:
	return Z_MAX * pow(maxf(tnt_kg, 1e-6), 1.0 / 3.0)


## Reflected impulse per square metre on a face turned to the burst, Pa s.
static func face_impulse(r_m: float, tnt_kg: float) -> float:
	return impulse_pa_s(r_m, tnt_kg) * reflection(overpressure_pa(r_m, tnt_kg))


## Pushes every mech and loose body near a burst at `point` (`tnt_kg` of filler; `on_ground` for a
## burst on impact). Each collider of a body takes the face impulse at its own distance over the area
## its box shows the burst, at its own centre, so the near side is pushed harder and a body in the air
## spins. A collider is skipped when the line from the burst meets another part of the same body or
## the world first (it is in their shadow). Returns [{"body", "impulse_ns"}] for what it pushed.
static func push(space: PhysicsDirectSpaceState3D, point: Vector3, tnt_kg: float, on_ground: bool = true) -> Array:
	var w := tnt_kg * (SURFACE_FACTOR if on_ground else 1.0)
	var reach := reach_m(w)
	var sphere := SphereShape3D.new()
	sphere.radius = reach
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = sphere
	q.transform = Transform3D(Basis.IDENTITY, point)
	q.collision_mask = 2 | 16
	var seen := {}
	var out: Array = []
	for r: Dictionary in space.intersect_shape(q, 64):
		var body := r["collider"] as RigidBody3D
		if body == null or seen.has(body.get_instance_id()):
			continue
		seen[body.get_instance_id()] = true
		var total := Vector3.ZERO
		for part: Array in body_parts(body):
			var box: AABB = part[1]
			var world_c := body.global_transform * box.get_center()
			var local := body.global_transform.affine_inverse() * point
			var dist := local.distance_to(local.clamp(box.position, box.end))
			if dist > reach or not _in_sight(space, point, world_c, body, int(part[0])):
				continue
			var dir := (world_c - point).normalized()
			var dir_l := body.global_transform.basis.inverse() * dir
			var sz := box.size
			var area := absf(dir_l.x) * sz.y * sz.z + absf(dir_l.y) * sz.x * sz.z + absf(dir_l.z) * sz.x * sz.y
			var j := dir * face_impulse(maxf(dist, 0.1), w) * area
			body.apply_impulse(j, world_c - body.global_position)
			total += j
		if total.length() > 0.0:
			out.append({"body": body, "impulse_ns": total.length()})
	return out


## True when nothing (the world or another part of `body`) stands between the burst and the part
## with shape owner `owner_id`.
static func _in_sight(space: PhysicsDirectSpaceState3D, from: Vector3, to: Vector3, body: CollisionObject3D, owner_id: int) -> bool:
	var q := PhysicsRayQueryParameters3D.create(from, to, 1 | body.collision_layer)
	var hit := space.intersect_ray(q)
	if hit.is_empty():
		return true
	if hit["collider"] != body:
		return false
	return body.shape_find_owner(int(hit["shape"])) == owner_id


## [shape owner id, AABB in the body's frame] for every enabled collider of `body` (cached: the
## colliders keep their shape; a lost armour panel is skipped by its disabled flag).
static func body_parts(body: CollisionObject3D) -> Array:
	var cached: Array = body.get_meta("blast_parts") if body.has_meta("blast_parts") else []
	if cached.is_empty():
		for owner_id in body.get_shape_owners():
			var xf := body.shape_owner_get_transform(owner_id)
			for k in body.shape_owner_get_shape_count(owner_id):
				cached.append([owner_id, xf * body.shape_owner_get_shape(owner_id, k).get_debug_mesh().get_aabb()])
		body.set_meta("blast_parts", cached)
	return cached.filter(func(p: Array) -> bool: return not body.is_shape_owner_disabled(int(p[0])))
