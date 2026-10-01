extends LegionBrain
## Ameise, the scout (enemies.json "behaviour": "scout"): finds the Juggernaut, calls every Legion
## unit within ai.call_radius_m to where it is, then keeps its distance (ai.keep_range_m) and circles
## while its two body-mounted machine guns fire bursts whenever the body bears. Too close and it
## backs off; too far and it closes. Its guns are fixed to the body, so it turns to shoot.

signal called(at: Vector3, heard_by: int)

var calls := 0
var _last_call_s := INF
var _burst_left := 0.0
var _gap_left := 0.0
var _circle := 1.0
var _circle_left := 0.0


func _ready() -> void:
	super()
	spotted.connect(_on_spotted)


func _physics_process(delta: float) -> void:
	_last_call_s += delta
	super(delta)


func _on_spotted(at: Vector3) -> void:
	if _last_call_s < float(ai.get("call_cooldown_s", 20.0)):
		return
	_last_call_s = 0.0
	calls += 1
	var reach := float(ai.get("call_radius_m", 600.0))
	var heard := 0
	for n: Node in get_tree().get_nodes_in_group("legion"):
		var other := n as LegionMech
		if other == null or other == unit or other.dead:
			continue
		var brain := other.get_node_or_null("Brain") as LegionBrain
		if brain != null and other.global_position.distance_to(unit.global_position) <= reach:
			brain.hear_of(at)
			heard += 1
	called.emit(at, heard)


func _attack(dt: float) -> void:
	var keep: Array = ai.get("keep_range_m", [150.0, 250.0])
	var d := distance_to_target()
	var away := _flat(unit.global_position - last_known).normalized()
	var speed := float(unit.def.get("speed_m_s", 14.0))
	_circle_left -= dt
	if _circle_left <= 0.0:
		_circle_left = _rng.randf_range(3.0, 7.0)
		_circle = -_circle if _rng.randf() < 0.5 else _circle
	if d < float(keep[0]):
		steer_dir(away + away.cross(Vector3.UP) * 0.4 * _circle, speed)
	elif d > float(keep[1]):
		steer_to(last_known, speed * 0.8)
	else:
		steer_dir(away.cross(Vector3.UP) * _circle, float(ai.get("strafe_m_s", 6.0)))
	face(last_known)
	unit.aim_point = target_centre() if sees else last_known
	_shoot(dt)


func _shoot(dt: float) -> void:
	if _gap_left > 0.0:
		_gap_left -= dt
		return
	if try_fire("ameise_mg", float(ai.get("fire_cone_deg", 4.0)), float(ai.get("spread_mrad", 4.0)), float(ai.get("fire_range_m", 450.0))) != null or _burst_left > 0.0:
		_burst_left += dt
		if _burst_left > float(ai.get("burst_s", 1.2)):
			_burst_left = 0.0
			_gap_left = float(ai.get("burst_gap_s", 1.5))
