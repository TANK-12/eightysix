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
	var master := AudioServer.get_bus_index("Master")
	if AudioServer.get_bus_effect_count(master) == 0:
		var squash := AudioEffectCompressor.new()
		squash.threshold = -18.0
		squash.ratio = 6.0
		squash.gain = 6.0
		AudioServer.add_bus_effect(master, squash)
		var limiter := AudioEffectHardLimiter.new()
		AudioServer.add_bus_effect(master, limiter)


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
