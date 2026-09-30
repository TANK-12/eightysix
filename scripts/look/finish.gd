class_name Finish
extends RefCounted
## Paint and wear on the Juggernaut (lane B4), from one data/finishes.json entry. Works on the
## per-mech StandardMaterial3D copies juggernaut_mech.gd already makes for Metal shine, keyed by the
## export's material names, so shine keeps scaling metallic on top of the finish. Grime is a detail
## layer: mottled dirt multiplied in, projected three ways in the part's own space so it rides along.

const GRIME_SCALE := 0.7  # repeats per metre
const GRIME_STEPS := 8  # grime amounts are rounded to eighths so parts share textures

static var _grime_cache := {}


## Applies finish_id to every material in mats whose resource_name the entry names. Returns
## {material: metallic} for the materials it changed, so the caller can refresh its shine bases.
static func apply_to(mats: Array, finish_id: String) -> Dictionary:
	var changed := {}
	if not Registry.has_entry("finishes", finish_id):
		return changed
	var spec: Dictionary = Registry.entry("finishes", finish_id).get("materials", {})
	for m: Variant in mats:
		var mat := m as StandardMaterial3D
		if mat == null:
			continue
		if not mat.has_meta("finish_export"):
			mat.set_meta("finish_export", {"albedo": [mat.albedo_color.r, mat.albedo_color.g, mat.albedo_color.b], "metallic": mat.metallic, "roughness": mat.roughness})
		# a material the finish does not name goes back to the export's look (live switching)
		var f: Dictionary = spec.get(_base_name(mat.resource_name), mat.get_meta("finish_export"))
		var a: Array = f.get("albedo", [1, 1, 1])
		mat.albedo_color = Color(float(a[0]), float(a[1]), float(a[2]))
		mat.metallic = float(f.get("metallic", mat.metallic))
		mat.roughness = float(f.get("roughness", mat.roughness))
		_set_grime(mat, float(f.get("grime", 0.0)))
		changed[mat] = mat.metallic
	return changed


## "JG2_paint" also matches Godot's import-renamed duplicates ("JG2_paint_001" and the like).
static func _base_name(n: String) -> String:
	for key in ["JG2_paint", "JG2_metal", "JG2_frame", "JG2_steel"]:
		if n.begins_with(key):
			return key
	return n


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
