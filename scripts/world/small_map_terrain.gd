class_name SmallMapTerrain
extends RefCounted
## The small map's ground (lane B3). One 1 m height grid, built from the map's maps.json entry: noise
## hills and ridges, a rim at the edges, the town levelled, roads laid on a smoothed bed, the river
## and lake cut below the water line, and shell craters. The same grid feeds the drawn chunks and one
## Jolt HeightMapShape3D, so what you see is what you stand on. A splat image tells the ground shader
## what to paint: r road, g shore and mud, b scorch, a town rubble.

const CHUNK_M := 64
## Ground detail rings: [grid step (m), drawn out to (m)]; the last ring has no end.
const LODS := [[1, 120.0], [2, 320.0], [4, 0.0]]
const ROAD_SHOULDER_M := 8.0

var size_m := 1024
var n := 1025
var half := 512.0
var water_level := 0.0
var grid := PackedFloat32Array()
var splat: Image
## Signed distance (m) from each grid point to the nearest road edge, river bank or lake shore
## (negative inside). Kept for scatter and tests.
var road_edge := PackedFloat32Array()
var water_edge := PackedFloat32Array()

var _coarse := PackedFloat32Array()
var _coarse_n := 0
const _COARSE_M := 8


func _init(entry: Dictionary) -> void:
	size_m = int(entry.get("size_m", 1024))
	n = size_m + 1
	half = size_m * 0.5
	water_level = float(entry.get("water_level_m", 0.0))
	var seed_value := int(entry.get("seed", 1))
	var t: Dictionary = entry.get("terrain", {})
	_base(seed_value, t)
	var s := PackedByteArray()
	s.resize(n * n * 4)
	s.fill(0)
	_flats(entry.get("flats", []), s)
	_make_coarse()
	_roads(entry.get("roads", []), s)
	_water(entry, seed_value, s)
	_craters(entry.get("craters", []), s)
	splat = Image.create_from_data(n, n, false, Image.FORMAT_RGBA8, s)


# --- queries ---------------------------------------------------------------------------------


## Height at world (x, z), bilinear between grid points (the same surface the collider uses).
func height_at(x: float, z: float) -> float:
	var fx := clampf(x + half, 0.0, size_m - 0.001)
	var fz := clampf(z + half, 0.0, size_m - 0.001)
	var x0 := int(fx)
	var z0 := int(fz)
	var tx := fx - x0
	var tz := fz - z0
	var i := z0 * n + x0
	return lerpf(lerpf(grid[i], grid[i + 1], tx), lerpf(grid[i + n], grid[i + n + 1], tx), tz)


func normal_at(x: float, z: float) -> Vector3:
	var e := 1.0
	return Vector3(height_at(x - e, z) - height_at(x + e, z), 2.0 * e, height_at(x, z - e) - height_at(x, z + e)).normalized()


## Splat weights at world (x, z): r road, g shore, b scorch, a town.
func splat_at(x: float, z: float) -> Color:
	var xi := clampi(int(roundf(x + half)), 0, n - 1)
	var zi := clampi(int(roundf(z + half)), 0, n - 1)
	return splat.get_pixel(xi, zi)


func road_edge_at(x: float, z: float) -> float:
	return road_edge[_index(x, z)]


func water_edge_at(x: float, z: float) -> float:
	return water_edge[_index(x, z)]


func _index(x: float, z: float) -> int:
	return clampi(int(roundf(z + half)), 0, n - 1) * n + clampi(int(roundf(x + half)), 0, n - 1)


# --- building the grid -----------------------------------------------------------------------


func _base(seed_value: int, t: Dictionary) -> void:
	var base := FastNoiseLite.new()
	base.seed = seed_value
	base.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	base.frequency = 0.0032
	base.fractal_octaves = 5
	var hills := FastNoiseLite.new()
	hills.seed = seed_value + 11
	hills.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	hills.frequency = 0.0019
	hills.fractal_octaves = 3
	var ridge := FastNoiseLite.new()
	ridge.seed = seed_value + 23
	ridge.frequency = 0.0085
	ridge.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	ridge.fractal_octaves = 4
	var rough := FastNoiseLite.new()
	rough.seed = seed_value + 37
	rough.frequency = 0.11
	rough.fractal_octaves = 3
	var floor_m := float(t.get("floor_m", 1.5))
	var base_m := float(t.get("base_m", 9.0))
	var hills_m := float(t.get("hills_m", 12.0))
	var ridges_m := float(t.get("ridges_m", 6.0))
	var rough_m := float(t.get("rough_m", 0.45))
	var rim_m := float(t.get("rim_m", 50.0))
	var rim_w := float(t.get("rim_width_m", 90.0))
	grid.resize(n * n)
	road_edge.resize(n * n)
	road_edge.fill(1.0e6)
	water_edge.resize(n * n)
	water_edge.fill(1.0e6)
	for zi in n:
		var z := zi - half
		for xi in n:
			var x := xi - half
			var b := base.get_noise_2d(x, z) * 0.5 + 0.5
			var hl := hills.get_noise_2d(x, z) * 0.5 + 0.5
			var r := ridge.get_noise_2d(x, z) * 0.5 + 0.5
			var h := floor_m + b * base_m + hl * hl * hills_m + r * ridges_m * (0.35 + 0.65 * hl)
			h += rough.get_noise_2d(x, z) * rough_m
			var edge := smoothstep(half - rim_w, half - 4.0, maxf(absf(x), absf(z)))
			h += edge * edge * rim_m * (0.75 + 0.5 * b)
			grid[zi * n + xi] = h


## The town and other flats: blend the ground to the height at their centre, keeping a little
## of the fine roughness so rubble ground is not a billiard table.
func _flats(flats: Array, s: PackedByteArray) -> void:
	for f: Dictionary in flats:
		var c: Array = f.get("center", [0, 0])
		var size: Array = f.get("size_m", [100, 100])
		var blend := float(f.get("blend_m", 30.0))
		var cx := float(c[0])
		var cz := float(c[1])
		var hx := float(size[0]) * 0.5
		var hz := float(size[1]) * 0.5
		var target := _average(cx, cz, minf(hx, hz))
		for zi in range(_gi(cz - hz - blend), _gi(cz + hz + blend) + 1):
			for xi in range(_gi(cx - hx - blend), _gi(cx + hx + blend) + 1):
				var dx := maxf(absf(xi - half - cx) - hx, 0.0)
				var dz := maxf(absf(zi - half - cz) - hz, 0.0)
				var w := 1.0 - smoothstep(0.0, blend, Vector2(dx, dz).length())
				if w <= 0.0:
					continue
				var i := zi * n + xi
				var fine := grid[i] - _ring(xi, zi)
				grid[i] = lerpf(grid[i], target + fine * 0.6, w)
				s[i * 4 + 3] = maxi(s[i * 4 + 3], int(w * w * 255.0))


## Road beds come from a smoothed copy of the ground (8 m samples, blurred twice), so roads run
## gently over the hills instead of copying every bump.
func _make_coarse() -> void:
	_coarse_n = size_m / _COARSE_M + 1
	var c := PackedFloat32Array()
	c.resize(_coarse_n * _coarse_n)
	for zi in _coarse_n:
		for xi in _coarse_n:
			c[zi * _coarse_n + xi] = grid[mini(zi * _COARSE_M, n - 1) * n + mini(xi * _COARSE_M, n - 1)]
	for pass_i in 3:
		var o := c.duplicate()
		for zi in _coarse_n:
			for xi in _coarse_n:
				var sum := 0.0
				var cnt := 0
				for dz in range(-1, 2):
					for dx in range(-1, 2):
						var xx := xi + dx
						var zz := zi + dz
						if xx >= 0 and zz >= 0 and xx < _coarse_n and zz < _coarse_n:
							sum += o[zz * _coarse_n + xx]
							cnt += 1
				c[zi * _coarse_n + xi] = sum / cnt
	_coarse = c


func _coarse_at(x: float, z: float) -> float:
	var fx := clampf((x + half) / _COARSE_M, 0.0, _coarse_n - 1.001)
	var fz := clampf((z + half) / _COARSE_M, 0.0, _coarse_n - 1.001)
	var x0 := int(fx)
	var z0 := int(fz)
	var tx := fx - x0
	var tz := fz - z0
	var i := z0 * _coarse_n + x0
	var a := lerpf(_coarse[i], _coarse[i + 1], tx)
	var b := lerpf(_coarse[i + _coarse_n], _coarse[i + _coarse_n + 1], tx)
	return lerpf(a, b, tz)


func _roads(roads: Array, s: PackedByteArray) -> void:
	for road: Dictionary in roads:
		var hw := float(road.get("width_m", 8.0)) * 0.5
		var pts := _points(road.get("points", []))
		for k in pts.size() - 1:
			_each_near_segment(pts[k], pts[k + 1], hw + ROAD_SHOULDER_M, func(i: int, d: float) -> void:
				road_edge[i] = minf(road_edge[i], d - hw)
			)
	var edge_noise := FastNoiseLite.new()
	edge_noise.frequency = 0.15
	for i in n * n:
		var e := road_edge[i]
		if e > ROAD_SHOULDER_M:
			continue
		var x := float(i % n) - half
		var z := float(i / n) - half
		var bed := _coarse_at(x, z)
		var t := 1.0 - smoothstep(0.0, ROAD_SHOULDER_M, e)
		grid[i] = lerpf(grid[i], bed + (grid[i] - bed) * 0.04, t)
		var paint := 1.0 - smoothstep(-0.8, 0.9, e + edge_noise.get_noise_2d(x, z) * 0.9)
		s[i * 4] = maxi(s[i * 4], int(paint * 255.0))


func _water(entry: Dictionary, seed_value: int, s: PackedByteArray) -> void:
	var river: Dictionary = entry.get("river", {})
	var lake: Dictionary = entry.get("lake", {})
	if not river.is_empty():
		var hw := float(river.get("width_m", 16.0)) * 0.5
		var bank := float(river.get("bank_m", 16.0))
		var pts := _points(river.get("points", []))
		for k in pts.size() - 1:
			_each_near_segment(pts[k], pts[k + 1], hw + bank * 2.5, func(i: int, d: float) -> void:
				water_edge[i] = minf(water_edge[i], d - hw)
			)
		_carve(float(river.get("depth_m", 2.5)), bank, hw, s)
	if not lake.is_empty():
		var c: Array = lake.get("center", [0, 0])
		var radius := float(lake.get("radius_m", 100.0))
		var shore := float(lake.get("shore_m", 30.0))
		var wobble := FastNoiseLite.new()
		wobble.seed = seed_value + 51
		wobble.frequency = 0.9
		var reach := radius * 1.2 + shore * 2.5
		var cx := float(c[0])
		var cz := float(c[1])
		var before := water_edge.duplicate()
		water_edge.fill(1.0e6)
		for zi in range(_gi(cz - reach), _gi(cz + reach) + 1):
			for xi in range(_gi(cx - reach), _gi(cx + reach) + 1):
				var v := Vector2(xi - half - cx, zi - half - cz)
				var r := radius * (1.0 + 0.14 * wobble.get_noise_1d(v.angle() * 3.0))
				water_edge[zi * n + xi] = v.length() - r
		_carve(float(lake.get("depth_m", 5.0)), shore, radius, s)
		for i in n * n:
			water_edge[i] = minf(water_edge[i], before[i])


## Cut the channel or basin described by the current water_edge field (only points closer than
## the far bank are touched): below the water line inside, a shore that climbs gently out of it.
func _carve(depth: float, bank: float, inner: float, s: PackedByteArray) -> void:
	var reach := bank * 2.5
	for i in n * n:
		var e := water_edge[i]
		if e > reach:
			continue
		var h := grid[i]
		if e < 0.0:
			var t := clampf(-e / maxf(inner, 1.0), 0.0, 1.0)
			var bed := water_level + 0.35 - (depth + 0.35) * (1.0 - (1.0 - t) * (1.0 - t))
			grid[i] = minf(h, bed)
		else:
			var shore := water_level + 0.35 + e * 0.1
			grid[i] = minf(h, lerpf(shore, h, smoothstep(0.0, reach, e)))
		var mud := 1.0 - smoothstep(1.0, 7.0, e)
		s[i * 4 + 1] = maxi(s[i * 4 + 1], int(mud * 255.0))


func _craters(craters: Array, s: PackedByteArray) -> void:
	for c: Array in craters:
		var cx := float(c[0])
		var cz := float(c[1])
		var r := float(c[2])
		var depth := r * 0.32
		var rim := r * 0.12
		var reach := r * 1.9
		for zi in range(_gi(cz - reach), _gi(cz + reach) + 1):
			for xi in range(_gi(cx - reach), _gi(cx + reach) + 1):
				var d := Vector2(xi - half - cx, zi - half - cz).length()
				if d > reach:
					continue
				var i := zi * n + xi
				var q := d / r
				if q < 1.0:
					grid[i] -= depth * (1.0 - q * q)
				grid[i] += rim * exp(-pow((q - 1.0) / 0.35, 2.0))
				var burn := 1.0 - smoothstep(0.35, 1.7, q)
				s[i * 4 + 2] = maxi(s[i * 4 + 2], int(burn * 255.0))


func _each_near_segment(a: Vector2, b: Vector2, reach: float, fn: Callable) -> void:
	var x0 := _gi(minf(a.x, b.x) - reach)
	var x1 := _gi(maxf(a.x, b.x) + reach)
	var z0 := _gi(minf(a.y, b.y) - reach)
	var z1 := _gi(maxf(a.y, b.y) + reach)
	var ab := b - a
	var len2 := maxf(ab.length_squared(), 0.0001)
	for zi in range(z0, z1 + 1):
		for xi in range(x0, x1 + 1):
			var p := Vector2(xi - half, zi - half)
			var t := clampf((p - a).dot(ab) / len2, 0.0, 1.0)
			var d := p.distance_to(a + ab * t)
			if d <= reach:
				fn.call(zi * n + xi, d)


func _average(x: float, z: float, radius: float) -> float:
	var sum := 0.0
	var cnt := 0
	var step := maxf(1.0, radius / 4.0)
	var dz := -radius
	while dz <= radius:
		var dx := -radius
		while dx <= radius:
			sum += grid[_index(x + dx, z + dz)]
			cnt += 1
			dx += step
		dz += step
	return sum / cnt


## Mean of the four grid points 2 m away: grid[i] minus this is the fine roughness at i.
func _ring(xi: int, zi: int) -> float:
	var a := grid[zi * n + maxi(xi - 2, 0)] + grid[zi * n + mini(xi + 2, n - 1)]
	return (a + grid[maxi(zi - 2, 0) * n + xi] + grid[mini(zi + 2, n - 1) * n + xi]) * 0.25


func _gi(v: float) -> int:
	return clampi(int(roundf(v + half)), 0, n - 1)


static func _points(raw: Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	for p: Array in raw:
		out.append(Vector2(float(p[0]), float(p[1])))
	return out


# --- meshes and collision --------------------------------------------------------------------


## One chunk of ground, CHUNK_M on a side, starting at grid index (x0, z0). step 1 is the near
## mesh; a bigger step makes the far copy, with a skirt that hides cracks against finer chunks.
func chunk_mesh(x0: int, z0: int, step: int) -> ArrayMesh:
	var cells := CHUNK_M / step
	var m := cells + 1
	var verts := PackedVector3Array()
	var normals := PackedVector3Array()
	verts.resize(m * m)
	normals.resize(m * m)
	for j in m:
		for i in m:
			var xi := mini(x0 + i * step, n - 1)
			var zi := mini(z0 + j * step, n - 1)
			var k := j * m + i
			verts[k] = Vector3(xi - half, grid[zi * n + xi], zi - half)
			normals[k] = _grid_normal(xi, zi)
	var indices := PackedInt32Array()
	for j in cells:
		for i in cells:
			var a := j * m + i
			var b := a + 1
			var c := a + m
			var d := c + 1
			indices.append_array([a, b, c, b, d, c])
	if step > 1:
		_add_skirt(verts, normals, indices, m, step * 1.5)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


func _grid_normal(xi: int, zi: int) -> Vector3:
	var hl := grid[zi * n + maxi(xi - 1, 0)]
	var hr := grid[zi * n + mini(xi + 1, n - 1)]
	var hd := grid[maxi(zi - 1, 0) * n + xi]
	var hu := grid[mini(zi + 1, n - 1) * n + xi]
	return Vector3(hl - hr, 2.0, hd - hu).normalized()


func _add_skirt(verts: PackedVector3Array, normals: PackedVector3Array, indices: PackedInt32Array, m: int, drop: float) -> void:
	var rings: Array[PackedInt32Array] = [PackedInt32Array(), PackedInt32Array(), PackedInt32Array(), PackedInt32Array()]
	for i in m:
		rings[0].append(i)  # z0 edge
		rings[1].append((m - 1) * m + i)  # far z edge
		rings[2].append(i * m)  # x0 edge
		rings[3].append(i * m + m - 1)  # far x edge
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


func build_shape() -> HeightMapShape3D:
	var shape := HeightMapShape3D.new()
	shape.map_width = n
	shape.map_depth = n
	shape.map_data = grid
	return shape


func chunk_count() -> int:
	return size_m / CHUNK_M
