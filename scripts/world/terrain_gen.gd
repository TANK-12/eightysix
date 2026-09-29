class_name TerrainGen
extends RefCounted
## Rocky noise terrain for the test range: one height grid feeds both the drawn mesh and a Jolt
## HeightMapShape3D, so what you see is exactly what you stand on. Spacing is 1 m (no shape
## scaling). The ground flattens around the spawn and rises into a rim at the edges.


static func heights(size_m: int, seed_value: int) -> PackedFloat32Array:
	var n := size_m + 1
	var half := size_m * 0.5
	var base := FastNoiseLite.new()
	base.seed = seed_value
	base.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	base.frequency = 0.0045
	base.fractal_type = FastNoiseLite.FRACTAL_FBM
	base.fractal_octaves = 5
	var ridge := FastNoiseLite.new()
	ridge.seed = seed_value + 1
	ridge.frequency = 0.012
	ridge.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	ridge.fractal_octaves = 4
	var rough := FastNoiseLite.new()
	rough.seed = seed_value + 2
	rough.frequency = 0.09
	rough.fractal_octaves = 3
	var spawn_level := base.get_noise_2d(0.0, 0.0) * 16.0
	var out := PackedFloat32Array()
	out.resize(n * n)
	for zi in n:
		for xi in n:
			var x := xi - half
			var z := zi - half
			var b := base.get_noise_2d(x, z)
			var h := b * 16.0 + ridge.get_noise_2d(x, z) * 6.0 * (0.5 + 0.5 * b) + rough.get_noise_2d(x, z) * 0.45
			var r := Vector2(x, z).length()
			h = lerpf(spawn_level, h, smoothstep(18.0, 48.0, r))
			var edge := smoothstep(half - 34.0, half - 2.0, maxf(absf(x), absf(z)))
			h += edge * edge * 26.0
			out[zi * n + xi] = h
	return out


## Height at world (x, z), bilinear between grid points.
static func height_at(grid: PackedFloat32Array, size_m: int, x: float, z: float) -> float:
	var n := size_m + 1
	var fx := clampf(x + size_m * 0.5, 0.0, size_m - 0.001)
	var fz := clampf(z + size_m * 0.5, 0.0, size_m - 0.001)
	var x0 := int(fx)
	var z0 := int(fz)
	var tx := fx - x0
	var tz := fz - z0
	var h00 := grid[z0 * n + x0]
	var h10 := grid[z0 * n + x0 + 1]
	var h01 := grid[(z0 + 1) * n + x0]
	var h11 := grid[(z0 + 1) * n + x0 + 1]
	return lerpf(lerpf(h00, h10, tx), lerpf(h01, h11, tx), tz)


static func build_mesh(grid: PackedFloat32Array, size_m: int) -> ArrayMesh:
	var n := size_m + 1
	var half := size_m * 0.5
	var verts := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	verts.resize(n * n)
	normals.resize(n * n)
	uvs.resize(n * n)
	for zi in n:
		for xi in n:
			var i := zi * n + xi
			verts[i] = Vector3(xi - half, grid[i], zi - half)
			var hl := grid[zi * n + maxi(xi - 1, 0)]
			var hr := grid[zi * n + mini(xi + 1, n - 1)]
			var hd := grid[maxi(zi - 1, 0) * n + xi]
			var hu := grid[mini(zi + 1, n - 1) * n + xi]
			normals[i] = Vector3(hl - hr, 2.0, hd - hu).normalized()
			uvs[i] = Vector2(xi, zi)
	var indices := PackedInt32Array()
	indices.resize((n - 1) * (n - 1) * 6)
	var k := 0
	for zi in n - 1:
		for xi in n - 1:
			var a := zi * n + xi
			var b := a + 1
			var c := a + n
			var d := c + 1
			indices[k] = a
			indices[k + 1] = b
			indices[k + 2] = c
			indices[k + 3] = b
			indices[k + 4] = d
			indices[k + 5] = c
			k += 6
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


static func build_shape(grid: PackedFloat32Array, size_m: int) -> HeightMapShape3D:
	var shape := HeightMapShape3D.new()
	shape.map_width = size_m + 1
	shape.map_depth = size_m + 1
	shape.map_data = grid
	return shape


## A lumpy boulder: a sphere pushed about by noise and squashed, with a matching convex collider.
static func rock_mesh(seed_value: int, size: Vector3) -> ArrayMesh:
	var sphere := SphereMesh.new()
	sphere.radius = 0.5
	sphere.height = 1.0
	sphere.radial_segments = 14
	sphere.rings = 9
	var arrays := sphere.get_mesh_arrays()
	var noise := FastNoiseLite.new()
	noise.seed = seed_value
	noise.frequency = 1.6
	noise.fractal_octaves = 3
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	for i in verts.size():
		var v := verts[i]
		var bump := 1.0 + noise.get_noise_3dv(v * 2.0) * 0.45
		verts[i] = Vector3(v.x * size.x, v.y * size.y, v.z * size.z) * bump
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var idx: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	for i in idx:
		st.add_vertex(verts[i])
	st.generate_normals()
	return st.commit()
