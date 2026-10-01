class_name Mission
extends Node
## A mission from data/missions.json (lane A4 part 2), run inside a level: spawns each wave's Legion
## groups at their areas (a group is a pack whose brains share contacts), shows the objective, moves
## to the next wave once the last unit of this one is destroyed (or at its after_s), and ends won
## when every wave is destroyed or lost when the player's Juggernaut is. The level only needs a
## "mech" (the player) and ground_height(x, z); a "terrain" with water_level keeps spawns out of
## the water.

signal objective_changed(text: String)
signal wave_started(index: int, units: int)
signal unit_destroyed(unit: LegionMech)
signal ended(won: bool)

const TRACK_EVERY_S := 4.0

var id := ""
var def: Dictionary = {}
var level: Node3D
var player: RigidBody3D
var wave := -1
var units: Array = []  # LegionMech of the current wave
var all_units: Array = []
var kills := 0
var state := "running"  # running, won, lost
var elapsed_s := 0.0
var objective := ""
## The last hits the player took: [seconds, ammo, shooter enemy id, damage dealt, part] (newest last).
var player_hits: Array = []
var hits_taken := 0
var _wave_s := 0.0
var _track_in := 0.0  # seconds to the next tracking call (wave "track_s")
var _next_in := -1.0
var _rng := RandomNumberGenerator.new()


## The first ready mission set on `map_id` (maps.json "mission", else the first missions.json entry
## on that map), or "".
static func for_map(map_id: String) -> String:
	var named := str(Registry.entry("maps", map_id).get("mission", "")) if Registry.has_entry("maps", map_id) else ""
	if named != "" and Registry.has_entry("missions", named):
		return named
	for m: String in Registry.ids("missions"):
		var e := Registry.entry("missions", m)
		if str(e.get("map", "")) == map_id and str(e.get("status", "")) == "ready":
			return m
	return ""


## Adds a mission node to `level_node` and starts it.
static func start_in(level_node: Node3D, mission_id: String) -> Mission:
	if not Registry.has_entry("missions", mission_id):
		push_warning("Mission: no mission '%s'" % mission_id)
		return null
	var m := Mission.new()
	m.name = "Mission"
	m.id = mission_id
	m.def = Registry.entry("missions", mission_id)
	m.level = level_node
	level_node.add_child(m)
	return m


func _ready() -> void:
	_rng.seed = hash(id)
	player = level.get("mech") as RigidBody3D
	var combat: Object = player.get_meta("combat") if player != null and player.has_meta("combat") else null
	if combat == null and player != null:
		combat = player.get_node_or_null("Combat")
	if combat != null and combat.has_signal("destroyed"):
		combat.connect("destroyed", _on_player_destroyed)
	if combat != null and combat.has_signal("hit_taken"):
		combat.connect("hit_taken", _on_player_hit)
	_start_wave(0)


func _physics_process(delta: float) -> void:
	if state != "running":
		return
	elapsed_s += delta
	_wave_s += delta
	if _next_in >= 0.0:
		_next_in -= delta
		if _next_in < 0.0:
			_start_wave(wave + 1)
		return
	var after := float(_wave_def().get("after_s", 0.0))
	if after > 0.0 and _wave_s >= after and wave + 1 < waves_total():
		_start_wave(wave + 1)
		return
	_track_player(delta)


## A wave with "track_s" keeps being told where the Juggernaut is (the same rough fix as when it was
## called in, ai.hearing_error of the distance off) every TRACK_EVERY_S for that many seconds, so it
## can cross a map much bigger than its own memory (perception.memory_s) allows. Lane B5 part 2.
func _track_player(delta: float) -> void:
	var track_s := float(_wave_def().get("track_s", 0.0))
	if track_s <= 0.0 or _wave_s > track_s or player == null or not bool(_wave_def().get("alerted", false)):
		return
	_track_in -= delta
	if _track_in > 0.0:
		return
	_track_in = TRACK_EVERY_S
	for u: LegionMech in units:
		var brain := u.get_node_or_null("Brain") as LegionBrain
		if brain != null and is_instance_valid(u) and not u.dead:
			var err := u.position.distance_to(player.global_position) * 0.1
			brain.hear_of(player.global_position + Vector3(_rng.randfn(0.0, err), 0.0, _rng.randfn(0.0, err)))


func waves_total() -> int:
	return (def.get("waves", []) as Array).size()


func alive() -> int:
	return units.filter(func(u: Variant) -> bool: return is_instance_valid(u) and not (u as LegionMech).dead).size()


func _wave_def() -> Dictionary:
	var list: Array = def.get("waves", [])
	return list[wave] if wave >= 0 and wave < list.size() else {}


func _start_wave(index: int) -> void:
	if index >= waves_total():
		_end(true)
		return
	wave = index
	_wave_s = 0.0
	_track_in = TRACK_EVERY_S
	_next_in = -1.0
	units = []
	var w := _wave_def()
	for g: Dictionary in w.get("groups", []):
		var members: Array = []
		var area: Dictionary = (def.get("areas", {}) as Dictionary).get(str(g.get("area", "")), {})
		for i in int(g.get("count", 1)):
			var u := _spawn(str(g["enemy"]), area, members, i)
			if u != null:
				units.append(u)
				all_units.append(u)
	# A wave that was called in arrives knowing roughly where the Juggernaut is (ai.hearing_error
	# of the distance off), so it hunts instead of patrolling.
	if bool(w.get("alerted", false)) and player != null:
		for u: LegionMech in units:
			var brain := u.get_node_or_null("Brain") as LegionBrain
			if brain != null:
				var err := u.position.distance_to(player.global_position) * 0.1
				brain.hear_of.call_deferred(player.global_position + Vector3(_rng.randfn(0.0, err), 0.0, _rng.randfn(0.0, err)))
	objective = str(w.get("objective", ""))
	objective_changed.emit(objective)
	wave_started.emit(wave, units.size())


func _spawn(enemy_id: String, area: Dictionary, members: Array, index: int) -> LegionMech:
	var u := LegionMech.build(enemy_id)
	if u == null:
		return null
	var at := spawn_point(area)
	u.position = at + Vector3.UP * 0.6
	if player != null:
		var to := player.global_position - at
		to.y = 0.0
		if to.length() > 1.0:
			u.basis = Basis.looking_at(to.normalized(), Vector3.UP)
	var brain := u.get_node_or_null("Brain") as LegionBrain
	if brain != null:
		brain.setup(at, members, index, _rng.randi())
		var map_id := str(def.get("map", ""))
		if Registry.has_entry("maps", map_id):
			brain.area_half_m = float(Registry.entry("maps", map_id).get("legion_area_half_m", INF))
		members.append(brain)
	u.destroyed.connect(_on_unit_destroyed.bind(u))
	level.add_child(u)
	return u


## A point inside `area` on open, dry ground: a ray from above must land on the ground itself (not a
## roof or a wall top) and above the water; after 16 tries it takes the area's centre.
func spawn_point(area: Dictionary) -> Vector3:
	var c: Array = area.get("at", [0.0, 0.0])
	var r := float(area.get("radius_m", 20.0))
	var water := -INF
	var terrain: Variant = level.get("terrain")
	if terrain != null and terrain is Object and "water_level" in (terrain as Object):
		water = float((terrain as Object).get("water_level")) + 0.3
	for i in 16:
		var a := _rng.randf() * TAU
		var d := sqrt(_rng.randf()) * r
		var x := float(c[0]) + cos(a) * d
		var z := float(c[1]) + sin(a) * d
		var h := _ground(x, z)
		if h < water:
			continue
		var space := level.get_world_3d().direct_space_state
		var q := PhysicsRayQueryParameters3D.create(Vector3(x, h + 60.0, z), Vector3(x, h - 2.0, z), 1)
		var hit := space.intersect_ray(q)
		if hit.is_empty() or absf((hit["position"] as Vector3).y - h) < 1.0:
			if not _crowded(Vector3(x, h, z)):
				return Vector3(x, h, z)
	return Vector3(float(c[0]), _ground(float(c[0]), float(c[1])), float(c[1]))


func _crowded(at: Vector3) -> bool:
	for u: Variant in all_units:
		if is_instance_valid(u) and (u as Node3D).position.distance_to(at) < 12.0:
			return true
	return false


func _ground(x: float, z: float) -> float:
	if level.has_method("ground_height"):
		return float(level.call("ground_height", x, z))
	return 0.0


func _on_unit_destroyed(u: LegionMech) -> void:
	kills += 1
	unit_destroyed.emit(u)
	if state != "running" or not units.has(u) or alive() > 0:
		return
	_next_in = float(_wave_def().get("delay_s", 5.0))
	if wave + 1 >= waves_total():
		_end(true)
	else:
		objective_changed.emit("Wave cleared. More Legion inbound")


func _on_player_hit(key: String, dealt: float, info: Dictionary) -> void:
	var shooter: Variant = info.get("shooter")
	var who := str((shooter as LegionMech).enemy_id) if shooter is LegionMech and is_instance_valid(shooter) else ""
	hits_taken += 1
	player_hits.append([snappedf(elapsed_s, 0.1), str(info.get("ammo", "")), who, snappedf(dealt, 1.0), key])
	if player_hits.size() > 40:
		player_hits.pop_front()


func _on_player_destroyed() -> void:
	_end(false)


func _end(won: bool) -> void:
	if state != "running":
		return
	state = "won" if won else "lost"
	_next_in = -1.0
	objective = "Mission complete" if won else "Juggernaut lost"
	objective_changed.emit(objective)
	ended.emit(won)


## Destroys every unit of the current wave (bot runs and tests use it to reach later waves).
func clear_wave() -> void:
	for u: Variant in units.duplicate():
		if is_instance_valid(u):
			var unit := u as LegionMech
			for i in 12:
				if unit.dead:
					break
				unit.take_hit({"key": "hull", "damage": 5000.0, "penetration_mm": 900.0, "point": unit.global_position, "splash": true})


func summary() -> Dictionary:
	return {
		"mission": id,
		"state": state,
		"wave": wave + 1,
		"waves": waves_total(),
		"alive": alive(),
		"kills": kills,
		"time_s": snappedf(elapsed_s, 0.1),
		"player_hits": hits_taken,
	}


## Every unit of the current wave: id, position, distance to the player, health and its brain's state.
func unit_report() -> Array:
	var out: Array = []
	for u: Variant in units:
		if not is_instance_valid(u):
			continue
		var unit := u as LegionMech
		var row := unit.telemetry()
		row["pos"] = [snappedf(unit.global_position.x, 0.1), snappedf(unit.global_position.y, 0.1), snappedf(unit.global_position.z, 0.1)]
		row["to_player_m"] = snappedf(unit.global_position.distance_to(player.global_position), 0.1) if player != null else -1.0
		var brain := unit.get_node_or_null("Brain") as LegionBrain
		if brain != null:
			row.merge(brain.telemetry())
		out.append(row)
	return out
