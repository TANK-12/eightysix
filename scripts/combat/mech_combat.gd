class_name MechCombat
extends Node3D
## A mech's combat systems, built by MechBuilder as the "Combat" child of every mech: the main gun
## (WeaponState + Projectile: ammo, reload, ballistics), recoil into the body, the wire anchors, ledge
## climbing, and per-part damage (DamageModel) with what it looks like: lost armour flung off,
## scorch marks, a limping leg, sparks and gouges under the feet in the skid.
##
## The gun is fixed to the chassis (physics supplement, point 2): a round leaves the muzzle socket
## along the body's heading (plus the parked raise, when that option is on). Recoil is a real impulse
## on the rigid body at the muzzle, scaled for game mode; in the air it is scaled much harder, so a
## shot mid-jump is the recoil dodge (supplement, point 3): it bends or reverses the arc.

signal fired(weapon: String, ammo: String)
signal reloaded(weapon: String)
signal hit_taken(key: String, dealt: float, info: Dictionary)
signal part_lost(key: String)
signal destroyed

var mech: RigidBody3D
var gun: WeaponState
var damage: DamageModel
var anchor: WireAnchor
var climb: MechClimb
var last_shot: Projectile
var shots_fired := 0
var last_recoil := Vector3.ZERO
var _c: Dictionary = {}
var _colliders: Dictionary = {}  # damage key -> [CollisionShape3D]
var _meshes: Dictionary = {}  # damage key -> [MeshInstance3D] (the visible part, hidden when lost)
var _skeleton: Skeleton3D
var _gun_bone := -1
var _gun_rest_pos := Vector3.ZERO
var _gun_back := Vector3.BACK
var _kick := 0.0
var _skid_sparks: Dictionary = {}  # leg name -> CPUParticles3D
var _skid_dust: Dictionary = {}
var _gouge_s := 0.0


func _ready() -> void:
	mech = get_parent() as RigidBody3D
	mech.set_meta("combat", self)
	_c = Registry.tune("combat", {})
	var def: Dictionary = mech.get("def")
	var loadout: Dictionary = def.get("loadout", {})
	var main_id := str(loadout.get("main_gun", ""))
	if Registry.has_entry("weapons", main_id):
		gun = WeaponState.new(main_id, Registry.entry("weapons", main_id), Settings.get_s("gameplay.ammo") == "unlimited")
	damage = DamageModel.new(def, Registry.tune("damage", {}))
	damage.part_lost.connect(_on_part_lost)
	damage.part_restored.connect(_on_part_restored)
	damage.destroyed.connect(_on_destroyed)
	_index_colliders()
	_index_meshes()
	for slot: String in loadout:
		var wid := str(loadout[slot])
		if anchor == null and Registry.has_entry("weapons", wid) and str(Registry.entry("weapons", wid).get("kind", "")) == "grapple":
			anchor = WireAnchor.new()
			anchor.name = "WireAnchor"
			anchor.setup(mech, Registry.entry("weapons", wid), _anchor_sockets(def))
			add_child(anchor)
	climb = MechClimb.new()
	climb.name = "Climb"
	add_child(climb)
	_wire_gun_kick()
	_build_skid_fx()


func _socket(name: String, fallback: Vector3) -> Vector3:
	var s: Variant = (mech.get("def") as Dictionary).get("sockets", {}).get(name)
	if s is Dictionary:
		var a: Array = (s as Dictionary)["at"]
		return Vector3(float(a[0]), float(a[1]), float(a[2]))
	return fallback


func muzzle_local() -> Vector3:
	return _socket("muzzle", Vector3(0.0, 0.85, -3.5))


func _anchor_sockets(def: Dictionary) -> Array:
	var out: Array = []
	for n: String in ["wire_anchor_L", "wire_anchor_R"]:
		if (def.get("sockets", {}) as Dictionary).has(n):
			out.append(_socket(n, Vector3.ZERO))
	return out


## Where spent cases leave: beside the receiver (the placement whose part id names one), or a
## little behind and right of the muzzle on a mech without one.
func _eject_local() -> Vector3:
	for placement: Dictionary in (mech.get("def") as Dictionary).get("parts", []):
		if str(placement["part"]).contains("receiver"):
			var a: Array = placement.get("at", [0, 0, 0])
			return Vector3(float(a[0]) + 0.6, float(a[1]) + 0.3, float(a[2]) - 0.6)
	return muzzle_local() + Vector3(0.5, 0.0, 3.0)


func _index_colliders() -> void:
	for node: Node in mech.find_children("*", "CollisionShape3D", true, false):
		if node.has_meta("damage_key"):
			var key := str(node.get_meta("damage_key"))
			if not _colliders.has(key):
				_colliders[key] = []
			(_colliders[key] as Array).append(node)


## The visible mesh of each detachable part: the real model's node named after the export part the
## collider's hulls come from ("JG2_sidepanel.L" -> "JG2_sidepanel_L"), else the placeholder box.
func _index_meshes() -> void:
	for key: String in damage.parts:
		if not damage.detachable(key):
			continue
		var part := Registry.entry("parts", str(damage.parts[key]["part"]))
		var from := str((part.get("collider", {}) if part.get("collider") is Dictionary else {}).get("hulls_from", ""))
		var found: Array = []
		if from != "":
			for node: Node in mech.find_children(from.replace(".", "_"), "MeshInstance3D", true, false):
				found.append(node)
		if found.is_empty():
			var box := mech.get_node_or_null("Mesh_" + key)
			if box is MeshInstance3D and (box as MeshInstance3D).visible:
				found.append(box)
		_meshes[key] = found


func _wire_gun_kick() -> void:
	var skels := mech.find_children("*", "Skeleton3D", true, false)
	if skels.is_empty():
		return
	_skeleton = skels[0] as Skeleton3D
	_gun_bone = _skeleton.find_bone("gun_pitch")
	if _gun_bone < 0:
		return
	_gun_rest_pos = _skeleton.get_bone_rest(_gun_bone).origin
	var parent := _skeleton.get_bone_parent(_gun_bone)
	var parent_basis := _skeleton.get_bone_global_rest(parent).basis if parent >= 0 else Basis.IDENTITY
	_gun_back = (parent_basis.inverse() * Vector3.BACK).normalized()


func _build_skid_fx() -> void:
	for leg: Dictionary in mech.get("legs"):
		var s := CPUParticles3D.new()
		var streak := BoxMesh.new()
		streak.size = Vector3(0.03, 0.3, 0.03)
		streak.material = CombatFx.spark_material()
		s.mesh = streak
		s.amount = 40
		s.lifetime = 0.45
		s.emitting = false
		s.particle_flag_align_y = true
		s.direction = Vector3.UP
		s.spread = 65.0
		s.initial_velocity_min = 4.0
		s.initial_velocity_max = 11.0
		s.gravity = Vector3(0, -14.0, 0)
		s.color = Color(1.0, 0.8, 0.45)
		s.name = "SkidSparks_" + str(leg["name"])
		add_child(s)
		_skid_sparks[leg["name"]] = s
		var d := CPUParticles3D.new()
		var quad := QuadMesh.new()
		quad.size = Vector2.ONE * 1.6
		quad.material = CombatFx.smoke_material()
		d.mesh = quad
		d.amount = 24
		d.lifetime = 1.6
		d.emitting = false
		d.direction = Vector3.UP
		d.spread = 50.0
		d.initial_velocity_min = 0.5
		d.initial_velocity_max = 2.5
		d.gravity = Vector3(0, 0.4, 0)
		var grow := Curve.new()
		grow.add_point(Vector2(0.0, 0.4))
		grow.add_point(Vector2(1.0, 1.8))
		d.scale_amount_curve = grow
		var ramp := Gradient.new()
		ramp.set_color(0, Color(0.55, 0.5, 0.43, 0.55))
		ramp.set_color(1, Color(0.55, 0.5, 0.43, 0.0))
		d.color_ramp = ramp
		d.name = "SkidDust_" + str(leg["name"])
		add_child(d)
		_skid_dust[leg["name"]] = d


# --- the gun ------------------------------------------------------------------------------------


func _physics_process(delta: float) -> void:
	if mech == null:
		return
	if gun != null and gun.tick(delta):
		reloaded.emit(gun.id)
		if mech.get("is_player"):
			Rumble.play("reload_done")
	if mech.get("is_player") and not Game.is_paused() and gun != null:
		if Controls.trigger("fire_main") > 0.5:
			fire_main()
		if Input.is_action_just_pressed("reload"):
			gun.start_reload()
		if Input.is_action_just_pressed("cycle_ammo"):
			gun.select_next_ammo()
	damage.tick(delta, Settings.get_b("gameplay.permanent_damage"))
	_limp()
	_update_skid_fx(delta)


func _process(delta: float) -> void:
	_kick = move_toward(_kick, 0.0, delta / maxf(float(_c.get("gun_kick_return_s", 0.3)), 0.01))
	if _skeleton != null and _gun_bone >= 0:
		var k := ease(_kick, 0.4)
		_skeleton.set_bone_pose_position(_gun_bone, _gun_rest_pos + _gun_back * float(_c.get("gun_kick_m", 0.35)) * k)


## The direction the fixed gun points: the chassis heading, lifted by the parked raise if it is on.
func gun_direction() -> Vector3:
	var b := mech.global_transform.basis
	var dir := -b.z
	var pitch := float(mech.get("_gun_pitch_deg")) if "_gun_pitch_deg" in mech else 0.0
	return dir.rotated(b.x, deg_to_rad(pitch)).normalized()


func fire_main() -> bool:
	if gun == null or damage.is_destroyed:
		return false
	var ammo := gun.fire()
	if ammo.is_empty():
		return false
	var xf := mech.global_transform
	var muzzle := xf * muzzle_local()
	var dir := gun_direction()
	var world := mech.get_parent()
	var scale := Settings.get_f("gameplay.player_damage") if mech.get("is_player") else 1.0
	var skip: Array[RID] = [mech.get_rid()]
	var hitboxes := mech.get_node_or_null("LegHitboxes") as CollisionObject3D
	if hitboxes != null:
		skip.append(hitboxes.get_rid())
	last_shot = Projectile.spawn(world, muzzle, dir * float(ammo.get("muzzle_m_s", 1000.0)) + mech.linear_velocity, ammo, mech, scale, skip)
	var airborne := bool(mech.get("airborne"))
	var j := float(gun.def.get("recoil_impulse_ns", 0.0))
	j *= float(_c.get("recoil_air_scale", 24.0)) if airborne else float(_c.get("recoil_game_scale", 6.0))
	if mech.call("bench_mode"):
		j = float(gun.def.get("recoil_impulse_ns", 0.0))
	last_recoil = -dir * j
	var arm := (muzzle - mech.global_position) * float(_c.get("recoil_point_share", 0.35))
	mech.apply_impulse(last_recoil, arm)
	_kick = 1.0
	CombatFx.muzzle(world, muzzle, dir)
	var eject := xf * _eject_local()
	var throw := xf.basis.x * randf_range(4.0, 6.0) + xf.basis.y * randf_range(2.5, 4.0) + xf.basis.z * randf_range(0.5, 1.5)
	CombatFx.casing(world, eject, xf.basis, mech.linear_velocity + throw)
	shots_fired += 1
	fired.emit(gun.id, str(ammo.get("id", "")))
	if mech.get("is_player"):
		Rumble.play("fire_main")
	return true


# --- taking hits --------------------------------------------------------------------------------


## A round or blast struck this mech. info: point, normal, dir, speed, projectile_kg, damage,
## penetration_mm, key (the damage key of the collider struck), shooter, splash.
func take_hit(info: Dictionary) -> Dictionary:
	var key := str(info.get("key", ""))
	var point: Vector3 = info.get("point", mech.global_position)
	if not damage.has(key):
		key = nearest_key(point)
	var dmg := float(info.get("damage", 0.0))
	if mech.get("is_player") and info.get("shooter") != mech:
		dmg *= Settings.get_f("gameplay.enemy_damage")
	var r := damage.hit(key, dmg, float(info.get("penetration_mm", 0.0)))
	if not bool(info.get("splash", false)):
		var dir: Vector3 = info.get("dir", Vector3.ZERO)
		var push := dir * float(info.get("projectile_kg", 1.0)) * float(info.get("speed", 0.0)) * float(_c.get("impact_push_scale", 4.0))
		mech.apply_impulse(push, point - mech.global_position)
		var normal: Vector3 = info.get("normal", Vector3.UP)
		var mark := CombatFx.decal(mech, point, normal, 0.9 if bool(r["penetrated"]) else 0.55)
		mark.modulate = Color(1, 1, 1, 0.95)
	if mech.get("is_player"):
		Rumble.play("hit_heavy" if float(r["dealt"]) >= 400.0 else "hit_light")
	hit_taken.emit(key, float(r["dealt"]), info)
	return r


## The damage key of the part nearest `point` (for hits that land on a collider with no key).
func nearest_key(point: Vector3) -> String:
	var best := ""
	var best_d := INF
	for key: String in _colliders:
		if not damage.has(key) or damage.is_lost(key):
			continue
		for cs: CollisionShape3D in _colliders[key]:
			var d := cs.global_position.distance_to(point)
			if d < best_d:
				best_d = d
				best = key
	return best


func _on_part_lost(key: String) -> void:
	var world := mech.get_parent()
	var at: Vector3 = mech.global_transform * (damage.parts[key]["at"] as Vector3)
	if damage.detachable(key):
		for cs: CollisionShape3D in _colliders.get(key, []):
			cs.set_deferred("disabled", true)
		for mi: MeshInstance3D in _meshes.get(key, []):
			if mi.visible and mi.is_inside_tree():
				var out := (mi.global_position - mech.global_position).normalized()
				CombatFx.fling(world, mi, mech.linear_velocity + (out + Vector3.UP * 0.8) * randf_range(5.0, 8.0), Vector3(randf(), randf(), randf()) * 9.0)
			mi.visible = false
	CombatFx.sparks(world, at, Vector3.UP, 30, 12.0, 80.0)
	CombatFx.smoke(world, at, Vector3.UP, 16, 1.6, Color(0.14, 0.13, 0.12, 0.75), 3.0, 3.0)
	part_lost.emit(key)


func _on_part_restored(key: String) -> void:
	for cs: CollisionShape3D in _colliders.get(key, []):
		cs.set_deferred("disabled", false)
	for mi: MeshInstance3D in _meshes.get(key, []):
		mi.visible = true


func _on_destroyed() -> void:
	var world := mech.get_parent()
	CombatFx.impact(world, mech.global_position, Vector3.UP, true, true)
	CombatFx.smoke(world, mech.global_position, Vector3.UP, 30, 3.0, Color(0.08, 0.08, 0.08, 0.8), 5.0, 4.0)
	destroyed.emit()


## A hurt leg limps: its corner sags (a downward force at the hip, a share of the weight that leg
## carries) and the drive's top speeds fall towards limp_speed_min as the worst leg weakens.
func _limp() -> void:
	var d: Dictionary = Registry.tune("damage", {})
	var legs: Array = mech.get("legs")
	var worst := 1.0
	var xf := mech.global_transform
	var share := mech.mass * 9.81 / maxf(legs.size(), 1)
	for leg: Dictionary in legs:
		var h := damage.leg_health(str(leg["name"]))
		worst = minf(worst, h)
		if h < 1.0 and bool(leg.get("loaded", false)):
			var hip := xf.basis * (leg["hip"] as Vector3)
			mech.apply_force(Vector3.DOWN * share * float(d.get("limp_sag_share", 0.35)) * (1.0 - h), hip)
	if "speed_scale" in mech:
		mech.set("speed_scale", lerpf(float(d.get("limp_speed_min", 0.45)), 1.0, worst))


func limp_factor() -> float:
	var worst := 1.0
	for leg: Dictionary in mech.get("legs"):
		worst = minf(worst, damage.leg_health(str(leg["name"])))
	return worst


# --- the skid, made loud: sparks and dust from the feet, gouges in the ground --------------------


func _update_skid_fx(delta: float) -> void:
	var skid := bool(mech.get("skidding")) and mech.linear_velocity.length() > 2.0
	_gouge_s -= delta
	var gouge := skid and _gouge_s <= 0.0
	if gouge:
		_gouge_s = float(_c.get("gouge_every_s", 0.12))
	for leg: Dictionary in mech.get("legs"):
		var on := skid and bool(leg.get("sole_contact", false))
		var foot: Vector3 = leg.get("foot", mech.global_position)
		var s: CPUParticles3D = _skid_sparks.get(leg["name"])
		var d: CPUParticles3D = _skid_dust.get(leg["name"])
		if s == null:
			continue
		s.global_position = foot + Vector3.UP * 0.1
		d.global_position = foot + Vector3.UP * 0.3
		s.emitting = on
		d.emitting = on
		if on and gouge:
			var n: Vector3 = leg.get("sole_normal", Vector3.UP)
			CombatFx.decal(mech.get_parent(), foot, n, 0.7, true, mech.linear_velocity)
