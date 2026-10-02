extends CanvasLayer
## Test bench readouts (lane B6): the battery and bus, and one cell per joint with the torque it gives
## against what it can give, its power and its winding temperature, coloured when it nears a limit and
## marked when it has tripped or broken. Drawn from the BenchDriver's rig; toggled by bench.hud / F7.

const SHADE := Color(0.0, 0.0, 0.0, 0.6)
const KINDS := ["hip_yaw", "hip_pitch", "knee", "ankle"]
const SHORT := {"hip_yaw": "yaw", "hip_pitch": "hip", "knee": "knee", "ankle": "ankle"}
const LEGS := ["fl", "fr", "rl", "rr"]
const ALARM := Color(0.95, 0.27, 0.22)
const CELL := Vector2(136.0, 48.0)

var driver: Node
var _draw: Control


func watch(d: Node) -> void:
	driver = d


func _ready() -> void:
	layer = 11
	visible = Settings.get_b("bench.hud")
	_draw = Control.new()
	_draw.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_draw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_draw.draw.connect(_on_draw)
	add_child(_draw)


func _process(_delta: float) -> void:
	if visible:
		_draw.queue_redraw()


func _label(at: Vector2, text: String, size: int, col: Color) -> void:
	var font := UiTheme.font("mono")
	_draw.draw_string_outline(font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, 4, SHADE)
	_draw.draw_string(font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, col)


func _bar(rect: Rect2, frac: float, col: Color, tick: float = -1.0) -> void:
	_draw.draw_rect(rect, Color(0.0, 0.0, 0.0, 0.5))
	_draw.draw_rect(Rect2(rect.position, Vector2(rect.size.x * clampf(frac, 0.0, 1.0), rect.size.y)), col)
	if tick >= 0.0:
		var x := rect.position.x + rect.size.x * clampf(tick, 0.0, 1.0)
		_draw.draw_line(Vector2(x, rect.position.y - 1.0), Vector2(x, rect.end.y + 1.0), Color(1.0, 1.0, 1.0, 0.7), 1.0)
	_draw.draw_rect(rect, Color(1.0, 1.0, 1.0, 0.25), false, 1.0)


func _level_colour(frac: float) -> Color:
	var read: Dictionary = driver.rig.cfg.get("readout", {})
	if frac >= float(read.get("alarm_frac", 0.95)):
		return ALARM
	if frac >= float(read.get("warn_frac", 0.75)):
		return UiTheme.color("warn")
	return UiTheme.color("accent")


func _temp_colour(j: Dictionary) -> Color:
	var temp := float(j["temp_c"])
	if temp >= float(j["max_c"]) - 10.0:
		return ALARM
	return UiTheme.color("warn") if temp >= float(j["derate_c"]) else UiTheme.color("accent")


func _on_draw() -> void:
	if driver == null or not is_instance_valid(driver) or not bool(driver.call("is_active")):
		return
	var rig: BenchRig = driver.rig
	var text := UiTheme.color("text")
	var dim := UiTheme.color("text_dim")
	var warn := UiTheme.color("warn")
	var cols := KINDS.size()
	var width := CELL.x * cols + 8.0
	var origin := Vector2(46.0, 112.0)
	var panel := Rect2(origin - Vector2(10.0, 24.0), Vector2(width + 20.0, 96.0 + CELL.y * LEGS.size() + 104.0))
	_draw.draw_rect(panel, Color(0.0, 0.0, 0.0, 0.35))
	_draw.draw_rect(panel, Color(UiTheme.color("accent"), 0.4), false, 1.0)
	_label(origin + Vector2(0.0, -4.0), "Test bench", 18, UiTheme.color("accent"))
	# the bus
	var charge := rig.charge_frac()
	var s: Dictionary = rig.supply
	_label(origin + Vector2(0.0, 22.0), "Battery %3.0f%%" % (charge * 100.0), 14, text)
	_bar(Rect2(origin + Vector2(124.0, 10.0), Vector2(width - 124.0, 12.0)), charge, UiTheme.color("accent") if charge > 0.2 else warn)
	var bus := "%.1f V   %.0f A   %.0f kW" % [float(s["voltage_v"]), float(s["current_a"]), rig.total_power_w() / 1000.0]
	_label(origin + Vector2(0.0, 44.0), bus, 14, text)
	if bool(s["brownout"]):
		_label(origin + Vector2(width - 90.0, 44.0), "brownout", 14, warn)
	elif charge <= 0.0:
		_label(origin + Vector2(width - 90.0, 44.0), "empty", 14, warn)
	var grid := origin + Vector2(0.0, 62.0)
	for c in cols:
		_label(grid + Vector2(CELL.x * c + 4.0, 0.0), SHORT[KINDS[c]], 13, dim)
	for r in LEGS.size():
		var name: String = LEGS[r]
		_label(grid + Vector2(-8.0, 28.0 + CELL.y * r), name, 13, dim)
		for c in cols:
			var id: String = driver.leg_joints.get(name, {}).get(KINDS[c], "")
			if id == "" or not rig.joints.has(id):
				continue
			_cell(grid + Vector2(CELL.x * c + 14.0, 8.0 + CELL.y * r), rig.joints[id])
	var foot := grid + Vector2(0.0, 24.0 + CELL.y * LEGS.size() + 8.0)
	var down := rig.down()
	if down.is_empty():
		_label(foot, "all joints on line", 13, dim)
	else:
		_label(foot, "%d joint(s) out: F6 resets the bench" % down.size(), 13, warn)
	var shown := 0
	for i in range(rig.events.size() - 1, -1, -1):
		if shown >= 3:
			break
		var e: Dictionary = rig.events[i]
		_label(foot + Vector2(0.0, 20.0 + 16.0 * shown), "%5.1f s  %s %s" % [float(e["t"]), str(e["joint"]).replace("jg2_act_", ""), str(e["what"])], 12, warn if shown == 0 else dim)
		shown += 1


## One joint: torque it gives over what it could give (tick = what the load asked), power, temperature.
func _cell(at: Vector2, j: Dictionary) -> void:
	var status := str(j["status"])
	var peak := maxf(float(j["stall_nm"]), 1.0)
	var given := float(j["torque_nm"]) / peak
	var asked := float(j["demand_nm"]) / peak
	var strain := asked / maxf(float(j["limit_nm"]) / peak, 0.01) if asked > 0.05 else 0.0
	var out := status == BenchRig.FAILED or status == BenchRig.TRIPPED or status == BenchRig.NO_POWER
	var col := Color(0.55, 0.55, 0.55) if out else _level_colour(strain)
	_bar(Rect2(at, Vector2(CELL.x - 20.0, 7.0)), given, col, asked)
	var temp_frac := (float(j["temp_c"]) - 20.0) / maxf(float(j["max_c"]) - 20.0, 1.0)
	var derate_tick := (float(j["derate_c"]) - 20.0) / maxf(float(j["max_c"]) - 20.0, 1.0)
	_bar(Rect2(at + Vector2(0.0, 10.0), Vector2(CELL.x - 20.0, 4.0)), temp_frac, _temp_colour(j), derate_tick)
	var line := "%.0f kNm %.0f kW %.0fC" % [float(j["torque_nm"]) / 1000.0, float(j["elec_w"]) / 1000.0, float(j["temp_c"])]
	_label(at + Vector2(0.0, 28.0), line, 12, UiTheme.color("text"))
	if status != BenchRig.OK and status != BenchRig.WARM:
		_label(at + Vector2(0.0, 41.0), status, 12, UiTheme.color("warn"))
	elif status == BenchRig.WARM:
		_label(at + Vector2(0.0, 41.0), "derated", 12, UiTheme.color("warn"))
