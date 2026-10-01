class_name Kit
extends RefCounted
## The asset kit (lane B3): rocks, plants, 57 mm rounds and casings, walls, ruined buildings, the
## bridge, the mast, tank traps and rubble, all built from the numbers in data/kit.json. A new piece
## is one entry there (a builder already here plus its numbers). Kit.build(id) returns a node ready to
## place: a StaticBody3D when the piece collides (layer world, plus grapple_surface when the entry says
## grapple), otherwise a plain Node3D. Walls and buildings are made of separate pieces; their boxes
## are kept in the "pieces" meta so Kit.break_apart() can turn them into loose debris (lane B5).

const TEX_DIR := "res://assets/kit/textures/"
const SHADER_DIR := "res://assets/kit/shaders/"
const LAYER_WORLD := 1
const LAYER_DEBRIS := 16
const LAYER_GRAPPLE := 64
const PIECE_DENSITY := 2100.0

static var _materials := {}


static func entry(id: String) -> Dictionary:
	return Registry.entry("kit", id)


static func ids() -> PackedStringArray:
	return Registry.ids("kit")


## Material by kit.json "materials" id, made once and shared.
static func material(id: String) -> Material:
	if _materials.has(id):
		return _materials[id]
	var spec: Dictionary = Registry.file("kit").get("materials", {}).get(id, {})
	var mat: Material
	if spec.has("shader"):
		var sm := ShaderMaterial.new()
		sm.shader = load(SHADER_DIR + str(spec["shader"]) + ".gdshader")
		sm.set_shader_parameter("colour_a", _colour(spec.get("colour_a", [0.2, 0.25, 0.1])))
		sm.set_shader_parameter("colour_b", _colour(spec.get("colour_b", [0.35, 0.35, 0.2])))
		mat = sm
	else:
		var m := StandardMaterial3D.new()
		if spec.has("textures"):
			var dir := TEX_DIR + str(spec["textures"]) + "/"
			m.albedo_texture = load(dir + "color.jpg")
			m.normal_enabled = true
			m.normal_texture = load(dir + "normal.jpg")
			m.roughness_texture = load(dir + "roughness.jpg")
			m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
			m.albedo_color = _colour(spec.get("tint", [1, 1, 1]))
			if bool(spec.get("triplanar", true)):
				var k := 1.0 / float(spec.get("scale_m", 2.0))
				m.uv1_triplanar = true
				m.uv1_world_triplanar = true
				m.uv1_scale = Vector3(k, k, k)
				m.uv1_triplanar_sharpness = 4.0
		else:
			m.albedo_color = _colour(spec.get("albedo", [0.5, 0.5, 0.5]))
		m.metallic = float(spec.get("metallic", 0.0))
		m.roughness = float(spec.get("roughness", 0.8))
		if float(spec.get("grime", 0.0)) > 0.0:
			# lane B4: mottled dirt and soot over the texture, fixed in the world (kit pieces do not move
			# until they break, and then nobody checks their stains)
			var step := roundi(clampf(float(spec["grime"]), 0.0, 1.0) * Finish.GRIME_STEPS)
			m.detail_enabled = true
			m.detail_albedo = Finish.grime_texture(step)
			m.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MUL
			m.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
			m.uv2_triplanar = true
			m.uv2_world_triplanar = true
			m.uv2_scale = Vector3.ONE * float(spec.get("grime_scale", 0.18))
		mat = m
	_materials[id] = mat
	return mat


static func _colour(a: Array) -> Color:
	return Color(float(a[0]), float(a[1]), float(a[2]))


## Build a kit piece. seed_value varies the random ones; overrides replace entry numbers (the map
## passes "size" for an outcrop, "damage" for a ruin, "length_m" and "end_heights" for a bridge).
static func build(id: String, seed_value: int = 0, overrides: Dictionary = {}) -> Node3D:
	var e := entry(id).duplicate(true)
	e.merge(overrides, true)
	var rng := RandomNumberGenerator.new()
	rng.seed = hash([id, seed_value])
	var parts := Parts.new()
	# lane B5: pieces broken off by damage (Destructible) are skipped by index; the builder still
	# runs every step (and every random draw) in the same order, so the rest come out the same
	parts.gone = e.get("gone", {})
	match str(e.get("builder", "")):
		"rock":
			_rock(parts, e, rng)
		"shrub":
			_shrub(parts, e, rng)
		"grass":
			_grass(parts, e, rng)
		"lathe":
			_lathe(parts, e)
		"wall":
			_wall(parts, e, rng)
		"building":
			_building(parts, e, rng)
		"bridge":
			_bridge(parts, e, rng)
		"mast":
			_mast(parts, e)
		"hedgehog":
			_hedgehog(parts, e)
		"rubble":
			_rubble(parts, e, rng)
		_:
			push_warning("Kit: '%s' has no builder '%s'" % [id, e.get("builder", "")])
	var mesh := parts.commit()
	var collision := str(e.get("collision", "none"))
	var root: Node3D
	if collision == "none":
		root = Node3D.new()
	else:
		var body := StaticBody3D.new()
		body.collision_layer = LAYER_WORLD | (LAYER_GRAPPLE if bool(e.get("grapple", false)) else 0)
		body.collision_mask = 0
		if collision == "convex" and parts.hull.is_empty():
			var cs := CollisionShape3D.new()
			cs.shape = mesh.create_convex_shape(true, true)
			body.add_child(cs)
		elif collision == "convex":
			var cs := CollisionShape3D.new()
			var hull := ConvexPolygonShape3D.new()
			hull.points = parts.hull
			cs.shape = hull
			body.add_child(cs)
		for s: Array in parts.shapes:
			var cs := CollisionShape3D.new()
			cs.shape = s[0]
			cs.transform = s[1]
			if s.size() > 2:
				cs.set_meta("piece", s[2])
			body.add_child(cs)
		root = body
	root.name = id.to_pascal_case()
	var mi := MeshInstance3D.new()
	mi.name = "Mesh"
	mi.mesh = mesh
	root.add_child(mi)
	root.set_meta("kit", id)
	root.set_meta("climb", bool(e.get("climb", false)))
	root.set_meta("grapple", bool(e.get("grapple", false)))
	root.set_meta("anchors", parts.anchors)
	if bool(e.get("break", false)):
		root.set_meta("pieces", parts.pieces)
	return root


## One loose piece of debris: a box body the size and material of kit piece `p`, at world
## transform `at`, added under `parent`.
static func debris(parent: Node, at: Transform3D, p: Dictionary) -> RigidBody3D:
	var size: Vector3 = p["size"]
	var body := RigidBody3D.new()
	body.collision_layer = LAYER_DEBRIS
	body.collision_mask = LAYER_WORLD | LAYER_DEBRIS
	body.mass = maxf(size.x * size.y * size.z * PIECE_DENSITY, 5.0)
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mi.mesh = box
	mi.material_override = material(str(p["material"]))
	body.add_child(mi)
	var cs := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	cs.shape = shape
	body.add_child(cs)
	parent.add_child(body)
	body.global_transform = at
	return body


## Turn a breakable kit piece into loose debris: one RigidBody3D per piece, added where the piece
## stood, pushed away from `from` by `impulse` (N s). The original node is freed. Returns the debris.
static func break_apart(node: Node3D, from: Vector3 = Vector3.ZERO, impulse: float = 0.0) -> Array[RigidBody3D]:
	var out: Array[RigidBody3D] = []
	if not node.has_meta("pieces") or node.get_parent() == null:
		return out
	var parent := node.get_parent()
	var xf := node.global_transform
	for p: Dictionary in node.get_meta("pieces"):
		if p.get("gone", false):
			continue
		var body := debris(parent, xf * (p["xf"] as Transform3D), p)
		if impulse > 0.0:
			var away := (body.global_position - from).normalized()
			body.apply_central_impulse(away * impulse / maxf(float(out.size()) * 0.1 + 1.0, 1.0))
		out.append(body)
	node.queue_free()
	return out


# --- builders --------------------------------------------------------------------------------


static func _range(e: Dictionary, key: String, rng: RandomNumberGenerator, fallback: float) -> float:
	var v: Variant = e.get(key, fallback)
	if v is Array:
		return rng.randf_range(float(v[0]), float(v[1]))
	return float(v)


## A lumpy rock: a sphere pushed about by noise, squashed and sunk. "size" overrides the size range.
static func _rock(parts: Parts, e: Dictionary, rng: RandomNumberGenerator) -> void:
	var s := float(e["size"]) if e.has("size") else _range(e, "size_m", rng, 1.0)
	var squash := _range(e, "squash", rng, 0.7)
	var dims := Vector3(s * rng.randf_range(0.85, 1.35), s * squash, s * rng.randf_range(0.85, 1.25))
	var detail := int(e.get("detail", 2))
	var noise := FastNoiseLite.new()
	noise.seed = rng.randi()
	noise.frequency = 1.1 + detail * 0.25
	noise.fractal_octaves = 2 + detail
	var amount := float(e.get("roughness", 0.35))
	var sphere := SphereMesh.new()
	sphere.radius = 0.5
	sphere.height = 1.0
	sphere.radial_segments = 10 + detail * 6
	sphere.rings = 6 + detail * 4
	var arrays := sphere.get_mesh_arrays()
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var sink := float(e.get("sink", 0.18))
	for i in verts.size():
		var v := verts[i]
		var bump := 1.0 + noise.get_noise_3dv(v * 2.0) * amount * 1.6
		var p := Vector3(v.x * dims.x, v.y * dims.y, v.z * dims.z) * bump
		if p.y > dims.y * 0.28:
			p.y = lerpf(p.y, dims.y * 0.28, 0.35)  # flatter tops read as weathered stone
		p.y -= dims.y * sink
		verts[i] = p
	var st := parts.surface(str(e.get("material", "rock")))
	var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var start := parts.count(str(e.get("material", "rock")))
	for v in verts:
		st.add_vertex(v)
	for i in idx:
		st.add_index(start + i)
	parts.add_count(str(e.get("material", "rock")), verts.size())
	parts.smooth.append(str(e.get("material", "rock")))
	if str(e.get("anchors", "")) == "top":
		parts.anchors.append(Vector3(0.0, dims.y * (0.5 - sink), 0.0))


static func _shrub(parts: Parts, e: Dictionary, rng: RandomNumberGenerator) -> void:
	# Lane B4: a dome of small leaf clusters on a few stems instead of 4-6 big blobs, so the plant has a
	# ragged, see-through silhouette. Each cluster is a stretched, turned octahedron (8 triangles):
	# about the triangle count of the old blobs. COLOR: r tone, g height share (sway), b 1 on stems.
	var s := _range(e, "size_m", rng, 1.4)
	var n := int(_range(e, "clusters", rng, 24))
	var st := parts.surface(str(e.get("material", "foliage")))
	var stems := int(e.get("stems", 4))
	var tips: Array[Vector3] = []
	for k in stems:
		var ang := TAU * (float(k) + rng.randf_range(-0.3, 0.3)) / stems
		tips.append(Vector3(cos(ang) * s * rng.randf_range(0.12, 0.3), s * rng.randf_range(0.45, 0.7), sin(ang) * s * rng.randf_range(0.12, 0.3)))
		_stem(st, Vector3(0.0, -0.05, 0.0), tips[k], s * 0.025, s)
	for c in n:
		# points spread through a squashed dome, denser toward the outside so the middle reads dark
		var dir := Vector3(rng.randf_range(-1, 1), rng.randf_range(0.05, 1.0), rng.randf_range(-1, 1)).normalized()
		var r := pow(rng.randf(), 0.4)
		var at := Vector3(dir.x * s * 0.48, dir.y * s * 0.62 + s * 0.12, dir.z * s * 0.48) * r
		var size := s * rng.randf_range(0.065, 0.12)
		var basis := Basis.from_euler(Vector3(rng.randf() * TAU, rng.randf() * TAU, rng.randf() * TAU)).scaled(Vector3(1.0, rng.randf_range(0.6, 0.95), rng.randf_range(0.8, 1.2)))
		var tone := rng.randf()
		var hv := clampf(at.y / (s * 0.9), 0.0, 1.0)
		var pts := [Vector3.RIGHT, Vector3.LEFT, Vector3.UP, Vector3.DOWN, Vector3.BACK, Vector3.FORWARD]
		var faces := [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]]
		for f: Array in faces:
			for k: int in f:
				var v: Vector3 = basis * (pts[k] as Vector3) * size
				st.set_color(Color(tone, hv, 0.0))
				# normals point away from the plant's middle, so the dome lights as one soft mass
				st.set_normal(((at + v) - Vector3(0.0, s * 0.25, 0.0)).normalized().lerp(v.normalized(), 0.35).normalized())
				st.add_vertex(at + v)
	parts.no_normals.append(str(e.get("material", "foliage")))


## A thin three-sided stem from a to b (COLOR.b = 1 marks wood for the foliage shader).
static func _stem(st: SurfaceTool, a: Vector3, b: Vector3, r: float, s: float) -> void:
	var up := (b - a).normalized()
	var side := up.cross(Vector3.FORWARD if absf(up.z) < 0.9 else Vector3.RIGHT).normalized()
	var ring: Array[Vector3] = []
	for k in 3:
		ring.append(side.rotated(up, TAU * k / 3.0) * r)
	for k in 3:
		var p := ring[k]
		var q := ring[(k + 1) % 3]
		for v: Vector3 in [a + p, b + p * 0.4, b + q * 0.4, a + p, b + q * 0.4, a + q]:
			st.set_color(Color(0.0, clampf(v.y / (s * 0.9), 0.0, 1.0), 1.0))
			st.set_normal(((p + q) * 0.5).normalized())
			st.add_vertex(v)


## A clump of grass blades, one leaning triangle each (cheap enough for thousands per chunk); UV.y runs 0 at the root to 1 at the tip (the shader sways by it).
static func _grass(parts: Parts, e: Dictionary, rng: RandomNumberGenerator) -> void:
	var h := _range(e, "size_m", rng, 0.6)
	var st := parts.surface(str(e.get("material", "grass")))
	for b in int(e.get("blades", 9)):
		var ang := rng.randf() * TAU
		var root := Vector3(cos(ang), 0.0, sin(ang)) * rng.randf_range(0.0, 0.18)
		var lean := Vector3(cos(ang + rng.randf_range(-0.6, 0.6)), 0.0, sin(ang + rng.randf_range(-0.6, 0.6)))
		var side := Vector3(-sin(ang), 0.0, cos(ang)) * rng.randf_range(0.018, 0.03)
		var bh := h * rng.randf_range(0.6, 1.15)
		var tone := rng.randf()
		var tip := root + lean * bh * 0.45 + Vector3(0.0, bh, 0.0)
		for v: Array in [[root - side, 0.0], [root + side, 0.0], [tip, 1.0]]:
			st.set_color(Color(tone, 0, 0))
			st.set_normal(Vector3.UP)
			st.set_uv(Vector2(0.0, v[1]))
			st.add_vertex(v[0])
	parts.no_normals.append(str(e.get("material", "grass")))


## Turn a profile of (radius, height) points about the Y axis, one surface per profile section.
## Normals come from each profile segment, so rims and shoulders stay crisp.
static func _lathe(parts: Parts, e: Dictionary) -> void:
	var segs := int(e.get("segments", 16))
	for section: Dictionary in e.get("profile", []):
		var mat := str(section.get("material", "brass"))
		var st := parts.surface(mat)
		var pts: Array = section.get("points", [])
		for k in pts.size() - 1:
			var p0 := Vector2(float(pts[k][0]), float(pts[k][1]))
			var p1 := Vector2(float(pts[k + 1][0]), float(pts[k + 1][1]))
			var d := p1 - p0
			if d.length() < 0.00001:
				continue
			var nrm2 := Vector2(d.y, -d.x).normalized()  # outward for a profile walked upward
			for s in segs:
				var a0 := TAU * s / segs
				var a1 := TAU * (s + 1) / segs
				var q := [
					[p0, a0], [p1, a1], [p1, a0],
					[p0, a0], [p0, a1], [p1, a1],
				]
				for v: Array in q:
					var p: Vector2 = v[0]
					var ang: float = v[1]
					var dir := Vector3(cos(ang), 0.0, sin(ang))
					st.set_normal((dir * nrm2.x + Vector3.UP * nrm2.y).normalized())
					st.add_vertex(dir * p.x + Vector3.UP * p.y)
		parts.no_normals.append(mat)


## A straight wall of blocks (about 1 m by 0.8 m) with an optional window hole; "damage" 0-1 eats
## the top away in a ragged line and knocks holes lower down.
static func _wall(parts: Parts, e: Dictionary, rng: RandomNumberGenerator) -> void:
	var w := float(e.get("width_m", 4.0))
	var h := float(e.get("height_m", 3.0))
	var t := float(e.get("thickness_m", 0.4))
	var cols := maxi(1, int(roundf(w / 1.0)))
	var rows := maxi(1, int(roundf(h / 0.8)))
	var win: Array = e.get("window", [])
	var mat := str(e.get("material", "brick"))
	var damage := float(e.get("damage", 0.0))
	for r in rows:
		for c in cols:
			var cw := w / cols
			var rh := h / rows
			var cx := -w * 0.5 + (c + 0.5) * cw
			var cy := (r + 0.5) * rh
			if win.size() == 4:
				var wx := -w * 0.5 + float(win[0])
				if cx > wx and cx < wx + float(win[2]) and cy > float(win[1]) and cy < float(win[1]) + float(win[3]):
					continue
			var keep := _survives(rng, (r + 1.0) / rows, damage, 0.0)
			if keep <= 0.0:
				continue
			var ph := rh * keep
			parts.piece(mat, Transform3D(Basis(), Vector3(cx, r * rh + ph * 0.5, 0.0)), Vector3(cw * 0.995, ph, t))
	parts.anchor_on_pieces(Vector3(0.0, h, 0.0), w)


## 1 for a whole piece, 0 for a missing one, in between for a broken-off top. v is the piece's
## height fraction (1 at the top), corner_bias adds damage near a collapsed corner.
static func _survives(rng: RandomNumberGenerator, v: float, damage: float, corner_bias: float) -> float:
	if damage <= 0.0:
		return 1.0
	var line := 1.25 - damage * 1.3 - corner_bias
	var j := rng.randf_range(-0.25, 0.25)
	if v + j > line:
		return 0.0
	if v > 0.15 and rng.randf() < damage * 0.12:
		return 0.0
	if v + j > line - 0.12:
		return rng.randf_range(0.35, 0.9)
	return 1.0


## A ruined house or block: outer walls per floor in 2 m columns (sill, window and lintel rows),
## floor slabs in 4 m tiles, a door on the ground floor, damage heaviest at one collapsed corner.
static func _building(parts: Parts, e: Dictionary, rng: RandomNumberGenerator) -> void:
	var fp: Array = e.get("footprint_m", [8.0, 8.0])
	var sx := float(fp[0])
	var sz := float(fp[1])
	var floors := int(e.get("floors", 1))
	var fh := float(e.get("floor_height_m", 3.0))
	var t := float(e.get("thickness_m", 0.4))
	var damage := float(e.get("damage", 0.4))
	var mat := str(e.get("material", "brick"))
	var windows := bool(e.get("windows", true))
	var total_h := floors * fh
	var corner := Vector2(sx * 0.5 * (1 if rng.randf() < 0.5 else -1), sz * 0.5 * (1 if rng.randf() < 0.5 else -1))
	var diag := Vector2(sx, sz).length()
	var rows := [[0.0, 0.9], [0.9, 2.1], [2.1, fh]]
	var fallen: Array = []  # [wall point, wall basis, lost area m2] for the rubble (lane B4)
	# walls: 0 front (+z), 1 back (-z), 2 right (+x), 3 left (-x)
	var walls := [
		[Vector3(0, 0, sz * 0.5 - t * 0.5), sx, 0.0],
		[Vector3(0, 0, -sz * 0.5 + t * 0.5), sx, PI],
		[Vector3(sx * 0.5 - t * 0.5, 0, 0), sz - t * 2.0, PI * 0.5],
		[Vector3(-sx * 0.5 + t * 0.5, 0, 0), sz - t * 2.0, -PI * 0.5],
	]
	for wi in walls.size():
		var centre: Vector3 = walls[wi][0]
		var length: float = walls[wi][1]
		var basis := Basis(Vector3.UP, float(walls[wi][2]))
		var cols := maxi(1, int(roundf(length / 2.0)))
		var cw := length / cols
		for f in floors:
			for r in rows.size():
				var y0: float = f * fh + float(rows[r][0])
				var y1: float = f * fh + float(rows[r][1])
				for c in cols:
					var lx := -length * 0.5 + (c + 0.5) * cw
					var is_edge := c == 0 or c == cols - 1
					if r == 1 and windows and not is_edge and c % 2 == 1:
						continue
					if r < 2 and f == 0 and wi == 0 and c == cols / 2 and bool(e.get("door", true)):
						continue
					var world := centre + basis * Vector3(lx, 0.0, 0.0)
					var bias := damage * 0.6 * (1.0 - Vector2(world.x, world.z).distance_to(corner) / diag)
					var keep := _survives(rng, y1 / total_h, damage, bias)
					if keep < 1.0:
						fallen.append([world, basis, cw * (y1 - y0) * (1.0 - keep)])
					if keep <= 0.0:
						continue
					var ph := (y1 - y0) * keep
					var xf := Transform3D(basis, centre + basis * Vector3(lx, 0.0, 0.0) + Vector3(0.0, y0 + ph * 0.5, 0.0))
					parts.piece(mat, xf, Vector3(cw * 0.995, ph, t))
	var slab := 0.25
	var tx := maxi(1, int(roundf(sx / 4.0)))
	var tz := maxi(1, int(roundf(sz / 4.0)))
	for f in range(1, floors + 1):
		for i in tx:
			for k in tz:
				var px := -sx * 0.5 + t + (i + 0.5) * (sx - t * 2.0) / tx
				var pz := -sz * 0.5 + t + (k + 0.5) * (sz - t * 2.0) / tz
				var bias := damage * 0.8 * (1.0 - Vector2(px, pz).distance_to(corner) / diag)
				if _survives(rng, float(f) / floors, damage, bias) < 1.0:
					continue
				parts.piece("concrete", Transform3D(Basis(), Vector3(px, f * fh - slab * 0.5, pz)), Vector3((sx - t * 2.0) / tx, slab, (sz - t * 2.0) / tz))
	for cx in [-1, 1]:
		for cz in [-1, 1]:
			parts.anchor_on_pieces(Vector3(cx * sx * 0.5, total_h, cz * sz * 0.5), 4.0)
	_fallen_rubble(parts, fallen, mat, t, rng)


## Lane B4: what fell off a wall lies at its foot, mostly outside: a few low chunks per lost piece,
## drawn only (no colliders, all under 0.5 m, so feet clip at most a little and break_apart is
## unchanged). The pile is densest under the most damaged stretch.
static func _fallen_rubble(parts: Parts, fallen: Array, mat: String, t: float, rng: RandomNumberGenerator) -> void:
	for f: Array in fallen:
		var at: Vector3 = f[0]
		var basis: Basis = f[1]
		var area: float = f[2]
		var out := basis * Vector3(0.0, 0.0, 1.0)
		var along := basis * Vector3(1.0, 0.0, 0.0)
		for k in clampi(int(area * 1.2), 1, 5):
			var d := rng.randf_range(-0.6, 2.6)
			var p := at + out * d + along * rng.randf_range(-1.0, 1.0)
			var size := Vector3(rng.randf_range(0.3, 0.9), rng.randf_range(0.15, 0.4), rng.randf_range(0.25, 0.6)) * (t / 0.4)
			size.y = minf(size.y, 0.45)
			var b := Basis.from_euler(Vector3(rng.randf_range(-0.4, 0.4), rng.randf() * TAU, rng.randf_range(-0.4, 0.4)))
			parts.box(mat if rng.randf() < 0.7 else "concrete", Transform3D(b, p + Vector3(0.0, size.y * 0.3, 0.0)), size)


## A road bridge along +X from 0 to length_m: deck spans on pillars, parapets, broken spans left
## out and (when "fallen") dropped into the river bed. end_heights are the deck heights at each end.
static func _bridge(parts: Parts, e: Dictionary, rng: RandomNumberGenerator) -> void:
	var length := float(e.get("length_m", 40.0))
	var ends: Array = e.get("end_heights", [0.0, 0.0])
	var width := float(e.get("width_m", 10.0))
	var deck := float(e.get("deck_m", 0.8))
	var span := float(e.get("span_m", 7.0))
	var par := float(e.get("parapet_m", 0.9))
	var pil := float(e.get("pillar_m", 1.4))
	var drop := float(e.get("pillar_drop_m", 14.0))
	# lane B5 part 2: steel bearings between each pillar and the deck. They are the bridge's weak points: a
	# span rests on two (needs 2) and comes down when one is shot out; concrete itself stands up to guns
	var bearing := float(e.get("bearing_m", 0.0))
	var mat := str(e.get("material", "concrete"))
	var broken: Array = e.get("broken_spans", [])
	var count := maxi(1, int(roundf(length / span)))
	var sl := length / count
	var h0 := float(ends[0])
	var h1 := float(ends[1])
	for k in count:
		var x0 := k * sl
		var x1 := x0 + sl
		var y0 := lerpf(h0, h1, x0 / length)
		var y1 := lerpf(h0, h1, x1 / length)
		var mid := Vector3((x0 + x1) * 0.5, (y0 + y1) * 0.5 - deck * 0.5, 0.0)
		var tilt := atan2(y1 - y0, sl)
		if broken.any(func(b: Variant) -> bool: return int(b) == k):
			if bool(e.get("fallen", false)):
				var fall := Basis(Vector3.BACK, deg_to_rad(rng.randf_range(24.0, 32.0))) * Basis(Vector3.RIGHT, deg_to_rad(rng.randf_range(-6.0, 6.0)))
				var at := mid + Vector3(sl * 0.1, -sl * 0.45, rng.randf_range(-1.0, 1.0))
				parts.piece(mat, Transform3D(fall, at), Vector3(sl * 0.96, deck, width))
			continue
		var b := Basis(Vector3.BACK, tilt)
		parts.piece(mat, Transform3D(b, mid), Vector3(sl * 1.005, deck, width), 2 if bearing > 0.0 else 1)
		for side in [-1.0, 1.0]:
			parts.piece(mat, Transform3D(b, mid + Vector3(0.0, deck * 0.5 + par * 0.5, side * (width * 0.5 - 0.15))), Vector3(sl * 0.98, par, 0.3))
	for k in range(1, count):
		var x := k * sl
		var y := lerpf(h0, h1, x / length) - deck
		parts.piece(mat, Transform3D(Basis(), Vector3(x, y - bearing - drop * 0.5, 0.0)), Vector3(pil, drop, width * 0.8))
		if bearing > 0.0:
			parts.piece("steel_rust", Transform3D(Basis(), Vector3(x, y - bearing * 0.5, 0.0)), Vector3(0.5, bearing, width * 0.6))
	# lane B5: an abutment block under each end (a bridge set into banks), so the end spans stand on something
	var abut := float(e.get("abutment_m", 0.0))
	if abut > 0.0:
		var abut_drop := drop  # same bottom as the pillars: they all stand on the same ground
		for end in [0, 1]:
			var x := 1.0 - abut * 0.5 if end == 0 else length - 1.0 + abut * 0.5
			var y := (h0 if end == 0 else h1) - deck
			parts.piece(mat, Transform3D(Basis(), Vector3(x, y - bearing - abut_drop * 0.5, 0.0)), Vector3(abut, abut_drop, width * 0.95))
			if bearing > 0.0:
				var bx := 0.6 if end == 0 else length - 0.6  # under the end span, on the abutment
				parts.piece("steel_rust", Transform3D(Basis(), Vector3(bx, y - bearing * 0.5, 0.0)), Vector3(0.5, bearing, width * 0.6))
	parts.anchors.append(Vector3(length * 0.5, h0 + par, width * 0.5))


## A tapering lattice radio mast: four legs, a ring and X braces every brace_every_m, a top cage.
static func _mast(parts: Parts, e: Dictionary) -> void:
	var h := float(e.get("height_m", 30.0))
	var base := float(e.get("base_m", 4.0)) * 0.5
	var top := float(e.get("top_m", 1.0)) * 0.5
	var leg := float(e.get("leg_m", 0.2))
	var every := float(e.get("brace_every_m", 3.0))
	var mat := str(e.get("material", "steel_rust"))
	var corners := [Vector2(1, 1), Vector2(-1, 1), Vector2(-1, -1), Vector2(1, -1)]
	var at := func(c: Vector2, y: float) -> Vector3:
		var r := lerpf(base, top, y / h)
		return Vector3(c.x * r, y, c.y * r)
	for c: Vector2 in corners:
		parts.beam(mat, at.call(c, 0.0), at.call(c, h), leg)
	var y := 0.0
	while y < h - 0.01:
		var y2 := minf(y + every, h)
		for i in 4:
			var a: Vector2 = corners[i]
			var b: Vector2 = corners[(i + 1) % 4]
			parts.beam(mat, at.call(a, y2), at.call(b, y2), leg * 0.6)
			parts.beam(mat, at.call(a, y), at.call(b, y2), leg * 0.45)
			parts.beam(mat, at.call(b, y), at.call(a, y2), leg * 0.45)
		y = y2
	parts.beam(mat, Vector3(0, h, 0), Vector3(0, h + 4.0, 0), leg * 0.8)
	for c: Vector2 in corners:
		parts.hull.append(at.call(c, 0.0))
		parts.hull.append(at.call(c, h))
	parts.anchors.append(Vector3(0.0, h, 0.0))


## A Czech hedgehog: three steel beams crossing at the middle, standing on three ends.
static func _hedgehog(parts: Parts, e: Dictionary) -> void:
	var s := float(e.get("size_m", 2.0))
	var beam := float(e.get("beam_m", 0.2))
	var mat := str(e.get("material", "steel_rust"))
	var tilt := Basis(Vector3(-1, 0, 1).normalized(), acos(1.0 / sqrt(3.0)))
	var centre := Vector3(0.0, s * 0.35, 0.0)
	for axis in [Vector3.RIGHT, Vector3.UP, Vector3.BACK]:
		var d: Vector3 = tilt * axis * s * 0.6
		parts.beam(mat, centre - d, centre + d, beam, true)


## A mound of concrete chunks, one convex collider for the whole pile.
static func _rubble(parts: Parts, e: Dictionary, rng: RandomNumberGenerator) -> void:
	var s := _range(e, "size_m", rng, 4.0)
	var mat := str(e.get("material", "concrete"))
	var chunks := int(e.get("chunks", 7))
	for k in chunks + 3:
		var r := s * 0.5 * sqrt(rng.randf())
		var ang := rng.randf() * TAU
		var p := Vector3(cos(ang) * r, 0.0, sin(ang) * r)
		var mound := s * 0.28 * (1.0 - r / (s * 0.5))
		var size := Vector3(rng.randf_range(0.5, 1.6), rng.randf_range(0.25, 0.7), rng.randf_range(0.5, 1.4)) * s * 0.22
		var b := Basis.from_euler(Vector3(rng.randf_range(-0.5, 0.5), rng.randf() * TAU, rng.randf_range(-0.5, 0.5)))
		parts.box(mat, Transform3D(b, p + Vector3(0.0, mound, 0.0)), size)
	for k in 12:
		var ang := TAU * k / 12.0
		parts.hull.append(Vector3(cos(ang) * s * 0.5, -0.2, sin(ang) * s * 0.5))
	parts.hull.append(Vector3(0.0, s * 0.3, 0.0))
	parts.anchors.append(Vector3(0.0, s * 0.3, 0.0))


# --- mesh assembly ---------------------------------------------------------------------------


## Collects geometry per material while a builder runs, then makes one ArrayMesh with a surface
## per material. Box pieces also go in `pieces` (for break_apart) and `shapes` (colliders).
class Parts:
	var tools := {}
	var counts := {}
	var smooth: Array[String] = []
	var no_normals: Array[String] = []
	var shapes: Array = []
	var pieces: Array = []
	var gone := {}  # piece index -> true: broken off (lane B5), not drawn or collided
	var next_piece := 0
	var hull := PackedVector3Array()
	var anchors: Array[Vector3] = []

	func surface(mat: String) -> SurfaceTool:
		if not tools.has(mat):
			var st := SurfaceTool.new()
			st.begin(Mesh.PRIMITIVE_TRIANGLES)
			tools[mat] = st
			counts[mat] = 0
		return tools[mat]

	func count(mat: String) -> int:
		surface(mat)
		return counts[mat]

	func add_count(mat: String, k: int) -> void:
		counts[mat] = int(counts.get(mat, 0)) + k

	## A breakable box: drawn, collided and listed for break_apart.
	## needs: how many standing pieces must hold it up from below (Destructible's support check; 2 for
	## a bridge span that rests on a bearing at each end).
	func piece(mat: String, xf: Transform3D, size: Vector3, needs: int = 1) -> void:
		var idx := next_piece
		next_piece += 1
		var lost := gone.has(idx) or gone.has(str(idx))
		pieces.append({"xf": xf, "size": size, "material": mat, "index": idx, "gone": lost, "needs": needs})
		if lost:
			return
		box(mat, xf, size)
		var shape := BoxShape3D.new()
		shape.size = size
		shapes.append([shape, xf, idx])

	## An anchor on top of the highest surviving piece within `radius` (horizontally) of `near`,
	## at that piece's centre, so damage never leaves an anchor hanging in the air.
	func anchor_on_pieces(near: Vector3, radius: float) -> void:
		var best := Vector3.ZERO
		var best_top := -INF
		for p: Dictionary in pieces:
			if p.get("gone", false):
				continue
			var xf: Transform3D = p["xf"]
			if Vector2(xf.origin.x - near.x, xf.origin.z - near.z).length() > radius:
				continue
			var top := xf.origin.y + (p["size"] as Vector3).y * 0.5
			if top > best_top:
				best_top = top
				best = Vector3(xf.origin.x, top, xf.origin.z)
		if best_top > -INF:
			anchors.append(best)

	## A drawn box (flat-shaded, 24 vertices), no collider.
	func box(mat: String, xf: Transform3D, size: Vector3) -> void:
		var st := surface(mat)
		var h := size * 0.5
		var faces := [
			[Vector3.RIGHT, Vector3.UP, Vector3.BACK],
			[Vector3.LEFT, Vector3.UP, Vector3.FORWARD],
			[Vector3.UP, Vector3.BACK, Vector3.RIGHT],
			[Vector3.DOWN, Vector3.FORWARD, Vector3.RIGHT],
			[Vector3.BACK, Vector3.UP, Vector3.LEFT],
			[Vector3.FORWARD, Vector3.UP, Vector3.RIGHT],
		]
		for f: Array in faces:
			var nrm: Vector3 = f[0]
			var u: Vector3 = f[1]
			var v: Vector3 = nrm.cross(u)
			var c := nrm * h
			var uu := u * h
			var vv := v * h
			var q := [c - uu - vv, c + uu - vv, c + uu + vv, c - uu + vv]
			var wn := (xf.basis * nrm).normalized()
			for k in [0, 2, 1, 0, 3, 2]:
				st.set_normal(wn)
				st.add_vertex(xf * (q[k] as Vector3))
		add_count(mat, 36)

	## A square beam from a to b; with `collide` it also gets a box collider.
	func beam(mat: String, a: Vector3, b: Vector3, thick: float, collide: bool = false) -> void:
		var d := b - a
		var y := d.normalized()
		var x := y.cross(Vector3.FORWARD if absf(y.dot(Vector3.FORWARD)) < 0.9 else Vector3.RIGHT).normalized()
		var z := x.cross(y)
		var xf := Transform3D(Basis(x, y, z), (a + b) * 0.5)
		var size := Vector3(thick, d.length(), thick)
		box(mat, xf, size)
		if collide:
			var shape := BoxShape3D.new()
			shape.size = size
			shapes.append([shape, xf])

	func commit() -> ArrayMesh:
		var mesh := ArrayMesh.new()
		for mat: String in tools:
			var st: SurfaceTool = tools[mat]
			if mat in smooth:
				st.generate_normals()
			st.commit(mesh)
			mesh.surface_set_material(mesh.get_surface_count() - 1, Kit.material(mat))
		return mesh
