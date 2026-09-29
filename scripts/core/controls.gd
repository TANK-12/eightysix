extends Node
## Input: builds Godot's InputMap from data/input.json, saves rebinds per scheme, and shapes
## analog input (radial stick dead zones, response curves, trigger curves, keyboard throttle ramp,
## smoothed mouse). Game code reads stick("move"), trigger("brake"), held("fire_main") and
## take_mouse_delta() rather than raw Input, so every setting applies everywhere.

signal bindings_changed(scheme: String)
signal device_changed(kind: String)

const SAVE_PATH := "user://bindings.cfg"
const PRESS_DEADZONE := 0.3
const JOY_BUTTONS := {
	"cross": JOY_BUTTON_A,
	"circle": JOY_BUTTON_B,
	"square": JOY_BUTTON_X,
	"triangle": JOY_BUTTON_Y,
	"create": JOY_BUTTON_BACK,
	"ps": JOY_BUTTON_GUIDE,
	"options": JOY_BUTTON_START,
	"l3": JOY_BUTTON_LEFT_STICK,
	"r3": JOY_BUTTON_RIGHT_STICK,
	"l1": JOY_BUTTON_LEFT_SHOULDER,
	"r1": JOY_BUTTON_RIGHT_SHOULDER,
	"dpad_up": JOY_BUTTON_DPAD_UP,
	"dpad_down": JOY_BUTTON_DPAD_DOWN,
	"dpad_left": JOY_BUTTON_DPAD_LEFT,
	"dpad_right": JOY_BUTTON_DPAD_RIGHT,
	"mic": JOY_BUTTON_MISC1,
	"touchpad": JOY_BUTTON_TOUCHPAD,
}
const JOY_AXES := {
	"left_x": JOY_AXIS_LEFT_X,
	"left_y": JOY_AXIS_LEFT_Y,
	"right_x": JOY_AXIS_RIGHT_X,
	"right_y": JOY_AXIS_RIGHT_Y,
	"l2": JOY_AXIS_TRIGGER_LEFT,
	"r2": JOY_AXIS_TRIGGER_RIGHT,
}
const MOUSE_BUTTONS := {
	"left": MOUSE_BUTTON_LEFT,
	"right": MOUSE_BUTTON_RIGHT,
	"middle": MOUSE_BUTTON_MIDDLE,
	"wheel_up": MOUSE_BUTTON_WHEEL_UP,
	"wheel_down": MOUSE_BUTTON_WHEEL_DOWN,
	"back": MOUSE_BUTTON_XBUTTON1,
	"forward": MOUSE_BUTTON_XBUTTON2,
}
const PAD_LABELS := {
	"cross": "Cross",
	"circle": "Circle",
	"square": "Square",
	"triangle": "Triangle",
	"create": "Create",
	"ps": "PS button",
	"options": "Options",
	"l3": "L3",
	"r3": "R3",
	"l1": "L1",
	"r1": "R1",
	"l2": "L2",
	"r2": "R2",
	"dpad_up": "D-pad up",
	"dpad_down": "D-pad down",
	"dpad_left": "D-pad left",
	"dpad_right": "D-pad right",
	"mic": "Mute button",
	"touchpad": "Touchpad",
	"left_x-": "Left stick left",
	"left_x+": "Left stick right",
	"left_y-": "Left stick up",
	"left_y+": "Left stick down",
	"right_x-": "Right stick left",
	"right_x+": "Right stick right",
	"right_y-": "Right stick up",
	"right_y+": "Right stick down",
}
const MOUSE_LABELS := {
	"left": "Left mouse",
	"right": "Right mouse",
	"middle": "Middle mouse",
	"wheel_up": "Wheel up",
	"wheel_down": "Wheel down",
	"back": "Mouse back",
	"forward": "Mouse forward",
}

var scheme := "standard"
var last_device := "kbm"
var save_path := SAVE_PATH
var _overrides: Dictionary = {}
var _mouse_raw := Vector2.ZERO
var _mouse_smooth := Vector2.ZERO
var _ramped: Dictionary = {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	load_overrides()
	scheme = "hardcore" if Settings.get_b("controls.hardcore_mode") else "standard"
	apply_scheme(scheme)
	Settings.changed.connect(_on_setting_changed)


func _on_setting_changed(key: String, value: Variant) -> void:
	if key == "controls.hardcore_mode":
		apply_scheme("hardcore" if bool(value) else "standard")


# --- bindings ---------------------------------------------------------------------------------


func actions() -> PackedStringArray:
	return PackedStringArray(Registry.file("input").get("entries", {}).keys())


func action_info(action: String) -> Dictionary:
	return Registry.file("input").get("entries", {}).get(action, {})


## Actions that have any binding in `scheme_name`, in the registry's group order.
func actions_for_scheme(scheme_name: String) -> PackedStringArray:
	var groups: Array = Registry.file("input").get("groups", [])
	var out: Array = []
	for action in actions():
		var info := action_info(action)
		if info.has(scheme_name) or info.has("all"):
			out.append(action)
	out.sort_custom(
		func(a: String, b: String) -> bool:
			var ga := groups.find(action_info(a).get("group", ""))
			var gb := groups.find(action_info(b).get("group", ""))
			return ga < gb if ga != gb else actions().find(a) < actions().find(b)
	)
	return PackedStringArray(out)


func default_bindings(action: String, scheme_name: String) -> Dictionary:
	var info := action_info(action)
	var block: Dictionary = info.get(scheme_name, info.get("all", {}))
	return {
		"keys": Array(block.get("keys", [])).duplicate(),
		"pad": Array(block.get("pad", [])).duplicate(),
	}


func bindings(action: String, scheme_name: String) -> Dictionary:
	var key := scheme_name + "/" + action
	if _overrides.has(key):
		var o: Dictionary = _overrides[key]
		return {"keys": Array(o.get("keys", [])).duplicate(), "pad": Array(o.get("pad", [])).duplicate()}
	return default_bindings(action, scheme_name)


func apply_scheme(scheme_name: String) -> void:
	scheme = scheme_name
	for action in actions():
		if not InputMap.has_action(action):
			InputMap.add_action(action, PRESS_DEADZONE)
		InputMap.action_erase_events(action)
		InputMap.action_set_deadzone(action, PRESS_DEADZONE)
		var b := bindings(action, scheme_name)
		for binding: String in b["keys"] + b["pad"]:
			var event := parse_binding(binding)
			if event != null:
				InputMap.action_add_event(action, event)
			else:
				push_warning("Controls: cannot read binding '%s' for %s" % [binding, action])
	bindings_changed.emit(scheme_name)


## Puts `binding` in a slot ("keys" or "pad", index 0 or 1). An empty string clears the slot.
func set_binding(action: String, scheme_name: String, slot: String, index: int, binding: String) -> void:
	var b := bindings(action, scheme_name)
	var list: Array = b[slot]
	while list.size() <= index:
		list.append("")
	list[index] = binding
	b[slot] = list.filter(func(s: String) -> bool: return s != "")
	_overrides[scheme_name + "/" + action] = b
	if b == default_bindings(action, scheme_name):
		_overrides.erase(scheme_name + "/" + action)
	save_overrides()
	if scheme_name == scheme:
		apply_scheme(scheme)
	else:
		bindings_changed.emit(scheme_name)


func reset_scheme(scheme_name: String) -> void:
	for key: String in _overrides.keys():
		if key.begins_with(scheme_name + "/"):
			_overrides.erase(key)
	save_overrides()
	apply_scheme(scheme)


## Other actions in the same scheme, live in an overlapping context, that already use `binding`.
func conflicts(action: String, scheme_name: String, binding: String) -> PackedStringArray:
	var out := PackedStringArray()
	var mine: Array = action_info(action).get("context", ["field"])
	for other in actions_for_scheme(scheme_name):
		if other == action:
			continue
		var theirs: Array = action_info(other).get("context", ["field"])
		var shared := "global" in mine or "global" in theirs
		for c: String in mine:
			shared = shared or c in theirs
		if not shared:
			continue
		var b := bindings(other, scheme_name)
		if binding in b["keys"] or binding in b["pad"]:
			out.append(other)
	return out


func load_overrides() -> void:
	_overrides.clear()
	var cfg := ConfigFile.new()
	if cfg.load(save_path) != OK:
		return
	for section in cfg.get_sections():
		for action in cfg.get_section_keys(section):
			var value: Variant = cfg.get_value(section, action)
			if value is Dictionary:
				_overrides[section + "/" + action] = value


func save_overrides() -> void:
	var cfg := ConfigFile.new()
	for key: String in _overrides:
		var parts := key.split("/")
		cfg.set_value(parts[0], parts[1], _overrides[key])
	var err := cfg.save(save_path)
	if err != OK:
		push_warning("Controls: could not save %s (%s)" % [save_path, error_string(err)])


static func parse_binding(binding: String) -> InputEvent:
	var colon := binding.find(":")
	if colon < 0:
		return null
	var kind := binding.substr(0, colon)
	var name := binding.substr(colon + 1)
	match kind:
		"key":
			var code := OS.find_keycode_from_string(name)
			if code == KEY_NONE:
				return null
			var key := InputEventKey.new()
			key.physical_keycode = code
			return key
		"mouse":
			if not MOUSE_BUTTONS.has(name):
				return null
			var mouse := InputEventMouseButton.new()
			mouse.button_index = MOUSE_BUTTONS[name]
			return mouse
		"joy":
			if JOY_BUTTONS.has(name):
				var button := InputEventJoypadButton.new()
				button.button_index = JOY_BUTTONS[name]
				button.device = -1
				return button
			if name == "l2" or name == "r2":
				var trig := InputEventJoypadMotion.new()
				trig.axis = JOY_AXES[name]
				trig.axis_value = 1.0
				trig.device = -1
				return trig
			var axis_name := name.substr(0, name.length() - 1)
			var sign_char := name.right(1)
			if JOY_AXES.has(axis_name) and (sign_char == "-" or sign_char == "+"):
				var motion := InputEventJoypadMotion.new()
				motion.axis = JOY_AXES[axis_name]
				motion.axis_value = -1.0 if sign_char == "-" else 1.0
				motion.device = -1
				return motion
	return null


## The binding string for a captured event, or "" when the event cannot be bound.
static func binding_of(event: InputEvent) -> String:
	if event is InputEventKey:
		var key := event as InputEventKey
		var code := key.physical_keycode if key.physical_keycode != KEY_NONE else key.keycode
		return "key:" + OS.get_keycode_string(code) if code != KEY_NONE else ""
	if event is InputEventMouseButton:
		var idx := (event as InputEventMouseButton).button_index
		for n: String in MOUSE_BUTTONS:
			if MOUSE_BUTTONS[n] == idx:
				return "mouse:" + n
	if event is InputEventJoypadButton:
		var b := (event as InputEventJoypadButton).button_index
		for n: String in JOY_BUTTONS:
			if JOY_BUTTONS[n] == b:
				return "joy:" + n
	if event is InputEventJoypadMotion:
		var m := event as InputEventJoypadMotion
		for n: String in JOY_AXES:
			if JOY_AXES[n] == m.axis:
				if n == "l2" or n == "r2":
					return "joy:" + n
				return "joy:" + n + ("-" if m.axis_value < 0.0 else "+")
	return ""


static func binding_label(binding: String) -> String:
	if binding == "":
		return "—"
	var colon := binding.find(":")
	var kind := binding.substr(0, colon)
	var name := binding.substr(colon + 1)
	match kind:
		"key":
			return name
		"mouse":
			return MOUSE_LABELS.get(name, name)
		"joy":
			return PAD_LABELS.get(name, name)
	return binding


# --- analog shaping ---------------------------------------------------------------------------


## One axis through a dead zone band and a power curve. Keeps the sign; 0..1 out.
static func shape(value: float, inner: float, outer: float, curve: float) -> float:
	var span := maxf(outer - inner, 0.001)
	var t := clampf((absf(value) - inner) / span, 0.0, 1.0)
	return signf(value) * pow(t, curve)


## A two-axis stick with a radial dead zone, so diagonals are not squashed.
static func shape_stick(v: Vector2, inner: float, outer: float, curve: float) -> Vector2:
	var length := v.length()
	if length <= inner or length < 0.0001:
		return Vector2.ZERO
	return v / length * shape(length, inner, outer, curve)


func stick_shaped(name: String) -> Vector2:
	var def: Dictionary = Registry.file("input").get("sticks", {}).get(name, {})
	if def.is_empty():
		return Vector2.ZERO
	var x_pair: Array = def["x"]
	var y_pair: Array = def["y"]
	var raw := Vector2(
		Input.get_action_raw_strength(x_pair[1]) - Input.get_action_raw_strength(x_pair[0]),
		Input.get_action_raw_strength(y_pair[1]) - Input.get_action_raw_strength(y_pair[0])
	)
	var prefix := "controls." + str(def.get("settings", name))
	return shape_stick(
		raw,
		Settings.get_f(prefix + "_inner"),
		Settings.get_f(prefix + "_outer"),
		Settings.get_f(prefix + "_curve")
	)


## The stick as the game should use it this tick: shaped, and ramped when it came from keys.
func stick(name: String) -> Vector2:
	return _ramped.get(name, stick_shaped(name))


func trigger(action: String) -> float:
	var raw := Input.get_action_raw_strength(action)
	return shape(
		raw,
		Settings.get_f("controls.trigger_inner"),
		Settings.get_f("controls.trigger_outer"),
		Settings.get_f("controls.trigger_curve")
	)


func held(action: String) -> bool:
	if Registry.file("input").get("triggers", {}).has(action):
		var threshold := Settings.get_f("controls.fire_threshold") if action == "fire_main" else 0.5
		return trigger(action) >= threshold
	return Input.is_action_pressed(action)


## Mouse movement since the last call, smoothed and scaled by the mouse settings (pixels).
func take_mouse_delta() -> Vector2:
	var smoothing := Settings.get_f("controls.mouse_smoothing")
	_mouse_smooth = _mouse_smooth.lerp(_mouse_raw, 1.0 - smoothing)
	_mouse_raw = Vector2.ZERO
	var out := _mouse_smooth * Settings.get_f("controls.mouse_sensitivity")
	if Settings.get_b("controls.mouse_invert_y"):
		out.y = -out.y
	return out


func _physics_process(delta: float) -> void:
	var ramp_s := Settings.get_f("controls.key_throttle_ramp")
	for name: String in Registry.file("input").get("sticks", {}):
		var target := stick_shaped(name)
		if last_device != "kbm" or ramp_s <= 0.0:
			_ramped[name] = target
			continue
		var current: Vector2 = _ramped.get(name, Vector2.ZERO)
		_ramped[name] = current.move_toward(target, delta / ramp_s)


func _input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			_mouse_raw += (event as InputEventMouseMotion).screen_relative
		_note_device("kbm")
	elif event is InputEventKey or event is InputEventMouseButton:
		_note_device("kbm")
	elif event is InputEventJoypadButton:
		_note_device("pad")
	elif event is InputEventJoypadMotion and absf((event as InputEventJoypadMotion).axis_value) > 0.4:
		_note_device("pad")


func _note_device(kind: String) -> void:
	if kind != last_device:
		last_device = kind
		device_changed.emit(kind)


func pad_name() -> String:
	var pads := Input.get_connected_joypads()
	return Input.get_joy_name(pads[0]) if pads.size() > 0 else ""
