class_name MechCombat
extends Node3D
## A mech's combat systems, built by MechBuilder as the "Combat" child of every mech: the main gun
## (WeaponState + Projectile: ammo, reload, ballistics), recoil into the body, the wire anchors, ledge
## climbing, and per-part damage (DamageModel) with what it looks like: lost armour flung off,
## scorch marks, a limping leg, sparks and gouges under the feet in the skid.
##
## The gun is fixed to the chassis (physics supplement, point 2): a round leaves the muzzle socket
## along the body's heading (plus the parked raise, when that option is on). Recoil is the real
## impulse (projectile plus propellant gas, Ballistics.recoil_impulse), unscaled, applied along the
## bore line: about 1 m/s on the 5.4 t Juggernaut. On the ground the feet's grip takes most of it and
## the body rocks back; in a slide or in the air the whole of it goes into motion, so a shot mid-jump
## or mid-slide is the recoil dodge (supplement, point 3). Each round fired leaves the mech lighter.

signal fired(weapon: String, ammo: String)
signal reloaded(weapon: String)
signal hit_taken(key: String, dealt: float, info: Dictionary)
signal part_lost(key: String)
signal destroyed

var mech: RigidBody3D
var gun: WeaponState
## The sub-arm machine guns (loadout "sub_guns", lane A3 part 5): one ammo state for the pair.
var sub_guns: WeaponState
var sub_shots := 0
var last_sub_recoil := Vector3.ZERO
var damage: DamageModel
var anchor: WireAnchor
var climb: MechClimb
var last_shot: Projectile
var shots_fired := 0
var last_recoil := Vector3.ZERO
var _c: Dictionary = {}
var _colliders: Dictionary = {}  # damage key -> [CollisionShape3D]
var _meshes: Dictionary = {}  # damage key -> [MeshInstance3D] (the visible part, hidden when lost)
var _skid_sparks: Dictionary = {}  # leg name -> CPUParticles3D
var _skid_live_s: Dictionary = {}  # leg name -> seconds its skid particles stay alive after stopping
var _gouge_s := 0.0
var _sub_side := 0  # which arm fires next: 0 left, 1 right
var _sub_dir: Array[Vector3] = [Vector3.FORWARD, Vector3.FORWARD]  # each arm's aim, body frame


func _ready() -> void:
	mech = get_parent() as RigidBody3D
	mech.set_meta("combat", self)
	_c = Registry.tune("combat", {})
	var def: Dictionary = mech.get("def")
	var loadout: Dictionary = def.get("loadout", {})
	var main_id := str(loadout.get("main_gun", ""))
	if Registry.has_entry("weapons", main_id):
		gun = WeaponState.new(main_id, Registry.entry("weapons", main_id), Settings.get_s("gameplay.ammo") == "unlimited")
	var sub_id := str(loadout.get("sub_guns", ""))
	if Registry.has_entry("weapons", sub_id):
		sub_guns = WeaponState.new(sub_id, Registry.entry("weapons", sub_id), Settings.get_s("gameplay.ammo") == "unlimited")
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
	_build_skid_fx()
	_tag_mech_layer.call_deferred()


## Puts every mesh of the mech (the skinned model loads in setup, so after the tree settles) on
## CombatFx.MECH_LAYER only.
func _tag_mech_layer() -> void:
	for node: Node in mech.find_children("*", "GeometryInstance3D", true, false):
		if node is Decal or node.get_parent() == self:
			continue
		(node as VisualInstance3D).layers = CombatFx.MECH_LAYER


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
		s.visible = false
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


# --- the gun ------------------------------------------------------------------------------------


func _physics_process(delta: float) -> void:
	if mech == null:
		return
	if gun != null and gun.tick(delta):
		reloaded.emit(gun.id)
		if mech.get("is_player"):
			Rumble.play("reload_done")
	if sub_guns != null:
		if sub_guns.tick(delta):
			reloaded.emit(sub_guns.id)
		_slew_sub_arms(delta)
		if mech.get("is_player") and not Game.is_paused() and Controls.trigger("fire_sub") > 0.5:
			fire_sub()
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


## The direction the fixed gun points: the chassis heading, lifted by the parked raise if it is on.
func gun_direction() -> Vector3:
	var b := mech.global_transform.basis
	var dir := -b.z
	var pitch := float(mech.get("_gun_pitch_deg")) if "_gun_pitch_deg" in mech else 0.0
	return dir.rotated(b.x, deg_to_rad(pitch)).normalized()


## Where a round fired now would land: its flight (drop and drag of the loaded round) from the
## muzzle along `dir`, cast in 0.1 s legs, out to `max_m`. {point, range_m, hit} (hit false: it flies
## past max_m, point is where it is then).
func impact(muzzle: Vector3, dir: Vector3, ammo: Dictionary, max_m: float = 2500.0) -> Dictionary:
	var space := mech.get_world_3d().direct_space_state
	var pos := muzzle
	var vel := dir * float(ammo.get("muzzle_m_s", 1000.0))
	var drag := float(ammo.get("drag_per_s", 0.0))
	var skip: Array[RID] = [mech.get_rid()]
	var hitboxes := mech.get_node_or_null("LegHitboxes") as CollisionObject3D
	if hitboxes != null:
		skip.append(hitboxes.get_rid())
	for i in 40:
		var s := Ballistics.step(pos, vel, 0.1, 9.81, drag)
		var q := PhysicsRayQueryParameters3D.create(pos, s[0], 1 | 2)
		q.exclude = skip
		var hit := space.intersect_ray(q)
		if not hit.is_empty():
			return {"point": hit["position"], "range_m": muzzle.distance_to(hit["position"]), "hit": true}
		pos = s[0]
		vel = s[1]
		if muzzle.distance_to(pos) > max_m:
			break
	return {"point": pos, "range_m": muzzle.distance_to(pos), "hit": false}


## The 57 mm's impact point now (the HUD's main gun mark).
func main_impact() -> Dictionary:
	if gun == null:
		return {}
	var ammo: Dictionary = (gun.def.get("ammo", {}) as Dictionary).get(gun.loaded_ammo, {})
	return impact(mech.global_transform * muzzle_local(), gun_direction(), ammo)


## The sub-arm guns' impact point (between the two arms' lines), for their small mark.
func sub_impact() -> Dictionary:
	if sub_guns == null:
		return {}
	var ammo: Dictionary = (sub_guns.def.get("ammo", {}) as Dictionary).get(sub_guns.loaded_ammo, {})
	var xf := mech.global_transform
	var from := (xf * sub_muzzle_local(0) + xf * sub_muzzle_local(1)) * 0.5
	return impact(from, (sub_direction(0) + sub_direction(1)).normalized(), ammo, float(sub_guns.def.get("range_m", 1500.0)))


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
	last_recoil = -dir * Ballistics.recoil_impulse(gun.def, ammo)
	# Along the bore line (any point on it gives the same torque about the centre of mass): the bore
	# sits about a metre above the centre of mass, so the body rocks back on its rear legs. The gun is
	# bolted solid to the frame, no recoil buffer and no barrel slide (Emerson 2026-10-01: "it should
	# just be straight into the frame and body"), so the whole kick lands in the body in one tick.
	mech.apply_impulse(last_recoil, muzzle - mech.global_position)
	if not gun.unlimited:
		mech.mass = maxf(mech.mass - float(gun.def.get("round_kg", 0.0)), 1.0)
	CombatFx.muzzle(world, muzzle, dir)
	var eject := xf * _eject_local()
	var throw := xf.basis.x * randf_range(4.0, 6.0) + xf.basis.y * randf_range(2.5, 4.0) + xf.basis.z * randf_range(0.5, 1.5)
	CombatFx.casing(world, eject, xf.basis, mech.linear_velocity + throw)
	shots_fired += 1
	fired.emit(gun.id, str(ammo.get("id", "")))
	if mech.get("is_player"):
		Rumble.play("fire_main")
	return true


# --- sub-arm machine guns -------------------------------------------------------------------------


## Where each sub-arm gun's muzzle is: the sub-arm socket plus the barrel ahead of it.
func sub_muzzle_local(side: int) -> Vector3:
	var fallback := Vector3(-0.4 if side == 0 else 0.4, -0.1, -1.7)
	return _socket("subarm_L" if side == 0 else "subarm_R", fallback) + Vector3(0.0, 0.0, -float(_c.get("sub_barrel_m", 0.6)))


## Where the sub-arm guns point (setting gameplay.sub_guns_aim, part 4 from Emerson's notes after 010):
## "fixed" straight ahead on the body like the 57 mm (his original ask, the default); "play" each mount
## swings up to combat.sub_play_deg toward the crosshair (the wire anchor's aim point); "arms" the
## sub-arms swing the guns onto it inside their reach. No faster than combat.sub_arm_slew_deg_s.
## Only the 12.7 mm guns ever move: the 57 mm is fixed to the body.
func _slew_sub_arms(delta: float) -> void:
	var xf := mech.global_transform
	var step := deg_to_rad(float(_c.get("sub_arm_slew_deg_s", 120.0))) * delta
	var mode := Settings.get_s("gameplay.sub_guns_aim")
	for side in 2:
		var from := xf * sub_muzzle_local(side)
		var want := -xf.basis.z
		if anchor != null and mode != "fixed":
			var aim := (anchor.aim_point(from, float(sub_guns.def.get("range_m", 1500.0))) - from).normalized()
			if mode == "arms":
				want = anchor.arm_limit(aim, xf.basis)
			else:
				var play := deg_to_rad(float(_c.get("sub_play_deg", 4.0)))
				var off := want.angle_to(aim)
				want = aim if off <= play else want.slerp(aim, play / off).normalized()
		var local := (xf.basis.inverse() * want).normalized()
		var have := _sub_dir[side]
		var angle := have.angle_to(local)
		_sub_dir[side] = local if angle <= step else have.slerp(local, step / angle).normalized()


## The world direction sub-arm `side` points now.
func sub_direction(side: int) -> Vector3:
	return (mech.global_transform.basis * _sub_dir[side]).normalized()


## One round from the next arm in turn. Recoil at its muzzle is the real projectile + gas impulse
## (0.045 kg + 0.015 kg of propellant at 890 m/s: 60 N s); the round's mass leaves the mech.
func fire_sub() -> bool:
	if sub_guns == null or damage.is_destroyed:
		return false
	var ammo := sub_guns.fire()
	if ammo.is_empty():
		return false
	var side := _sub_side
	_sub_side = 1 - _sub_side
	var muzzle := mech.global_transform * sub_muzzle_local(side)
	var dir := sub_direction(side)
	var skip: Array[RID] = [mech.get_rid()]
	var hitboxes := mech.get_node_or_null("LegHitboxes") as CollisionObject3D
	if hitboxes != null:
		skip.append(hitboxes.get_rid())
	var scale := Settings.get_f("gameplay.player_damage") if mech.get("is_player") else 1.0
	Projectile.spawn(mech.get_parent(), muzzle, dir * float(ammo.get("muzzle_m_s", 890.0)) + mech.linear_velocity, ammo, mech, scale, skip)
	last_sub_recoil = -dir * Ballistics.recoil_impulse(sub_guns.def, ammo)
	mech.apply_impulse(last_sub_recoil, muzzle - mech.global_position)
	if not sub_guns.unlimited:
		mech.mass = maxf(mech.mass - float(sub_guns.def.get("round_kg", 0.0)), 1.0)
	CombatFx.muzzle(mech.get_parent(), muzzle, dir, 0.35)
	sub_shots += 1
	fired.emit(sub_guns.id, str(ammo.get("id", "")))
	if mech.get("is_player"):
		Rumble.play("fire_sub")
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
		var push := dir * float(info.get("projectile_kg", 1.0)) * float(info.get("speed", 0.0)) * float(_c.get("impact_push_scale", 1.0))
		mech.apply_impulse(push, point - mech.global_position)
		var normal: Vector3 = info.get("normal", Vector3.UP)
		var mark := CombatFx.decal(mech, point, normal, 0.9 if bool(r["penetrated"]) else 0.55)
		mark.modulate = Color(1, 1, 1, 0.95)
		mark.cull_mask = CombatFx.MECH_LAYER
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
		if s == null:
			continue
		s.global_position = foot + Vector3.UP * 0.1
		if s.emitting != on:  # assigning it every frame restarts the emitter
			s.emitting = on
		# Shown only while emitting and for one lifetime after, until the last spark fades.
		var live := float(_skid_live_s.get(leg["name"], 0.0))
		live = s.lifetime if on else maxf(live - delta, 0.0)
		_skid_live_s[leg["name"]] = live
		s.visible = on or live > 0.0
		if on and gouge:
			var n: Vector3 = leg.get("sole_normal", Vector3.UP)
			# Dust as one-shot puffs on the gouge beat (a looping emitter here drew black balls).
			CombatFx.smoke(mech.get_parent(), foot + Vector3.UP * 0.3, Vector3.UP, 3, 1.5, Color(0.6, 0.55, 0.47, 0.35), 1.4, 2.2)
			CombatFx.decal(mech.get_parent(), foot, n, 0.7, true, mech.linear_velocity)
