extends Node
## Graphics presets and display settings, applied live.
##
## Picking a preset (Settings "graphics.preset") copies its fields from data/graphics_presets.json
## into the matching graphics.* settings; changing any of those by hand turns the preset to Custom.
## apply() pushes everything to the window, the renderer and the scene: WorldEnvironments in the
## "world_environment" group, suns in "sun", cameras in "game_camera". Nodes that join those groups
## later are picked up as they enter the tree, so levels need no extra call.

signal applied

const COLOUR_FILTER_SHADER := "res://assets/shaders/colour_filter.gdshader"
const FILTER_MODES := {"none": 0, "protanopia": 1, "deuteranopia": 2, "tritanopia": 3, "greyscale": 4}

var _copying_preset := false
var _filter_layer: CanvasLayer
var _filter_rect: ColorRect
var _fps_layer: CanvasLayer
var _fps_label: Label
var _fps_mode := "off"


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_make_overlays()
	Settings.changed.connect(_on_setting_changed)
	get_tree().node_added.connect(_on_node_added)
	var preset := Settings.get_s("graphics.preset")
	if preset != "custom" and not preset_matches(preset):
		copy_preset(preset)
	apply()


## Every graphics.* setting that belongs to a preset, keyed by its preset field.
func preset_keys() -> Dictionary:
	var out := {}
	for key: String in Settings.keys():
		var field := str(Settings.item(key).get("preset_field", ""))
		if field != "":
			out[field] = key
	return out


func copy_preset(preset_id: String) -> void:
	if not Registry.has_entry("graphics_presets", preset_id):
		return
	var preset := Registry.entry("graphics_presets", preset_id)
	_copying_preset = true
	var fields := preset_keys()
	for field: String in fields:
		if preset.has(field):
			Settings.set_value(fields[field], preset[field])
	_copying_preset = false


func preset_matches(preset_id: String) -> bool:
	if not Registry.has_entry("graphics_presets", preset_id):
		return false
	var preset := Registry.entry("graphics_presets", preset_id)
	var fields := preset_keys()
	for field: String in fields:
		if preset.has(field) and Settings.sanitise(fields[field], preset[field]) != null:
			var want: Variant = Settings.sanitise(fields[field], preset[field])
			var have: Variant = Settings.get_value(fields[field])
			if not Settings._same(want, have):
				return false
	return true


func _on_setting_changed(key: String, value: Variant) -> void:
	if key == "graphics.preset":
		if str(value) != "custom":
			copy_preset(str(value))
		apply()
		return
	if not key.begins_with("graphics.") and not key.begins_with("accessibility."):
		return
	if not _copying_preset and Settings.item(key).has("preset_field"):
		var preset := Settings.get_s("graphics.preset")
		if preset != "custom" and not preset_matches(preset):
			Settings.set_value("graphics.preset", "custom")
	if not _copying_preset:
		apply()


func apply() -> void:
	var root := get_tree().root
	var scale := Settings.get_f("graphics.resolution_scale")
	root.scaling_3d_scale = scale
	match Settings.get_s("graphics.upscaler"):
		"fsr1":
			root.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR if scale < 0.999 else Viewport.SCALING_3D_MODE_BILINEAR
		"fsr2":
			root.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR2
		_:
			root.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	match Settings.get_s("graphics.msaa"):
		"2x":
			root.msaa_3d = Viewport.MSAA_2X
		"4x":
			root.msaa_3d = Viewport.MSAA_4X
		_:
			root.msaa_3d = Viewport.MSAA_DISABLED
	var aa := Settings.get_s("graphics.screen_aa")
	root.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA if aa == "fxaa" else Viewport.SCREEN_SPACE_AA_DISABLED
	root.use_taa = aa == "taa"
	root.mesh_lod_threshold = Settings.get_f("graphics.lod_bias")
	root.anisotropic_filtering_level = int(Settings.get_f("graphics.anisotropic")) as Viewport.AnisotropicFiltering
	root.content_scale_factor = Settings.get_f("accessibility.ui_scale")

	RenderingServer.directional_shadow_atlas_set_size(int(Settings.get_f("graphics.shadow_size")), true)
	var filter := int(Settings.get_f("graphics.shadow_filter")) as RenderingServer.ShadowQuality
	RenderingServer.directional_soft_shadow_filter_set_quality(filter)
	RenderingServer.positional_soft_shadow_filter_set_quality(filter)
	RenderingServer.environment_set_volumetric_fog_volume_size(
		int(Settings.get_f("graphics.fog_volume_size")), int(Settings.get_f("graphics.fog_volume_depth"))
	)

	_apply_window()
	for node in get_tree().get_nodes_in_group("world_environment"):
		_apply_environment(node)
	for node in get_tree().get_nodes_in_group("sun"):
		_apply_sun(node)
	for node in get_tree().get_nodes_in_group("game_camera"):
		_apply_camera(node)
	_apply_colour_filter()
	_set_fps_mode(Settings.get_s("graphics.show_fps"))
	applied.emit()


func _apply_window() -> void:
	if DisplayServer.get_name() == "headless" or Bot.active:
		return
	match Settings.get_s("graphics.window_mode"):
		"fullscreen":
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN)
		"borderless":
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
		_:
			if DisplayServer.window_get_mode() != DisplayServer.WINDOW_MODE_WINDOWED:
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
	match Settings.get_s("graphics.vsync"):
		"off":
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		"adaptive":
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ADAPTIVE)
		"mailbox":
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_MAILBOX)
		_:
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED)
	Engine.max_fps = int(Settings.get_f("graphics.fps_cap"))


func _apply_environment(node: Node) -> void:
	var holder := node as WorldEnvironment
	if holder == null or holder.environment == null:
		return
	var env := holder.environment
	env.sdfgi_enabled = Settings.get_b("graphics.sdfgi")
	env.ssao_enabled = Settings.get_b("graphics.ssao")
	env.ssil_enabled = Settings.get_b("graphics.ssil")
	env.ssr_enabled = Settings.get_b("graphics.ssr")
	env.glow_enabled = Settings.get_b("graphics.glow")
	env.volumetric_fog_enabled = Settings.get_b("graphics.volumetric_fog")
	env.adjustment_enabled = true
	env.adjustment_brightness = Settings.get_f("graphics.brightness")


func _apply_sun(node: Node) -> void:
	var sun := node as DirectionalLight3D
	if sun == null:
		return
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = Settings.get_f("graphics.shadow_distance")


func _apply_camera(node: Node) -> void:
	var cam := node as Camera3D
	if cam != null:
		cam.far = Settings.get_f("graphics.draw_distance")


func _on_node_added(node: Node) -> void:
	if node is WorldEnvironment or node is DirectionalLight3D or node is Camera3D:
		_apply_new_node.call_deferred(node)


## Untyped on purpose: a node freed before this deferred call runs arrives as a freed Object,
## which a typed Node argument rejects before the validity check can run.
func _apply_new_node(node: Variant) -> void:
	if not is_instance_valid(node):
		return
	if node.is_in_group("world_environment"):
		_apply_environment(node)
	if node.is_in_group("sun"):
		_apply_sun(node)
	if node.is_in_group("game_camera"):
		_apply_camera(node)


# --- overlays: colour filter and frame-rate counter ------------------------------------------


func _make_overlays() -> void:
	_filter_layer = CanvasLayer.new()
	_filter_layer.layer = 120
	add_child(_filter_layer)
	_filter_rect = ColorRect.new()
	_filter_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_filter_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var mat := ShaderMaterial.new()
	mat.shader = load(COLOUR_FILTER_SHADER)
	_filter_rect.material = mat
	_filter_layer.add_child(_filter_rect)

	_fps_layer = CanvasLayer.new()
	_fps_layer.layer = 110
	add_child(_fps_layer)
	_fps_label = Label.new()
	_fps_label.theme_type_variation = "MonoLabel"
	_fps_label.position = Vector2(16, 12)
	UiTheme.adopt(_fps_label)
	_fps_layer.add_child(_fps_label)


func _apply_colour_filter() -> void:
	var mode: int = FILTER_MODES.get(Settings.get_s("accessibility.colour_filter"), 0)
	_filter_layer.visible = mode != 0
	var mat := _filter_rect.material as ShaderMaterial
	mat.set_shader_parameter("mode", mode)
	mat.set_shader_parameter("strength", Settings.get_f("accessibility.colour_filter_strength"))


func _set_fps_mode(mode: String) -> void:
	_fps_mode = mode
	_fps_layer.visible = mode != "off"


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_fps"):
		var next := "fps" if _fps_mode == "off" else ("full" if _fps_mode == "fps" else "off")
		Settings.set_value("graphics.show_fps", next)


func _process(_delta: float) -> void:
	if _fps_mode == "off":
		return
	var fps := Engine.get_frames_per_second()
	if _fps_mode == "fps":
		_fps_label.text = "%d fps" % fps
	else:
		_fps_label.text = "%d fps  %.1f ms  %s" % [
			fps,
			1000.0 / maxf(fps, 1.0),
			Settings.label_for("graphics.preset", Settings.get_value("graphics.preset")),
		]
