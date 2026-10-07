extends RefCounted
## The after-action numbers of one sortie (lane A7): what the player fired and hit, the Legion parts
## they shot off, their kills and the longest one, the damage they took, and from those a grade (S to
## D) with personal bests per mission kept in records_file. Mission feeds it; the end card reads it.

signal part_shot_off(unit: Node, key: String)
signal kill_scored(unit: Node, distance_m: float)

const GRADES := [[90, "S"], [75, "A"], [60, "B"], [40, "C"], [0, "D"]]
const DEFAULT_PAR_S := 600.0

var records_file := "user://records.cfg"  # tests point it elsewhere
var player: Node3D
var hits := 0  # rounds of the player's that struck a Legion unit (blast splash not counted)
var damage_dealt := 0.0
var parts_off: Array = []  # [enemy id, part key] in the order they came off
var kills_by_you := 0
var longest_kill_m := 0.0
var damage_taken := 0.0
var shots := 0  # main gun + sub-arm rounds, set by finish()
var _shots_at_start := 0


func start(player_node: Node3D) -> void:
	player = player_node
	_shots_at_start = _shots_now()


## Starts listening to one Legion unit's hits, lost parts and death.
func watch_unit(u: Node) -> void:
	u.connect("hit_taken", _on_unit_hit.bind(u))
	u.connect("part_lost", _on_unit_part_lost.bind(u))
	u.connect("destroyed", _on_unit_destroyed.bind(u))


func took(dealt: float) -> void:
	damage_taken += dealt


func accuracy() -> float:
	return clampf(float(hits) / float(shots), 0.0, 1.0) if shots > 0 else 0.0


## The armour the player has left, 0..1 (1 with no damage model).
func armour_left() -> float:
	var combat: Object = player.get_meta("combat") if player != null and is_instance_valid(player) and player.has_meta("combat") else null
	if combat == null or combat.get("damage") == null:
		return 1.0
	return clampf(float((combat.get("damage") as Object).call("total_fraction")), 0.0, 1.0)


## Points out of 100: a win 40, armour left up to 25, accuracy up to 20, and up to 15 for beating
## `par_s`. A loss keeps only the accuracy and armour parts, so it lands on D or C.
static func score(won: bool, armour: float, acc: float, time_s: float, par_s: float) -> int:
	var pts := 25.0 * clampf(armour, 0.0, 1.0) + 20.0 * clampf(acc / 0.6, 0.0, 1.0)
	if won:
		pts += 40.0 + 15.0 * clampf(par_s / maxf(time_s, 1.0), 0.0, 1.0)
	return roundi(pts)


static func grade_of(points: int) -> String:
	for g: Array in GRADES:
		if points >= int(g[0]):
			return str(g[1])
	return "D"


## The numbers at the end, and which of them beat this mission's saved bests (saved here when won).
func finish(mission_id: String, won: bool, time_s: float, par_s: float = DEFAULT_PAR_S) -> Dictionary:
	shots = _shots_now() - _shots_at_start
	var pts := score(won, armour_left(), accuracy(), time_s, par_s)
	var out := {
		"shots": shots,
		"hits": hits,
		"accuracy": snappedf(accuracy(), 0.001),
		"parts_off": parts_off.size(),
		"kills_by_you": kills_by_you,
		"longest_kill_m": snappedf(longest_kill_m, 1.0),
		"damage_taken": snappedf(damage_taken, 1.0),
		"armour_left": snappedf(armour_left(), 0.01),
		"score": pts,
		"grade": grade_of(pts),
		"bests": [],
	}
	if won and Registry.has_entry("missions", mission_id):  # a test's made-up mission leaves the records alone
		out["bests"] = _save_bests(mission_id, out, time_s)
	return out


## Writes every number that beat the record and returns their names (first win: all of them).
func _save_bests(mission_id: String, out: Dictionary, time_s: float) -> Array:
	var cfg := ConfigFile.new()
	cfg.load(records_file)
	var beaten: Array = []
	var checks := [
		["score", float(out["score"]), true],
		["time_s", time_s, false],
		["accuracy", float(out["accuracy"]), true],
		["longest_kill_m", float(out["longest_kill_m"]), true],
	]
	for c: Array in checks:
		var name := str(c[0])
		var value := float(c[1])
		var higher := bool(c[2])
		if higher and value <= 0.0:  # no hits or no kills: nothing to hold up as a best
			continue
		if not cfg.has_section_key(mission_id, name):
			cfg.set_value(mission_id, name, value)
			beaten.append(name)
			continue
		var old := float(cfg.get_value(mission_id, name))
		if (higher and value > old) or (not higher and value < old):
			cfg.set_value(mission_id, name, value)
			beaten.append(name)
	cfg.set_value(mission_id, "wins", int(cfg.get_value(mission_id, "wins", 0)) + 1)
	cfg.save(records_file)
	return beaten


func best(mission_id: String, name: String, fallback: Variant = null) -> Variant:
	var cfg := ConfigFile.new()
	cfg.load(records_file)
	return cfg.get_value(mission_id, name, fallback)


func _shots_now() -> int:
	var combat: Object = player.get_meta("combat") if player != null and is_instance_valid(player) and player.has_meta("combat") else null
	if combat == null:
		return 0
	return int(combat.get("shots_fired")) + int(combat.get("sub_shots")) + int(combat.get("blade_strikes") if "blade_strikes" in combat else 0)


func _on_unit_hit(_key: String, dealt: float, info: Dictionary, _u: Node) -> void:
	if info.get("shooter") != player or player == null:
		return
	damage_dealt += dealt
	if not bool(info.get("splash", false)):
		hits += 1


## Parts and deaths are judged by the unit's last_shooter, set before the hit's damage (part_lost
## and destroyed fire inside it, before hit_taken), so the killing shot that ends a mission counts.
func _on_unit_part_lost(key: String, u: Node) -> void:
	if key == "hull" or bool(u.get("dead")) or not _by_player(u):
		return
	parts_off.append([str(u.get("enemy_id")), key])
	part_shot_off.emit(u, key)


func _on_unit_destroyed(u: Node) -> void:
	if not _by_player(u) or not is_instance_valid(player):
		return
	kills_by_you += 1
	var d := (u as Node3D).global_position.distance_to(player.global_position)
	longest_kill_m = maxf(longest_kill_m, d)
	kill_scored.emit(u, d)


func _by_player(u: Node) -> bool:
	return player != null and u.get("last_shooter") == player
