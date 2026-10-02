class_name MoveHints
extends Control
## Move hints (lane A4 part 5, the plan's "every new move appears in the controls tips, and the first time a
## move is possible a small hint shows"): data/hints.json lists them, each with a "when" over the numbers and
## flags of the state built here from the mech. One shows at a time, once ever (user://move_hints_seen.json;
## a bot run keeps its list in memory so it never marks Emerson's real hints as seen), a few seconds apart.
## Settings > Gameplay > HUD > Move hints turns them off.

const SEEN_PATH := "user://move_hints_seen.json"
const GAP_S := 5.0
const FADE_S := 0.4

var mech: Node3D
var persist := true
var seen: Array = []
var current := ""
var shown_s := 0.0
var _gap_s := 2.0
var _play_s := 0.0
var _anchor_ready := false
var _anchor_s := 0.0
var _text := ""


func watch(node: Node3D) -> void:
	mech = node


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	persist = not Bot.active
	if persist and FileAccess.file_exists(SEEN_PATH):
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(SEEN_PATH))
		if data is Array:
			seen = data


## True when every item of `when` holds for `state`.
static func matches(when: Array, state: Dictionary) -> bool:
	for item: Dictionary in when:
		var key := str(item["key"])
		if not state.has(key):
			return false
		var value: Variant = state[key]
		if item.has("is") and bool(value) != bool(item["is"]):
			return false
		if item.has("min") and float(value) < float(item["min"]):
			return false
		if item.has("max") and float(value) > float(item["max"]):
			return false
	return true


## The id of the first hint (by "order") that is due for `state` and not in `seen`; "" when none is.
static func pick(entries: Dictionary, state: Dictionary, seen_ids: Array) -> String:
	var ids: Array = entries.keys()
	ids.sort_custom(func(a: Variant, b: Variant) -> bool: return float((entries[a] as Dictionary).get("order", 1000.0)) < float((entries[b] as Dictionary).get("order", 1000.0)))
	for id: String in ids:
		if seen_ids.has(id):
			continue
		if matches((entries[id] as Dictionary).get("when", []), state):
			return id
	return ""


## `text` with each {action} replaced by the player's binding: the key, and the pad button when a pad is in.
static func bind_text(text: String) -> String:
	var out := text
	var regex := RegEx.create_from_string("\\{([a-z_]+)\\}")
	for m in regex.search_all(text):
		var action := m.get_string(1)
		var b: Dictionary = Controls.bindings(action, Controls.scheme)
		var parts: PackedStringArray = []
		if not (b["keys"] as Array).is_empty():
			parts.append(Controls.binding_label(str((b["keys"] as Array)[0])))
		if not (b["pad"] as Array).is_empty() and not Input.get_connected_joypads().is_empty():
			parts.append(Controls.binding_label(str((b["pad"] as Array)[0])))
		if parts.is_empty():
			parts.append(str(Controls.action_info(action).get("label", action)))
		out = out.replace(m.get_string(), " / ".join(parts))
	return out


func state() -> Dictionary:
	var s := {"play_s": _play_s, "anchor_ready": _anchor_ready, "cockpit_view": false}
	s["squad"] = get_tree().get_nodes_in_group("squad_mech").size()  # allied Juggernauts on the map (lane A5)
	var cam := get_viewport().get_camera_3d()
	if cam != null and "view" in cam:
		s["cockpit_view"] = str(cam.get("view")) == "cockpit"
	if mech != null and is_instance_valid(mech) and mech.has_method("telemetry"):
		var t: Dictionary = mech.call("telemetry")
		s["speed_m_s"] = float(t["speed_m_s"])
		s["airborne"] = bool(t["airborne"])
		s["skidding"] = bool(t["skidding"])
		s["charging"] = bool(t["charging"])
		s["running"] = bool(mech.get("running"))
	return s


func _process(delta: float) -> void:
	if mech == null or not is_instance_valid(mech) or Game.is_paused():
		return
	if not Settings.get_b("gameplay.move_hints"):
		current = ""
		queue_redraw()
		return
	_play_s += delta
	var combat := mech.get_node_or_null("Combat") as MechCombat
	_anchor_s -= delta
	if _anchor_s <= 0.0 and combat != null and combat.anchor != null:
		_anchor_s = 0.3
		_anchor_ready = combat.anchor.state == WireAnchor.State.IDLE and str(combat.anchor.preview().get("state", "")) == "ok"
	var entries: Dictionary = Registry.file("hints").get("entries", {})
	if current != "":
		shown_s += delta
		if shown_s >= float((entries.get(current, {}) as Dictionary).get("show_s", 7.0)):
			current = ""
			_gap_s = GAP_S
		queue_redraw()
		return
	_gap_s -= delta
	if _gap_s > 0.0:
		return
	var id := pick(entries, state(), seen)
	if id != "":
		show_hint(id)


func show_hint(id: String) -> void:
	current = id
	shown_s = 0.0
	_text = bind_text(str((Registry.file("hints").get("entries", {}) as Dictionary)[id].get("text", id)))
	seen.append(id)
	if persist:
		var f := FileAccess.open(SEEN_PATH, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(seen))
	queue_redraw()


func _draw() -> void:
	if current == "" or _text == "":
		return
	var entries: Dictionary = Registry.file("hints").get("entries", {})
	var total := float((entries.get(current, {}) as Dictionary).get("show_s", 7.0))
	var alpha := clampf(minf(shown_s / FADE_S, (total - shown_s) / FADE_S), 0.0, 1.0)
	var font := UiTheme.font("body")
	var size_px := 18
	var width := minf(size.x - 120.0, 760.0)
	var lines := font.get_multiline_string_size(_text, HORIZONTAL_ALIGNMENT_LEFT, width - 40.0, size_px)
	width = minf(width, lines.x + 44.0)
	var rect := Rect2((size.x - width) * 0.5, size.y - 150.0 - lines.y, width, lines.y + 26.0)
	draw_rect(rect, Color(UiTheme.color("panel"), 0.85 * alpha))
	draw_rect(rect, Color(UiTheme.color("line"), alpha), false, 1.0)
	draw_rect(Rect2(rect.position, Vector2(3.0, rect.size.y)), Color(UiTheme.color("accent"), alpha))
	draw_multiline_string(font, rect.position + Vector2(20.0, 13.0 + font.get_ascent(size_px)), _text, HORIZONTAL_ALIGNMENT_LEFT, width - 40.0, size_px, -1, Color(UiTheme.color("text"), alpha))
