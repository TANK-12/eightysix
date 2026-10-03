extends Node
## Controller rumble from data/rumble.json. Rumble.play("fire_main") plays that event's steps on
## every connected pad, scaled by Settings > Controls > Rumble. Patterns can overlap; the strongest
## weak and strong motor values win each frame.
##
## Why it cannot stick on:
## - every effect handed to the pad has a finite length (the time to the next change, at most
##   SEND_CEIL_S, plus SEND_SLACK_S), so a frozen game or a lost stop call still ends within ~0.4 s;
## - a looping pattern lives only while its cause keeps calling play() (the owner refreshes it every
##   frame; it lapses `hold_ms` after the last call), so a freed mech, a released wire or a missed
##   stop() cannot leave it running; it also has a hard `max_s`;
## - loops are dropped on pause and on losing window focus; stop_all() silences at once.
## A play() or stop() takes effect on the same frame (flushed at the end of it), not the next.

const SEND_CEIL_S := 0.3
const SEND_SLACK_S := 0.1
const MIN_SEND_S := 0.15
const REFRESH_MARGIN_S := 0.06
const HOLD_S := 0.25
const LOOP_MAX_S := 30.0
const MIN_STEP_S := 0.005

## Tests: when `test_pads` is not empty those pads are used instead of the real ones and nothing is
## sent to Input; with `record` every start/stop that would be sent is appended to `log` as
## {"t": engine seconds, "frame": process frame, "kind": "start"|"stop", "pad", "weak", "strong", "duration"}.
var test_pads: Array = []
var record := false
var log: Array = []

var _playing: Dictionary = {}
var _clock := 0.0
var _on := false
var _sent := Vector2.ZERO
var _sent_until := 0.0
var _queued := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	Input.joy_connection_changed.connect(_on_pad_changed)


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
				"s": maxf(float(step.get("ms", 50.0)) / 1000.0, MIN_STEP_S),
			}
		)
	return out


## Starts the event. A one-shot restarts from its first step. A looping event that is already
## playing is only refreshed (call it every frame while the cause lasts).
func play(event: String, device: int = -1, extra_scale: float = 1.0) -> void:
	if not Registry.has_entry("rumble", event):
		return
	var pattern := Registry.entry("rumble", event)
	var looping := bool(pattern.get("loop", false))
	if looping and get_tree().paused:
		return
	if looping and _playing.has(event):
		var live: Dictionary = _playing[event]
		live["seen"] = _clock
		live["scale"] = extra_scale
		if _clock - float(live["scaled_at"]) >= 0.2:
			live["steps"] = scaled_steps(event, extra_scale)
			live["scaled_at"] = _clock
			live["index"] = mini(int(live["index"]), (live["steps"] as Array).size() - 1)
		return
	var steps := scaled_steps(event, extra_scale)
	if steps.is_empty():
		return
	_playing[event] = {
		"steps": steps,
		"index": 0,
		"left": steps[0]["s"],
		"loop": looping,
		"device": device,
		"seen": _clock,
		"born": _clock,
		"hold": float(pattern.get("hold_ms", HOLD_S * 1000.0)) / 1000.0,
		"max": float(pattern.get("max_s", LOOP_MAX_S)),
		"scale": extra_scale,
		"scaled_at": _clock,
	}
	_queue_flush()


func stop(event: String) -> void:
	if _playing.erase(event):
		_queue_flush()


func is_playing(event: String) -> bool:
	return _playing.has(event)


## Silences every pad now.
func stop_all() -> void:
	_playing.clear()
	_flush()


func _process(delta: float) -> void:
	var dt := delta / maxf(Engine.time_scale, 0.01)
	_clock += dt
	_advance(dt)
	_flush()


func _advance(dt: float) -> void:
	var paused := get_tree().paused
	for event: String in _playing.keys():
		var p: Dictionary = _playing[event]
		if bool(p["loop"]) and (paused or _clock - float(p["seen"]) > float(p["hold"]) + dt):
			_playing.erase(event)
			continue
		p["left"] = float(p["left"]) - dt
		while float(p["left"]) <= 0.0:
			p["index"] = int(p["index"]) + 1
			var steps: Array = p["steps"]
			if int(p["index"]) >= steps.size():
				if not bool(p["loop"]):
					_playing.erase(event)
					break
				p["index"] = 0
			p["left"] = float(p["left"]) + float(steps[p["index"]]["s"])


func _queue_flush() -> void:
	if not _queued:
		_queued = true
		_flush.call_deferred()


## Merges what is playing and sends it to the pads only when it changed or the effect on the pad is
## about to run out (see SEND_*): the same value is never restarted every frame.
func _flush() -> void:
	_queued = false
	var weak := 0.0
	var strong := 0.0
	var next := SEND_CEIL_S
	for event: String in _playing:
		var p: Dictionary = _playing[event]
		if bool(p["loop"]) and _clock - float(p["born"]) > float(p["max"]):
			continue
		var step: Dictionary = (p["steps"] as Array)[p["index"]]
		weak = maxf(weak, step["weak"])
		strong = maxf(strong, step["strong"])
		next = minf(next, float(p["left"]))
	var want := Vector2(weak, strong)
	if want.x <= 0.0005 and want.y <= 0.0005:
		if _on:
			_on = false
			_sent = Vector2.ZERO
			for pad in _pads():
				_log_event("stop", pad, 0.0, 0.0, 0.0)
				if test_pads.is_empty():
					Input.stop_joy_vibration(pad)
		return
	if _on and want.is_equal_approx(_sent) and _sent_until - _clock > REFRESH_MARGIN_S:
		return
	var duration := maxf(next, MIN_SEND_S) + SEND_SLACK_S
	_on = true
	_sent = want
	_sent_until = _clock + duration
	for pad in _pads():
		_log_event("start", pad, want.x, want.y, duration)
		if test_pads.is_empty():
			Input.start_joy_vibration(pad, want.x, want.y, duration)


func _pads() -> Array:
	return test_pads if not test_pads.is_empty() else Input.get_connected_joypads()


func _log_event(kind: String, pad: int, weak: float, strong: float, duration: float) -> void:
	if record:
		log.append(
			{
				"t": _clock,
				"frame": Engine.get_process_frames(),
				"kind": kind,
				"pad": pad,
				"weak": weak,
				"strong": strong,
				"duration": duration,
			}
		)


func _on_pad_changed(_device: int, _connected: bool) -> void:
	_sent_until = 0.0


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT or what == NOTIFICATION_WM_CLOSE_REQUEST:
		stop_all()
	elif what == NOTIFICATION_PREDELETE:
		for pad in Input.get_connected_joypads():
			Input.stop_joy_vibration(pad)
