class_name MissionRun
extends RefCounted
## What a level does around a mission, shared so a map does not copy it (lane B5 part 2; the big map
## uses it, the small map still has its own copies of the same four things): start the map's mission
## with its objective HUD, and the bot hooks that report on it and park a camera by a Legion unit.


## Starts `mission_id` ("" = the map's own, Mission.for_map(map_id)) in `level` with its objective
## HUD. Null when the map has no mission.
static func start(level: Node3D, map_id: String, mission_id: String = "") -> Mission:
	if mission_id == "":
		mission_id = Mission.for_map(map_id)
	if mission_id == "":
		return null
	var mission := Mission.start_in(level, mission_id)
	if mission == null:
		return null
	var hud := MissionHud.new()
	level.add_child(hud)
	hud.watch(mission)
	return mission


## Bot: the mission's state, every unit's telemetry and the player's last hits into the bot report
## under "legion" (label: when).
static func report(mission: Mission, label: String) -> void:
	if mission == null or not Bot.active:
		return
	if not Bot.report.has("legion"):
		Bot.report["legion"] = []
	(Bot.report["legion"] as Array).append({"label": label, "mission": mission.summary(), "units": mission.unit_report(), "player_hits": mission.player_hits.slice(-12)})


## Bot: parks `camera` beside Legion unit `index`, looking at it.
static func look_at(mission: Mission, camera: Camera3D, index: int, side_m: float, up_m: float, ground: Callable) -> void:
	if mission == null or mission.units.is_empty():
		push_warning("MissionRun: no Legion to look at")
		return
	var u := mission.units[clampi(index, 0, mission.units.size() - 1)] as Node3D
	var at := u.global_position
	var eye := at + u.global_transform.basis.x * side_m + u.global_transform.basis.z * side_m * 0.5
	eye.y = maxf(at.y + up_m, float(ground.call(eye.x, eye.z)) + 2.0)
	camera.global_position = eye
	camera.look_at(at + Vector3.UP * 2.0, Vector3.UP)
	camera.current = true
