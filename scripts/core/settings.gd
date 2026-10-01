extends Node
## Player settings. Defaults and the menu layout come from data/settings.json; changed values are
## saved to user://settings.cfg (a short moment after the last change, and on quit).
## Everything that reacts to a setting listens to `changed` and reads get_value().

signal changed(key: String, value: Variant)

const SAVE_PATH := "user://settings.cfg"
const SAVE_DELAY_S := 0.6

var save_path := SAVE_PATH
var _items: Dictionary = {}
var _values: Dictionary = {}
var _sections: Array = []
var _save_in := -1.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	build_schema()
	load_saved()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		if _save_in >= 0.0:
			save_now()


func _process(delta: float) -> void:
	if _save_in < 0.0:
		return
	_save_in -= delta
	if _save_in < 0.0:
		save_now()


## Reads settings.json into a flat key -> item table and expands generated groups.
func build_schema() -> void:
	_items.clear()
	_sections = []
	var raw_sections: Array = Registry.file("settings").get("sections", [])
	for raw_section: Dictionary in raw_sections:
		var section := raw_section.duplicate(true)
		for page: Dictionary in section.get("pages", []):
			for group: Dictionary in page.get("groups", []):
				if str(group.get("generate", "")) == "audio_buses":
					group["items"] = _audio_bus_items()
				elif str(group.get("generate", "")) == "sound_mix":
					group["items"] = _sound_mix_items(str(group.get("bus", "")))
				for item: Dictionary in group.get("items", []):
					item["section"] = section["id"]
					item["page"] = page["id"]
					_items[str(item["key"])] = item
		_sections.append(section)
	for key: String in _items:
		if not _values.has(key) and _items[key].has("default"):
			_values[key] = _items[key]["default"]


func sections() -> Array:
	return _sections


func has_key(key: String) -> bool:
	return _items.has(key)


func item(key: String) -> Dictionary:
	return _items.get(key, {})


func keys() -> Array:
	return _items.keys()


func get_value(key: String) -> Variant:
	if _values.has(key):
		return _values[key]
	push_warning("Settings: unknown key '%s'" % key)
	return null


func get_f(key: String) -> float:
	return float(get_value(key))


func get_b(key: String) -> bool:
	return bool(get_value(key))


func get_s(key: String) -> String:
	return str(get_value(key))


func default_of(key: String) -> Variant:
	return item(key).get("default")


func is_default(key: String) -> bool:
	return _same(get_value(key), default_of(key))


## Sets a value (clamped or checked against its item) and tells listeners. Returns true if it changed.
func set_value(key: String, value: Variant, save: bool = true) -> bool:
	if not _items.has(key):
		push_warning("Settings: unknown key '%s'" % key)
		return false
	var clean: Variant = sanitise(key, value)
	if clean == null:
		push_warning("Settings: %s cannot be %s" % [key, str(value)])
		return false
	if _values.has(key) and _same(_values[key], clean):
		return false
	_values[key] = clean
	if save:
		_save_in = SAVE_DELAY_S
	changed.emit(key, clean)
	return true


func reset(key: String) -> void:
	if item(key).has("default"):
		set_value(key, default_of(key))


func reset_page(section_id: String, page_id: String) -> void:
	for key: String in _items:
		var it: Dictionary = _items[key]
		if it["section"] == section_id and it["page"] == page_id:
			reset(key)


## The value an item would store for `value`, or null when it is not allowed.
func sanitise(key: String, value: Variant) -> Variant:
	var it := item(key)
	match str(it.get("type", "")):
		"toggle":
			return bool(value)
		"slider":
			var lo: float = float(it.get("min", 0.0))
			var hi: float = float(it.get("max", 1.0))
			var step: float = float(it.get("step", 0.0))
			var v := clampf(float(value), lo, hi)
			if step > 0.0:
				v = clampf(lo + roundf((v - lo) / step) * step, lo, hi)
			return snappedf(v, 0.0001)
		"choice":
			for option: Array in options_for(key):
				if _same(option[0], value):
					return option[0]
			return null
		_:
			return value


## [value, label] pairs for a choice item, including ones drawn from a registry.
func options_for(key: String) -> Array:
	var it := item(key)
	var out: Array = []
	match str(it.get("options_from", "")):
		"":
			out = it.get("options", []).duplicate(true)
		"audio_devices":
			for device in AudioServer.get_output_device_list():
				out.append([device, device])
		var registry_name:
			for id in Registry.ids(registry_name):
				var e := Registry.entry(registry_name, id)
				# an entry with "show_if": "<setting key>" is offered only while that setting is on
				if e.has("show_if") and not get_b(str(e["show_if"])):
					continue
				out.append([id, str(e.get("label", id))])
	for extra: Array in it.get("extra_options", []):
		out.append(extra)
	return out


func label_for(key: String, value: Variant) -> String:
	var it := item(key)
	match str(it.get("type", "")):
		"toggle":
			return "On" if bool(value) else "Off"
		"choice":
			for option: Array in options_for(key):
				if _same(option[0], value):
					return str(option[1])
			return str(value)
		"slider":
			return format_number(float(value), str(it.get("format", "float")))
		_:
			return str(value)


static func format_number(v: float, fmt: String) -> String:
	match fmt:
		"percent":
			return "%d%%" % roundi(v * 100.0)
		"x":
			return "%.2fx" % v
		"deg":
			return "%d°" % roundi(v)
		"m":
			return "%d m" % roundi(v)
		"metres":
			return "%.2f m" % v
		"s":
			return "%.2f s" % v
		"int":
			return "%d" % roundi(v)
		"db":
			return "%.1f dB" % v
		_:
			return "%.2f" % v


func save_now() -> void:
	_save_in = -1.0
	var cfg := ConfigFile.new()
	for key: String in _values:
		if is_default(key):
			continue
		var dot := key.find(".")
		cfg.set_value(key.substr(0, dot), key.substr(dot + 1), _values[key])
	var err := cfg.save(save_path)
	if err != OK:
		push_warning("Settings: could not save %s (%s)" % [save_path, error_string(err)])


func load_saved() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(save_path) != OK:
		return
	for section in cfg.get_sections():
		for name in cfg.get_section_keys(section):
			var key := section + "." + name
			if _items.has(key):
				var clean: Variant = sanitise(key, cfg.get_value(section, name))
				if clean != null:
					_values[key] = clean


## Back to every default without saving (tests use this).
func reset_all_quietly() -> void:
	_values.clear()
	for key: String in _items:
		if _items[key].has("default"):
			_values[key] = _items[key]["default"]


## Lane B4 part 2: Emerson's own mix. For every sound on `bus` in sounds.json, a choice of which
## recording plays (when the entry offers "choices") and a level in dB on top of the entry's own;
## the lowest step silences it. Sfx reads both live (audio.pick.<id>, audio.level.<id>).
const SOUND_LEVEL_OFF_DB := -40.0


func _sound_mix_items(bus: String) -> Array:
	var out: Array = []
	for id in Registry.ids("sounds"):
		var e := Registry.entry("sounds", id)
		if str(e.get("bus", "")) != bus:
			continue
		var label := str(e.get("label", id))
		var choices: Array = e.get("choices", [])
		if choices.size() > 1:
			var options: Array = []
			for c: Dictionary in choices:
				options.append([str(c["id"]), str(c.get("label", c["id"]))])
			out.append(
				{
					"key": "audio.pick." + id,
					"label": label,
					"type": "choice",
					"options": options,
					"default": str(e.get("choice", choices[0]["id"])),
					"help": "Which recording plays for %s. It plays once when you change it." % label.to_lower(),
				}
			)
		out.append(
			{
				"key": "audio.level." + id,
				"label": "    Level" if choices.size() > 1 else label,
				"type": "slider",
				"min": SOUND_LEVEL_OFF_DB,
				"max": 12.0,
				"step": 1.0,
				"format": "db",
				"default": 0.0,
				"help": "%s: louder or quieter than the game's mix (0 dB). All the way down turns it off." % label,
			}
		)
	return out


func _audio_bus_items() -> Array:
	var out: Array = []
	for bus: Dictionary in Registry.file("sounds").get("buses", []):
		out.append(
			{
				"key": "audio." + str(bus["id"]),
				"label": str(bus.get("label", bus["id"])),
				"type": "slider",
				"min": 0.0,
				"max": 1.0,
				"step": 0.01,
				"format": "percent",
				"default": float(bus.get("default", 1.0 if bus["id"] == "master" else 0.85)),
				"help": "Volume of %s." % str(bus.get("label", bus["id"])).to_lower(),
			}
		)
	return out


static func _same(a: Variant, b: Variant) -> bool:
	if (a is float or a is int) and (b is float or b is int):
		return is_equal_approx(float(a), float(b))
	return typeof(a) == typeof(b) and a == b
