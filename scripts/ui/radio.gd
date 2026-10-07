class_name HandlerRadio
extends CanvasLayer
## Handler radio (lane A7): the Handler talks you through the mission over the Para-RAID: who is
## coming and from where, your kills (and the long ones), the Legion parts you shoot off and what
## that does, the Löwe ranging you, heavy hits, low armour, the win or the loss. Lines come from
## data/radio.json, one at a time at the top left, typed out like a teleprinter, with the subtitle
## settings (Settings > Accessibility > Subtitles) for size, box and speaker name.

const TYPE_CHARS_S := 70.0
const HOLD_S := 2.2
const HOLD_PER_CHAR_S := 0.045
const FADE_S := 0.4
const QUEUE_MAX := 4
const LONG_KILL_M := 600.0
const LOW_ARMOUR := 0.34
const SIZES := {"small": 18, "medium": 22, "large": 28, "huge": 36}

var mission: Node
var shown_line := ""  # the line on screen now ("" when none)
var said: Array = []  # every line said this mission, in order (tests and the bot report read it)
var _queue: Array = []  # [priority, text]
var _cool: Dictionary = {}  # event -> seconds of quiet left
var _done_once: Dictionary = {}
var _left := 0.0
var _panel: PanelContainer
var _speaker: Label
var _text: Label
var _rng := RandomNumberGenerator.new()


static func enabled() -> bool:
	return Settings.get_b("gameplay.handler_radio") and Settings.get_b("accessibility.subtitles")


func _ready() -> void:
	layer = 13
	add_to_group("handler_radio")
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	UiTheme.adopt(root)
	add_child(root)
	_panel = PanelContainer.new()
	_panel.position = Vector2(40, 200)
	_panel.custom_minimum_size.x = 560
	_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_panel.modulate.a = 0.0
	root.add_child(_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	_panel.add_child(box)
	_speaker = Label.new()
	_speaker.theme_type_variation = "AccentLabel"
	box.add_child(_speaker)
	_text = Label.new()
	_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_text.custom_minimum_size.x = 540
	box.add_child(_text)
	_style()
	Settings.changed.connect(func(key: String, _v: Variant) -> void: if key.begins_with("accessibility.subtitle") or key == "accessibility.speaker_names": _style())


func watch(m: Node) -> void:
	mission = m
	_rng.seed = hash(str(m.get("id")))
	m.connect("wave_started", _on_wave)
	m.connect("objective_changed", _on_objective)
	m.connect("ended", _on_ended)
	var sortie: Object = m.get("sortie")
	if sortie != null:
		sortie.connect("kill_scored", _on_kill)
		sortie.connect("part_shot_off", _on_part)
	var player := m.get("player") as Node
	var combat: Object = player.get_meta("combat") if player != null and player.has_meta("combat") else null
	if combat != null:
		combat.connect("hit_taken", _on_player_hit)
	if int(m.get("wave")) >= 0:
		_on_wave(int(m.get("wave")), (m.get("units") as Array).size())  # the first wave starts in Mission._ready


## Says the line for `event` (with its placeholders filled) unless the radio is off, the event is cooling
## down or was a once-only one already said. Returns the text queued, or "".
func say(event: String, vars: Dictionary = {}) -> String:
	var e: Dictionary = (Registry.file("radio").get("events", {}) as Dictionary).get(event, {})
	var lines: Array = e.get("lines", [])
	if lines.is_empty() or not enabled() or float(_cool.get(event, 0.0)) > 0.0 or _done_once.has(event):
		return ""
	if bool(e.get("once", false)):
		_done_once[event] = true
	_cool[event] = float(e.get("cooldown_s", 0.0))
	var text := str(lines[_rng.randi() % lines.size()])
	var all := vars.duplicate()
	all["callsign"] = str(Registry.file("radio").get("callsign", "Undertaker"))
	for k: String in all:
		text = text.replace("{%s}" % k, str(all[k]))
	var pri := int(e.get("priority", 0))
	_queue.append([pri, text])
	_queue.sort_custom(func(a: Array, b: Array) -> bool: return a[0] > b[0])
	while _queue.size() > QUEUE_MAX:
		_queue.pop_back()
	if pri >= 3 and shown_line != "":
		_left = minf(_left, FADE_S)  # the end of the mission cuts in
	return text


func _process(delta: float) -> void:
	for k: String in _cool.keys():
		_cool[k] = maxf(float(_cool[k]) - delta, 0.0)
	if shown_line != "":
		_left -= delta
		_text.visible_ratio = minf(_text.visible_ratio + delta * TYPE_CHARS_S / maxf(float(shown_line.length()), 1.0), 1.0)
		_panel.modulate.a = clampf(_left / FADE_S, 0.0, 1.0)
		if _left > 0.0:
			return
		shown_line = ""
	if not _queue.is_empty():
		_show(str(_queue.pop_front()[1]))


func _show(text: String) -> void:
	shown_line = text
	said.append(text)
	_text.text = text
	_text.visible_ratio = 0.0
	_speaker.text = str(Registry.file("radio").get("speaker", "Handler One"))
	_speaker.visible = Settings.get_b("accessibility.speaker_names")
	_left = HOLD_S + HOLD_PER_CHAR_S * text.length() + text.length() / TYPE_CHARS_S
	_panel.modulate.a = 1.0
	Sfx.play("ui_hover", null, -8.0, 0.7)


func _style() -> void:
	var size := int(SIZES.get(Settings.get_s("accessibility.subtitle_size"), 22))
	_text.add_theme_font_size_override("font_size", size)
	_speaker.add_theme_font_size_override("font_size", maxi(size - 6, 14))
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0, 0, 0, Settings.get_f("accessibility.subtitle_background"))
	sb.border_color = UiTheme.color("accent")
	sb.border_width_left = 3
	sb.set_content_margin_all(12)
	sb.content_margin_left = 16
	_panel.add_theme_stylebox_override("panel", sb)


## "two Ameise", "three Grauwolf and a Löwe": what a wave holds, by kind.
static func describe(units: Array) -> String:
	var counts := {}
	var order: Array = []
	for u: Variant in units:
		if not is_instance_valid(u):
			continue
		var label := str(Registry.entry("enemies", str((u as Object).get("enemy_id"))).get("label", "Legion"))
		if not counts.has(label):
			order.append(label)
		counts[label] = int(counts.get(label, 0)) + 1
	var words := ["no", "a", "two", "three", "four", "five", "six", "seven", "eight"]
	var parts := PackedStringArray()
	for label: String in order:
		var n := int(counts[label])
		parts.append("%s %s" % [words[n] if n < words.size() else str(n), label])
	if parts.size() <= 1:
		return "".join(parts)
	return ", ".join(parts.slice(0, parts.size() - 1)) + " and " + parts[parts.size() - 1]


func _on_wave(index: int, count: int) -> void:
	var units: Array = mission.get("units")
	for u: Variant in units:
		if is_instance_valid(u) and (u as Object).has_signal("fired"):
			(u as Object).connect("fired", _on_legion_fired)
	var g: Dictionary = mission.call("guide")
	var vars := {"count": count, "enemies": describe(units), "bearing": "%03d" % (roundi(float(g.get("bearing_deg", 0.0))) % 360), "distance": roundi(float(g.get("distance_m", 0.0)))}
	var last := index + 1 >= int(mission.call("waves_total"))
	say("wave_first" if index == 0 else ("wave_last" if last else "wave"), vars)


func _on_objective(text: String) -> void:
	if text.begins_with("Wave cleared"):
		say("wave_cleared")


func _on_ended(won: bool) -> void:
	say("won" if won else "lost")


func _on_kill(unit: Node, distance_m: float) -> void:
	var vars := {"enemy": str(Registry.entry("enemies", str(unit.get("enemy_id"))).get("label", "Legion")), "distance": roundi(distance_m)}
	if mission != null and mission.get("state") != "running":
		return  # the last kill: "won" says it
	say("kill_long" if distance_m >= LONG_KILL_M else "kill", vars)


func _on_part(unit: Node, key: String) -> void:
	var dmg: Object = unit.get("damage")
	var kind := str((dmg.get("parts") as Dictionary).get(key, {}).get("kind", "")) if dmg != null else ""
	var events: Dictionary = Registry.file("radio").get("events", {})
	say("part." + key if events.has("part." + key) else "part." + kind)


func _on_legion_fired(weapon: String, _ammo: String) -> void:
	if weapon == "lowe_120mm":
		say("lowe_fired")


func _on_player_hit(_key: String, dealt: float, _info: Dictionary) -> void:
	var sortie: Object = mission.get("sortie") if mission != null else null
	if sortie != null and float(sortie.call("armour_left")) < LOW_ARMOUR:
		say("armour_low")
	elif dealt >= 600.0:
		say("hit_heavy")
