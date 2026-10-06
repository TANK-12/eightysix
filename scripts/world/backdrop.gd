class_name Backdrop
extends RefCounted

const GORGE_M := 350.0
const RIM_FALL := 0.25  # how fast (m per m outward) the far hills may fall below a high rim behind it
## Far hills beyond a map's edge (lane B4), so the rim is not the end of the world. Visual only: no
## collision, no shadows. A grid over the square out to extent_m, minus the playable map, rising from
## just under the rim top at the edge to ridges further out; fog does the rest. From the map entry's
## "backdrop" block: {extent_m, cell_m, start_m, rise_m, ridge_m, colour, seed, texture_m, relief (the rock normal map's strength), and for the
## gorge: gorge_rise_m (how far out a gap in the rim takes to climb into the hills), bend_m and
## bend_over_m (the rim's shape slides this far sideways over that distance out, so a gorge curves
## out of sight instead of running straight into a ramp), water_reach_m (the map's water plane
## reaches this far past the edge, showing only where the ground is below it: the river runs on)}.


## edge_height(x, z): the map terrain's height at a point on its edge. Where the rim is low (the river's
## gorge), the far hills start at that height and climb over gorge_rise_m (GORGE_M if the map does not
## say), so the gorge runs on out of the map, curving by bend_m.
static func build(parent: Node3D, entry: Dictionary, rock: Texture2D = null, edge_height: Callable = Callable()) -> MeshInstance3D:
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
			var x := -extent + xi * cell
			var z := -extent + zi * cell
			var edge := INF
			# every vertex a drawn cell uses (cells reach two cells inside the edge, see below); sampling
			# only the outer row left the inner rows at the default height: a 22 m slab across the gorge
			if edge_height.is_valid() and maxf(absf(x), absf(z)) >= half - 2.0 * cell - 0.01:
				var at := edge_sample(x, z, half, b)
				edge = float(edge_height.call(at.x, at.y))
			heights[zi * (cells + 1) + xi] = height_at(x, z, half, b, noise, edge)
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
		# and its relief at the same scale (lane LOOK2): without it the far hills shaded like smooth plastic
		var nrm_path := rock.resource_path.get_base_dir().path_join("normal.jpg")
		if ResourceLoader.exists(nrm_path):
			mat.normal_enabled = true
			mat.normal_texture = load(nrm_path)
			mat.normal_scale = float(b.get("relief", 1.6))
	mi.material_override = mat
	parent.add_child(mi)
	_reach_water(parent, half, float(b.get("water_reach_m", 0.0)))
	return mi


## Where on the map's edge (x, z) takes the rim's height from: straight in, slid sideways along the
## edge by bend_m over bend_over_m outward, so whatever the rim does there (a gorge, a pass) curves.
static func edge_sample(x: float, z: float, half: float, b: Dictionary) -> Vector2:
	var out := maxf(maxf(absf(x), absf(z)) - half, 0.0)
	var slide := float(b.get("bend_m", 0.0)) * smoothstep(0.0, float(b.get("bend_over_m", 300.0)), out)
	if absf(z) >= absf(x):
		x -= slide * signf(z)
	else:
		z += slide * signf(x)
	return Vector2(clampf(x, -half, half), clampf(z, -half, half))


## The map's own water plane (a "Water" PlaneMesh sibling, built before the backdrop) made reach_m
## wider on every side. The far hills cover it everywhere but where they dip below the water.
static func _reach_water(parent: Node, half: float, reach_m: float) -> void:
	var water := parent.get_node_or_null("Water") as MeshInstance3D
	if reach_m <= 0.0 or water == null or not (water.mesh is PlaneMesh):
		return
	var plane := (water.mesh as PlaneMesh).duplicate() as PlaneMesh
	plane.size = Vector2.ONE * (half + reach_m) * 2.0
	plane.subdivide_width = 16
	plane.subdivide_depth = 16
	water.mesh = plane


## Height (m) of the backdrop at (x, z): under the rim top at the map's edge (so the rim hides the
## join), rising outward, with ridged hills on top. Inside the map it sinks well below the ground.
## With the terrain's edge height: below a low rim it starts at that height (the gorge, above); behind
## a high rim it starts at the rim's height and falls at most RIM_FALL per metre outward.
static func height_at(x: float, z: float, half: float, b: Dictionary, noise: FastNoiseLite, edge: float = INF) -> float:
	var out := maxf(absf(x), absf(z)) - half
	var start := float(b.get("start_m", 30.0))
	var gorge := 1.0
	if edge < start:
		# a gap in the rim: begin just under the terrain there and climb to the usual hills over GORGE_M
		# eased in: the floor stays near the water for the first stretch, then climbs round the bend
		gorge = pow(smoothstep(0.0, float(b.get("gorge_rise_m", GORGE_M)), maxf(out, 0.0)), 2.0)
		start = lerpf(edge - 1.0, start, gorge)
	if out < 0.0:
		return start + out * 0.5
	var rise := clampf(out / 400.0, 0.0, 1.0) * gorge
	var ridge := noise.get_noise_2d(x, z) * 0.5 + 0.5
	var hills := start + rise * float(b.get("rise_m", 60.0)) + ridge * rise * float(b.get("ridge_m", 110.0))
	if edge != INF and edge > start:
		# a high rim: carry it on outward, falling gently, until the hills take over (no flat shelf
		# of far hill behind the gorge's walls)
		hills = maxf(hills, edge - 0.5 - out * RIM_FALL)
	return hills
