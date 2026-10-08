class_name SmallMapSky
extends RefCounted
## Sky, sun, fog and clouds for the maps (lane B3), from one data/weather.json entry. The environment
## joins the "world_environment" group and the sun the "sun" group, so the graphics presets still
## switch SDFGI, SSAO, volumetric fog and shadows on them. Cloud quality follows Settings > Graphics
## > Clouds live.

const SKY_SHADER := preload("res://assets/kit/shaders/sky.gdshader")
const CLOUD_QUALITY := {"off": 0, "low": 1, "high": 2}

var env := Environment.new()
var world_env := WorldEnvironment.new()
var sun := DirectionalLight3D.new()
var sky_mat := ShaderMaterial.new()
var weather_id := ""
var water_mats: Array[ShaderMaterial] = []  # lane B4: water reflects this weather's sky
## lane B5: a bigger map thins every fog by this (the weathers' fog is set for a 1 km map; over 4 km
## it piles up into a brown wall); maps.json "fog_scale", applied with the weather
var fog_scale := 1.0


func _init(parent: Node, weather: String) -> void:
	sky_mat.shader = SKY_SHADER
	var tex := NoiseTexture2D.new()
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_PERLIN
	noise.frequency = 0.012
	noise.fractal_octaves = 5
	tex.noise = noise
	tex.width = 512
	tex.height = 512
	tex.seamless = true
	tex.generate_mipmaps = true
	sky_mat.set_shader_parameter("cloud_noise", tex)
	var sky := Sky.new()
	sky.sky_material = sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.fog_enabled = true
	env.fog_aerial_perspective = 0.55
	env.fog_sky_affect = 0.35
	env.volumetric_fog_anisotropy = 0.45
	env.ssao_radius = 1.8
	env.ssao_intensity = 1.8
	env.glow_bloom = 0.0
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	env.sdfgi_use_occlusion = true
	env.sdfgi_cascades = 4
	world_env.environment = env
	world_env.add_to_group("world_environment")
	parent.add_child(world_env)
	sun.light_angular_distance = 0.6
	sun.shadow_blur = 1.2
	sun.add_to_group("sun")
	parent.add_child(sun)
	apply(weather)
	_apply_clouds()
	_apply_splits()
	Settings.changed.connect(_on_setting)


func apply(id: String) -> void:
	if not Registry.has_entry("weather", id):
		push_warning("SmallMapSky: no weather '%s'" % id)
		return
	weather_id = id
	var w := Registry.entry("weather", id)
	var el := deg_to_rad(float(w.get("sun_elevation_deg", 30.0)))
	var az := deg_to_rad(float(w.get("sun_azimuth_deg", 135.0)))
	# azimuth clockwise from north (-Z); the light shines from the sun toward the ground
	var to_sun := Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el))
	sun.basis = Basis.looking_at(-to_sun, Vector3.UP if absf(to_sun.y) < 0.99 else Vector3.FORWARD)
	sun.light_energy = float(w.get("sun_energy", 1.3))
	sun.light_color = _c(w, "sun_colour")
	for m in water_mats:
		m.set_shader_parameter("sky_top", _c(w, "sky_top"))
		m.set_shader_parameter("sky_horizon", _c(w, "sky_horizon"))
	sky_mat.set_shader_parameter("sky_top", _c(w, "sky_top"))
	sky_mat.set_shader_parameter("sky_horizon", _c(w, "sky_horizon"))
	sky_mat.set_shader_parameter("ground_colour", _c(w, "ground_colour"))
	sky_mat.set_shader_parameter("cloud_lit", _c(w, "cloud_lit"))
	sky_mat.set_shader_parameter("cloud_shade", _c(w, "cloud_shade"))
	sky_mat.set_shader_parameter("coverage", float(w.get("cloud_coverage", 0.5)))
	# LOOK3: a weather made for one map ("fog_unscaled") already has that map's fog, so fog_scale is left out
	var k := 1.0 if bool(w.get("fog_unscaled", false)) else fog_scale
	sky_mat.set_shader_parameter("cloud_scale", float(w.get("cloud_scale", 1.0)))
	sky_mat.set_shader_parameter("sky_saturation", float(w.get("sky_saturation", 1.3)))
	env.fog_light_color = _c(w, "fog_colour")
	env.fog_density = float(w.get("fog_density", 0.001)) * k
	env.volumetric_fog_density = float(w.get("volumetric_density", 0.01)) * k
	env.volumetric_fog_length = float(w.get("volumetric_length_m", 180.0))
	env.volumetric_fog_albedo = _c(w, "fog_colour").lightened(0.2)
	env.ambient_light_energy = float(w.get("ambient_energy", 0.85))
	env.tonemap_exposure = float(w.get("exposure", 1.0))
	env.tonemap_white = float(w.get("white", 1.0))
	# lane LOOK2: AgX ignores tonemap_white; its own white point (Godot default 16.29) is for HDR scenes far brighter
	# than ours, so sunlit ground topped out near 170 of 255 and the picture read as washed out
	env.tonemap_agx_white = float(w.get("agx_white", 16.29))
	env.tonemap_agx_contrast = float(w.get("agx_contrast", 1.25))
	env.volumetric_fog_ambient_inject = float(w.get("volumetric_ambient_inject", 0.4))
	# lane B4 part 3: only light above the threshold blooms (the sun disc, muzzle flashes, fire)
	env.glow_intensity = float(w.get("glow_intensity", 0.3))
	env.glow_hdr_threshold = float(w.get("glow_threshold", 1.4))
	# lane B4: sun-lit haze toward the sun, fog that pools in the valley floor, and a film grade
	env.fog_sun_scatter = float(w.get("sun_scatter", 0.0))
	env.fog_height = float(w.get("height_fog_top_m", 0.0))
	env.fog_height_density = float(w.get("height_fog_density", 0.0)) * k
	env.fog_sky_affect = float(w.get("fog_sky_affect", 0.35))
	env.volumetric_fog_anisotropy = float(w.get("volumetric_anisotropy", 0.45))
	var grade: Dictionary = w.get("grade", {})
	# Alpha 0.1.1: the grade's contrast is a soft S-curve in the grade table (FilmGrade.contrast_curve); the
	# environment's own contrast is a straight line that clipped every shadow under 16 of 255 to black
	env.adjustment_contrast = 1.0
	env.adjustment_saturation = float(grade.get("saturation", 1.0))
	var table := grade.has("contrast") or grade.has("shadow_shift") or grade.has("highlight_shift")
	env.adjustment_color_correction = FilmGrade.lut(grade) if table else null


func _apply_clouds() -> void:
	sky_mat.set_shader_parameter("quality", int(CLOUD_QUALITY.get(Settings.get_s("graphics.clouds"), 1)))


## Two shadow cascades are plenty up to 100 m and measured about 7 ms cheaper on the Iris Xe (Medium);
## longer shadow distances (High, Ultra) keep four.
func _apply_splits() -> void:
	var short := Settings.get_f("graphics.shadow_distance") <= 100.0
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS if short else DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS


func _on_setting(key: String, _value: Variant) -> void:
	if key == "graphics.clouds":
		_apply_clouds()
	elif key == "graphics.shadow_distance":
		_apply_splits()


func disconnect_settings() -> void:
	if Settings.changed.is_connected(_on_setting):
		Settings.changed.disconnect(_on_setting)


static func _c(w: Dictionary, key: String) -> Color:
	var a: Array = w.get(key, [0.5, 0.5, 0.5])
	return Color(float(a[0]), float(a[1]), float(a[2]))
