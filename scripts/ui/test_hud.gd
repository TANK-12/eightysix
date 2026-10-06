extends CanvasLayer
## The HUD of the range and the valley: the 57 mm's mark where its round would land (part 4: Emerson could
## not tell where the main gun aims) and the sub-arm guns' small cross, a heading tape, and (part 5, Emerson's
## note 7, "a better HUD") a status block in the manner of the anime's viewscreen overlays: corner brackets, a
## big speed figure with its gait, a speed bar, the four legs as pips (lit when carrying weight), an
## attitude ball and the jump charge as a ring, with lane A3's CombatHud (ammo, range marks, damage
## diagram, wire anchor) drawn over it. All drawn in one pass from the mech's telemetry.

const TUTORIAL := preload("res://scripts/ui/tutorial.gd")
const SHADE := Color(0.0, 0.0, 0.0, 0.55)

var mech: Node3D
var _root: Control
var _draw: Control
var _combat: CombatHud
var _hints: MoveHints
var _tutorial: Control  # Tutorial (lane A6 stub), preloaded so a fresh class cache is not needed
var _main_hit: Dictionary = {}
var _sub_hit: Dictionary = {}
var _aim_s := 0.0
var _t: Dictionary = {}
var _charge := 0.0
var _legs_down: Dictionary = {}  # leg name -> carrying weight


func watch(node: Node3D) -> void:
	mech = node
	_combat.watch(node)
	_hints.watch(node)


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

	_hints = MoveHints.new()
	_root.add_child(_hints)
	_tutorial = TUTORIAL.new()
	_tutorial.call("watch", _hints)
	_root.add_child(_tutorial)
	_root.scale = Vector2.ONE * Settings.get_f("gameplay.hud_scale")


func _process(delta: float) -> void:
	if mech == null or not is_instance_valid(mech) or not mech.has_method("telemetry"):
		return
	_t = mech.call("telemetry")
	_charge = float(mech.call("charge_fraction"))
	for leg: Dictionary in mech.get("legs"):
		_legs_down[str(leg["name"])] = bool(leg.get("loaded", false))
	# Where the guns' rounds would land, ten times a second (a cast flight each).
	_aim_s -= delta
	var combat := mech.get_node_or_null("Combat") as MechCombat
	if _aim_s <= 0.0 and combat != null:
		_aim_s = 0.1
		_main_hit = combat.main_impact()
		_sub_hit = combat.sub_impact()
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
	_draw_frame(accent)
	_draw_status(accent, metric)
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
	var mission := get_tree().get_first_node_in_group("mission") as Mission
	if mission != null and Settings.get_b("gameplay.objective_guide"):
		var g := mission.guide()
		if not g.is_empty():
			var off := clampf(angle_difference(deg_to_rad(heading), deg_to_rad(float(g["bearing_deg"]))), -1.0471976, 1.0471976)
			var px := cx + rad_to_deg(off) * px_per_deg
			var warn := UiTheme.color("warn")
			_draw.draw_colored_polygon(PackedVector2Array([Vector2(px, 36), Vector2(px + 7, 44), Vector2(px, 52), Vector2(px - 7, 44)]), warn)
	var chip := Rect2(cx - 26.0, 4.0, 52.0, 24.0)
	_draw.draw_rect(chip, SHADE)
	_draw.draw_rect(chip, Color(col, 0.6), false, 1.0)
	_draw.draw_string(UiTheme.font("heading"), Vector2(cx - 20.0, 23.0), "%03d" % roundi(heading), HORIZONTAL_ALIGNMENT_LEFT, -1, 20, col)


## Four corner brackets just inside the window, like a viewscreen's frame.
func _draw_frame(accent: Color) -> void:
	var col := Color(accent, 0.4)
	var m := 18.0
	var l := 30.0
	var w := _draw.size.x
	var h := _draw.size.y
	for corner: Vector2 in [Vector2(m, m), Vector2(w - m, m), Vector2(m, h - m), Vector2(w - m, h - m)]:
		var sx := 1.0 if corner.x < w * 0.5 else -1.0
		var sy := 1.0 if corner.y < h * 0.5 else -1.0
		_draw.draw_line(corner, corner + Vector2(sx * l, 0.0), col, 1.5, true)
		_draw.draw_line(corner, corner + Vector2(0.0, sy * l), col, 1.5, true)


## Bottom left: speed and gait, a speed bar, the legs, the attitude ball with the jump charge around it.
func _draw_status(accent: Color, metric: bool) -> void:
	if _t.is_empty():
		return
	var head := UiTheme.font("heading")
	var mono := UiTheme.font("mono")
	var text := UiTheme.color("text")
	var dim := UiTheme.color("text_dim")
	var warn := UiTheme.color("warn")
	var base := Vector2(52.0, _draw.size.y - 52.0)
	var speed_m_s := float(_t["speed_m_s"])
	var speed := speed_m_s * (3.6 if metric else 2.237)
	var figure := str(roundi(speed))
	_draw.draw_string_outline(head, base + Vector2(0.0, -64.0), figure, HORIZONTAL_ALIGNMENT_LEFT, -1, 66, 6, SHADE)
	_draw.draw_string(head, base + Vector2(0.0, -64.0), figure, HORIZONTAL_ALIGNMENT_LEFT, -1, 66, text)
	var figure_w := head.get_string_size(figure, HORIZONTAL_ALIGNMENT_LEFT, -1, 66).x
	_label(mono, base + Vector2(figure_w + 12.0, -68.0), "km/h" if metric else "mph", 18, text)
	var gait := "stand"
	if bool(_t["airborne"]):
		gait = "airborne"
	elif bool(_t["skidding"]):
		gait = "skid"
	elif bool(_t["charging"]):
		gait = "jump charge"
	elif bool(mech.get("running")):
		gait = "gallop"
	elif speed_m_s > 0.5:
		gait = "walk"
	_label(mono, base + Vector2(figure_w + 12.0, -46.0), gait, 18, warn if gait in ["airborne", "skid", "jump charge"] else accent)
	# The speed bar: the gallop's top speed is the full length, a tick every quarter.
	var top := Registry.tune_f("juggernaut.drive.run_m_s", 19.5)
	var bar := Rect2(base + Vector2(0.0, -30.0), Vector2(250.0, 5.0))
	_draw.draw_rect(Rect2(bar.position - Vector2(1.0, 1.0), bar.size + Vector2(2.0, 2.0)), SHADE)
	_draw.draw_rect(bar, Color(accent, 0.25))
	_draw.draw_rect(Rect2(bar.position, Vector2(bar.size.x * clampf(speed_m_s / maxf(top, 1.0), 0.0, 1.0), bar.size.y)), accent)
	for q in range(1, 4):
		_draw.draw_line(bar.position + Vector2(bar.size.x * q / 4.0, -3.0), bar.position + Vector2(bar.size.x * q / 4.0, 8.0), Color(text, 0.5), 1.0)
	_label(mono, base + Vector2(0.0, -6.0), "hdg %03d   pitch %+.0f   roll %+.0f" % [roundi(float(_t["heading_deg"])), float(_t["pitch_deg"]), float(_t["roll_deg"])], 16, text)
	_label(mono, base + Vector2(0.0, 14.0), "%.1f t   %s" % [float(_t["mass_kg"]) / 1000.0, "test bench" if _t["physics_mode"] == "bench" else "game mode"], 14, dim)
	# The four legs seen from above, nose up: lit while carrying weight.
	var pips := base + Vector2(336.0, -40.0)
	for name: String in ["fl", "fr", "rl", "rr"]:
		var at := pips + Vector2(-1.0 if name.ends_with("l") else 1.0, -1.0 if name.begins_with("f") else 1.0) * 10.0
		var r := Rect2(at - Vector2(6.0, 6.0), Vector2(12.0, 12.0))
		_draw.draw_rect(Rect2(r.position - Vector2(1.5, 1.5), r.size + Vector2(3.0, 3.0)), SHADE)
		if bool(_legs_down.get(name, false)):
			_draw.draw_rect(r, accent)
		else:
			_draw.draw_rect(r, Color(accent, 0.7), false, 1.5)
	_label(mono, pips + Vector2(-24.0, 38.0), "legs %d/4" % int(_t["grounded_legs"]), 14, text)
	# The attitude ball: the horizon line tilts against the roll and shifts with the pitch.
	var ball := base + Vector2(420.0, -40.0)
	var radius := 31.0
	_draw.draw_circle(ball, radius, Color(0.0, 0.0, 0.0, 0.35))
	var roll := deg_to_rad(float(_t["roll_deg"]))
	var shift := clampf(float(_t["pitch_deg"]) / 30.0, -1.0, 1.0) * radius * 0.7
	var along := Vector2(cos(-roll), sin(-roll))
	var across := Vector2(-along.y, along.x)
	var mid := ball + across * shift
	var half := sqrt(maxf(radius * radius - shift * shift, 0.0)) * 0.95
	_draw.draw_line(mid - along * half, mid + along * half, accent, 2.0, true)
	_draw.draw_arc(ball, radius, 0.0, TAU, 40, Color(text, 0.55), 1.5, true)
	_draw.draw_line(ball - Vector2(9.0, 0.0), ball - Vector2(3.0, 0.0), text, 1.5, true)
	_draw.draw_line(ball + Vector2(3.0, 0.0), ball + Vector2(9.0, 0.0), text, 1.5, true)
	# The jump charge winds up around the ball.
	if _charge > 0.01:
		var sweep := TAU * clampf(_charge, 0.0, 1.0)
		var ring := accent.lerp(warn, clampf(_charge, 0.0, 1.0))
		_draw.draw_arc(ball, radius + 7.0, -PI * 0.5, -PI * 0.5 + sweep, 48, SHADE, 6.0, true)
		_draw.draw_arc(ball, radius + 7.0, -PI * 0.5, -PI * 0.5 + sweep, 48, ring, 3.0, true)
