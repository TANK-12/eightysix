extends Node
## Sound effects (lane B4). Sfx.play("<sounds.json entry>", where) plays one random take of the entry:
## placed in the world when `where` is a Vector3 or Node3D (and the entry is not "2d"), on its bus,
## with a little pitch jitter so repeats differ. Far guns and impacts arrive late, at the speed of
## sound (a 57 mm shot 700 m away is heard 2 s after the flash). Sounds behind walls or hills are
## muffled (a ray from the listener, a few times a second). Sfx.loop() starts a looping sound that
## follows a node (servos, wind, the winch). Buttons click and projectiles hit by themselves: this
## node listens for them joining the tree, so menus and combat code need no sound calls.

const POOL_3D := 40
const POOL_2D := 10
const SPEED_OF_SOUND_M_S := 343.0
const DELAY_FROM_M := 25.0
const OPEN_CUTOFF_HZ := 9000.0
const OCCLUDED_CUTOFF_HZ := 900.0
const OCCLUDED_DB := -8.0
const OCCLUSION_MASK := 1  # the "world" physics layer: terrain, walls, rocks
const OCCLUSION_EVERY_S := 0.12
const REVERB_BLEND_S := 1.0  # walking from the valley into town changes the reverb over about a second
const ATTENUATION := {
	"inverse": AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE,
	"inverse_square": AudioStreamPlayer3D.ATTENUATION_INVERSE_SQUARE_DISTANCE,
	"logarithmic": AudioStreamPlayer3D.ATTENUATION_LOGARITHMIC,
}

var played := 0  # takes started since launch (tests and bot reports)
var counts := {}  # event -> takes started, saved beside a recording (lane B4 sound checks)
var log_3d: Array = []  # while recording: each placed take's final volume, muffle and distance
var _streams := {}
var _pool3: Array[AudioStreamPlayer3D] = []
var _pool2: Array[AudioStreamPlayer] = []
var _next3 := 0
var _next2 := 0
var _occlusion_t := 0.0
var _warned := {}
var _recording := false
var _zones: Array = []
var _reverb_now := {}
var _voices := {}  # first file of an entry -> its sounding pool players (for max_voices)


func _ready() -> void:
	for i in POOL_3D:
		var p := AudioStreamPlayer3D.new()
		p.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_PHYSICS_STEP
		add_child(p)
		_pool3.append(p)
	for i in POOL_2D:
		var p := AudioStreamPlayer.new()
		p.process_mode = Node.PROCESS_MODE_ALWAYS
		add_child(p)
		_pool2.append(p)
	get_tree().node_added.connect(_on_node_added)


func has(event: String) -> bool:
	return Registry.has_entry("sounds", event)


## Plays one take of `event`. where: null (2D), a Vector3 or a Node3D. Returns the player, or null
## when the entry is missing or the sound is delayed by distance (it starts later by itself).
func play(event: String, where: Variant = null, volume_db: float = 0.0, pitch: float = 1.0) -> Node:
	if not has(event):
		if not _warned.has(event):
			_warned[event] = true
			push_warning("Sfx: no sound '%s' in sounds.json" % event)
		return null
	var e := Registry.entry("sounds", event)
	var stream := _pick(e)
	if stream == null:
		return null
	counts[event] = int(counts.get(event, 0)) + 1
	var jitter := float(e.get("pitch_jitter", 0.0))
	var p_scale := pitch * (1.0 + randf_range(-jitter, jitter))
	var vol := float(e.get("volume_db", 0.0)) + volume_db
	var pos: Variant = _position(where)
	if bool(e.get("2d", false)) or pos == null:
		var p2 := _pool2[_next2]
		_next2 = (_next2 + 1) % POOL_2D
		_start(p2, stream, str(e.get("bus", "Effects")), vol, p_scale)
		return p2
	var delay := 0.0
	if bool(e.get("delay_by_distance", false)):
		var d := _listener_pos().distance_to(pos)
		if d > DELAY_FROM_M:
			delay = d / SPEED_OF_SOUND_M_S
	if delay > 0.0:
		get_tree().create_timer(delay, false).timeout.connect(_play_3d.bind(e, stream, pos, vol, p_scale))
		return null
	return _play_3d(e, stream, pos, vol, p_scale)


## A looping sound that follows `follow` (3D) or plays everywhere (null). The caller keeps the
## player: set volume_db and pitch_scale as it goes, queue_free() it to stop.
func loop(event: String, follow: Node3D = null) -> Node:
	if not has(event):
		return null
	var e := Registry.entry("sounds", event)
	var stream := _pick(e)
	if stream == null:
		return null
	var player: Node
	if follow == null or bool(e.get("2d", false)):
		var p2 := AudioStreamPlayer.new()
		p2.stream = _looped(stream)
		p2.bus = _bus_name(str(e.get("bus", "Effects")))
		p2.volume_db = float(e.get("volume_db", 0.0))
		(follow if follow != null else self).add_child(p2)
		p2.play()
		player = p2
	else:
		var p3 := AudioStreamPlayer3D.new()
		_configure_3d(p3, e)
		p3.stream = _looped(stream)
		p3.volume_db = float(e.get("volume_db", 0.0))
		follow.add_child(p3)
		p3.play()
		player = p3
	played += 1
	return player


func _play_3d(e: Dictionary, stream: AudioStream, pos: Vector3, vol: float, p_scale: float) -> AudioStreamPlayer3D:
	var p := _voice_for(e)
	_configure_3d(p, e)
	p.global_position = pos
	p.set_meta("base_db", vol)
	p.set_meta("occlude", bool(e.get("occlude", true)))
	_start(p, stream, str(e.get("bus", "Effects")), vol, p_scale)
	_occlude(p)
	if _recording and log_3d.size() < 400:
		log_3d.append({"t": snappedf(Time.get_ticks_msec() / 1000.0, 0.01), "file": stream.resource_path.get_file(), "db": snappedf(p.volume_db, 0.1), "cutoff_hz": p.attenuation_filter_cutoff_hz, "m": snappedf(_listener_pos().distance_to(pos), 0.1)})
	return p


## A pool player for this sound. An entry with "max_voices" (fast guns) reuses its own oldest take
## once that many are sounding, so a burst does not pile up into a wash or take every voice.
func _voice_for(e: Dictionary) -> AudioStreamPlayer3D:
	var cap := int(e.get("max_voices", 0))
	var key := str(e.get("files", [""])[0])
	if cap > 0:
		var mine: Array = _voices.get(key, [])
		mine = mine.filter(func(v: AudioStreamPlayer3D) -> bool: return v.playing and v.get_meta("voice_of", "") == key)
		if mine.size() >= cap:
			var oldest: AudioStreamPlayer3D = mine.pop_front()
			mine.append(oldest)
			_voices[key] = mine
			return oldest
		var p := _next_pool_player()
		p.set_meta("voice_of", key)
		mine.append(p)
		_voices[key] = mine
		return p
	var q := _next_pool_player()
	q.set_meta("voice_of", "")
	return q


func _next_pool_player() -> AudioStreamPlayer3D:
	var p := _pool3[_next3]
	_next3 = (_next3 + 1) % POOL_3D
	return p


func _configure_3d(p: AudioStreamPlayer3D, e: Dictionary) -> void:
	p.bus = _bus_name(str(e.get("bus", "Effects")))
	p.unit_size = float(e.get("unit_size", 10.0))
	p.max_distance = float(e.get("max_distance_m", 500.0))
	p.attenuation_model = ATTENUATION.get(str(e.get("attenuation", "inverse")), AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE)
	p.attenuation_filter_cutoff_hz = OPEN_CUTOFF_HZ
	p.attenuation_filter_db = -18.0


func _start(p: Node, stream: AudioStream, bus: String, vol: float, p_scale: float) -> void:
	p.set("stream", stream)
	p.set("bus", _bus_name(bus))
	p.set("volume_db", vol)
	p.set("pitch_scale", p_scale)
	p.call("play")
	played += 1


## The mixer's bus name for a sounds.json bus id ("weapons" -> "Weapons").
func _bus_name(id: String) -> String:
	for b: Dictionary in Registry.file("sounds").get("buses", []):
		if str(b["id"]) == id or str(b["name"]) == id:
			return str(b["name"])
	return "Master"


func _pick(e: Dictionary) -> AudioStream:
	var files: Array = e.get("files", [])
	if files.is_empty():
		return null
	var path := str(files[randi() % files.size()])
	if not _streams.has(path):
		_streams[path] = load(path) if ResourceLoader.exists(path) else null
	return _streams[path]


func _looped(stream: AudioStream) -> AudioStream:
	var wav := stream as AudioStreamWAV
	if wav == null:
		return stream
	var copy := wav.duplicate() as AudioStreamWAV
	copy.loop_mode = AudioStreamWAV.LOOP_FORWARD
	copy.loop_begin = 0
	copy.loop_end = int(wav.get_length() * wav.mix_rate)
	return copy


func _position(where: Variant) -> Variant:
	if where is Vector3:
		return where
	if where is Node3D and is_instance_valid(where) and (where as Node3D).is_inside_tree():
		return (where as Node3D).global_position
	return null


func _listener_pos() -> Vector3:
	var cam := get_viewport().get_camera_3d()
	return cam.global_position if cam != null else Vector3.ZERO


## A reverb zone (lane B4): while the listener is inside `box`, the Effects reverb moves toward the
## sounds.json "reverbs" entry `reverb`, scaled by `amount`; the highest priority zone wins. First
## tried as Area3D reverb sends, which take the zone's share off each sound's own bus: with the
## send bus wet-only that cut every sound by 6-14 dB, and the share skipped the category sliders.
func add_reverb_zone(box: AABB, reverb: String, amount: float, priority: int = 0) -> void:
	_zones.append({"box": box, "reverb": reverb, "amount": amount, "priority": priority})


func clear_reverb_zones() -> void:
	_zones.clear()
	_reverb_now = {}


## The reverb the listener should hear at `where`: the zone entry's fields with wet scaled by amount.
func reverb_at(where: Vector3) -> Dictionary:
	var best: Dictionary = {}
	for z: Dictionary in _zones:
		if (z["box"] as AABB).has_point(where) and (best.is_empty() or int(z["priority"]) > int(best["priority"])):
			best = z
	if best.is_empty():
		return {"wet": 0.0}
	var spec: Dictionary = Registry.file("sounds").get("reverbs", {}).get(str(best["reverb"]), {}).duplicate()
	spec["wet"] = float(spec.get("wet", 0.3)) * float(best["amount"])
	return spec


func _update_reverb(delta: float) -> void:
	if _zones.is_empty():
		return
	var want := reverb_at(_listener_pos())
	var k := clampf(delta / REVERB_BLEND_S, 0.0, 1.0)
	for f: String in AudioMix.REVERB_FIELDS:
		if want.has(f):
			var now := float(_reverb_now.get(f, want[f] if f != "wet" else 0.0))
			_reverb_now[f] = lerpf(now, float(want[f]), k)
	AudioMix.set_reverb(_reverb_now)


## Records everything the Master bus plays (lane B4), for listening checks from bot runs: the Dummy
## audio driver still mixes, so a run off screen yields a real WAV of the game's sound.
func record(on: bool, path: String = "") -> void:
	var master := AudioServer.get_bus_index("Master")
	var rec: AudioEffectRecord = null
	for i in AudioServer.get_bus_effect_count(master):
		if AudioServer.get_bus_effect(master, i) is AudioEffectRecord:
			rec = AudioServer.get_bus_effect(master, i)
	if rec == null:
		rec = AudioEffectRecord.new()
		AudioServer.add_bus_effect(master, rec)
	_recording = on
	if on:
		counts.clear()
		log_3d.clear()
		rec.set_recording_active(true)
		return
	rec.set_recording_active(false)
	var clip := rec.get_recording()
	if clip != null and path != "":
		clip.save_to_wav(path)
		var f := FileAccess.open(path.get_basename() + ".json", FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify({"played": counts, "placed": log_3d, "sounding_at_end": _sounding(), "buses": _buses()}, " "))


func _buses() -> Array:
	var out: Array = []
	for i in AudioServer.bus_count:
		var fx: Array = []
		for k in AudioServer.get_bus_effect_count(i):
			fx.append("%s%s" % [AudioServer.get_bus_effect(i, k).get_class(), "" if AudioServer.is_bus_effect_enabled(i, k) else " (off)"])
		out.append({"bus": AudioServer.get_bus_name(i), "db": snappedf(AudioServer.get_bus_volume_db(i), 0.1), "mute": AudioServer.is_bus_mute(i), "send": AudioServer.get_bus_send(i), "fx": fx})
	return out


## Every player in the tree that is sounding now: stream, volume, bus (sound-check diagnostics).
func _sounding() -> Array:
	var out: Array = []
	for n: Node in get_tree().root.find_children("*", "", true, false):
		if (n is AudioStreamPlayer or n is AudioStreamPlayer3D) and bool(n.get("playing")):
			var st: AudioStream = n.get("stream")
			out.append({"path": str(n.get_path()).right(60), "file": st.resource_path.get_file() if st != null else "", "db": snappedf(float(n.get("volume_db")), 0.1), "bus": str(n.get("bus"))})
	return out


# --- occlusion ---------------------------------------------------------------------------------


func _physics_process(delta: float) -> void:
	_update_reverb(delta)
	_occlusion_t += delta
	if _occlusion_t < OCCLUSION_EVERY_S:
		return
	_occlusion_t = 0.0
	for p in _pool3:
		if p.playing:
			_occlude(p)


## Muffle and quieten a sound when solid world geometry is between it and the listener.
func _occlude(p: AudioStreamPlayer3D) -> void:
	if not bool(p.get_meta("occlude", true)) or not p.is_inside_tree():
		return
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var from := cam.global_position
	var to := p.global_position
	if from.distance_to(to) < 2.0:
		return
	# stop short of the source so the ground it sits on does not count
	var q := PhysicsRayQueryParameters3D.create(from, to + (from - to).normalized() * 1.5, OCCLUSION_MASK)
	var hit := p.get_world_3d().direct_space_state.intersect_ray(q)
	var blocked := not hit.is_empty()
	p.attenuation_filter_cutoff_hz = OCCLUDED_CUTOFF_HZ if blocked else OPEN_CUTOFF_HZ
	p.volume_db = float(p.get_meta("base_db", 0.0)) + (OCCLUDED_DB if blocked else 0.0)


# --- things that make sound by themselves ------------------------------------------------------


func _on_node_added(node: Node) -> void:
	if node is BaseButton:
		var b := node as BaseButton
		b.pressed.connect(play.bind("ui_click"))
		b.focus_entered.connect(_hover.bind(b))
		b.mouse_entered.connect(_hover.bind(b))
	elif node.has_signal("impacted") and node is Node3D:
		node.connect("impacted", _on_impact)
	elif node.has_signal("stepped") and node is RigidBody3D and not node.has_node("MechSounds"):
		var ms := MechSounds.new()
		ms.name = "MechSounds"
		node.add_child.call_deferred(ms)


func _hover(b: BaseButton) -> void:
	if b.is_visible_in_tree() and not b.disabled:
		play("ui_hover")


func _on_impact(info: Dictionary) -> void:
	var surface := surface_of(info.get("collider"))
	var sounds: Dictionary = Registry.file("sounds").get("surfaces", {}).get(surface, {})
	play(str(sounds.get("impact", "impact_dirt")), info.get("point", Vector3.ZERO))


## "metal" for anything that moves (mechs, Legion), "rock" for kit pieces (walls, rubble, rocks),
## "dirt" for the terrain and anything unknown.
static func surface_of(collider: Variant) -> String:
	if not (collider is Node) or not is_instance_valid(collider):
		return "dirt"
	var n := collider as Node
	var moving := n is RigidBody3D or n is CharacterBody3D or n is VehicleBody3D
	while n != null:
		if n.has_meta("kit"):
			return "rock"
		n = n.get_parent()
	return "metal" if moving else "dirt"
