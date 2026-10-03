class_name Projectile
extends Node3D
## A round in flight: Ballistics steps it each physics tick and a ray covers the segment it moved,
## so it hits whatever lies on its path (world, mech chassis parts, leg hitboxes). On a hit it hands
## the struck part to the receiver's take_hit(), pushes loose rigid bodies with its momentum, sets
## off splash damage for blast rounds, pushes what is near an explosive burst (Blast, from the
## round's "tnt_kg"), and leaves impact effects. A glowing tracer shows the path.

signal impacted(info: Dictionary)
## A grazing round glanced off the ground and flies on (version 015, Emerson's note 7 after 012).
signal skipped(info: Dictionary)

const MASK := 1 | 2 | 4

var velocity := Vector3.ZERO
var ammo: Dictionary = {}
var shooter: Node = null
var damage_scale := 1.0
var exclude: Array[RID] = []
var life_s := 4.0
var gravity := 9.81
var push_scale := 4.0
var traveled_m := 0.0
var skips := 0
var cracked_pa := 0.0  # the N-wave peak the player's mech felt when this round passed it (0: never)
var _trace_from_m := 0.0  # where along its flight the tracer starts: the muzzle, or the last skip
var _tracers: Array = []  # [MeshInstance3D, length, behind] per streak, grown from the muzzle by _grow_tracers()
static var _tracer_meshes := {}  # Vector3(length, width, glow) -> BoxMesh, shared by every round of that look


static func spawn(world: Node, from: Vector3, vel: Vector3, round_def: Dictionary, owner_node: Node, scale: float, skip: Array[RID]) -> Projectile:
	var p := Projectile.new()
	p.velocity = vel
	p.ammo = round_def
	p.shooter = owner_node
	p.damage_scale = scale
	p.exclude = skip
	var c: Dictionary = Registry.tune("combat", {})
	p.life_s = float(c.get("projectile_life_s", 4.0))
	p.push_scale = float(c.get("impact_push_scale", 1.0))
	p.gravity = Registry.tune_f("physics.gravity_m_s2", 9.81)
	p.name = "Round"
	world.add_child(p)
	p.global_position = from
	var length := float(round_def.get("tracer_len_m", c.get("tracer_len_m", 9.0)))
	var width := float(round_def.get("tracer_w_m", 0.07))
	# Settings > Shell tracers (Emerson's note 6 after 012): shells (1 kg and up) can be bright with a trail, or off.
	var style := Settings.get_s("fx.shell_tracer") if float(round_def.get("projectile_kg", 0.0)) >= 1.0 else "normal"
	if style == "bright":
		p._build_tracer(length * 1.5, width * 3.0, 2.0)
		p._build_tracer(length * 5.0, width * 1.5, 0.6, length * 1.5)
	elif style != "off":
		p._build_tracer(length, width)
	p._face()
	p._grow_tracers()
	return p


## A glowing box behind the round, `length` long, starting `behind` metres back; `glow` scales its emission.
func _build_tracer(length: float, width: float = 0.07, glow: float = 1.0, behind: float = 0.0) -> void:
	var tracer := MeshInstance3D.new()
	var key := Vector3(length, width, glow)
	if not _tracer_meshes.has(key):
		var box := BoxMesh.new()
		box.size = Vector3(width, width, length)
		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.albedo_color = Color(1.0, 0.62, 0.3)
		mat.emission_enabled = true
		mat.emission = Color(1.0, 0.5, 0.2)
		mat.emission_energy_multiplier = 8.0 * glow
		if glow < 1.0:
			# the trail: a faint see-through streak behind the bright head
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			mat.albedo_color.a = 0.35
		box.material = mat
		_tracer_meshes[key] = box
	tracer.mesh = _tracer_meshes[key]
	tracer.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(tracer)
	_tracers.append([tracer, length, behind])


## A streak only covers the path the round has really flown: drawn at full length from the first
## frame, it stuck out behind the muzzle through and behind the mech (Emerson after 014: "I can see
## the start behind the mech", the shells' light out the back). Each streak grows from the muzzle
## until it reaches its length.
func _grow_tracers() -> void:
	for t: Array in _tracers:
		var mi := t[0] as MeshInstance3D
		var length := float(t[1])
		var behind := float(t[2])
		var shown := clampf(traveled_m - _trace_from_m - behind, 0.0, length)
		mi.visible = shown > 0.01
		mi.scale = Vector3(1.0, 1.0, maxf(shown / length, 0.001))
		mi.position = Vector3(0, 0, behind + shown * 0.5)


func _face() -> void:
	if velocity.length() > 0.01:
		var up := Vector3.UP if absf(velocity.normalized().y) < 0.99 else Vector3.RIGHT
		look_at(global_position + velocity, up)


func _physics_process(delta: float) -> void:
	life_s -= delta
	if life_s <= 0.0:
		queue_free()
		return
	var s := Ballistics.step(global_position, velocity, delta, gravity, float(ammo.get("drag_per_s", 0.0)))
	var to: Vector3 = s[0]
	var q := PhysicsRayQueryParameters3D.create(global_position, to, MASK, exclude)
	q.collide_with_areas = true
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	_near_miss(global_position, to if hit.is_empty() else (hit["position"] as Vector3))
	if not hit.is_empty():
		if not _skip(hit):
			_impact(hit)
		return
	traveled_m += global_position.distance_to(to)
	global_position = to
	velocity = s[1]
	_face()
	_grow_tracers()


## The velocity a round leaves the ground with after striking it at `vel` (ground normal `normal`), or
## Vector3.ZERO when it does not skip: its grazing angle is over the ammo's ricochet.max_deg x the
## ground's hardness, or it would leave slower than min_exit_m_s. Into the ground the speed comes back
## x restitution; friction takes friction x (1 + restitution) x that speed off the speed along the
## ground (an impulse model, so the round only ever loses energy).
static func skip_velocity(vel: Vector3, normal: Vector3, rule: Dictionary, ground: Dictionary) -> Vector3:
	var speed := vel.length()
	var into := -vel.dot(normal)
	if rule.is_empty() or ground.is_empty() or speed < 0.001 or into <= 0.0:
		return Vector3.ZERO
	var graze := rad_to_deg(asin(clampf(into / speed, 0.0, 1.0)))
	if graze > float(rule.get("max_deg", 0.0)) * float(ground.get("hardness", 0.0)):
		return Vector3.ZERO
	var e := float(ground.get("restitution", 0.0))
	var along := vel + normal * into
	var along_speed := maxf(along.length() - float(ground.get("friction", 0.0)) * (1.0 + e) * into, 0.0)
	var out := (along.normalized() * along_speed if along.length() > 0.001 else Vector3.ZERO) + normal * into * e
	return out if out.length() >= float(rule.get("min_exit_m_s", 0.0)) else Vector3.ZERO


## A grazing round on the ground (not a mech, not a loose body) glances off and flies on, with a puff
## and a gouge where it struck. False when it does not skip (the caller then makes the impact).
func _skip(hit: Dictionary) -> bool:
	var rule: Dictionary = ammo.get("ricochet", {})
	var collider: Object = hit["collider"]
	if rule.is_empty() or skips >= int(rule.get("max_skips", 1)) or CombatHits.receiver(collider) != null or collider is RigidBody3D:
		return false
	var normal: Vector3 = hit["normal"]
	var grounds: Dictionary = Registry.tune("combat.grounds", {})
	var out := skip_velocity(velocity, normal, rule, grounds.get(Sfx.surface_of(collider), {}))
	if out == Vector3.ZERO:
		return false
	var point: Vector3 = hit["position"]
	traveled_m += global_position.distance_to(point)
	var info := {"point": point, "normal": normal, "dir": velocity.normalized(), "speed": velocity.length(), "exit_speed": out.length(), "ammo": str(ammo.get("id", "")), "projectile_kg": float(ammo.get("projectile_kg", 1.0)), "collider": collider, "skip": true}
	var world := get_parent()
	var shell := float(info["projectile_kg"]) >= 1.0
	CombatFx.impact(world, point, normal, false, false, shell)
	CombatFx.decal(world, point, normal, 0.8 if shell else 0.3)
	skips += 1
	global_position = point + normal * 0.05
	velocity = out
	_trace_from_m = traveled_m
	_face()
	_grow_tracers()
	skipped.emit(info)
	return true


## Version 015 (Emerson's note 7 after 012): a supersonic round that is not the player's own passing
## within near_miss.within_m of his mech cracks: the N-wave's peak sets the crack's loudness, the camera
## shake and the rumble. Its push is worked out and applied only if it is big enough to matter, which a
## passing round never is (Blast.nwave_push_pa_s; tuning combat.near_miss).
func _near_miss(a: Vector3, b: Vector3) -> void:
	if cracked_pa > 0.0 or not is_inside_tree():
		return
	var mach := velocity.length() / 343.0
	if mach <= 1.0:
		return
	var player := get_tree().get_first_node_in_group("player_mech") as RigidBody3D
	if player == null or player == shooter:
		return
	var nm: Dictionary = Registry.tune("combat.near_miss", {})
	var c := player.global_transform * player.center_of_mass
	var closest := Geometry3D.get_closest_point_to_segment(c, a, b)
	var x := closest.distance_to(c)
	if x > float(nm.get("within_m", 8.0)) or closest.is_equal_approx(b):
		return
	var d := float(ammo.get("diameter_m", 0.0))
	var l := float(ammo.get("length_m", 0.0))
	cracked_pa = Blast.nwave_pa(mach, d, l, x)
	if cracked_pa <= 0.0:
		return
	var level := clampf(cracked_pa / float(nm.get("shake_ref_pa", 2000.0)), 0.0, 1.0)
	var cam := get_viewport().get_camera_3d()
	if cam != null and cam.has_method("add_shake"):
		cam.call("add_shake", float(nm.get("shake_max", 0.6)) * maxf(level, 0.1))
	Sfx.play("near_miss_crack", closest, linear_to_db(clampf(level * 2.0, 0.3, 1.5)))
	Rumble.play("wake_near_miss", -1, clampf(level * 1.5, 0.2, 1.5))
	var push_ns := Blast.nwave_push_pa_s(mach, d, l, x) * float(nm.get("side_area_m2", 22.0))
	if push_ns > float(nm.get("push_floor_ns", 50.0)):
		player.apply_central_impulse((c - closest).normalized() * push_ns)


func _impact(hit: Dictionary) -> void:
	var point: Vector3 = hit["position"]
	var normal: Vector3 = hit["normal"]
	var collider: Object = hit["collider"]
	var speed := velocity.length()
	var dir := velocity / maxf(speed, 0.001)
	traveled_m += global_position.distance_to(point)
	var key := CombatHits.key_of(collider, int(hit["shape"]))
	var target := CombatHits.receiver(collider)
	var blast_r := float(ammo.get("blast_radius_m", 0.0))
	var info := {
		"point": point,
		"normal": normal,
		"dir": dir,
		"speed": speed,
		"ammo": str(ammo.get("id", "")),
		"projectile_kg": float(ammo.get("projectile_kg", 1.0)),
		"damage": float(ammo.get("damage", 0.0)) * damage_scale,
		"penetration_mm": float(ammo.get("penetration_mm", 0.0)),
		"blast_damage": float(ammo.get("damage", 0.0)) * damage_scale * 0.6,
		"key": key,
		"shooter": shooter,
		"collider": collider,
		"range_m": traveled_m,
	}
	if target != null:
		target.call("take_hit", info)
	elif collider is RigidBody3D:
		var body := collider as RigidBody3D
		body.apply_impulse(dir * info["projectile_kg"] * speed * push_scale, point - body.global_position)
	if blast_r > 0.0:
		CombatHits.blast(get_world_3d().direct_space_state, point, blast_r, info, key)
	var tnt := float(ammo.get("tnt_kg", 0.0))
	if tnt > 0.0:
		info["pushed"] = Blast.push(get_world_3d().direct_space_state, point + normal * 0.2, tnt, true)
		for p: Dictionary in info["pushed"]:
			if (p["body"] as Node).is_in_group("player_mech"):
				Rumble.play("wake_near_miss", -1, clampf(float(p["impulse_ns"]) / 2000.0, 0.2, 1.5))
	var world := get_parent()
	var metal := target != null or (collider is Node and (collider as Node).is_in_group("mechs"))
	CombatFx.impact(world, point, normal, metal, blast_r > 0.0, float(info["projectile_kg"]) >= 1.0)
	if not metal:
		var shell := blast_r > 0.0 or float(info["projectile_kg"]) >= 1.0
		CombatFx.decal(world, point, normal, (1.6 + blast_r * 0.5) * (sqrt(CombatFx.blast_size()) if blast_r > 0.0 else 1.0) if shell else 0.4)
	impacted.emit(info)
	queue_free()
