class_name ResonanceBlade
extends Node
## The resonance blade (lane A7): the Juggernaut Model 2's two forward blades (jg2_blade_l / _r) as a
## close-in weapon. Hold Blade (X) with a Legion unit within reach of the blade tips and the blades
## tune to it: the meter fills over tune_s, glowing brighter, and holds full (tuned) for
## tuned_window_s before it drifts back to half. Release to strike: the blades lunge into the part
## nearest the tips for damage x (1 + resonance_damage_x x resonance) at more penetration the better
## the tune, so a strike released in the tuned window cuts through a Löwe's front plate and an early
## one barely scratches it. Numbers live in weapons.json "hf_blade"; MechCombat adds one when the
## mech carries blade parts.

signal tuned  # the meter just filled
signal struck(unit: Node, dealt: float, resonance: float)

const WEAPON := "hf_blade"
const GLOW := Color(0.45, 0.85, 1.0)

var combat: Node  # the MechCombat this belongs to
var mech: RigidBody3D
var def: Dictionary
var charging := false
var resonance := 0.0  # 0..1, 1 = tuned
var target: Node3D  # the Legion unit in reach while charging (null: none)
var last_strike: Dictionary = {}  # {unit, dealt, resonance, penetrated} of the last strike that landed
var _held_s := 0.0  # seconds tuned to the current target
var _cool := 0.0
var _flash := 0.0
var _said_tuned := false
var _glow: StandardMaterial3D
var _blade_meshes: Array[GeometryInstance3D] = []
var _blade_keys: Array = []  # damage keys of the blade parts
var _own: Array[RID] = []  # the mech's own collision objects, left out of the reach query


func _ready() -> void:
	combat = get_parent()
	mech = combat.get_parent() as RigidBody3D
	def = Registry.entry("weapons", WEAPON)
	var damage: Object = combat.get("damage")
	if damage != null:
		for key: String in damage.get("parts"):
			if str(damage.get("parts")[key].get("part", "")).contains("blade"):
				_blade_keys.append(key)
	_glow = StandardMaterial3D.new()
	_glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_glow.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	_glow.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_glow.albedo_color = Color(GLOW, 0.0)
	_find_meshes.call_deferred()  # the skinned model loads in the mech's setup


## True when a mech definition carries blade parts (MechCombat asks before adding one).
static func fits(mech_def: Dictionary) -> bool:
	for p: Variant in mech_def.get("parts", []):
		if p is Dictionary and str((p as Dictionary).get("part", "")).contains("blade"):
			return Registry.has_entry("weapons", WEAPON)
	return false


func _find_meshes() -> void:
	for n: Node in mech.find_children("*", "MeshInstance3D", true, false):
		if n.name.to_lower().contains("blade"):
			_blade_meshes.append(n as GeometryInstance3D)
			(n as GeometryInstance3D).material_overlay = _glow


## Where the two blade tips meet, in the world.
func tip() -> Vector3:
	var t: Array = def.get("tip", [0.0, -0.3, -3.4])
	return mech.global_transform * Vector3(float(t[0]), float(t[1]), float(t[2]))


## At least one blade is still on the mech (a mech without blade damage parts always has them).
func blades_ok() -> bool:
	var damage: Object = combat.get("damage")
	if _blade_keys.is_empty() or damage == null:
		return true
	return _blade_keys.any(func(k: String) -> bool: return not bool(damage.call("is_lost", k)))


func ready_to_strike() -> bool:
	return _cool <= 0.0 and blades_ok() and not bool(combat.get("damage").get("is_destroyed"))


## The live Legion unit nearest the blade tips with a part inside reach_m and in front of the mech.
func find_target() -> Node3D:
	var at := tip()
	var space := mech.get_world_3d().direct_space_state
	var q := PhysicsShapeQueryParameters3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = float(def.get("reach_m", 3.0))
	q.shape = sphere
	q.transform = Transform3D(Basis(), at)
	q.collide_with_areas = true
	# Legion bodies and hitboxes only: a trimesh ground answers with one result per triangle and
	# filled every slot before the unit at the tips (bot run 605). Our own shapes share those layers.
	q.collision_mask = MechBuilder.LAYER_MECH | MechBuilder.LAYER_HITBOX
	q.exclude = _own_shapes()
	var fwd := -mech.global_transform.basis.z
	var face := cos(deg_to_rad(float(def.get("face_deg", 60.0))))
	var best: Node3D = null
	var best_d := INF
	for r: Dictionary in space.intersect_shape(q, 32):
		var u := _unit_of(r.get("collider") as Node)
		if u == null or u == best:
			continue
		var to := u.global_position - mech.global_position
		to.y = 0.0
		if to.length() > 0.5 and fwd.dot(to.normalized()) < face:
			continue
		var d := at.distance_to(u.global_position)
		if d < best_d:
			best_d = d
			best = u
	return best


## The RIDs of the mech and every collision object on it (its hitboxes), found once.
func _own_shapes() -> Array[RID]:
	if _own.is_empty():
		_own.append(mech.get_rid())
		for n: Node in mech.find_children("*", "CollisionObject3D", true, false):
			_own.append((n as CollisionObject3D).get_rid())
	return _own


func _unit_of(n: Node) -> Node3D:
	while n != null:
		if n.is_in_group("legion"):
			return null if bool(n.get("dead")) else n as Node3D
		n = n.get_parent()
	return null


func _physics_process(delta: float) -> void:
	if mech == null:
		return
	_cool = maxf(_cool - delta, 0.0)
	_flash = maxf(_flash - delta * 3.0, 0.0)
	if bool(mech.get("is_player")) and not Game.is_paused():
		hold(Controls.held("blade"), delta)
	_glow.albedo_color = Color(GLOW, clampf(resonance * 0.55 + _flash, 0.0, 1.0))


## One tick of the Blade button: held charges, let go strikes (tests and bots call it directly).
func hold(down: bool, delta: float) -> void:
	if down and not charging and ready_to_strike():
		charging = true
		_held_s = 0.0
		_said_tuned = false
		Sfx.play("hydraulic_hiss", mech, -6.0, 1.4)
	elif not down and charging:
		charging = false
		strike()
		return
	if not charging:
		resonance = 0.0
		return
	var now := find_target()
	if now != target:
		target = now
		_held_s = 0.0
	if target == null:
		resonance = maxf(resonance - delta * 2.0, 0.0)
		return
	_held_s += delta
	resonance = curve(_held_s, def)
	if resonance >= 1.0 and not _said_tuned:
		_said_tuned = true
		tuned.emit()
		Sfx.play("ui_confirm", null, -4.0, 1.5)
		Rumble.play("blade_tuned")


## The meter after `held_s` tuned to one target: a rise to 1 over tune_s, full for tuned_window_s, then
## a drift down to 0.5 over drift_s.
static func curve(held_s: float, d: Dictionary) -> float:
	var tune := float(d.get("tune_s", 1.2))
	var window := float(d.get("tuned_window_s", 0.5))
	if held_s < tune:
		return clampf(held_s / tune, 0.0, 1.0)
	if held_s <= tune + window:
		return 1.0
	return lerpf(1.0, 0.5, clampf((held_s - tune - window) / float(d.get("drift_s", 1.0)), 0.0, 1.0))


## Lunges and cuts the target's part nearest the tips (or the air). True when it landed.
func strike() -> bool:
	if not ready_to_strike():
		return false
	var res := resonance
	_cool = float(def.get("cooldown_s", 0.9))
	_flash = 0.4 + res * 0.6
	combat.set("blade_strikes", int(combat.get("blade_strikes")) + 1)
	var fwd := -mech.global_transform.basis.z
	mech.apply_central_impulse(fwd * mech.mass * float(def.get("lunge_m_s", 1.2)))
	var at := tip()
	var u := target if target != null and is_instance_valid(target) and not bool(target.get("dead")) else find_target()
	resonance = 0.0
	target = null
	if u == null:
		Sfx.play("hydraulic_hiss", mech, -2.0, 0.8)
		return false
	var dir := (u.global_position - at).normalized()
	var r: Dictionary = u.call(
		"take_hit",
		{
			"point": at,
			"normal": -dir,
			"dir": dir,
			"speed": float(def.get("push_m_s", 14.0)),
			"projectile_kg": float(def.get("push_kg", 300.0)),
			"damage": float(def.get("damage", 1600.0)) * (1.0 + float(def.get("resonance_damage_x", 2.0)) * res),
			"penetration_mm": float(def.get("penetration_mm", 250.0)) + float(def.get("resonance_penetration_mm", 600.0)) * res,
			"ammo": "blade",
			"shooter": mech,
		}
	)
	var dealt := float(r.get("dealt", 0.0))
	last_strike = {"unit": u, "dealt": dealt, "resonance": res, "penetrated": bool(r.get("penetrated", false))}
	CombatFx.sparks(mech.get_parent(), at, -dir, roundi(40 + 100 * res), 12.0 + 10.0 * res, 80.0)
	Sfx.play("impact_metal", at, 2.0, 0.8 + 0.5 * res)
	if bool(mech.get("is_player")):
		Rumble.play("blade_strike")
	struck.emit(u, dealt, res)
	return true
