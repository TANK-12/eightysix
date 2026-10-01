extends Node
## The music player (lane B4 part 2). Plays tracks from data/music.json (files in ~/Music/86/, kept
## outside the game) on the Music bus: one for the menus, one while exploring, one in combat, each
## picked in Settings > Audio > Music (a track, Shuffle or Off). Combat starts when a gun or a hit
## sounds near the listener and ends after COMBAT_HOLD_S of quiet. Changes crossfade over FADE_S.

const FADE_S := 2.5
const COMBAT_HOLD_S := 25.0
const COMBAT_NEAR_M := 400.0
const SETTING := {"menu": "audio.music_menu", "explore": "audio.music_explore", "combat": "audio.music_combat"}

var context := "menu"
var track := ""  # music.json id now playing, "" for none
var _players: Array[AudioStreamPlayer] = []
var _live := 0
var _fade := 1.0
var _combat_t := 0.0
var _streams := {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for i in 2:
		var p := AudioStreamPlayer.new()
		p.bus = "Music"
		p.volume_db = -80.0
		p.finished.connect(_on_finished.bind(p))
		add_child(p)
		_players.append(p)
	Settings.changed.connect(_on_setting_changed)
	Sfx.sounded.connect(_on_sounded)
	get_tree().scene_changed.connect(_on_scene_changed)
	_on_scene_changed.call_deferred()


## Tracks that may play in `ctx`, after the language filter; missing files are left out.
func candidates(ctx: String) -> PackedStringArray:
	var lang := Settings.get_s("audio.music_language") if Settings.has_key("audio.music_language") else "any"
	var out := PackedStringArray()
	for id in Registry.ids("music"):
		var e := Registry.entry("music", id)
		if not ctx in e.get("use", []):
			continue
		if lang != "any" and str(e.get("language", "none")) not in [lang, "none"]:
			continue
		if FileAccess.file_exists(path_of(id)):
			out.append(id)
	return out


func path_of(id: String) -> String:
	var p := str(Registry.entry("music", id).get("path", ""))
	return OS.get_environment("HOME") + p.substr(1) if p.begins_with("~") else p


## The track `ctx` wants now: the chosen one, a shuffled one, or "" for silence.
func choose(ctx: String) -> String:
	var want := Settings.get_s(SETTING[ctx]) if Settings.has_key(SETTING[ctx]) else "shuffle"
	if want == "off":
		return ""
	if want != "shuffle" and FileAccess.file_exists(path_of(want)):
		return want
	var pool := candidates(ctx)
	if pool.is_empty():
		return ""
	if pool.size() > 1 and track in pool:
		pool.remove_at(pool.find(track))
	return pool[randi() % pool.size()]


func set_context(ctx: String) -> void:
	if ctx == context and track != "":
		return
	context = ctx
	play(choose(ctx))


func skip() -> void:
	play(choose(context))


## Crossfades to `id` ("" fades to silence).
func play(id: String) -> void:
	track = id
	var next := _players[1 - _live]
	next.stop()
	if id != "":
		var stream := _load(id)
		if stream == null:
			track = ""
		else:
			next.stream = stream
			next.volume_db = -80.0
			next.play()
	_live = 1 - _live
	_fade = 0.0


func _load(id: String) -> AudioStream:
	if not _streams.has(id):
		var path := path_of(id)
		var s: AudioStream = null
		match path.get_extension().to_lower():
			"mp3":
				s = AudioStreamMP3.load_from_file(path)
			"ogg":
				s = AudioStreamOggVorbis.load_from_file(path)
		_streams[id] = s
	return _streams[id]


func _process(delta: float) -> void:
	if _fade < 1.0:
		_fade = minf(_fade + delta / FADE_S, 1.0)
		var level := float(Registry.entry("music", track).get("volume_db", 0.0)) if track != "" else 0.0
		_players[_live].volume_db = linear_to_db(maxf(_fade, 0.0001)) + level
		_players[1 - _live].volume_db = linear_to_db(maxf(1.0 - _fade, 0.0001))
		if _fade >= 1.0:
			_players[1 - _live].stop()
	if context == "combat":
		_combat_t -= delta
		if _combat_t <= 0.0:
			set_context("explore")


func _on_finished(p: AudioStreamPlayer) -> void:
	if p == _players[_live]:
		skip()


func _on_sounded(_event: String, bus: String, distance_m: float) -> void:
	if context == "menu" or bus not in ["weapons", "impacts"] or distance_m > COMBAT_NEAR_M:
		return
	_combat_t = COMBAT_HOLD_S
	set_context("combat")


func _on_scene_changed() -> void:
	var scene := get_tree().current_scene
	var in_menu := scene == null or scene.scene_file_path.contains("/ui/")
	set_context("menu" if in_menu else "explore")


func _on_setting_changed(key: String, _value: Variant) -> void:
	if key == SETTING.get(context, "") or key == "audio.music_language":
		play(choose(context))
