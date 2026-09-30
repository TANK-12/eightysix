extends Node
## The mixer: builds the audio buses listed in data/sounds.json and applies Settings > Audio
## (bus volumes, output device, night-mode dynamic range, mute in the background).
## Lane B4 adds reverb zones, occlusion and the sound library on top.

var _focused := true


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	build_buses()
	apply()
	Settings.changed.connect(_on_setting_changed)


func build_buses() -> void:
	for bus: Dictionary in Registry.file("sounds").get("buses", []):
		var name := str(bus["name"])
		var index := AudioServer.get_bus_index(name)
		if index < 0:
			AudioServer.add_bus()
			index = AudioServer.bus_count - 1
			AudioServer.set_bus_name(index, name)
		if bus.has("send"):
			AudioServer.set_bus_send(index, str(bus["send"]))
	_build_reverbs()
	var master := AudioServer.get_bus_index("Master")
	if AudioServer.get_bus_effect_count(master) == 0:
		var squash := AudioEffectCompressor.new()
		squash.threshold = -18.0
		squash.ratio = 6.0
		squash.gain = 6.0
		AudioServer.add_bus_effect(master, squash)
		var limiter := AudioEffectHardLimiter.new()
		AudioServer.add_bus_effect(master, limiter)


## Lane B4: one reverb on the Effects bus. Sfx sets its character from the reverb zone the listener
## is in (sounds.json "reverbs"), so every category keeps its own volume slider.
const REVERB_FIELDS := ["room_size", "damping", "spread", "wet", "predelay_ms", "predelay_feedback", "hipass"]


func _build_reverbs() -> void:
	var fx := AudioServer.get_bus_index("Effects")
	if fx < 0 or effects_reverb() != null:
		return
	var rv := AudioEffectReverb.new()
	rv.dry = 1.0
	rv.wet = 0.0
	AudioServer.add_bus_effect(fx, rv)


func effects_reverb() -> AudioEffectReverb:
	var fx := AudioServer.get_bus_index("Effects")
	for i in AudioServer.get_bus_effect_count(fx):
		if AudioServer.get_bus_effect(fx, i) is AudioEffectReverb:
			return AudioServer.get_bus_effect(fx, i)
	return null


## Sets the Effects reverb from a dictionary of REVERB_FIELDS (missing fields are left alone).
func set_reverb(spec: Dictionary) -> void:
	var rv := effects_reverb()
	if rv == null:
		return
	rv.room_size = float(spec.get("room_size", rv.room_size))
	rv.damping = float(spec.get("damping", rv.damping))
	rv.spread = float(spec.get("spread", rv.spread))
	rv.wet = float(spec.get("wet", rv.wet))
	rv.predelay_msec = float(spec.get("predelay_ms", rv.predelay_msec))
	rv.predelay_feedback = float(spec.get("predelay_feedback", rv.predelay_feedback))
	rv.hipass = float(spec.get("hipass", rv.hipass))


func apply() -> void:
	for bus: Dictionary in Registry.file("sounds").get("buses", []):
		var key := "audio." + str(bus["id"])
		var index := AudioServer.get_bus_index(str(bus["name"]))
		if index >= 0 and Settings.has_key(key):
			var linear := Settings.get_f(key)
			AudioServer.set_bus_volume_db(index, linear_to_db(maxf(linear, 0.0001)))
			AudioServer.set_bus_mute(index, linear <= 0.001)
	var master := AudioServer.get_bus_index("Master")
	AudioServer.set_bus_effect_enabled(master, 0, Settings.get_s("audio.dynamic_range") == "night")
	var device := Settings.get_s("audio.output_device")
	if device in AudioServer.get_output_device_list() and AudioServer.output_device != device:
		AudioServer.output_device = device
	_apply_focus_mute()


func _on_setting_changed(key: String, _value: Variant) -> void:
	if key.begins_with("audio."):
		apply()


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		_focused = false
		_apply_focus_mute()
	elif what == NOTIFICATION_APPLICATION_FOCUS_IN:
		_focused = true
		_apply_focus_mute()


func _apply_focus_mute() -> void:
	var master := AudioServer.get_bus_index("Master")
	var muted := Settings.get_b("audio.mute_unfocused") and not _focused
	AudioServer.set_bus_mute(master, muted or Settings.get_f("audio.master") <= 0.001)
