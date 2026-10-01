extends CanvasLayer
## Test HUD for lane A1's range: the 57 mm's mark where its round would land (part 4: Emerson could
## not tell where the main gun aims) and the sub-arm guns' small cross, a heading tape, and a
## readout of speed, legs on the ground, jump charge, skid and physics mode, with lane A3's
## CombatHud (ammo, range marks, damage diagram, wire anchor) drawn over it.

const SHADE := Color(0.0, 0.0, 0.0, 0.55)

var mech: Node3D
var _root: Control
var _readout: Label
var _flags: Label
var _charge: ProgressBar
var _draw: Control
var _combat: CombatHud
var _main_hit: Dictionary = {}
var _sub_hit: Dictionary = {}
var _aim_s := 0.0


func watch(node: Node3D) -> void:
	mech = node
	_combat.watch(node)


func _ready() -> void:
	layer = 10
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	UiTheme.adopt(_root)
	add_child(_root)
	_draw = Control.new()
	_draw.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_draw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_draw.draw.connect(_on_draw)
	_root.add_child(_draw)
	_combat = CombatHud.new()
	_root.add_child(_combat)

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


func _process(delta: float) -> void:
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
	# Where the guns' rounds would land, ten times a second (a cast flight each).
	_aim_s -= delta
	var combat := mech.get_node_or_null("Combat") as MechCombat
	if _aim_s <= 0.0 and combat != null:
		_aim_s = 0.1
		_main_hit = combat.main_impact()
		_sub_hit = combat.sub_impact()
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
	var mono := UiTheme.font("mono")
	var metric := Settings.get_s("gameplay.units") == "metric"
	# The sub-arm guns' mark: a small cross, dimmer, so it never reads as the 57 mm's.
	if not _sub_hit.is_empty() and not cam.is_position_behind(_sub_hit["point"]):
		var q := cam.unproject_position(_sub_hit["point"])
		var dim := Color(UiTheme.color("text"), 0.75)
		for pass_i in 2:
			for d: Vector2 in [Vector2(1, 1), Vector2(1, -1)]:
				_draw.draw_line(q - d * 7.0, q + d * 7.0, SHADE if pass_i == 0 else dim, 4.0 if pass_i == 0 else 1.5, true)
		_label(mono, q + Vector2(10.0, -7.0), "12.7", 12, dim)
	# The 57 mm's mark: where its round would land along the bore line, with the range.
	var style := Settings.get_s("gameplay.crosshair")
	if style != "none" and not _main_hit.is_empty() and not cam.is_position_behind(_main_hit["point"]):
		var p := cam.unproject_position(_main_hit["point"])
		# Drawn twice, a dark rim under the colour, so it reads over sky, ground and the mech's own gun.
		for pass_i in 2:
			var col := SHADE if pass_i == 0 else accent
			var w := 4.5 if pass_i == 0 else 2.0
			if style == "dot":
				_draw.draw_arc(p, 9.0, 0.0, TAU, 32, col, w, true)
				_draw.draw_circle(p, 3.5 if pass_i == 0 else 2.5, col)
				continue
			_draw.draw_arc(p, 22.0, 0.0, TAU, 48, col, w, true)
			for d: Vector2 in [Vector2.LEFT, Vector2.RIGHT, Vector2.UP, Vector2.DOWN]:
				_draw.draw_line(p + d * 28.0, p + d * 42.0, col, w, true)
			_draw.draw_circle(p, 3.0 if pass_i == 0 else 2.0, col)
		var r := float(_main_hit["range_m"]) * (1.0 if metric else 1.0936)
		var txt := ("57 mm  %d %s" % [roundi(r), "m" if metric else "yd"]) if bool(_main_hit["hit"]) else "57 mm  far"
		_label(mono, p + Vector2(48.0, 6.0), txt, 15, accent)
	if Settings.get_b("gameplay.heading_tape"):
		_draw_heading(accent)


## Text with a dark rim, readable over anything.
func _label(font: Font, at: Vector2, text: String, font_size: int, col: Color) -> void:
	_draw.draw_string_outline(font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, 4, SHADE)
	_draw.draw_string(font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, col)


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
