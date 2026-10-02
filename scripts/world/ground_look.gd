class_name GroundLook
extends RefCounted
## The ground material both maps share (lane LOOK): ground.gdshader with its CC0 texture sets and the map's
## palette (maps.json "palette" -> "ground": any shader uniform by name, a 3-number list is a colour). A map
## also hands the "kit" block of its palette to Kit.apply_palette, so one ruin is painted for the map played.

const SHADER := preload("res://assets/kit/shaders/ground.gdshader")
const TEX := "res://assets/kit/textures/"

## shader uniform -> texture folder (color.jpg, normal.jpg)
const SETS := {
	"ground": "dirt",
	"turf": "grass_turf",
	"stone": "stones",
	"road": "gravel",
	"rock": "rock",
	"town": "concrete_dark",
}


## The material for one map entry (`water_level`: where the shore turns to wet mud).
static func material(entry: Dictionary, water_level: float) -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = SHADER
	for prefix: String in SETS:
		mat.set_shader_parameter(prefix + "_col", load(TEX + str(SETS[prefix]) + "/color.jpg"))
		mat.set_shader_parameter(prefix + "_nrm", load(TEX + str(SETS[prefix]) + "/normal.jpg"))
	mat.set_shader_parameter("macro", Kit.macro_noise())
	mat.set_shader_parameter("water_level", water_level)
	var palette: Dictionary = entry.get("palette", {})
	for uniform: String in palette.get("ground", {}):
		var v: Variant = palette["ground"][uniform]
		mat.set_shader_parameter(uniform, Color(float(v[0]), float(v[1]), float(v[2])) if v is Array else v)
	Kit.apply_palette(palette.get("kit", {}))
	return mat
