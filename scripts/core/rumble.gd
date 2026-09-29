extends Node
## Controller rumble from data/rumble.json. Rumble.play("fire_main") plays that event's steps on
## every connected pad (or one device), scaled by Settings > Controls > Rumble. Patterns can overlap;
## the strongest weak and strong motor values win each frame. Looping patterns run until stop().

var _playing: Dictionary = {}
var _last := Vector2(-1.0, -1.0)


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


## The event's steps with every setting applied: [{"weak", "strong", "s"}], values 0..1.
func scaled_steps(event: String, extra_scale: float = 1.0) -> Array:
	if not Registry.has_entry("rumble", event):
		return []
	var pattern := Registry.entry("rumble", event)
	var scale := extra_scale
	if not Settings.get_b("rumble.enabled"):
		scale = 0.0
	scale *= Settings.get_f("rumble.intensity")
	var category := "rumble." + str(pattern.get("category", "movement"))
	if Settings.has_key(category):
		scale *= Settings.get_f(category)
	var out: Array = []
	for step: Dictionary in pattern.get("steps", []):
		out.append(
			{
				"weak": clampf(float(step.get("weak", 0.0)) * scale, 0.0, 1.0),
				"strong": clampf(float(step.get("strong", 0.0)) * scale, 0.0, 1.0),
				"s": float(step.get("ms", 50.0)) / 1000.0,
			}
		)
	return out


func play(event: String, device: int = -1, extra_scale: float = 1.0) -> void:
	var steps := scaled_steps(event, extra_scale)
	if steps.is_empty():
		return
	var looping := bool(Registry.entry("rumble", event).get("loop", false))
	_playing[event] = {"steps": steps, "index": 0, "left": steps[0]["s"], "loop": looping, "device": device}


func stop(event: String) -> void:
	_playing.erase(event)


func is_playing(event: String) -> bool:
	return _playing.has(event)


func stop_all() -> void:
	_playing.clear()


func _process(delta: float) -> void:
	var weak := 0.0
	var strong := 0.0
	for event: String in _playing.keys():
		var p: Dictionary = _playing[event]
		p["left"] = float(p["left"]) - delta
		while float(p["left"]) <= 0.0:
			p["index"] = int(p["index"]) + 1
			var steps: Array = p["steps"]
			if int(p["index"]) >= steps.size():
				if not p["loop"]:
					_playing.erase(event)
					break
				p["index"] = 0
			p["left"] = float(p["left"]) + float(steps[p["index"]]["s"])
		if not _playing.has(event):
			continue
		var step: Dictionary = p["steps"][p["index"]]
		weak = maxf(weak, step["weak"])
		strong = maxf(strong, step["strong"])
	_drive(weak, strong)


func _drive(weak: float, strong: float) -> void:
	var now := Vector2(weak, strong)
	if now.is_equal_approx(_last):
		return
	_last = now
	for pad in Input.get_connected_joypads():
		if weak <= 0.0 and strong <= 0.0:
			Input.stop_joy_vibration(pad)
		else:
			Input.start_joy_vibration(pad, weak, strong, 0.0)
