class_name Projectile
extends Node3D
## A round in flight: Ballistics steps it each physics tick and a ray covers the segment it moved,
## so it hits whatever lies on its path (world, mech chassis parts, leg hitboxes). On a hit it hands
## the struck part to the receiver's take_hit(), pushes loose rigid bodies with its momentum, sets
## off splash damage for blast rounds, pushes what is near an explosive burst (Blast, from the
## round's "tnt_kg"), and leaves impact effects. A glowing tracer shows the path.

signal impacted(info: Dictionary)

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
var _tracer: MeshInstance3D
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
	return p


## A glowing box behind the round, `length` long, starting `behind` metres back; `glow` scales its emission.
func _build_tracer(length: float, width: float = 0.07, glow: float = 1.0, behind: float = 0.0) -> void:
	_tracer = MeshInstance3D.new()
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
	_tracer.mesh = _tracer_meshes[key]
	_tracer.position = Vector3(0, 0, behind + length * 0.5)
	_tracer.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_tracer)


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
	if not hit.is_empty():
		_impact(hit)
		return
	traveled_m += global_position.distance_to(to)
	global_position = to
	velocity = s[1]
	_face()


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
