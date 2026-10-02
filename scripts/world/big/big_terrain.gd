class_name BigTerrain
extends RefCounted
## The big map's ground (lane B5). Height is a pure function of (x, z): noise hills, ridges and rim
## mountains, a river valley, then the map's features from its maps.json entry (town flats, roads on
## a smoothed bed, the river and lakes cut below the water line, shell craters). So any 128 m tile can
## be made at any grid step, on any thread, the same every time, and neighbouring tiles share their
## edge heights exactly. An overview grid at FAR_STEP covers the whole map at load (far ground, far
## height queries, placement); BigStream makes the 1 m tiles near the action from tile().
## Splat channels as the small map: r road, g shore and mud, b scorch, a town.

const TILE_M := 128
const FAR_STEP := 8
const CELL_M := 256  # feature index cells: each lists the features that reach into it
const ROAD_SHOULDER_M := 10.0
const WATER_REACH := 2.5  # banks reach this many bank widths from the water's edge
const FORD_DEPTH_M := 0.5  # where a road crosses a river the water is this deep
const BRIDGE_REACH_M := 26.0  # a bridged road steepens the river's banks this far either side of it
const BRIDGE_BANK_KEEP := 0.22  # share of the normal bank width left right at a bridged road
const FORD_REACH_M := 14.0  # the river bed climbs to the ford over this far either side of the road

var entry: Dictionary
var size_m := 4096
var half := 2048.0
var water_level := 0.0
var tiles := 32  # tiles per side
var on := 513  # overview points per side
var overview := PackedFloat32Array()  # final height at FAR_STEP
var overview_splat: Image

var _t: Dictionary
var _n_base := FastNoiseLite.new()
var _n_hills := FastNoiseLite.new()
var _n_ridge := FastNoiseLite.new()
var _n_rough := FastNoiseLite.new()
var _n_spur := FastNoiseLite.new()
var _n_peaks := FastNoiseLite.new()
var _n_mid := FastNoiseLite.new()  # ridged hills a few hundred metres across, between the big swells
var _n_wx := FastNoiseLite.new()  # the water's meander: river banks and lake shores wander by these
var _n_wz := FastNoiseLite.new()
var _meander_m := 30.0
var _bed := PackedFloat32Array()  # natural ground blurred over ~40 m: roads and towns sit on it
var _roads: Array = []  # {a, b: Vector2, half_w: float}
var _rivers: Array = []  # {a, b: Vector2, half_w, bank, depth}
var _lakes: Array = []  # {c: Vector2, r, shore, depth}
var _flats: Array = []  # {c: Vector2, half: Vector2, cos, sin, blend, h}
var _craters: Array = []  # {c: Vector2, r}
var _cells := {}  # Vector2i -> {"roads": [], "rivers": [], "lakes": [], "flats": [], "craters": []}
var _valley_m := 450.0
var _valley_keep := 0.2


func _init(map_entry: Dictionary) -> void:
	entry = map_entry
	size_m = int(entry.get("size_m", 4096))
	half = size_m * 0.5
	tiles = size_m / TILE_M
	on = size_m / FAR_STEP + 1
	water_level = float(entry.get("water_level_m", 0.0))
	_t = entry.get("terrain", {})
	_valley_m = float(_t.get("valley_m", 450.0))
	_valley_keep = float(_t.get("valley_keep", 0.2))
	_setup_noise(int(entry.get("seed", 1)))
	_read_features()
	_make_bed()
	for f: Dictionary in _flats:
		f["h"] = _bed_at(f["c"].x, f["c"].y) + float(f["lift"])
	_make_overview()


# --- queries ---------------------------------------------------------------------------------


## Height at world (x, z) straight from the function (what a 1 m tile holds at its grid points).
func sample(x: float, z: float) -> float:
	return _eval(x, z, _cell_at(x, z), null, 0)


## Height at world (x, z), bilinear between 1 m grid points: the same surface a near tile's mesh and
## collider are made from.
func height_at(x: float, z: float) -> float:
	var x0 := floorf(x)
	var z0 := floorf(z)
	var tx := x - x0
	var tz := z - z0
	var c := _cell_at(x, z)
	var h00 := _eval(x0, z0, c, null, 0)
	var h10 := _eval(x0 + 1.0, z0, c, null, 0)
	var h01 := _eval(x0, z0 + 1.0, c, null, 0)
	var h11 := _eval(x0 + 1.0, z0 + 1.0, c, null, 0)
	return lerpf(lerpf(h00, h10, tx), lerpf(h01, h11, tx), tz)


## Height from the overview grid (cheap; far queries and placement where 1 m detail does not matter).
func overview_height(x: float, z: float) -> float:
	var fx := clampf((x + half) / FAR_STEP, 0.0, on - 1.001)
	var fz := clampf((z + half) / FAR_STEP, 0.0, on - 1.001)
	var xi := int(fx)
	var zi := int(fz)
	var i := zi * on + xi
	return lerpf(lerpf(overview[i], overview[i + 1], fx - xi), lerpf(overview[i + on], overview[i + on + 1], fx - xi), fz - zi)


func normal_at(x: float, z: float) -> Vector3:
	return Vector3(height_at(x - 1.0, z) - height_at(x + 1.0, z), 2.0, height_at(x, z - 1.0) - height_at(x, z + 1.0)).normalized()


## Splat weights at world (x, z): r road, g shore, b scorch, a town.
func splat_at(x: float, z: float) -> Color:
	var s := PackedByteArray()
	s.resize(4)
	_eval(x, z, _cell_at(x, z), s, 0)
	return Color(s[0] / 255.0, s[1] / 255.0, s[2] / 255.0, s[3] / 255.0)


## Signed distance (m) to the nearest road edge (negative on the road).
func road_edge_at(x: float, z: float) -> float:
	var p := Vector2(x, z)
	var best := 1.0e6
	for r: Dictionary in _cell_at(x, z)["roads"]:
		best = minf(best, _seg_dist(p, r["a"], r["b"]) - float(r["half_w"]))
	return best


## Signed distance (m) to the nearest water edge, river or lake (negative in the water).
func water_edge_at(x: float, z: float) -> float:
	return _water_edge(Vector2(x, z), _cell_at(x, z))


## World position of tile (tx, tz)'s low corner.
func tile_origin(tx: int, tz: int) -> Vector2:
	return Vector2(tx * TILE_M - half, tz * TILE_M - half)


func tile_of(x: float, z: float) -> Vector2i:
	return Vector2i(clampi(int(floor((x + half) / TILE_M)), 0, tiles - 1), clampi(int(floor((z + half) / TILE_M)), 0, tiles - 1))


# --- tiles -----------------------------------------------------------------------------------


## One tile's ground at `step` m: {"n": points per side, "heights": n*n, "splat": n*n*4 bytes,
## "normals": n*n} with one extra ring of heights sampled outside the tile so edge normals match the
## neighbour's. Pure: safe on a worker thread.
func tile(tx: int, tz: int, step: int) -> Dictionary:
	var o := tile_origin(tx, tz)
	var n := TILE_M / step + 1
	var m := n + 2
	var c := _cell_at(o.x + TILE_M * 0.5, o.y + TILE_M * 0.5)
	var ring := PackedFloat32Array()
	ring.resize(m * m)
	var splat := PackedByteArray()
	splat.resize(n * n * 4)
	splat.fill(0)
	var heights := PackedFloat32Array()
	heights.resize(n * n)
	for j in m:
		var z := o.y + (j - 1) * step
		for i in m:
			var x := o.x + (i - 1) * step
			var inside := i >= 1 and j >= 1 and i <= n and j <= n
			var h := _eval(x, z, c, splat if inside else null, ((j - 1) * n + (i - 1)) * 4 if inside else 0)
			ring[j * m + i] = h
			if inside:
				heights[(j - 1) * n + (i - 1)] = h
	var normals := PackedVector3Array()
	normals.resize(n * n)
	for j in n:
		for i in n:
			var k := (j + 1) * m + (i + 1)
			normals[j * n + i] = Vector3(ring[k - 1] - ring[k + 1], 2.0 * step, ring[k - m] - ring[k + m]).normalized()
	return {"tx": tx, "tz": tz, "step": step, "n": n, "heights": heights, "splat": splat, "normals": normals}


## A drawable mesh from tile() data, local to the tile's low corner; skirts hide cracks against
## coarser neighbours.
static func tile_mesh(t: Dictionary, skirt_m: float) -> ArrayMesh:
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, mesh_arrays(t, skirt_m))
	return mesh


## The surface arrays tile_mesh() draws (plain arrays: safe to build on a worker thread).
static func mesh_arrays(t: Dictionary, skirt_m: float) -> Array:
	var n := int(t["n"])
	var step := float(t["step"])
	var heights: PackedFloat32Array = t["heights"]
	var normals: PackedVector3Array = (t["normals"] as PackedVector3Array).duplicate()
	var verts := PackedVector3Array()
	verts.resize(n * n)
	for j in n:
		for i in n:
			verts[j * n + i] = Vector3(i * step, heights[j * n + i], j * step)
	var indices := PackedInt32Array()
	indices.resize((n - 1) * (n - 1) * 6)
	var w := 0
	for j in n - 1:
		for i in n - 1:
			var a := j * n + i
			var b := a + 1
			var cc := a + n
			var d := cc + 1
			indices[w] = a
			indices[w + 1] = b
			indices[w + 2] = cc
			indices[w + 3] = b
			indices[w + 4] = d
			indices[w + 5] = cc
			w += 6
	if skirt_m > 0.0:
		_add_skirt(verts, normals, indices, n, skirt_m)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	return arrays


## Tile data at twice the step, taken from finer tile data (every other point).
static func coarsen(t: Dictionary) -> Dictionary:
	var n := int(t["n"])
	var m := (n - 1) / 2 + 1
	var heights: PackedFloat32Array = t["heights"]
	var normals: PackedVector3Array = t["normals"]
	var h2 := PackedFloat32Array()
	h2.resize(m * m)
	var n2 := PackedVector3Array()
	n2.resize(m * m)
	for j in m:
		for i in m:
			h2[j * m + i] = heights[(j * 2) * n + i * 2]
			n2[j * m + i] = normals[(j * 2) * n + i * 2]
	return {"tx": t["tx"], "tz": t["tz"], "step": int(t["step"]) * 2, "n": m, "heights": h2, "normals": n2}


## The collider for tile() data, to sit at the tile's centre (HeightMapShape3D is centred).
static func tile_shape(t: Dictionary) -> HeightMapShape3D:
	var shape := HeightMapShape3D.new()
	shape.map_width = int(t["n"])
	shape.map_depth = int(t["n"])
	if int(t["step"]) == 1:
		shape.map_data = t["heights"]
	else:
		# the collider scales uniformly by step (CollisionShape3D), so heights go in divided by it
		var h: PackedFloat32Array = (t["heights"] as PackedFloat32Array).duplicate()
		for i in h.size():
			h[i] /= float(t["step"])
		shape.map_data = h
	return shape


## The overview grid's data for tile (tx, tz), as tile() returns at FAR_STEP.
func overview_tile(tx: int, tz: int) -> Dictionary:
	var n := TILE_M / FAR_STEP + 1
	var per := TILE_M / FAR_STEP
	var heights := PackedFloat32Array()
	heights.resize(n * n)
	var normals := PackedVector3Array()
	normals.resize(n * n)
	for j in n:
		for i in n:
			var xi := tx * per + i
			var zi := tz * per + j
			heights[j * n + i] = overview[zi * on + xi]
			var hl := overview[zi * on + maxi(xi - 1, 0)]
			var hr := overview[zi * on + mini(xi + 1, on - 1)]
			var hd := overview[maxi(zi - 1, 0) * on + xi]
			var hu := overview[mini(zi + 1, on - 1) * on + xi]
			normals[j * n + i] = Vector3(hl - hr, 2.0 * FAR_STEP, hd - hu).normalized()
	return {"tx": tx, "tz": tz, "step": FAR_STEP, "n": n, "heights": heights, "normals": normals}


# --- the height function -----------------------------------------------------------------------


func _setup_noise(seed_value: int) -> void:
	var scale := float(_t.get("feature_scale", 2.6))  # landforms this many times the small map's
	for spec: Array in [[_n_base, 0, 0.0032, 5, false], [_n_hills, 11, 0.0019, 3, false], [_n_ridge, 23, 0.0085, 4, true], [_n_spur, 71, 0.011, 2, false], [_n_peaks, 72, 0.007, 3, false]]:
		var nz: FastNoiseLite = spec[0]
		nz.seed = seed_value + int(spec[1])
		nz.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
		nz.frequency = float(spec[2]) / scale
		nz.fractal_octaves = int(spec[3])
		if spec[4]:
			nz.noise_type = FastNoiseLite.TYPE_SIMPLEX
			nz.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	_n_mid.seed = seed_value + 41
	_n_mid.noise_type = FastNoiseLite.TYPE_SIMPLEX
	_n_mid.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	_n_mid.frequency = float(_t.get("mid_frequency", 0.0045))
	_n_mid.fractal_octaves = 3
	for nz: FastNoiseLite in [_n_wx, _n_wz]:
		nz.seed = seed_value + (51 if nz == _n_wx else 52)
		nz.frequency = 0.004
		nz.fractal_octaves = 2
	_meander_m = float(_t.get("meander_m", 30.0))
	_n_rough.seed = seed_value + 37
	_n_rough.frequency = 0.11
	_n_rough.fractal_octaves = 3


## The ground before roads, towns and water: hills, ridges and the rim, lowered toward the river.
func _natural(x: float, z: float, water_d: float) -> float:
	var b := _n_base.get_noise_2d(x, z) * 0.5 + 0.5
	var hl := _n_hills.get_noise_2d(x, z) * 0.5 + 0.5
	var r := _n_ridge.get_noise_2d(x, z) * 0.5 + 0.5
	var md := _n_mid.get_noise_2d(x, z) * 0.5 + 0.5
	var relief := b * float(_t.get("base_m", 22.0)) + hl * hl * float(_t.get("hills_m", 60.0)) + r * float(_t.get("ridges_m", 18.0)) * (0.35 + 0.65 * hl)
	# the ridged hills rise only where the big swells already are: open plains stay open
	relief += md * md * float(_t.get("mid_m", 0.0)) * smoothstep(0.3, 0.75, hl)
	relief *= lerpf(_valley_keep, 1.0, smoothstep(0.0, _valley_m, water_d))
	var h := float(_t.get("floor_m", 1.6)) + relief
	var rim_w := float(_t.get("rim_width_m", 320.0))
	var spur := _n_spur.get_noise_2d(x, z) * 0.5 + 0.5
	var edge := smoothstep(half - rim_w, half - 8.0, maxf(absf(x), absf(z)) + spur * spur * rim_w * 0.55)
	if edge > 0.0:
		h += edge * edge * float(_t.get("rim_m", 160.0)) * maxf(0.75, 0.8 + 0.5 * b + 0.55 * _n_peaks.get_noise_2d(x, z))
		# sharp crests and gullies on the mountains (the ridged noise again, squared), so the rim is rock, not cones
		h += edge * edge * float(_t.get("rim_crag_m", 0.0)) * r * r
	return h


## Height at (x, z) with every feature in cell c. With splat, writes the four weights at splat[at].
func _eval(x: float, z: float, c: Dictionary, splat: Variant, at: int) -> float:
	var p := Vector2(x, z)
	var water_d := _water_edge(p, c)
	var h := _natural(x, z, water_d) + _n_rough.get_noise_2d(x, z) * float(_t.get("rough_m", 0.45))
	var town := 0.0
	var flat_w := 0.0
	var flat_h := 0.0
	for f: Dictionary in c["flats"]:
		var d := p - (f["c"] as Vector2)
		var lx := absf(d.x * float(f["cos"]) + d.y * float(f["sin"])) - (f["half"] as Vector2).x
		var lz := absf(-d.x * float(f["sin"]) + d.y * float(f["cos"])) - (f["half"] as Vector2).y
		var out := Vector2(maxf(lx, 0.0), maxf(lz, 0.0)).length() + minf(maxf(lx, lz), 0.0)
		var w := 1.0 - smoothstep(0.0, float(f["blend"]), out)
		if w > 0.0:
			h = lerpf(h, float(f["h"]) + _n_rough.get_noise_2d(x, z) * 0.12, w)
			town = maxf(town, 1.0 - smoothstep(-8.0, 4.0, out))
			if w > flat_w:
				flat_w = w
				flat_h = float(f["h"])
	var road := 0.0
	var road_d := 1.0e6
	var ford_d := 1.0e6  # distance to the roads that ford the river (a bridged road crosses it dry)
	var bridge_d := 1.0e6
	for r: Dictionary in c["roads"]:
		var rd := _seg_dist(p, r["a"], r["b"]) - float(r["half_w"])
		road_d = minf(road_d, rd)
		if r["bridged"]:
			bridge_d = minf(bridge_d, rd)
		else:
			ford_d = minf(ford_d, rd)
	if road_d < ROAD_SHOULDER_M:
		# in and near a town the road sits on the town's level ground
		var bed := lerpf(_bed_at(x, z), flat_h, flat_w)
		h = lerpf(bed + 0.12, h, smoothstep(0.0, ROAD_SHOULDER_M, road_d))
		road = 1.0 - smoothstep(-0.5, 1.5, road_d)
	var mud := 0.0
	var pw := _wander(p)
	for rv: Dictionary in c["rivers"]:
		var e := _river_edge(pw, rv)
		var depth := float(rv["depth"])
		var bank := float(rv["bank"])
		if ford_d < FORD_REACH_M:
			depth = lerpf(FORD_DEPTH_M, depth, smoothstep(0.0, FORD_REACH_M, ford_d))
		if bridge_d < BRIDGE_REACH_M:
			bank *= lerpf(BRIDGE_BANK_KEEP, 1.0, smoothstep(0.0, BRIDGE_REACH_M, bridge_d))
		h = _carve(h, e, bank, float(rv["half_w"]), depth)
		mud = maxf(mud, 1.0 - smoothstep(1.0, 9.0, e))
	for lk: Dictionary in c["lakes"]:
		var e := _lake_edge(pw, lk)
		h = _carve(h, e, float(lk["shore"]), float(lk["r"]) * 0.5, float(lk["depth"]))
		mud = maxf(mud, 1.0 - smoothstep(1.0, 9.0, e))
	var scorch := 0.0
	for cr: Dictionary in c["craters"]:
		var r := float(cr["r"])
		var q := p.distance_to(cr["c"]) / r
		if q < 1.9:
			if q < 1.0:
				h -= r * 0.32 * (1.0 - q * q)
			h += r * 0.12 * exp(-pow((q - 1.0) / 0.35, 2.0))
			scorch = maxf(scorch, 1.0 - smoothstep(0.35, 1.7, q))
	if splat != null:
		var s: PackedByteArray = splat
		s[at] = int(road * 255.0)
		s[at + 1] = int(mud * 255.0)
		s[at + 2] = int(scorch * 255.0)
		s[at + 3] = int(town * 255.0)
	return h


## River and lake banks: below the water line inside, a shore that climbs out over WATER_REACH banks.
func _carve(h: float, e: float, bank: float, inner: float, depth: float) -> float:
	var reach := bank * WATER_REACH
	if e > reach:
		return h
	if e < 0.0:
		var t := clampf(-e / maxf(inner, 1.0), 0.0, 1.0)
		return minf(h, water_level + 0.35 - (depth + 0.35) * (1.0 - (1.0 - t) * (1.0 - t)))
	return minf(h, lerpf(water_level + 0.35 + e * 0.1, h, smoothstep(0.0, reach, e)))


func _water_edge(p: Vector2, c: Dictionary) -> float:
	var best := 1.0e6
	if c["rivers"].is_empty() and c["lakes"].is_empty():
		return best
	var pw := _wander(p)
	for rv: Dictionary in c["rivers"]:
		best = minf(best, _river_edge(pw, rv))
	for lk: Dictionary in c["lakes"]:
		best = minf(best, _lake_edge(pw, lk))
	return best


## The point the water's shape is read at: moved up to meander_m by smooth noise, so a river drawn
## as straight segments wanders and a lake's shore is not a circle.
func _wander(p: Vector2) -> Vector2:
	return p + Vector2(_n_wx.get_noise_2d(p.x, p.y), _n_wz.get_noise_2d(p.x, p.y)) * _meander_m


## Signed distance to a river's bank; the river is up to 35 % wider or narrower along its course.
func _river_edge(pw: Vector2, rv: Dictionary) -> float:
	return _seg_dist(pw, rv["a"], rv["b"]) - float(rv["half_w"]) * (1.0 + 0.35 * _n_wz.get_noise_2d(pw.y * 0.5, pw.x * 0.5))


## Signed distance to a lake's shore: bays and points from the shore noise taken around the rim.
func _lake_edge(pw: Vector2, lk: Dictionary) -> float:
	var d := pw - (lk["c"] as Vector2)
	var dir := d.normalized() if d.length() > 0.01 else Vector2.RIGHT
	var r := float(lk["r"])
	var rim := (lk["c"] as Vector2) + dir * r
	return d.length() - r * (1.0 + 0.28 * _n_spur.get_noise_2d(rim.x * 1.3, rim.y * 1.3))


static func _seg_dist(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var t := clampf((p - a).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
	return p.distance_to(a + ab * t)


# --- features and their index --------------------------------------------------------------------


func _read_features() -> void:
	var cells_per := size_m / CELL_M
	for cz in cells_per + 2:
		for cx in cells_per + 2:
			_cells[Vector2i(cx - 1, cz - 1)] = {"roads": [], "rivers": [], "lakes": [], "flats": [], "craters": []}
	for road: Dictionary in entry.get("roads", []):
		var pts := _points(road["points"])
		for i in pts.size() - 1:
			var f := {"a": pts[i], "b": pts[i + 1], "half_w": float(road.get("width_m", 8.0)) * 0.5, "bridged": bool(road.get("bridged", false))}
			_roads.append(f)
			_index("roads", f, _seg_box(pts[i], pts[i + 1]), float(f["half_w"]) + maxf(ROAD_SHOULDER_M, BRIDGE_REACH_M if f["bridged"] else 0.0))
	for rv: Dictionary in entry.get("rivers", []):
		var pts := _points(rv["points"])
		for i in pts.size() - 1:
			var f := {"a": pts[i], "b": pts[i + 1], "half_w": float(rv.get("width_m", 20.0)) * 0.5, "bank": float(rv.get("bank_m", 20.0)), "depth": float(rv.get("depth_m", 2.6))}
			_rivers.append(f)
			# the valley widens the reach: _natural lowers the hills within valley_m of the water
			_index("rivers", f, _seg_box(pts[i], pts[i + 1]), float(f["half_w"]) + maxf(float(f["bank"]) * WATER_REACH, _valley_m) + 16.0)
	for lk: Dictionary in entry.get("lakes", []):
		var c := _v2(lk["center"])
		var f := {"c": c, "r": float(lk["radius_m"]), "shore": float(lk.get("shore_m", 36.0)), "depth": float(lk.get("depth_m", 6.0))}
		_lakes.append(f)
		_index("lakes", f, Rect2(c, Vector2.ZERO), float(f["r"]) + maxf(float(f["shore"]) * WATER_REACH, _valley_m) + 16.0)
	for fl: Dictionary in entry.get("towns", []):
		var c := _v2(fl["center"])
		var sz: Array = fl["size_m"]
		var a := deg_to_rad(float(fl.get("rot", 0.0)))
		var hs := Vector2(float(sz[0]), float(sz[1])) * 0.5
		var f := {"id": str(fl["id"]), "c": c, "half": hs, "cos": cos(a), "sin": sin(a), "blend": float(fl.get("blend_m", 50.0)), "lift": float(fl.get("lift_m", 0.0)), "h": 0.0}
		_flats.append(f)
		_index("flats", f, Rect2(c, Vector2.ZERO), hs.length() + float(f["blend"]) + 4.0)
	var craters: Array = (entry.get("craters", []) as Array).duplicate()
	for field: Dictionary in entry.get("crater_fields", []):
		craters.append_array(_crater_field(field))
	for cr: Array in craters:
		var f := {"c": Vector2(float(cr[0]), float(cr[1])), "r": float(cr[2])}
		_craters.append(f)
		_index("craters", f, Rect2(f["c"], Vector2.ZERO), float(f["r"]) * 1.9)


## A field's craters, [x, z, r] each: spread at random (its own seed) over its rectangle, none on a
## road or within reach of the water.
func _crater_field(field: Dictionary) -> Array:
	var rng := RandomNumberGenerator.new()
	rng.seed = int(field.get("seed", 1))
	var c := _v2(field["center"])
	var sz: Array = field["size_m"]
	var rr: Array = field.get("r_m", [3.0, 8.0])
	var out: Array = []
	for i in int(field.get("count", 10)):
		var x := c.x + rng.randf_range(-0.5, 0.5) * float(sz[0])
		var z := c.y + rng.randf_range(-0.5, 0.5) * float(sz[1])
		var r := rng.randf_range(float(rr[0]), float(rr[1]))
		if road_edge_at(x, z) < r * 2.0 or water_edge_at(x, z) < r * 2.0 + 6.0:
			continue
		out.append([x, z, r])
	return out


func _index(kind: String, f: Dictionary, box: Rect2, reach: float) -> void:
	var lo := Vector2i(floori((box.position.x - reach + half) / CELL_M), floori((box.position.y - reach + half) / CELL_M))
	var hi := Vector2i(floori((box.end.x + reach + half) / CELL_M), floori((box.end.y + reach + half) / CELL_M))
	for cz in range(lo.y, hi.y + 1):
		for cx in range(lo.x, hi.x + 1):
			var key := Vector2i(cx, cz)
			if _cells.has(key):
				(_cells[key][kind] as Array).append(f)


## The feature lists for the cell holding (x, z). A tile (128 m) never spans two cells (256 m), and
## every feature is listed in each cell it reaches into, so one lookup serves a whole tile.
func _cell_at(x: float, z: float) -> Dictionary:
	var key := Vector2i(floori((x + half) / CELL_M), floori((z + half) / CELL_M))
	return _cells.get(key, _cells[Vector2i(clampi(key.x, -1, size_m / CELL_M), clampi(key.y, -1, size_m / CELL_M))])


static func _seg_box(a: Vector2, b: Vector2) -> Rect2:
	return Rect2(Vector2(minf(a.x, b.x), minf(a.y, b.y)), (a - b).abs())


static func _points(raw: Array) -> Array[Vector2]:
	var out: Array[Vector2] = []
	for p: Array in raw:
		out.append(Vector2(float(p[0]), float(p[1])))
	return out


static func _v2(a: Array) -> Vector2:
	return Vector2(float(a[0]), float(a[1]))


# --- overview grid and road bed --------------------------------------------------------------


## The natural ground at FAR_STEP, box-blurred twice over `bed_blur_cells` each way: what roads and
## town flats are levelled to, so they follow the land's long lines but not its bumps.
func _make_bed() -> void:
	_bed.resize(on * on)
	for zi in on:
		var z := zi * FAR_STEP - half
		for xi in on:
			var x := xi * FAR_STEP - half
			_bed[zi * on + xi] = _natural(x, z, _water_edge(Vector2(x, z), _cell_at(x, z)))
	var r := int(_t.get("bed_blur_cells", 3))
	for _pass in 2:
		_bed = _blur_rows(_blur_rows(_bed, r, true), r, false)


func _blur_rows(src: PackedFloat32Array, r: int, along_x: bool) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(on * on)
	var w := 1.0 / (2 * r + 1)
	for a in on:
		var acc := 0.0
		for k in range(-r, r + 1):
			var b0 := clampi(k, 0, on - 1)
			acc += src[a * on + b0] if along_x else src[b0 * on + a]
		for b in on:
			if along_x:
				out[a * on + b] = acc * w
			else:
				out[b * on + a] = acc * w
			var add := mini(b + r + 1, on - 1)
			var sub := maxi(b - r, 0)
			acc += (src[a * on + add] - src[a * on + sub]) if along_x else (src[add * on + a] - src[sub * on + a])
	return out


func _bed_at(x: float, z: float) -> float:
	var fx := clampf((x + half) / FAR_STEP, 0.0, on - 1.001)
	var fz := clampf((z + half) / FAR_STEP, 0.0, on - 1.001)
	var xi := int(fx)
	var zi := int(fz)
	var i := zi * on + xi
	return lerpf(lerpf(_bed[i], _bed[i + 1], fx - xi), lerpf(_bed[i + on], _bed[i + on + 1], fx - xi), fz - zi)


func _make_overview() -> void:
	overview.resize(on * on)
	var s := PackedByteArray()
	s.resize(on * on * 4)
	for zi in on:
		var z := zi * FAR_STEP - half
		for xi in on:
			var x := xi * FAR_STEP - half
			overview[zi * on + xi] = _eval(x, z, _cell_at(x, z), s, (zi * on + xi) * 4)
	overview_splat = Image.create_from_data(on, on, false, Image.FORMAT_RGBA8, s)


static func _add_skirt(verts: PackedVector3Array, normals: PackedVector3Array, indices: PackedInt32Array, m: int, drop: float) -> void:
	var rings: Array[PackedInt32Array] = [PackedInt32Array(), PackedInt32Array(), PackedInt32Array(), PackedInt32Array()]
	for i in m:
		rings[0].append(i)
		rings[1].append((m - 1) * m + i)
		rings[2].append(i * m)
		rings[3].append(i * m + m - 1)
	for edge in rings:
		var base := verts.size()
		for k in edge:
			verts.append(verts[k] - Vector3(0.0, drop, 0.0))
			normals.append(normals[k])
		for s in edge.size() - 1:
			var a := edge[s]
			var b := edge[s + 1]
			var c := base + s
			var d := base + s + 1
			indices.append_array([a, c, b, b, c, d, a, b, c, b, d, c])
