class_name MechSounds
extends Node
## The sounds of one mech (lane B4), from the signals its locomotion and combat code already emit:
## footsteps by surface under each foot, jump and landing, the gun, reload and the casing landing,
## the wire. Three loops follow the body: leg servos rising with speed, feet skidding, the winch
## reeling. Sfx adds one of these to every mech that joins the tree, so mech code needs no sound calls.

const LEG_OFFSETS := {"fl": Vector3(-2.2, 0, -1.6), "fr": Vector3(2.2, 0, -1.6), "rl": Vector3(-2.2, 0, 1.6), "rr": Vector3(2.2, 0, 1.6)}
const CASING_FALL_S := 0.6  # from the ejection port to the ground, about 2 m
const SERVO_QUIET_DB := -44.0
const SERVO_LOUD_DB := -22.0
const SKID_DB := -14.0
const REEL_FROM := 0.5  # m/s of cable on the winch drum
const SLIDE_FROM := 0.3  # telemetry slide amount above which the feet audibly skid
const POLL_S := 0.1

var mech: RigidBody3D
var _servo: AudioStreamPlayer3D
var _skid: AudioStreamPlayer3D
var _reel: AudioStreamPlayer3D
var _anchor: Node
var _poll := 0.0
## A Legion mech's "sounds" block from enemies.json (step, step_db, step_pitch, servo, servo_db, servo_pitch);
## empty for the Juggernaut, which uses the foot, servo and gun sounds of the surface and weapon tables.
var _legion: Dictionary = {}


func _ready() -> void:
	mech = get_parent() as RigidBody3D
	if mech == null:
		return
	mech.connect("stepped", _on_stepped)
	if mech.has_signal("landed"):
		mech.connect("landed", _on_landed)
	if mech.has_signal("jumped"):
		mech.connect("jumped", _on_jumped)
	if "enemy_id" in mech:
		_legion = (mech.get("def") as Dictionary).get("sounds", {})
	var combat := mech.get_node_or_null("Combat")
	if combat == null and mech.has_signal("fired"):
		# a Legion mech fires from its own body: no Combat node, the signal is on the mech itself
		mech.connect("fired", _on_fired)
	if combat != null:
		combat.connect("fired", _on_fired)
		combat.connect("reloaded", _on_reloaded)
		_anchor = combat.get_node_or_null("WireAnchor")
		if _anchor != null:
			_anchor.connect("attached", _on_wire_attached)
			_anchor.connect("snapped", _on_wire_snapped)
	_servo = Sfx.loop(str(_legion.get("servo", "servo_loop")), mech) as AudioStreamPlayer3D
	_skid = Sfx.loop("skid_loop", mech) as AudioStreamPlayer3D
	_reel = Sfx.loop("wire_reel_loop", mech) as AudioStreamPlayer3D
	for p in [_servo, _skid, _reel]:
		if p != null:
			p.volume_db = -80.0


func _process(delta: float) -> void:
	if mech == null:
		return
	_poll += delta
	if _poll < POLL_S:
		return
	_poll = 0.0
	var speed := mech.linear_velocity.length()
	var turn := absf(mech.angular_velocity.y)
	var work := clampf(speed / 18.0 + turn * 0.4, 0.0, 1.0)
	if _servo != null:
		var servo_event := str(_legion.get("servo", "servo_loop"))
		_servo.volume_db = lerpf(SERVO_QUIET_DB, SERVO_LOUD_DB, sqrt(work)) + Sfx.mix_db(servo_event) + float(_legion.get("servo_db", 0.0))
		_servo.pitch_scale = (0.85 + work * 0.45) * float(_legion.get("servo_pitch", 1.0)) * float(Sfx.choice_of(servo_event).get("pitch", 1.0))
	# telemetry "slide" is an amount 0-1 (a slight slip while running is normal), "skidding" a flag
	var slide := 0.0
	if mech.has_method("telemetry"):
		var t: Dictionary = mech.call("telemetry")
		slide = maxf(float(t.get("slide", 0.0)), 1.0 if bool(t.get("skidding", false)) else 0.0)
	if _skid != null:
		var on := slide > SLIDE_FROM and speed > 2.0
		_skid.volume_db = SKID_DB + linear_to_db(clampf(slide * speed / 12.0, 0.05, 1.0)) + Sfx.mix_db("skid_loop") if on else -80.0
	if _reel != null and _anchor != null:
		# the drum's cable speed (m/s), only while the wire is out: louder and higher the faster it
		# turns. A drum easing to a stop below REEL_FROM is silent (it hummed at 76 Hz forever).
		var drum := absf(float(_anchor.get("_rope_speed")))
		var out := int(_anchor.get("state")) != 0
		_reel.volume_db = lerpf(-30.0, -14.0, clampf(drum / 6.0, 0.0, 1.0)) + Sfx.mix_db("wire_reel_loop") if out and drum > REEL_FROM else -80.0
		_reel.pitch_scale = 0.8 + clampf(drum / 6.0, 0.0, 1.0) * 0.5


func _foot_at(leg: String) -> Vector3:
	if not _legion.is_empty():
		for l: Dictionary in mech.get("legs"):
			if str(l.get("tag", "")) == leg:
				return mech.call("sole_world", l)
	return mech.global_transform * LEG_OFFSETS.get(leg, Vector3.ZERO)


func _surface_under(at: Vector3) -> String:
	var q := PhysicsRayQueryParameters3D.create(at + Vector3.UP * 1.5, at + Vector3.DOWN * 3.0, Sfx.OCCLUSION_MASK)
	q.exclude = [mech.get_rid()]
	var hit := mech.get_world_3d().direct_space_state.intersect_ray(q)
	return Sfx.surface_of(hit.get("collider")) if not hit.is_empty() else "dirt"


func _on_stepped(leg: String) -> void:
	var at := _foot_at(leg)
	if _legion.has("step"):
		var pace := clampf(mech.linear_velocity.length() / 12.0, 0.0, 1.0)
		Sfx.play(str(_legion["step"]), at, lerpf(-9.0, 0.0, pace) + float(_legion.get("step_db", 0.0)), float(_legion.get("step_pitch", 1.0)))
		return
	var surf: Dictionary = Registry.file("sounds").get("surfaces", {}).get(_surface_under(at), {})
	var speed := mech.linear_velocity.length()
	Sfx.play(str(surf.get("foot", "foot_dirt")), at, lerpf(-9.0, 0.0, clampf(speed / 15.0, 0.0, 1.0)))


func _on_landed(impact_speed: float) -> void:
	if impact_speed > 3.0:
		Sfx.play("land_heavy", mech, lerpf(-8.0, 0.0, clampf((impact_speed - 3.0) / 8.0, 0.0, 1.0)))
	for leg: String in LEG_OFFSETS:
		_on_stepped(leg)


func _on_jumped(_speed: float) -> void:
	Sfx.play("hydraulic_hiss", mech)


func _weapon_sounds(weapon: String) -> Dictionary:
	return Registry.file("sounds").get("weapons", {}).get(weapon, {})


func _on_fired(weapon: String, _ammo: String) -> void:
	var s := _weapon_sounds(weapon)
	if s.has("fire"):
		Sfx.play(str(s["fire"]), mech)
	if s.has("casing"):
		var where := mech.global_position
		get_tree().create_timer(CASING_FALL_S, false).timeout.connect(func() -> void: Sfx.play(str(s["casing"]), where))


func _on_reloaded(weapon: String) -> void:
	var s := _weapon_sounds(weapon)
	if s.has("reload"):
		Sfx.play(str(s["reload"]), mech)


func _on_wire_attached(point: Vector3) -> void:
	Sfx.play("wire_anchor_hit", point)


func _on_wire_snapped() -> void:
	Sfx.play("impact_metal", mech, -6.0)
