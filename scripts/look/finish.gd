class_name Finish
extends RefCounted
## Paint and wear on the Juggernaut (lane B4), from one data/finishes.json entry. Works on the
## per-mech StandardMaterial3D copies juggernaut_mech.gd already makes for Metal shine, keyed by the
## export's material names, so shine keeps scaling metallic on top of the finish. Grime is a detail
## layer: mottled dirt multiplied in, projected three ways in the part's own space so it rides along.
## A finish material may name a surface (data/mech_surfaces.json, look part 3): real CC0 albedo,
## normal and roughness/metal maps, projected the same way because the exports carry no UV maps.
## The Legion use the same code with their own registry (data/legion_finishes.json). Grime rises
## from the feet: band_copies gives low parts their own material copies, and a finish material's
## grime_rise adds dirt per band (tuning.json "mech_grime_bands").

const GRIME_SCALE := 0.7  # repeats per metre
const GRIME_STEPS := 8  # grime amounts are rounded to eighths so parts share textures
const SURFACE_DIR := "res://assets/textures/mech"
const SURFACE_ROUGH_MEAN := 0.75  # tools/make_mech_textures.py brings each roughness map to this mean

static var _grime_cache := {}


## Applies finish_id to every material in mats whose resource_name the entry names. Returns
## {material: metallic} for the materials it changed, so the caller can refresh its shine bases.
static func apply_to(mats: Array, finish_id: String, registry := "finishes") -> Dictionary:
	var changed := {}
	if not Registry.has_entry(registry, finish_id):
		return changed
	var spec: Dictionary = Registry.entry(registry, finish_id).get("materials", {})
	for m: Variant in mats:
		var mat := m as StandardMaterial3D
		if mat == null:
			continue
		if not mat.has_meta("finish_export"):
			var e := mat.emission
			mat.set_meta("finish_export", {"albedo": [mat.albedo_color.r, mat.albedo_color.g, mat.albedo_color.b], "metallic": mat.metallic, "roughness": mat.roughness, "emission": [e.r, e.g, e.b]})
		# a material the finish does not name goes back to the export's look (live switching)
		var f: Dictionary = spec.get(_key_in(spec, mat.resource_name), mat.get_meta("finish_export"))
		var a: Array = f.get("albedo", [1, 1, 1])
		mat.albedo_color = Color(float(a[0]), float(a[1]), float(a[2]))
		mat.metallic = float(f.get("metallic", mat.metallic))
		mat.roughness = float(f.get("roughness", mat.roughness))
		var glow: Array = f.get("emission", mat.get_meta("finish_export")["emission"])
		mat.emission = Color(float(glow[0]), float(glow[1]), float(glow[2]))
		var surface := _apply_surface(mat, str(f.get("surface", "")))
		if surface:
			# the map's mean times this gives the finish's roughness as its average
			mat.roughness = minf(mat.roughness / SURFACE_ROUGH_MEAN, 1.0)
		var rise: Array = f.get("grime_rise", [])
		var band := int(mat.get_meta("finish_band", -1))
		var low := float(rise[band]) if band >= 0 and band < rise.size() else 0.0
		mat.set_meta("finish_grime", float(f.get("grime", 0.0)) + low)
		mat.set_meta("finish_roughness", mat.roughness)
		_apply_grime(mat)
		changed[mat] = mat.metallic
	return changed


## Gives every surface under root whose material want(mat) accepts a copy per height band, so the
## feet and lower legs can carry more grime than the hull. Bands are fractions of the model's rest
## height (tuning.json "mech_grime_bands" heights, lowest first; a part's band is where its centre
## sits, the top band is everything above). cache maps material and band to its copy, so models
## sharing materials (every Legion of a kind) share the copies; returns the copies new to cache.
static func band_copies(root: Node3D, cache: Dictionary, want: Callable) -> Array:
	var heights: Array = Registry.tune("mech_grime_bands", {}).get("heights", [])
	var parts: Array = []
	var floor_y := INF
	var top_y := -INF
	for n: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if mi.mesh == null:
			continue
		var box := rest_transform(mi, root) * mi.get_aabb()
		floor_y = minf(floor_y, box.position.y)
		top_y = maxf(top_y, box.end.y)
		parts.append([mi, box.get_center().y])
	var made: Array = []
	for pc: Array in parts:
		var mi: MeshInstance3D = pc[0]
		var band := heights.size()
		for b in heights.size():
			if float(pc[1]) < lerpf(floor_y, top_y, float(heights[b])):
				band = b
				break
		for i in mi.mesh.get_surface_count():
			var mat := mi.get_active_material(i) as StandardMaterial3D
			if mat == null or mat.has_meta("finish_band") or not want.call(mat):
				continue
			var key := "%d:%d" % [mat.get_instance_id(), band]
			if not cache.has(key):
				var dup := mat.duplicate() as StandardMaterial3D
				dup.set_meta("finish_band", band)
				cache[key] = dup
				made.append(dup)
			mi.set_surface_override_material(i, cache[key])
	return made


## mi's transform in root's space from the local transforms (works before the model is in the tree).
static func rest_transform(mi: Node3D, root: Node3D) -> Transform3D:
	var xf := mi.transform
	var p := mi.get_parent() as Node3D
	while p != null and p != root:
		xf = p.transform * xf
		p = p.get_parent() as Node3D
	return xf


## "JG2_paint" also matches Godot's import-renamed duplicates ("JG2_paint_001" and the like).
static func _base_name(n: String) -> String:
	for key in ["JG2_paint", "JG2_metal", "JG2_frame", "JG2_steel"]:
		if n.begins_with(key):
			return key
	return n


## The finish key a material name belongs to: the longest key it starts with, so "LG_shell_dark_night"
## is LG_shell_dark (not LG_shell) and "JG2_paint_001" is JG2_paint. "" when none fits.
static func _key_in(spec: Dictionary, n: String) -> String:
	var best := ""
	for key: String in spec:
		if n.begins_with(key) and key.length() > best.length():
			best = key
	return best


## Lays a data/mech_surfaces.json surface on mat, projected three ways in the part's own space so it
## rides with the part. "" (or an unknown id) puts the export's own maps back. True if one was laid.
static func _apply_surface(mat: StandardMaterial3D, surface_id: String) -> bool:
	if not mat.has_meta("finish_export_maps"):
		mat.set_meta("finish_export_maps", {"albedo": mat.albedo_texture, "normal": mat.normal_texture, "normal_on": mat.normal_enabled, "normal_scale": mat.normal_scale, "roughness": mat.roughness_texture, "metallic": mat.metallic_texture, "triplanar": mat.uv1_triplanar, "scale": mat.uv1_scale})
	if surface_id == "" or not Registry.has_entry("mech_surfaces", surface_id):
		var e: Dictionary = mat.get_meta("finish_export_maps")
		mat.albedo_texture = e["albedo"]
		mat.normal_texture = e["normal"]
		mat.normal_enabled = e["normal_on"]
		mat.normal_scale = e["normal_scale"]
		mat.roughness_texture = e["roughness"]
		mat.metallic_texture = e["metallic"]
		mat.uv1_triplanar = e["triplanar"]
		mat.uv1_scale = e["scale"]
		mat.ao_enabled = false
		mat.set_meta("finish_surface", "")
		return false
	var s := Registry.entry("mech_surfaces", surface_id)
	var dir := SURFACE_DIR.path_join(surface_id)
	var orm: Texture2D = load(dir.path_join("orm.jpg"))
	mat.albedo_texture = load(dir.path_join("albedo.jpg"))
	mat.normal_enabled = true
	mat.normal_texture = load(dir.path_join("normal.jpg"))
	mat.normal_scale = float(s.get("normal", 1.0))
	mat.roughness_texture = orm
	mat.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	mat.metallic_texture = orm
	mat.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE
	mat.uv1_triplanar = true
	mat.uv1_world_triplanar = false
	mat.uv1_scale = Vector3.ONE * float(s.get("scale", 1.0))
	mat.uv1_triplanar_sharpness = 4.0
	# the occlusion map darkens the cavities between rivets, panel lines and dents
	mat.ao_enabled = true
	mat.ao_texture = orm
	mat.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	mat.ao_light_affect = float(s.get("ao_light", 0.0))
	mat.set_meta("finish_surface", surface_id)
	return true


## Dirt picked up on top of the finish over a sortie (GrimeBuildup); kept across finish switches.
static func set_extra(mat: StandardMaterial3D, extra: float, roughness_gain: float) -> void:
	mat.set_meta("grime_extra", maxf(extra, 0.0))
	mat.set_meta("grime_roughness_gain", roughness_gain)
	_apply_grime(mat)


## How dirty a finished material is now: the finish's own grime plus any sortie dirt, 0-1.
static func grime_of(mat: StandardMaterial3D) -> float:
	return clampf(float(mat.get_meta("finish_grime", 0.0)) + float(mat.get_meta("grime_extra", 0.0)), 0.0, 1.0)


static func _apply_grime(mat: StandardMaterial3D) -> void:
	var extra := float(mat.get_meta("grime_extra", 0.0))
	var rough := float(mat.get_meta("finish_roughness", mat.roughness))
	mat.roughness = clampf(rough + extra * float(mat.get_meta("grime_roughness_gain", 0.0)), 0.0, 1.0)
	_set_grime(mat, grime_of(mat))


static func _set_grime(mat: StandardMaterial3D, amount: float) -> void:
	var step := roundi(clampf(amount, 0.0, 1.0) * GRIME_STEPS)
	mat.detail_enabled = step > 0
	if step == 0:
		return
	mat.detail_albedo = grime_texture(step)
	mat.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MUL
	mat.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
	mat.uv2_triplanar = true
	mat.uv2_world_triplanar = false
	mat.uv2_scale = Vector3.ONE * GRIME_SCALE
	mat.uv2_triplanar_sharpness = 2.0


## Mottled dirt: white (no change) through to a dusty brown at the heaviest, as a colour ramp over
## cellular-ish noise. step 1..GRIME_STEPS.
static func grime_texture(step: int) -> NoiseTexture2D:
	if _grime_cache.has(step):
		return _grime_cache[step]
	var amount := float(step) / GRIME_STEPS
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.02
	noise.fractal_octaves = 5
	noise.fractal_gain = 0.6
	noise.seed = 86
	var ramp := Gradient.new()
	var dirt := Color(1.0, 1.0, 1.0).lerp(Color(0.55, 0.47, 0.38), amount)
	ramp.set_color(0, dirt)
	ramp.set_color(1, Color(1.0, 1.0, 1.0))
	ramp.add_point(0.45, Color(1.0, 1.0, 1.0).lerp(dirt, 0.35))
	var tex := NoiseTexture2D.new()
	tex.width = 256
	tex.height = 256
	tex.seamless = true
	tex.noise = noise
	tex.color_ramp = ramp
	tex.generate_mipmaps = true
	_grime_cache[step] = tex
	return tex
