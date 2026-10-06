class_name BigForest
extends Node3D
## A forest of fir trees over a streamed map (2026-10-03, maps part 2: "grassland, forest, and normal
## cities"). Trees stand on a jittered grid (`cell_m` apart, so a mech always finds a lane between
## trunks), thinned by `density`, cleared in noise patches, kept off roads, water, steep ground and the
## spawn, and only where the map's woods mask (osm_map.py woods.png) is white. Near the camera each
## 128 m tile draws its trees as one MultiMesh of a real tree (bark trunk and bough cards); beyond
## near_m every tree is one billboard in a few big MultiMeshes, so the whole map's forest is a few
## dozen draw calls. Trunks get colliders only in the tiles round each mech. The rules are the map
## entry's "forest" block; textures come from tools/maps/tree_textures.py (Poly Haven fir_tree_01 bark).

const TEX := "res://assets/trees/fir/"
const SHADER := preload("res://assets/trees/tree.gdshader")
const TREE_H := 20.0  # the tree mesh's height (m); each tree is scaled to its own height
const SINK_M := 1.5  # the trunk starts this far under the ground, so no tree floats on a slope
const FAR_CHUNK := 4  # far billboards: one MultiMesh per this many tiles each way
const TRUNK_HIT_R := 0.45  # trunk collider radius (m)
const TRUNK_HIT_H := 10.0

var terrain: BigTerrain
var cfg: Dictionary
## Vector2i tile -> PackedFloat32Array of [x, y, z, scale, turn] per tree
var trees := {}
var count := 0
var near_m := 240.0
var _near := {}  # tile -> MultiMeshInstance3D
var _bodies := {}  # tile -> StaticBody3D
var _exact := {}  # tiles whose heights were sampled on the 1 m ground
var _tree_mesh: ArrayMesh
var _shape: CylinderShape3D
var _wait := 0.0


## `avoid(x, z)` true keeps a tree off that spot (the city's buildings).
func setup(t: BigTerrain, avoid: Callable = Callable()) -> void:
	terrain = t
	cfg = t.entry.get("forest", {})
	near_m = float(cfg.get("near_m", 240.0)) * (0.6 + 0.4 * clampf(Settings.get_f("graphics.foliage_density"), 0.0, 1.0))
	trees = BigForest.plan(t, cfg, avoid)
	for key: Vector2i in trees:
		count += (trees[key] as PackedFloat32Array).size() / 5
	_tree_mesh = _make_tree()
	_shape = CylinderShape3D.new()
	_shape.radius = TRUNK_HIT_R
	_shape.height = TRUNK_HIT_H
	_build_far()


## Where the trees stand: {tile: [x, y, z, scale, turn] * n}. y is the 8 m overview's height (the near
## tiles refine it on the 1 m ground). Pure apart from reading the mask, so a test can call it.
static func plan(t: BigTerrain, c: Dictionary, avoid: Callable = Callable()) -> Dictionary:
	var out := {}
	var cell := float(c.get("cell_m", 11.0))
	var jitter := float(c.get("jitter", 0.2))
	var density := float(c.get("density", 0.75))
	var road_clear := float(c.get("road_clear_m", 4.0))
	var water_clear := float(c.get("water_clear_m", 6.0))
	var max_slope := cos(deg_to_rad(float(c.get("max_slope_deg", 38.0))))
	var hs: Array = c.get("height_m", [16.0, 26.0])
	var edge := t.half - float(c.get("edge_m", 30.0))
	var spawn: Array = t.entry.get("spawn", {}).get("position", [0.0, 0.0, 0.0])
	var spawn_at := Vector2(float(spawn[0]), float(spawn[2]))
	var spawn_clear := float(c.get("spawn_clear_m", 30.0))
	var clearing := FastNoiseLite.new()
	clearing.seed = int(c.get("seed", 1))
	clearing.frequency = float(c.get("clearing_frequency", 0.006))
	var clear_cut := float(c.get("clearing_cut", -0.35))
	var mask: Image = null
	if c.has("mask"):
		var tex := load(str(c["mask"])) as Texture2D
		if tex != null:
			mask = tex.get_image()
			if mask.is_compressed():
				mask.decompress()
	var mask_k := (mask.get_width() / float(t.size_m)) if mask != null else 0.0
	var rng := RandomNumberGenerator.new()
	rng.seed = int(c.get("seed", 1))
	var n := int(t.size_m / cell)
	for iz in n:
		for ix in n:
			var x := -t.half + (ix + 0.5 + rng.randf_range(-jitter, jitter)) * cell
			var z := -t.half + (iz + 0.5 + rng.randf_range(-jitter, jitter)) * cell
			var keep := rng.randf() < density
			var size := rng.randf_range(float(hs[0]), float(hs[1])) / TREE_H
			var turn := rng.randf() * TAU
			if not keep or absf(x) > edge or absf(z) > edge:
				continue
			if mask != null and mask.get_pixel(clampi(int((x + t.half) * mask_k), 0, mask.get_width() - 1), clampi(int((z + t.half) * mask_k), 0, mask.get_height() - 1)).r < 0.5:
				continue
			if clearing.get_noise_2d(x, z) < clear_cut or Vector2(x, z).distance_to(spawn_at) < spawn_clear:
				continue
			if t.road_edge_at(x, z) < road_clear or t.water_edge_at(x, z) < water_clear:
				continue
			if avoid.is_valid() and avoid.call(x, z):
				continue
			var e := 4.0
			var nrm := Vector3(t.overview_height(x - e, z) - t.overview_height(x + e, z), 2.0 * e, t.overview_height(x, z - e) - t.overview_height(x, z + e)).normalized()
			if nrm.y < max_slope:
				continue
			var y := t.overview_height(x, z)
			# packed arrays are values: take the tile's, add to it, put it back
			var key := t.tile_of(x, z)
			var a: PackedFloat32Array = out.get(key, PackedFloat32Array())
			a.append_array([x, y, z, size, turn])
			out[key] = a
	return out


## True when a tree trunk stands within `r` metres of (x, z) (tests, and anything placed later).
func trunk_near(x: float, z: float, r: float) -> bool:
	var key := terrain.tile_of(x, z)
	for dz in range(-1, 2):
		for dx in range(-1, 2):
			var a: PackedFloat32Array = trees.get(Vector2i(key.x + dx, key.y + dz), PackedFloat32Array())
			for i in range(0, a.size(), 5):
				if Vector2(a[i], a[i + 2]).distance_to(Vector2(x, z)) < r:
					return true
	return false


func near_tiles() -> int:
	return _near.size()


func body_tiles() -> int:
	return _bodies.size()


func _process(delta: float) -> void:
	_wait -= delta
	if _wait > 0.0:
		return
	_wait = 0.2
	update()


## Near meshes round the camera, trunk colliders round every mech; both dropped once out of reach.
func update() -> void:
	var cam := get_viewport().get_camera_3d() if is_inside_tree() else null
	var want_near := {}
	if cam != null:
		var c := terrain.tile_of(cam.global_position.x, cam.global_position.z)
		var r := int(ceil(near_m / BigTerrain.TILE_M))
		for dz in range(-r, r + 1):
			for dx in range(-r, r + 1):
				want_near[Vector2i(c.x + dx, c.y + dz)] = true
	var built := 0
	for key: Vector2i in want_near:
		if not _near.has(key) and trees.has(key) and built < 4:
			_near[key] = _build_near(key)
			built += 1
	for key: Vector2i in _near.keys():
		if not want_near.has(key):
			(_near[key] as Node).queue_free()
			_near.erase(key)
	var want_body := {}
	if is_inside_tree():
		for m: Node in get_tree().get_nodes_in_group("mechs"):
			var p := (m as Node3D).global_position
			var c := terrain.tile_of(p.x, p.z)
			for dz in range(-1, 2):
				for dx in range(-1, 2):
					want_body[Vector2i(c.x + dx, c.y + dz)] = true
	for key: Vector2i in want_body:
		if not _bodies.has(key) and trees.has(key):
			_bodies[key] = _build_body(key)
	for key: Vector2i in _bodies.keys():
		if not want_body.has(key):
			(_bodies[key] as Node).queue_free()
			_bodies.erase(key)


## Puts the colliders and near trees round `at` in place now (before a mech is parked there).
func prime(at: Vector3) -> void:
	var c := terrain.tile_of(at.x, at.z)
	for dz in range(-1, 2):
		for dx in range(-1, 2):
			var key := Vector2i(c.x + dx, c.y + dz)
			if trees.has(key) and not _bodies.has(key):
				_bodies[key] = _build_body(key)


## The tile's trees on the 1 m ground (the same surface the near tiles' colliders use).
func _refine(key: Vector2i) -> PackedFloat32Array:
	var a: PackedFloat32Array = trees[key]
	if not _exact.has(key):
		for i in range(0, a.size(), 5):
			a[i + 1] = terrain.sample(a[i], a[i + 2])
		trees[key] = a
		_exact[key] = true
	return a


func _build_near(key: Vector2i) -> MultiMeshInstance3D:
	var a := _refine(key)
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = _tree_mesh
	mm.instance_count = a.size() / 5
	for i in mm.instance_count:
		var s := a[i * 5 + 3]
		var b := Basis(Vector3.UP, a[i * 5 + 4]).scaled(Vector3(s, s, s))
		mm.set_instance_transform(i, Transform3D(b, Vector3(a[i * 5], a[i * 5 + 1], a[i * 5 + 2])))
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if bool(cfg.get("shadows", true)) else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	return mi


func _build_body(key: Vector2i) -> StaticBody3D:
	var a := _refine(key)
	var body := StaticBody3D.new()
	body.collision_layer = Kit.LAYER_WORLD | Kit.LAYER_GRAPPLE
	body.collision_mask = 0
	for i in range(0, a.size(), 5):
		var cs := CollisionShape3D.new()
		cs.shape = _shape
		cs.position = Vector3(a[i], a[i + 1] + TRUNK_HIT_H * 0.5 - SINK_M, a[i + 2])
		body.add_child(cs)
	add_child(body)
	return body


## Every tree as a billboard, one MultiMesh per FAR_CHUNK x FAR_CHUNK tiles (the shader hides the
## ones within near_m, where the near meshes draw).
func _build_far() -> void:
	var quad := ArrayMesh.new()
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	var w := TREE_H * 0.25
	arr[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-w, -SINK_M * 0.3, 0), Vector3(w, -SINK_M * 0.3, 0), Vector3(w, TREE_H, 0), Vector3(-w, TREE_H, 0)])
	arr[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.BACK, Vector3.BACK, Vector3.BACK, Vector3.BACK])
	arr[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2(0, 1), Vector2(1, 1), Vector2(1, 0), Vector2(0, 0)])
	arr[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 2, 1, 0, 3, 2])
	quad.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	quad.surface_set_material(0, _material(2, "far.png", ""))
	quad.custom_aabb = AABB(Vector3(-w * 2.0, -SINK_M, -w * 2.0), Vector3(w * 4.0, TREE_H + SINK_M, w * 4.0))
	var chunks := {}
	for key: Vector2i in trees:
		var ck := Vector2i(key.x / FAR_CHUNK, key.y / FAR_CHUNK)
		var a: PackedFloat32Array = chunks.get(ck, PackedFloat32Array())
		a.append_array(trees[key])
		chunks[ck] = a
	for ck: Vector2i in chunks:
		var a: PackedFloat32Array = chunks[ck]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = quad
		mm.instance_count = a.size() / 5
		for i in mm.instance_count:
			var s := a[i * 5 + 3]
			mm.set_instance_transform(i, Transform3D(Basis.from_scale(Vector3(s, s, s)), Vector3(a[i * 5], a[i * 5 + 1], a[i * 5 + 2])))
		var mi := MultiMeshInstance3D.new()
		mi.multimesh = mm
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.visibility_range_end = float(cfg.get("far_m", 3200.0))
		add_child(mi)


func _material(part: int, albedo: String, normal: String) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = SHADER
	m.set_shader_parameter("part", part)
	m.set_shader_parameter("albedo_tex", load(TEX + albedo))
	if normal != "":
		m.set_shader_parameter("normal_tex", load(TEX + normal))
		m.set_shader_parameter("has_normal", true)
	m.set_shader_parameter("near_m", near_m)
	var tint: Array = cfg.get("tint", [1.0, 1.0, 1.0])
	m.set_shader_parameter("tint", Color(float(tint[0]), float(tint[1]), float(tint[2])))
	return m


## One fir, TREE_H tall: a tapering bark trunk and whorls of drooping boughs, each bough two crossed
## cards (seen from the side and from above), shorter toward the top.
func _make_tree() -> ArrayMesh:
	var mesh := ArrayMesh.new()
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var sides := 7
	var y0 := -SINK_M
	var y1 := TREE_H * 0.93
	for i in sides:
		var a0 := TAU * i / sides
		var a1 := TAU * (i + 1) / sides
		var ring := [[a0, 0.0], [a1, 0.0], [a1, 1.0], [a0, 1.0]]
		var vs := []
		for p: Array in ring:
			var ang := float(p[0])
			var t := float(p[1])
			var r := lerpf(0.34, 0.05, t)
			var y := lerpf(y0, y1, t)
			vs.append([Vector3(cos(ang) * r, y, sin(ang) * r), Vector3(cos(ang), 0.15, sin(ang)).normalized(), Vector2(2.0 * ang / TAU, y / 2.4)])
		for idx: int in [0, 2, 1, 0, 3, 2]:
			st.set_normal(vs[idx][1])
			st.set_uv(vs[idx][2])
			st.add_vertex(vs[idx][0])
	st.generate_tangents()
	st.commit(mesh)
	mesh.surface_set_material(0, _material(0, "bark.jpg", "bark_nrm.jpg"))
	st = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var whorls := int(cfg.get("whorls", 12))
	var per := int(cfg.get("boughs_per_whorl", 5))
	var low := TREE_H * float(cfg.get("crown_start", 0.14))
	for wi in whorls:
		var t := float(wi) / (whorls - 1)
		var y := lerpf(low, TREE_H * 0.98, t)
		var reach := lerpf(TREE_H * 0.25, 0.7, pow(t, 0.85))
		var droop := reach * 0.32
		for bi in per:
			var ang := TAU * bi / per + wi * 2.39996
			var dir := Vector3(cos(ang), 0.0, sin(ang))
			var root := dir * 0.15 + Vector3(0, y, 0)
			var tip := dir * reach + Vector3(0, y - droop, 0)
			var flat := Vector3(-dir.z, 0.0, dir.x)
			for roll: float in [0.5, -0.5]:
				var side := (flat * cos(roll) + Vector3.UP * sin(roll)) * maxf(reach * 0.32, 0.5)
				var q := [root - side * 0.5, tip - side, tip + side, root + side * 0.5]
				var uv := [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]
				for idx: int in [0, 1, 2, 0, 2, 3]:
					st.set_normal(Vector3.UP)
					st.set_uv(uv[idx])
					st.add_vertex(q[idx])
	st.commit(mesh)
	var boughs := _material(1, "branch.png", "")
	boughs.set_shader_parameter("sway", float(cfg.get("sway", 0.25)))
	mesh.surface_set_material(1, boughs)
	mesh.custom_aabb = AABB(Vector3(-TREE_H * 0.3, -SINK_M, -TREE_H * 0.3), Vector3(TREE_H * 0.6, TREE_H + SINK_M, TREE_H * 0.6))
	return mesh
