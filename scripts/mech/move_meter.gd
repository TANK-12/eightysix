class_name MoveMeter
extends Node
## Lane A3 part 4: the scoreboard's movement numbers (PLAN "Raising the bar": every session appends a
## row; tools/scoreboard.py reads logs/score_move.json). Rides on the player mech for a bot run
## (tools/bot/score_move.json, bot step {"meter": "start"}) and measures, every physics tick:
## top speed on the ground (a running jump's leap, and 1.5 s after landing, not counted); 0-50 km/h
## from a standstill; stuck events (move stick held, under 1 m/s for over 1 s);
## belly scrapes on flat ground (a chassis collider touching the world while 2+ legs are down on
## ground within 8 deg of level, not in the 0.6 s after a landing, where the plan allows the belly to
## touch; "flat" also needs the four spring contacts within 0.25 m of each other in height, so a crater
## lip or a kerb crossed at speed is not counted as flat: the leg hitboxes never collide, so any body
## contact is the chassis);
## the longest slide and the body's turn in it; the air turn rate from leg swing alone; and the
## main gun's recoil kick (speed change along the recoil, two ticks after a shot).

const KMH := 3.6

var mech: RigidBody3D
var top_speed := 0.0
var t0_50 := -1.0
var stuck_events := 0
var belly_scrapes := 0
var belly_scrape_s := 0.0
var belly_scrape_at: Array = []  # [bot seconds, x, z, speed m/s, skidding] of each scrape's start
var slide_m := 0.0
var slide_turn_deg := 0.0
var air_turn_deg_s := 0.0
var recoil_dv := 0.0

var _clock := 0.0
var _since_air := 99.0
var _still_since := -1.0
var _slow_s := 0.0
var _stuck := false
var _scraping := false
var _slide_from := Vector3.ZERO
var _slide_yaw := 0.0
var _sliding := false
var _air_s := 0.0
var _air_yaw := 0.0
var _air_turned := 0.0
var _was_air := false
var _shot_v := Vector3.ZERO
var _shot_dir := Vector3.ZERO
var _shot_wait := 0


func watch(body: RigidBody3D) -> void:
	mech = body
	var combat := mech.get_node_or_null("Combat")
	if combat != null and combat.has_signal("fired"):
		combat.connect("fired", _on_fired)


func _physics_process(delta: float) -> void:
	if mech == null or not is_instance_valid(mech):
		return
	_clock += delta
	var v := mech.linear_velocity
	var speed := Vector2(v.x, v.z).length()
	_since_air = 0.0 if bool(mech.get("airborne")) else _since_air + delta
	if _since_air > 1.5:
		top_speed = maxf(top_speed, speed)
	_track_start(speed)
	_track_stuck(speed, delta)
	_track_scrape(delta)
	_track_slide()
	_track_air(delta)
	if _shot_wait > 0:
		_shot_wait -= 1
		if _shot_wait == 0:
			recoil_dv = maxf(recoil_dv, (v - _shot_v).dot(_shot_dir))


func _track_start(speed: float) -> void:
	if speed < 0.5:
		_still_since = _clock
	elif t0_50 < 0.0 and _still_since >= 0.0 and speed >= 50.0 / KMH:
		t0_50 = _clock - _still_since


func _track_stuck(speed: float, delta: float) -> void:
	var pushing := Controls.stick("move").length() > 0.5 and not bool(mech.get("airborne"))
	_slow_s = _slow_s + delta if pushing and speed < 1.0 else 0.0
	if _slow_s > 1.0 and not _stuck:
		stuck_events += 1
	_stuck = _slow_s > 1.0


func _track_scrape(delta: float) -> void:
	var flat := (mech.get("ground_normal") as Vector3).dot(Vector3.UP) > cos(deg_to_rad(8.0)) and _level_under()
	var touching := mech.get_contact_count() > 0 and int(mech.get("grounded_legs")) >= 2 and flat and _since_air > 0.6
	if touching:
		belly_scrape_s += delta
		if not _scraping:
			belly_scrapes += 1
			var p := mech.global_position
			var v := mech.linear_velocity
			belly_scrape_at.append([snappedf(_clock, 0.01), snappedf(p.x, 0.1), snappedf(p.z, 0.1), snappedf(v.length(), 0.1), mech.get("skidding")])
	_scraping = touching


func _level_under() -> bool:
	var lo := INF
	var hi := -INF
	for leg: Dictionary in mech.get("legs"):
		if not bool(leg.get("contact", false)):
			return false
		var y := (leg["hit"] as Vector3).y
		lo = minf(lo, y)
		hi = maxf(hi, y)
	return hi - lo < 0.25


func _track_slide() -> void:
	var on := bool(mech.get("skidding"))
	if on and not _sliding:
		_slide_from = mech.global_position
		_slide_yaw = _yaw()
	elif on:
		var d := mech.global_position - _slide_from
		slide_m = maxf(slide_m, Vector2(d.x, d.z).length())
		slide_turn_deg = maxf(slide_turn_deg, absf(rad_to_deg(wrapf(_yaw() - _slide_yaw, -PI, PI))))
	_sliding = on


func _track_air(delta: float) -> void:
	var air := bool(mech.get("airborne"))
	if air and not _was_air:
		_air_s = 0.0
		_air_yaw = _yaw()
		_air_turned = 0.0
	elif air:
		_air_s += delta
		_air_turned = maxf(_air_turned, absf(rad_to_deg(wrapf(_yaw() - _air_yaw, -PI, PI))))
	elif _was_air and _air_s > 0.5:
		air_turn_deg_s = maxf(air_turn_deg_s, _air_turned / _air_s)
	_was_air = air


func _on_fired(_weapon: String, _ammo: String) -> void:
	# The impulse is queued inside fire_main; read the speed change two ticks on, along the recoil
	# (gravity and drag in those 1/60 s are a few cm/s across it at most).
	_shot_v = mech.linear_velocity
	var recoil: Vector3 = mech.get_node("Combat").get("last_recoil")
	_shot_dir = recoil.normalized()
	_shot_wait = 2


func _yaw() -> float:
	var f := -mech.global_transform.basis.z
	return atan2(-f.x, -f.z)


func results() -> Dictionary:
	return {
		"top_speed_kmh": snappedf(top_speed * KMH, 0.1),
		"t0_50_s": snappedf(t0_50, 0.01) if t0_50 >= 0.0 else null,
		"slide_m": snappedf(slide_m, 0.1),
		"slide_turn_deg": snappedf(slide_turn_deg, 0.1),
		"stuck_events": stuck_events,
		"belly_scrapes_flat": belly_scrapes,
		"belly_scrape_s": snappedf(belly_scrape_s, 0.01),
		"belly_scrape_at": belly_scrape_at,
		"air_turn_deg_s": snappedf(air_turn_deg_s, 0.1),
		"recoil_dv_m_s": snappedf(recoil_dv, 0.01),
	}
