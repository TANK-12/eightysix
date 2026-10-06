class_name BigCity
extends Node3D
## A real town's buildings (2026-10-03, maps part 2): every footprint in the map's osm.json (OpenStreetMap,
## made by tools/maps/osm_map.py) stood on the survey ground and raised to its height, many of them
## ruined (Eighty Six: the town was fought through). One mesh and one collider per chunk_m square, so a
## town of thousands of houses is a few dozen draw calls. Walls use the kit's facade materials (a PBR
## plaster, brick or concrete wall with a grid of windows, facade.gdshader; each wall gets its own UVs
## and a CUSTOM0 channel saying how long it is, its storey height, how ruined it is and its seed); roofs
## use masonry in batched mode. Intact houses get a pitched roof when their footprint is a small
## rectangle, otherwise a flat one. Mid-size props stand along the streets and in the ruins (power
## poles, burnt-out trucks, rubble piles; Emerson, crew note 750). The rules are the entry's "city"
## block: materials, how ruined, roof pitch, chunk size, draw range and "props".

const SINK_M := 0.6  # walls start this far under the lowest corner, so no gap shows on a slope
const GRID_M := 64.0  # blocked() looks up buildings in cells this size
const COLUMN_M := 2.6  # ruined walls break into columns about this wide, each with its own height


var terrain: BigTerrain
var cfg: Dictionary
## One per building: {"poly": PackedVector2Array (anticlockwise seen from above), "foot": float, "top":
## float, "ruin": float (0 intact, 1 flattened), "roof": "gable"|"flat"|"none", "kind": String}
var buildings: Array = []
var chunks := {}  # Vector2i -> {"mesh": MeshInstance3D, "body": StaticBody3D}
var rubble: Array[Vector3] = []  # where the flattened buildings left a heap (kit rubble piles)
var props: Array[Node3D] = []  # every street and ruin prop (kit pieces, copies of a few built ones)
var _grid := {}  # Vector2i (GRID_M cells) -> indices of the buildings whose box reaches into it


func setup(t: BigTerrain) -> void:
	terrain = t
	cfg = t.entry.get("city", {})
	var data := BigTerrain.osm(str(t.entry.get("osm", {}).get("file", "")))
	var rng := RandomNumberGenerator.new()
	rng.seed = int(cfg.get("seed", 86))
	var ruin_noise := FastNoiseLite.new()
	ruin_noise.seed = int(cfg.get("seed", 86))
	ruin_noise.frequency = float(cfg.get("ruin_patch_frequency", 0.004))
	var ruined := float(cfg.get("ruined_share", 0.45))
	var flattened := float(cfg.get("flattened_share", 0.08))
	for b: Dictionary in data.get("buildings", []):
		var flat: Array = b["p"]
		var poly := PackedVector2Array()
		for i in range(0, flat.size() - 1, 2):
			poly.append(Vector2(float(flat[i]), float(flat[i + 1])))
		if poly.size() < 3:
			continue
		if Geometry2D.is_polygon_clockwise(poly):
			poly.reverse()
		var lo := INF
		var hi := -INF
		var c := Vector2.ZERO
		for p: Vector2 in poly:
			var g := terrain.sample(p.x, p.y)
			lo = minf(lo, g)
			hi = maxf(hi, g)
			c += p
		c /= poly.size()
		# battle damage comes in patches (streets that were fought over), with a little luck per house
		var heat := clampf(ruin_noise.get_noise_2d(c.x, c.y) * 0.5 + 0.5 + rng.randf_range(-0.25, 0.25), 0.0, 1.0)
		var ruin := 0.0
		var roll := rng.randf()
		if roll < flattened * (0.5 + heat):
			ruin = 1.0
		elif roll < ruined * (0.4 + 1.2 * heat):
			ruin = rng.randf_range(0.25, 0.8)
		var h := float(b.get("h", 6.0))
		var roof := "none"
		if ruin == 0.0:
			roof = "gable" if _gable_ok(poly, str(b.get("kind", "")), int(b.get("levels", 2))) else "flat"
		buildings.append({"poly": poly, "foot": lo - SINK_M, "top": hi + h, "h": h, "ruin": ruin, "roof": roof, "kind": str(b.get("kind", "yes")), "levels": int(b.get("levels", 2)), "c": c, "seed": rng.randi()})
		if ruin == 1.0:
			rubble.append(Vector3(c.x, lo, c.y))
		var box := Rect2(poly[0], Vector2.ZERO)
		for p: Vector2 in poly:
			box = box.expand(p)
		for gz in range(floori(box.position.y / GRID_M), floori(box.end.y / GRID_M) + 1):
			for gx in range(floori(box.position.x / GRID_M), floori(box.end.x / GRID_M) + 1):
				var k := Vector2i(gx, gz)
				if not _grid.has(k):
					_grid[k] = []
				(_grid[k] as Array).append(buildings.size() - 1)
	_build()
	_build_props()


## True for a footprint that takes a pitched roof: four corners, near-square angles, not too wide.
func _gable_ok(poly: PackedVector2Array, kind: String, levels: int) -> bool:
	if poly.size() != 4 or levels > int(cfg.get("gable_max_levels", 4)) or kind in cfg.get("flat_kinds", []):
		return false
	for i in 4:
		var a := (poly[(i + 1) % 4] - poly[i]).normalized()
		var b := (poly[(i + 2) % 4] - poly[(i + 1) % 4]).normalized()
		if absf(a.dot(b)) > 0.2:
			return false
	var short := minf(poly[0].distance_to(poly[1]), poly[1].distance_to(poly[2]))
	return short <= float(cfg.get("gable_max_span_m", 16.0))


func _build() -> void:
	var chunk_m := float(cfg.get("chunk_m", 256.0))
	var by_chunk := {}
	for i in buildings.size():
		var c: Vector2 = buildings[i]["c"]
		var key := Vector2i(floori(c.x / chunk_m), floori(c.y / chunk_m))
		if not by_chunk.has(key):
			by_chunk[key] = []
		by_chunk[key].append(i)
	var walls := _wall_ids()
	var mats := {}
	for id: String in walls + [str(cfg.get("roof_material", "roof_slate")), str(cfg.get("flat_roof_material", "concrete"))]:
		if mats.has(id):
			continue
		var m := Kit.material(id).duplicate() as Material
		if m is ShaderMaterial and (m as ShaderMaterial).shader.resource_path.ends_with("masonry.gdshader"):
			(m as ShaderMaterial).set_shader_parameter("batched", true)
		mats[id] = m
	for key: Vector2i in by_chunk:
		var surfaces := {}  # material id -> SurfaceTool
		var faces := PackedVector3Array()
		for i: int in by_chunk[key]:
			_add_building(buildings[i], surfaces, faces)
		var mesh := ArrayMesh.new()
		for id: String in surfaces:
			var st: SurfaceTool = surfaces[id]
			st.generate_normals()
			if id in walls:
				st.generate_tangents()  # the facade's normal maps
			st.commit(mesh)
			mesh.surface_set_material(mesh.get_surface_count() - 1, mats[id])
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.visibility_range_end = float(cfg.get("draw_m", 1600.0))
		mi.visibility_range_end_margin = 100.0
		mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		add_child(mi)
		var body := StaticBody3D.new()
		body.collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE
		body.collision_mask = 0
		var shape := ConcavePolygonShape3D.new()
		shape.backface_collision = true
		shape.set_faces(faces)
		var cs := CollisionShape3D.new()
		cs.shape = shape
		body.add_child(cs)
		add_child(body)
		chunks[key] = {"mesh": mi, "body": body}


## Every wall material the town uses: the houses' list, the heavy (concrete) one, the ruins' one.
func _wall_ids() -> Array:
	var ids: Array = cfg.get("wall_materials", ["facade_white"]).duplicate()
	for id: String in [str(cfg.get("heavy_wall_material", "facade_concrete")), str(cfg.get("ruin_wall_material", "facade_damaged"))]:
		if not id in ids:
			ids.append(id)
	return ids


## The chunk's SurfaceTool for a material; flat-shaded (corners stay sharp), and a wall surface carries
## the facade's CUSTOM0 channel.
func _surface(surfaces: Dictionary, id: String, wall: bool = false) -> SurfaceTool:
	if not surfaces.has(id):
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		st.set_smooth_group(-1)
		if wall:
			st.set_custom_format(0, SurfaceTool.CUSTOM_RGBA_FLOAT)
		surfaces[id] = st
	return surfaces[id]


## Walls (and the inside face when the roof is gone), the roof, into the chunk's surfaces and collider faces.
func _add_building(b: Dictionary, surfaces: Dictionary, faces: PackedVector3Array) -> void:
	var poly: PackedVector2Array = b["poly"]
	var rng := RandomNumberGenerator.new()
	rng.seed = int(b["seed"])
	var foot := float(b["foot"])
	var top := float(b["top"])
	var ruin := float(b["ruin"])
	var levels := int(b["levels"])
	var heavy: bool = str(b["kind"]) in cfg.get("concrete_kinds", []) or levels >= 4
	var houses: Array = cfg.get("wall_materials", ["facade_white"])
	var wall_id := str(houses[rng.randi() % houses.size()])
	if heavy:
		wall_id = str(cfg.get("heavy_wall_material", "facade_concrete"))
	elif ruin > 0.0 and rng.randf() < float(cfg.get("ruin_wall_share", 0.5)):
		wall_id = str(cfg.get("ruin_wall_material", "facade_damaged"))
	var st := _surface(surfaces, wall_id, true)
	var c: Vector2 = b["c"]
	# storey height from the mapped height and storeys; a flattened stub gets no windows
	var storey := clampf(float(b["h"]) / maxi(levels, 1), 2.6, 4.2) if ruin < 1.0 else 0.0
	var info := Color(0.0, storey, ruin, levels + float(int(b["seed"]) % 997) / 1000.0)
	var tag := [Vector2(foot, LEVEL_STOREY), Vector2(c.x, c.y)]
	# a ruin's walls are columns of different heights; a flattened house keeps a ragged stub
	var n := poly.size()
	var span := top - foot
	for i in n:
		var a := poly[i]
		var e := poly[(i + 1) % n]
		var length := a.distance_to(e)
		info.r = length
		var cols := 1 if ruin == 0.0 else maxi(int(ceil(length / COLUMN_M)), 1)
		var prev_h := top if ruin == 0.0 else _ruin_top(foot, span, ruin, rng)
		for k in cols:
			var p0 := a.lerp(e, float(k) / cols)
			var p1 := a.lerp(e, float(k + 1) / cols)
			var h1 := top if ruin == 0.0 else _ruin_top(foot, span, ruin, rng)
			var q := [Vector3(p0.x, foot, p0.y), Vector3(p1.x, foot, p1.y), Vector3(p1.x, h1, p1.y), Vector3(p0.x, prev_h, p0.y)]
			var along := [length * k / cols, length * (k + 1) / cols, length * (k + 1) / cols, length * k / cols]
			_wall_quad(st, q, along, foot, info, c, faces, ruin > 0.0)
			prev_h = h1
	match str(b["roof"]):
		"gable":
			_gable(b, surfaces, faces, tag, st, Color(0.0, 0.0, ruin, info.a))
		"flat":
			var rst := _surface(surfaces, str(cfg.get("flat_roof_material", "concrete")))
			var tris := Geometry2D.triangulate_polygon(poly)
			for j in range(0, tris.size(), 3):
				# anticlockwise from above, so the triangle faces up with this winding in Godot
				for idx: int in [tris[j], tris[j + 2], tris[j + 1]]:
					_vert(rst, Vector3(poly[idx].x, top, poly[idx].y), [Vector2(foot, 0.0), c])
					faces.append(Vector3(poly[idx].x, top, poly[idx].y))


const LEVEL_STOREY := 3.0


func _ruin_top(foot: float, span: float, ruin: float, rng: RandomNumberGenerator) -> float:
	if ruin >= 1.0:
		return foot + SINK_M + rng.randf_range(0.3, 1.8)
	return foot + span * clampf(1.0 - ruin * rng.randf_range(0.35, 1.25), 0.12, 1.0)


## A pitched roof along the rectangle's long side (gable ends close the triangle under it).
func _gable(b: Dictionary, surfaces: Dictionary, faces: PackedVector3Array, tag: Array, wall_st: SurfaceTool, info: Color) -> void:
	var poly: PackedVector2Array = b["poly"]
	var top := float(b["top"])
	var long_first := poly[0].distance_to(poly[1]) >= poly[1].distance_to(poly[2])
	# corners so that a-b and d-c are the long sides (eaves) and b-c, d-a the gable ends
	var a := poly[0] if long_first else poly[1]
	var bb := poly[1] if long_first else poly[2]
	var c := poly[2] if long_first else poly[3]
	var d := poly[3] if long_first else poly[0]
	var span := a.distance_to(d)
	var rise := span * 0.5 * tan(deg_to_rad(float(cfg.get("roof_pitch_deg", 40.0))))
	var m0 := (a + d) * 0.5
	var m1 := (bb + c) * 0.5
	var A := Vector3(a.x, top, a.y)
	var B := Vector3(bb.x, top, bb.y)
	var C := Vector3(c.x, top, c.y)
	var D := Vector3(d.x, top, d.y)
	var R0 := Vector3(m0.x, top + rise, m0.y)
	var R1 := Vector3(m1.x, top + rise, m1.y)
	# small overhang at the eaves
	var out_ab := (A - D).normalized() * 0.4
	var out_dc := (D - A).normalized() * 0.4
	var roof_st := _surface(surfaces, str(cfg.get("roof_material", "roof_slate")))
	var rtag := [Vector2(top, 0.0), tag[1]]
	_quad(roof_st, [A + out_ab - Vector3(0, 0.25, 0), B + out_ab - Vector3(0, 0.25, 0), R1, R0], rtag, faces, false)
	_quad(roof_st, [C + out_dc - Vector3(0, 0.25, 0), D + out_dc - Vector3(0, 0.25, 0), R0, R1], rtag, faces, false)
	# the gable ends: wall material without windows (storey 0), UV along the end wall
	var foot := float(b["foot"])
	for tri: Array in [[B, C, R1], [D, A, R0]]:
		var w: float = (tri[0] as Vector3).distance_to(tri[1])
		info.r = w
		var along := [0.0, w, w * 0.5]
		for j in 3:
			_wvert(wall_st, tri[j], Vector2(along[j], (tri[j] as Vector3).y - foot), info, tag[1])
			faces.append(tri[j])


## One quad (corners anticlockwise seen from the side it faces), and its back when `both`.
func _quad(st: SurfaceTool, q: Array, tag: Array, faces: PackedVector3Array, both: bool) -> void:
	for idx: int in [0, 1, 2, 0, 2, 3]:
		_vert(st, q[idx], tag)
		faces.append(q[idx])
	if both:
		for idx: int in [0, 2, 1, 0, 3, 2]:
			_vert(st, q[idx], tag)


func _vert(st: SurfaceTool, v: Vector3, tag: Array) -> void:
	st.set_uv(tag[0])
	st.set_uv2(tag[1])
	st.add_vertex(v)


## One wall quad for the facade shader: UV = (metres along the wall, metres above the foot), UV2 = the
## building's centre, CUSTOM0 = info. `along` holds each corner's distance along the wall.
func _wall_quad(st: SurfaceTool, q: Array, along: Array, foot: float, info: Color, c: Vector2, faces: PackedVector3Array, both: bool) -> void:
	for idx: int in [0, 1, 2, 0, 2, 3]:
		_wvert(st, q[idx], Vector2(along[idx], (q[idx] as Vector3).y - foot), info, c)
		faces.append(q[idx])
	if both:
		for idx: int in [0, 2, 1, 0, 3, 2]:
			_wvert(st, q[idx], Vector2(along[idx], (q[idx] as Vector3).y - foot), info, c)


func _wvert(st: SurfaceTool, v: Vector3, uv: Vector2, info: Color, c: Vector2) -> void:
	st.set_uv(uv)
	st.set_uv2(c)
	st.set_custom(0, info)
	st.add_vertex(v)


## Street and ruin props from the entry's "props" block: power poles every pole_every_m along one side
## of the listed road kinds, burnt-out trucks parked at the kerb (wrecks_per_km), a rubble pile on every
## flattened house (up to rubble_max). Each kind is built `variants` times and copied, so a thousand
## props cost a handful of meshes; they are solid but do not break (a Destructible each would take
## seconds to build).
func _build_props() -> void:
	var pc: Dictionary = cfg.get("props", {})
	if pc.is_empty():
		return
	var holder := Node3D.new()
	holder.name = "Props"
	add_child(holder)
	var rng := RandomNumberGenerator.new()
	rng.seed = int(cfg.get("seed", 86)) + 7
	var draw_m := float(pc.get("draw_m", 700.0))
	var protos := {}
	for id: String in [str(pc.get("pole", "power_pole")), str(pc.get("wreck", "wreck_truck")), str(pc.get("rubble", "rubble_pile"))]:
		protos[id] = []
		for k in int(pc.get("variants", 3)):
			var node := Kit.build(id, int(cfg.get("seed", 86)) * 10 + k)
			var mi := node.get_node_or_null("Mesh") as MeshInstance3D
			if mi != null:
				mi.visibility_range_end = draw_m
				mi.visibility_range_end_margin = 40.0
				mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			protos[id].append(node)
	var cap := int(pc.get("max", 1500))
	var data := BigTerrain.osm(str(terrain.entry.get("osm", {}).get("file", "")))
	var pole_kinds: Array = pc.get("pole_kinds", ["residential", "tertiary", "secondary", "primary", "living_street", "unclassified"])
	var wreck_kinds: Array = pc.get("wreck_kinds", ["residential", "tertiary", "secondary", "primary", "service"])
	var pole_every := float(pc.get("pole_every_m", 50.0))
	var wreck_chance := float(pc.get("wrecks_per_km", 3.0)) / 1000.0
	for road: Dictionary in data.get("roads", []):
		var kind := str(road.get("kind", ""))
		var half := float(road.get("width_m", 6.0)) * 0.5
		var pts: Array = road.get("points", [])
		var side := 1.0 if rng.randf() < 0.5 else -1.0
		var next_pole := rng.randf_range(0.0, pole_every)
		var run := 0.0
		for i in pts.size() - 1:
			var a := Vector2(float(pts[i][0]), float(pts[i][1]))
			var e := Vector2(float(pts[i + 1][0]), float(pts[i + 1][1]))
			var seg := a.distance_to(e)
			if seg < 0.01:
				continue
			var dir := (e - a) / seg
			var out := Vector2(-dir.y, dir.x) * side
			if kind in pole_kinds:
				while next_pole <= run + seg and props.size() < cap:
					var p := a + dir * (next_pole - run) + out * (half + 1.2)
					_place(holder, protos[str(pc.get("pole", "power_pole"))], p, rng.randf() * TAU, rng)
					next_pole += pole_every
			if kind in wreck_kinds and rng.randf() < wreck_chance * seg and props.size() < cap:
				var p := a + dir * rng.randf_range(0.0, seg) + out * maxf(half - 1.6, 0.0)
				_place(holder, protos[str(pc.get("wreck", "wreck_truck"))], p, -dir.angle() + rng.randf_range(-0.35, 0.35), rng, false)
			run += seg
	var piles := 0
	for r: Vector3 in rubble:
		if piles >= int(pc.get("rubble_max", 400)) or props.size() >= cap:
			break
		_place(holder, protos[str(pc.get("rubble", "rubble_pile"))], Vector2(r.x, r.z), rng.randf() * TAU, rng, false)
		piles += 1
	for id: String in protos:
		for node: Node3D in protos[id]:
			node.free()


## A copy of one of `protos` standing on the ground at p (x, z), turned by yaw; skipped inside a house
## when `clear` (a pole is never put through a wall).
func _place(holder: Node3D, protos: Array, p: Vector2, yaw: float, rng: RandomNumberGenerator, clear: bool = true) -> void:
	if clear and blocked(p.x, p.y, 0.6):
		return
	var node := (protos[rng.randi() % protos.size()] as Node3D).duplicate() as Node3D
	node.position = Vector3(p.x, terrain.sample(p.x, p.y) - 0.05, p.y)
	node.rotation.y = yaw
	holder.add_child(node)
	props.append(node)


## True when (x, z) is inside a building's footprint, or within `pad` metres of one (pad < GRID_M).
func blocked(x: float, z: float, pad: float = 0.0) -> bool:
	var p := Vector2(x, z)
	var seen := {}
	for gz in range(floori((z - pad) / GRID_M), floori((z + pad) / GRID_M) + 1):
		for gx in range(floori((x - pad) / GRID_M), floori((x + pad) / GRID_M) + 1):
			for i: int in _grid.get(Vector2i(gx, gz), []):
				if seen.has(i):
					continue
				seen[i] = true
				var poly: PackedVector2Array = buildings[i]["poly"]
				if Geometry2D.is_point_in_polygon(p, poly):
					return true
				if pad > 0.0:
					for j in poly.size():
						if Geometry2D.get_closest_point_to_segment(p, poly[j], poly[(j + 1) % poly.size()]).distance_to(p) < pad:
							return true
	return false
