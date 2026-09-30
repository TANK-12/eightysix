class_name CombatHud
extends Control
## Lane A3's combat HUD, drawn over any level's HUD for the mech it watches (its "Combat" child):
## the main gun's magazine as pips, the rounds in reserve, the loaded and selected ammunition and a
## reload bar; a top-down damage diagram of every part the DamageModel tracks, coloured by health,
## with lost parts drawn as empty outlines; range marks under the reticle where the loaded round
## drops at 500, 1000 and 1500 m; and the wire anchor: a bracket on the grapple surface in reach, or
## the cable tension while attached. Colours and fonts come from the theme (UiTheme).

const RANGE_MARKS := [500.0, 1000.0, 1500.0]
const DIAGRAM := Vector2(190.0, 230.0)
const TARGET_EVERY_S := 0.1

var mech: RigidBody3D
var combat: MechCombat
var _target: Dictionary = {}
var _target_s := 0.0
var _drops: Dictionary = {}  # ammo id -> [drop at each RANGE_MARKS distance]


func watch(node: Node3D) -> void:
	mech = node as RigidBody3D
	combat = mech.get_node_or_null("Combat") as MechCombat if mech != null else null


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(delta: float) -> void:
	if combat == null or not is_instance_valid(mech):
		return
	_target_s -= delta
	if _target_s <= 0.0 and combat.anchor != null:
		_target_s = TARGET_EVERY_S
		_target = combat.anchor.preview() if combat.anchor.state == WireAnchor.State.IDLE else {}
	queue_redraw()


## Health 1 -> good, 0.5 -> warn, 0 -> bad.
static func health_color(f: float) -> Color:
	var good := UiTheme.color("good")
	var warn := UiTheme.color("warn")
	var bad := UiTheme.color("bad")
	return warn.lerp(good, (f - 0.5) * 2.0) if f >= 0.5 else bad.lerp(warn, f * 2.0)


func _draw() -> void:
	if combat == null or not is_instance_valid(mech):
		return
	var cam := get_viewport().get_camera_3d()
	if combat.gun != null:
		_draw_ammo()
		if cam != null:
			_draw_range_marks(cam)
	_draw_damage()
	if combat.anchor != null and cam != null:
		_draw_anchor(cam)


func _panel(rect: Rect2) -> void:
	draw_rect(rect, UiTheme.color("panel"))
	draw_rect(rect, UiTheme.color("line"), false, 1.0)


func _draw_ammo() -> void:
	var g := combat.gun
	var font := UiTheme.font("mono")
	var head := UiTheme.font("heading")
	var text := UiTheme.color("text")
	var dim := UiTheme.color("text_dim")
	var accent := UiTheme.color("accent")
	var rect := Rect2(size.x - 360.0, size.y - 170.0, 320.0, 130.0)
	_panel(rect)
	var x := rect.position.x + 18.0
	var y := rect.position.y + 50.0
	var mag_col := UiTheme.color("warn") if g.magazine <= 2 else text
	draw_string(head, Vector2(x, y), "%02d" % g.magazine, HORIZONTAL_ALIGNMENT_LEFT, -1, 44, mag_col)
	var reserve := "inf" if g.unlimited else str(g.reserve)
	draw_string(font, Vector2(x + 64.0, y), "/ " + reserve, HORIZONTAL_ALIGNMENT_LEFT, -1, 20, dim)
	var loaded := str((g.def.get("ammo", {}) as Dictionary).get(g.loaded_ammo, {}).get("label", g.loaded_ammo))
	draw_string(head, Vector2(rect.end.x - 18.0 - 110.0, y), loaded, HORIZONTAL_ALIGNMENT_RIGHT, 110, 26, accent)
	if g.selected_ammo != g.loaded_ammo:
		var next := str((g.def.get("ammo", {}) as Dictionary).get(g.selected_ammo, {}).get("label", g.selected_ammo))
		draw_string(font, Vector2(rect.end.x - 18.0 - 140.0, y + 20.0), "next " + next, HORIZONTAL_ALIGNMENT_RIGHT, 140, 14, dim)
	# One pip per round the magazine holds.
	var pip_w := minf(16.0, (rect.size.x - 36.0) / maxf(g.magazine_size, 1) - 4.0)
	for i in g.magazine_size:
		var r := Rect2(x + i * (pip_w + 4.0), y + 30.0, pip_w, 12.0)
		if i < g.magazine:
			draw_rect(r, accent)
		else:
			draw_rect(r, UiTheme.color("line"), false, 1.0)
	var bar := Rect2(x, rect.end.y - 22.0, rect.size.x - 36.0, 5.0)
	draw_rect(bar, UiTheme.color("accent_soft"))
	if g.reloading():
		draw_rect(Rect2(bar.position, Vector2(bar.size.x * g.reload_fraction(), bar.size.y)), UiTheme.color("warn"))
		draw_string(font, Vector2(x, bar.position.y - 6.0), "reloading", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, UiTheme.color("warn"))


## Where the loaded round falls below the bore line at each range mark, marked on the screen under
## the reticle (the gun is fixed, so the player ranges by pitching the whole chassis).
func _draw_range_marks(cam: Camera3D) -> void:
	var g := combat.gun
	var ammo: Dictionary = (g.def.get("ammo", {}) as Dictionary).get(g.loaded_ammo, {})
	if not _drops.has(g.loaded_ammo):
		var list: Array = []
		for d: float in RANGE_MARKS:
			list.append(Ballistics.drop_at(d, float(ammo.get("muzzle_m_s", 1000.0)), 9.81, float(ammo.get("drag_per_s", 0.0))))
		_drops[g.loaded_ammo] = list
	var muzzle := mech.global_transform * combat.muzzle_local()
	var dir := combat.gun_direction()
	var col := Color(UiTheme.color("accent"), 0.75)
	var font := UiTheme.font("mono")
	var drops: Array = _drops[g.loaded_ammo]
	for i in RANGE_MARKS.size():
		var at := muzzle + dir * float(RANGE_MARKS[i]) + Vector3.DOWN * float(drops[i])
		if cam.is_position_behind(at):
			continue
		var p := cam.unproject_position(at)
		var half := 10.0 - i * 2.0
		draw_line(p - Vector2(half, 0.0), p + Vector2(half, 0.0), col, 1.5, true)
		draw_string(font, p + Vector2(half + 4.0, 5.0), str(int(RANGE_MARKS[i] / 100.0)), HORIZONTAL_ALIGNMENT_LEFT, -1, 12, col)


## Top-down plan of the mech, nose up: each tracked part is a box at its body-frame position,
## sized from its collider; leg segments sit in a row outward from their hip, foot outermost.
func _draw_damage() -> void:
	var dm := combat.damage
	var rect := Rect2(size.x - 40.0 - DIAGRAM.x, 40.0, DIAGRAM.x, DIAGRAM.y + 30.0)
	_panel(rect)
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	for key: String in dm.parts:
		var p: Dictionary = dm.parts[key]
		var at: Vector3 = p["at"]
		lo = lo.min(Vector2(at.x, at.z))
		hi = hi.max(Vector2(at.x, at.z))
	var span := (hi - lo).max(Vector2.ONE)
	var area := Rect2(rect.position + Vector2(24.0, 44.0), DIAGRAM - Vector2(48.0, 40.0))
	var k := minf(area.size.x / span.x, area.size.y / span.y) * 0.8
	var centre := area.get_center()
	var mid := (lo + hi) * 0.5
	var outline := UiTheme.color("bad")
	for key: String in dm.parts:
		var p: Dictionary = dm.parts[key]
		var at: Vector3 = p["at"]
		var s: Vector3 = p["size"]
		var c := centre + (Vector2(at.x, at.z) - mid) * k
		var box := Vector2(maxf(s.x * k, 6.0), maxf(s.z * k, 6.0))
		var leg := str(p["leg"])
		if leg != "":
			var seg := ["upper", "lower", "foot"].find(key.get_slice("_", 2))
			box = Vector2(9.0, 9.0)
			c += Vector2(signf(at.x) * (14.0 + seg * 11.0), 0.0)
		var r := Rect2(c - box * 0.5, box)
		if dm.is_lost(key):
			draw_rect(r, outline, false, 1.5)
		else:
			draw_rect(r, Color(health_color(dm.fraction(key)), 0.8))
	var font := UiTheme.font("heading")
	var total := dm.total_fraction()
	draw_string(font, rect.position + Vector2(14.0, 26.0), "hull %d%%" % roundi(total * 100.0), HORIZONTAL_ALIGNMENT_LEFT, -1, 20, health_color(total))
	if combat.limp_factor() < 1.0:
		draw_string(UiTheme.font("mono"), rect.position + Vector2(14.0, rect.size.y - 12.0), "leg damaged: limping", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, UiTheme.color("warn"))


## Attached: cable length and tension against the wire's breaking strength (warn colour near it),
## and a bracket on the anchor. Idle: where a shot would go, a bracket on a grapple surface it would
## bite, a cross on something it cannot bite, a dim ring where it gives up out of range.
func _draw_anchor(cam: Camera3D) -> void:
	var a := combat.anchor
	var accent := UiTheme.color("accent")
	var mono := UiTheme.font("mono")
	if a.state == WireAnchor.State.ATTACHED:
		var cap := float(a.def.get("cable_break_n", 170000.0))
		var f := clampf(a.tension / maxf(cap, 1.0), 0.0, 1.0)
		var bar := Rect2(size.x * 0.5 - 120.0, size.y - 60.0, 240.0, 6.0)
		draw_rect(bar, UiTheme.color("accent_soft"))
		draw_rect(Rect2(bar.position, Vector2(bar.size.x * f, bar.size.y)), accent.lerp(UiTheme.color("warn"), f))
		var slack := " slack" if a.tension <= 0.0 else ""
		draw_string(mono, bar.position + Vector2(0.0, -8.0), "cable %.0f m  %d / %d kN%s" % [a.rope_len, roundi(a.tension / 1000.0), roundi(cap / 1000.0), slack], HORIZONTAL_ALIGNMENT_LEFT, -1, 14, accent)
		if not cam.is_position_behind(a.anchor_point):
			_bracket(cam.unproject_position(a.anchor_point), 14.0, UiTheme.color("warn"))
		return
	if _target.is_empty():
		return
	var point: Vector3 = _target["point"]
	if cam.is_position_behind(point):
		return
	var p := cam.unproject_position(point)
	match str(_target["state"]):
		"ok":
			_bracket(p, 18.0, accent)
		"surface":
			var bad := UiTheme.color("bad")
			draw_line(p + Vector2(-8, -8), p + Vector2(8, 8), bad, 2.0, true)
			draw_line(p + Vector2(-8, 8), p + Vector2(8, -8), bad, 2.0, true)
		_:
			draw_arc(p, 10.0, 0.0, TAU, 20, UiTheme.color("accent_soft"), 1.5, true)
	if bool(_target.get("clamped", false)):
		draw_string(mono, p + Vector2(22.0, 5.0), "arm limit", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, UiTheme.color("warn"))


func _bracket(p: Vector2, r: float, col: Color) -> void:
	for sx: float in [-1.0, 1.0]:
		for sy: float in [-1.0, 1.0]:
			var corner := p + Vector2(sx, sy) * r
			draw_line(corner, corner - Vector2(sx * r * 0.5, 0.0), col, 2.0, true)
			draw_line(corner, corner - Vector2(0.0, sy * r * 0.5), col, 2.0, true)
