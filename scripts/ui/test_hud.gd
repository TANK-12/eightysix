extends CanvasLayer
## Test HUD for lane A1's range: a gun reticle where the fixed gun points, a heading tape, and a
## readout of speed, legs on the ground, jump charge, skid and physics mode. Lane A3 builds the real
## HUD (ammo, damage diagram); this one is here so a run can be read from a screenshot.

var mech: Node3D
var _root: Control
var _readout: Label
var _flags: Label
var _charge: ProgressBar
var _draw: Control


func watch(node: Node3D) -> void:
	mech = node


func _ready() -> void:
	layer = 10
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_draw = Control.new()
	_draw.set_anchors_preset(Control.PRESET_FULL_RECT)
	_draw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_draw.draw.connect(_on_draw)
	_root.add_child(_draw)

	var panel := PanelContainer.new()
	panel.theme_type_variation = "HelpPanel"
	panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	panel.offset_left = 40
	panel.offset_bottom = -40
	panel.offset_top = -210
	panel.offset_right = 520
	panel.modulate = Color(1, 1, 1, Settings.get_f("gameplay.hud_opacity"))
	_root.add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	panel.add_child(box)
	_readout = Label.new()
	_readout.theme_type_variation = "MonoLabel"
	box.add_child(_readout)
	_charge = ProgressBar.new()
	_charge.show_percentage = false
	_charge.custom_minimum_size = Vector2(440, 6)
	box.add_child(_charge)
	_flags = Label.new()
	_flags.theme_type_variation = "WarnLabel"
	box.add_child(_flags)
	_root.scale = Vector2.ONE * Settings.get_f("gameplay.hud_scale")


func _process(_delta: float) -> void:
	if mech == null or not is_instance_valid(mech) or not mech.has_method("telemetry"):
		return
	var t: Dictionary = mech.call("telemetry")
	var metric := Settings.get_s("gameplay.units") == "metric"
	var speed := float(t["speed_m_s"]) * (3.6 if metric else 2.237)
	_readout.text = "%3d %s   hdg %03d°   legs %d/4\npitch %+5.1f°   mass %.1f t   %s" % [
		roundi(speed),
		"km/h" if metric else "mph",
		roundi(float(t["heading_deg"])),
		int(t["grounded_legs"]),
		float(t["pitch_deg"]),
		float(t["mass_kg"]) / 1000.0,
		"test bench" if t["physics_mode"] == "bench" else "game mode",
	]
	_charge.value = float(mech.call("charge_fraction")) * 100.0
	var flags := PackedStringArray()
	if bool(t["charging"]):
		flags.append("charging jump")
	if bool(t["airborne"]):
		flags.append("airborne")
	if bool(t["skidding"]):
		flags.append("skid")
	_flags.text = "  ·  ".join(flags)
	_draw.queue_redraw()


func _on_draw() -> void:
	if mech == null or not is_instance_valid(mech):
		return
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var accent := UiTheme.color("accent")
	var ray: Array = mech.call("gun_ray")
	var aim_point: Vector3 = (ray[0] as Vector3) + (ray[1] as Vector3) * 250.0
	var style := Settings.get_s("gameplay.crosshair")
	if style != "none" and not cam.is_position_behind(aim_point):
		var p := cam.unproject_position(aim_point)
		if style == "dot":
			_draw.draw_circle(p, 3.0, accent)
		else:
			_draw.draw_arc(p, 18.0, 0.0, TAU, 40, accent, 1.5, true)
			for d: Vector2 in [Vector2.LEFT, Vector2.RIGHT, Vector2.UP, Vector2.DOWN]:
				_draw.draw_line(p + d * 24.0, p + d * 36.0, accent, 1.5, true)
			_draw.draw_circle(p, 1.5, accent)
	if Settings.get_b("gameplay.heading_tape"):
		_draw_heading(accent)


func _draw_heading(col: Color) -> void:
	var heading := float(mech.call("heading_deg"))
	var width := _draw.size.x
	var cx := width * 0.5
	var px_per_deg := 6.0
	var font := UiTheme.font("mono")
	for deg in range(int(heading) - 60, int(heading) + 61):
		if deg % 5 != 0:
			continue
		var x := cx + (deg - heading) * px_per_deg
		var tall := deg % 15 == 0
		_draw.draw_line(Vector2(x, 40), Vector2(x, 52 if tall else 46), Color(col, 0.7), 1.0)
		if deg % 30 == 0:
			var label := "%03d" % posmod(deg, 360)
			_draw.draw_string(font, Vector2(x - 18, 76), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(col, 0.8))
	_draw.draw_line(Vector2(cx, 34), Vector2(cx, 56), UiTheme.color("warn"), 2.0)
