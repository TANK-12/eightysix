class_name Backdrop
extends RefCounted
## Far hills beyond a map's edge (lane B4), so the rim is not the end of the world. Visual only: no
## collision, no shadows. A grid over the square out to extent_m, minus the playable map, rising from
## just under the rim top at the edge to ridges further out; fog does the rest. From the map entry's
## "backdrop" block: {extent_m, cell_m, start_m, rise_m, ridge_m, colour, seed}.


static func build(parent: Node3D, entry: Dictionary, rock: Texture2D = null) -> MeshInstance3D:
	var b: Dictionary = entry.get("backdrop", {})
	if b.is_empty():
		return null
	var half := float(entry.get("size_m", 1024)) * 0.5
	var extent := float(b.get("extent_m", 1600.0))
	var cell := float(b.get("cell_m", 32.0))
	var noise := FastNoiseLite.new()
	noise.seed = int(b.get("seed", 86))
	noise.frequency = 0.0022
	noise.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	noise.fractal_octaves = 4
	var cells := int(ceil(extent * 2.0 / cell))
	var heights := PackedFloat32Array()
	heights.resize((cells + 1) * (cells + 1))
	for zi in cells + 1:
		for xi in cells + 1:
			heights[zi * (cells + 1) + xi] = height_at(-extent + xi * cell, -extent + zi * cell, half, b, noise)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for zi in cells:
		for xi in cells:
			var x0 := -extent + xi * cell
			var z0 := -extent + zi * cell
			# skip cells wholly inside the playable map (the terrain is drawn there)
			if maxf(absf(x0 + cell * 0.5), absf(z0 + cell * 0.5)) + cell * 0.5 < half - cell:
				continue
			var p00 := Vector3(x0, heights[zi * (cells + 1) + xi], z0)
			var p10 := Vector3(x0 + cell, heights[zi * (cells + 1) + xi + 1], z0)
			var p01 := Vector3(x0, heights[(zi + 1) * (cells + 1) + xi], z0 + cell)
			var p11 := Vector3(x0 + cell, heights[(zi + 1) * (cells + 1) + xi + 1], z0 + cell)
			for v: Vector3 in [p00, p10, p11, p00, p11, p01]:
				st.add_vertex(v)
	st.generate_normals()
	var mi := MeshInstance3D.new()
	mi.name = "Backdrop"
	mi.mesh = st.commit()
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var mat := StandardMaterial3D.new()
	var c: Array = b.get("colour", [0.3, 0.26, 0.21])
	mat.albedo_color = Color(float(c[0]), float(c[1]), float(c[2]))
	mat.roughness = 1.0
	mat.metallic_specular = 0.2
	if rock != null:
		# the map's rock at a hill-sized scale, projected three ways, so the far hills are not cardboard
		mat.albedo_texture = rock
		mat.uv1_triplanar = true
		mat.uv1_world_triplanar = true
		mat.uv1_scale = Vector3.ONE / float(b.get("texture_m", 60.0))
		mat.albedo_color = mat.albedo_color * 1.6
	mi.material_override = mat
	parent.add_child(mi)
	return mi


## Height (m) of the backdrop at (x, z): under the rim top at the map's edge (so the rim hides the
## join), rising outward, with ridged hills on top. Inside the map it sinks well below the ground.
static func height_at(x: float, z: float, half: float, b: Dictionary, noise: FastNoiseLite) -> float:
	var out := maxf(absf(x), absf(z)) - half
	if out < 0.0:
		return float(b.get("start_m", 30.0)) + out * 0.5
	var rise := clampf(out / 400.0, 0.0, 1.0)
	var ridge := noise.get_noise_2d(x, z) * 0.5 + 0.5
	return float(b.get("start_m", 30.0)) + rise * float(b.get("rise_m", 60.0)) + ridge * rise * float(b.get("ridge_m", 110.0))
