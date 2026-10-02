class_name CombatFx
extends RefCounted
## The look of combat: muzzle blast, tracers, impact sparks and dust, scorch and gouge decals, spent
## casings and flung armour. Everything here is fire-and-forget (it frees itself) and cheap enough for
## the Low preset: CPU particles with small counts, one short-lived light per event.

const MAX_DECALS := 64
const MAX_CASINGS := 24
const MAX_DEBRIS := 16
## Render layer 20 holds every mech's meshes: ground decals skip it (so a gouge never paints the feet
## standing in it) and hull scorch marks use only it.
const MECH_LAYER := 1 << 19
## The parts of a Juggernaut that the pilot's own first-person view leaves out (its hull, legs and canopy: see
## MechCombat._tag_mech_layer) sit on this layer instead of MECH_LAYER, and the cockpit camera's mask skips it.
const COCKPIT_SHELL_LAYER := 1 << 9
## Every layer a mech's meshes can be on: what hull scorch marks use, and ground decals leave alone.
const MECH_LAYERS := MECH_LAYER | COCKPIT_SHELL_LAYER

static var _decals: Array = []
static var _casings: Array = []
static var _debris: Array = []
static var _scorch_tex: Texture2D
static var _gouge_tex: Texture2D
static var _smoke_mat: StandardMaterial3D
static var _spark_mat: StandardMaterial3D
static var _brass_mat: StandardMaterial3D
static var _fire_mat: StandardMaterial3D
static var _clod_mat: StandardMaterial3D


## Settings > Graphics > World detail > Combat effects (Emerson, 2026-10-02). Both are look only: a blast's
## damage and push come from the ammo data, never from these.
static func blast_size() -> float:
	return maxf(Settings.get_f("fx.blast_size"), 0.1)


static func hit_dust() -> float:
	return maxf(Settings.get_f("fx.hit_dust"), 0.1)


## How much longer dust hangs about at a given hit_dust (2x dust lasts 1.6x as long).
static func dust_linger(dust: float) -> float:
	return maxf(1.0 + (dust - 1.0) * 0.6, 0.4)


static func _free_after(node: Node, seconds: float) -> void:
	if node.is_inside_tree():
		node.get_tree().create_timer(seconds, false).timeout.connect(node.queue_free)


static func spark_material() -> StandardMaterial3D:
	if _spark_mat == null:
		_spark_mat = StandardMaterial3D.new()
		_spark_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		_spark_mat.albedo_color = Color(1.0, 0.72, 0.32)
		_spark_mat.emission_enabled = true
		_spark_mat.emission = Color(1.0, 0.55, 0.18)
		_spark_mat.emission_energy_multiplier = 6.0
		_spark_mat.vertex_color_use_as_albedo = true
	return _spark_mat


static func smoke_material() -> StandardMaterial3D:
	if _smoke_mat == null:
		_smoke_mat = StandardMaterial3D.new()
		_smoke_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_smoke_mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
		_smoke_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		_smoke_mat.vertex_color_use_as_albedo = true
		_smoke_mat.albedo_texture = _radial(64, Color(1, 1, 1, 1), Color(1, 1, 1, 0))
		_smoke_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
		_smoke_mat.roughness = 1.0
		# Smoke is a volume, not a surface: no shadow maps on it.
		_smoke_mat.disable_receive_shadows = true
	return _smoke_mat


static func _radial(size: int, inner: Color, outer: Color) -> GradientTexture2D:
	var g := Gradient.new()
	g.set_color(0, inner)
	g.set_color(1, outer)
	var tex := GradientTexture2D.new()
	tex.gradient = g
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(1.0, 0.5)
	tex.width = size
	tex.height = size
	return tex


static func scorch_texture() -> Texture2D:
	if _scorch_tex == null:
		var g := Gradient.new()
		g.offsets = PackedFloat32Array([0.0, 0.35, 0.7, 1.0])
		g.colors = PackedColorArray([Color(0.02, 0.02, 0.02, 0.95), Color(0.06, 0.05, 0.04, 0.85), Color(0.12, 0.1, 0.08, 0.4), Color(0.2, 0.18, 0.15, 0.0)])
		var tex := GradientTexture2D.new()
		tex.gradient = g
		tex.fill = GradientTexture2D.FILL_RADIAL
		tex.fill_from = Vector2(0.5, 0.5)
		tex.fill_to = Vector2(1.0, 0.5)
		tex.width = 128
		tex.height = 128
		_scorch_tex = tex
	return _scorch_tex


static func gouge_texture() -> Texture2D:
	if _gouge_tex == null:
		var g := Gradient.new()
		g.offsets = PackedFloat32Array([0.0, 0.5, 1.0])
		g.colors = PackedColorArray([Color(0.08, 0.07, 0.06, 0.0), Color(0.08, 0.07, 0.06, 0.8), Color(0.08, 0.07, 0.06, 0.0)])
		var tex := GradientTexture2D.new()
		tex.gradient = g
		tex.fill_from = Vector2(0.0, 0.5)
		tex.fill_to = Vector2(1.0, 0.5)
		tex.width = 64
		tex.height = 16
		_gouge_tex = tex
	return _gouge_tex


static func fire_material() -> StandardMaterial3D:
	if _fire_mat == null:
		_fire_mat = StandardMaterial3D.new()
		_fire_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		_fire_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_fire_mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		_fire_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		_fire_mat.vertex_color_use_as_albedo = true
		_fire_mat.albedo_texture = _radial(64, Color(1, 1, 1, 1), Color(1, 1, 1, 0))
		_fire_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	return _fire_mat


static func clod_material() -> StandardMaterial3D:
	if _clod_mat == null:
		_clod_mat = StandardMaterial3D.new()
		_clod_mat.albedo_color = Color(0.22, 0.18, 0.14)
		_clod_mat.roughness = 1.0
	return _clod_mat


static func brass_material() -> StandardMaterial3D:
	if _brass_mat == null:
		_brass_mat = StandardMaterial3D.new()
		_brass_mat.albedo_color = Color(0.78, 0.6, 0.3)
		_brass_mat.metallic = 1.0
		_brass_mat.roughness = 0.32
	return _brass_mat


## A burst of hot streaks (align to velocity, fall under gravity).
static func sparks(parent: Node, pos: Vector3, dir: Vector3, amount: int, speed: float, spread_deg: float = 55.0) -> CPUParticles3D:
	var p := CPUParticles3D.new()
	var streak := BoxMesh.new()
	streak.size = Vector3(0.025, 0.28, 0.025)
	streak.material = spark_material()
	p.mesh = streak
	p.amount = maxi(amount, 1)
	p.lifetime = 0.55
	p.one_shot = true
	p.explosiveness = 0.95
	p.particle_flag_align_y = true
	p.direction = Vector3.UP
	p.spread = spread_deg
	p.initial_velocity_min = speed * 0.4
	p.initial_velocity_max = speed
	p.gravity = Vector3(0, -14.0, 0)
	p.scale_amount_min = 0.5
	p.scale_amount_max = 1.2
	p.color = Color(1.0, 0.8, 0.45)
	parent.add_child(p)
	p.global_position = pos
	_orient_up(p, dir)
	p.emitting = true
	_free_after(p, 1.2)
	return p


## Billowing smoke or dust: grows and fades.
static func smoke(parent: Node, pos: Vector3, dir: Vector3, amount: int, size: float, color: Color, life: float = 1.8, speed: float = 2.0) -> CPUParticles3D:
	var p := CPUParticles3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * size
	quad.material = smoke_material()
	p.mesh = quad
	p.amount = maxi(amount, 1)
	p.lifetime = life
	p.one_shot = true
	p.explosiveness = 0.85
	p.direction = Vector3.UP
	p.spread = 40.0
	p.initial_velocity_min = speed * 0.3
	p.initial_velocity_max = speed
	p.damping_min = 1.5
	p.damping_max = 3.0
	p.gravity = Vector3(0, 0.6, 0)
	var grow := Curve.new()
	grow.add_point(Vector2(0.0, 0.35))
	grow.add_point(Vector2(1.0, 1.6))
	p.scale_amount_curve = grow
	var ramp := Gradient.new()
	ramp.set_color(0, color)
	ramp.set_color(1, Color(color, 0.0))
	p.color_ramp = ramp
	p.angle_min = 0.0
	p.angle_max = 360.0
	parent.add_child(p)
	p.global_position = pos
	_orient_up(p, dir)
	p.emitting = true
	_free_after(p, life + 0.3)
	return p


static func flash_light(parent: Node, pos: Vector3, color: Color, energy: float, reach: float, seconds: float) -> OmniLight3D:
	var light := OmniLight3D.new()
	light.light_color = color
	light.light_energy = energy
	light.omni_range = reach
	light.shadow_enabled = false
	parent.add_child(light)
	light.global_position = pos
	if light.is_inside_tree():
		var tw := light.create_tween()
		tw.tween_property(light, "light_energy", 0.0, seconds)
		tw.tween_callback(light.queue_free)
	return light


## The 57 mm's muzzle blast: a flash cone, a light, a smoke ring and a dust kick.
## `size` scales the flash (1 for the 57 mm, about 0.35 for a 12.7 mm).
static func muzzle(parent: Node, pos: Vector3, dir: Vector3, size: float = 1.0) -> void:
	var flash := MeshInstance3D.new()
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.55 * size
	cone.height = 2.6 * size
	cone.radial_segments = 10
	cone.rings = 1
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.albedo_color = Color(1.0, 0.7, 0.35, 0.9)
	cone.material = mat
	flash.mesh = cone
	parent.add_child(flash)
	flash.global_position = pos + dir * 1.2 * size
	_orient_up(flash, dir)
	if flash.is_inside_tree():
		var tw := flash.create_tween()
		tw.tween_property(flash, "scale", Vector3(1.6, 0.4, 1.6), 0.07)
		tw.tween_callback(flash.queue_free)
	flash_light(parent, pos + dir * 0.8, Color(1.0, 0.72, 0.4), 9.0 * size, 14.0 * size, 0.12)
	sparks(parent, pos + dir * 0.5, dir, maxi(int(18 * size), 3), 26.0, 18.0)
	if size < 0.5:
		return  # a machine gun's flash: no smoke rings at 16 rounds a second
	var puff := smoke(parent, pos + dir * 1.0, dir, 14, 1.4, Color(0.72, 0.7, 0.66, 0.55), 1.6, 9.0)
	puff.spread = 70.0
	for side: float in [-1.0, 1.0]:
		var ring := smoke(parent, pos, dir.cross(Vector3.UP).normalized() * side, 6, 1.1, Color(0.7, 0.68, 0.64, 0.4), 1.2, 7.0)
		ring.spread = 25.0


## A round's hit: sparks and dust, scaled by the Hit dust setting. A high-explosive shell (`big`) adds a
## fireball and flash scaled by Shell hit size, a dark dust column and, on the ground, thrown clods. A
## `heavy` solid round (a 57 mm dart: no explosive, so no fire) still throws a dirt eruption off the ground
## from its own speed, scaled by the same two settings. Returns every node it made (each frees itself).
static func impact(parent: Node, pos: Vector3, normal: Vector3, metal: bool, big: bool, heavy: bool = false) -> Array:
	var made: Array = []
	var dust := hit_dust()
	var linger := dust_linger(dust)
	var boom := 1.6 if big else 1.0
	if metal:
		made.append(sparks(parent, pos, normal, int(34 * boom), 18.0 * boom, 70.0))
		made.append(flash_light(parent, pos + normal * 0.4, Color(1.0, 0.75, 0.45), 6.0 * boom, 9.0 * boom, 0.15))
		made.append(smoke(parent, pos, normal, 6, 1.0 * boom, Color(0.25, 0.24, 0.23, 0.6), 1.6, 2.5))
	else:
		made.append(sparks(parent, pos, normal, int(10 * boom), 12.0, 45.0))
		made.append(smoke(parent, pos, normal, mini(int(14 * boom * sqrt(dust)), 48), 1.8 * boom * dust, Color(0.5, 0.45, 0.38, 0.7), 2.4 * linger, 7.0 * boom * sqrt(dust)))
		made.append(flash_light(parent, pos + normal * 0.5, Color(1.0, 0.7, 0.4), 3.0 * boom, 8.0, 0.1))
	if big:
		var size := blast_size()
		made.append_array(fireball(parent, pos, normal, size))
		made.append(smoke(parent, pos, normal, mini(int(18 * sqrt(dust)), 48), 2.8 * dust, Color(0.18, 0.16, 0.15, 0.7), 3.2 * linger, 6.0 * sqrt(dust)))
		if not metal:
			made.append(clods(parent, pos, normal, size * dust))
	elif heavy and not metal:
		var kick := blast_size() * dust
		made.append(clods(parent, pos, normal, 0.6 * kick))
		made.append(smoke(parent, pos, normal, mini(int(10 * sqrt(kick)), 40), 2.2 * kick, Color(0.42, 0.37, 0.3, 0.65), 2.6 * linger, 5.0 * sqrt(kick)))
	return made


## A high-explosive shell's fireball: hot quads that swell and burn out in a third of a second, and its flash.
## `size` 1 is about 2 m across.
static func fireball(parent: Node, pos: Vector3, normal: Vector3, size: float) -> Array:
	var p := CPUParticles3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * 2.2 * size
	quad.material = fire_material()
	p.mesh = quad
	p.amount = 10
	p.lifetime = 0.35
	p.one_shot = true
	p.explosiveness = 1.0
	p.direction = Vector3.UP
	p.spread = 80.0
	p.initial_velocity_min = 3.0 * size
	p.initial_velocity_max = 9.0 * size
	p.damping_min = 12.0
	p.damping_max = 20.0
	p.gravity = Vector3.ZERO
	var grow := Curve.new()
	grow.add_point(Vector2(0.0, 0.4))
	grow.add_point(Vector2(1.0, 1.3))
	p.scale_amount_curve = grow
	var ramp := Gradient.new()
	ramp.offsets = PackedFloat32Array([0.0, 0.45, 1.0])
	ramp.colors = PackedColorArray([Color(1.0, 0.86, 0.55, 1.0), Color(1.0, 0.42, 0.1, 0.7), Color(0.3, 0.08, 0.02, 0.0)])
	p.color_ramp = ramp
	p.angle_max = 360.0
	p.set_meta("fx", "fireball")
	parent.add_child(p)
	p.global_position = pos + normal.normalized() * 0.5 * size
	_orient_up(p, normal)
	p.emitting = true
	_free_after(p, 0.8)
	var light := flash_light(parent, pos + normal.normalized() * size, Color(1.0, 0.7, 0.38), 10.0 * sqrt(size), 22.0 * size, 0.25)
	light.set_meta("fx", "flash")
	return [p, light]


## Dirt thrown out of a shell's crater: dark lumps on ballistic arcs. `amount` 1 is 16 clods.
static func clods(parent: Node, pos: Vector3, normal: Vector3, amount: float) -> CPUParticles3D:
	var p := CPUParticles3D.new()
	var lump := BoxMesh.new()
	lump.size = Vector3.ONE * 0.2
	lump.material = clod_material()
	p.mesh = lump
	p.amount = clampi(int(16 * amount), 4, 80)
	p.lifetime = 1.6
	p.one_shot = true
	p.explosiveness = 0.95
	p.direction = Vector3.UP
	p.spread = 35.0
	p.initial_velocity_min = 6.0 * sqrt(amount)
	p.initial_velocity_max = 16.0 * sqrt(amount)
	p.gravity = Vector3(0, -9.8, 0)
	p.scale_amount_min = 0.6
	p.scale_amount_max = 1.8
	p.set_meta("fx", "clods")
	parent.add_child(p)
	p.global_position = pos
	_orient_up(p, normal)
	p.emitting = true
	_free_after(p, 2.0)
	return p


## A scorch (or gouge) decal pressed onto whatever is under `pos`, facing out along `normal`.
static func decal(parent: Node, pos: Vector3, normal: Vector3, size: float, gouge: bool = false, along: Vector3 = Vector3.FORWARD) -> Decal:
	var d := Decal.new()
	d.texture_albedo = gouge_texture() if gouge else scorch_texture()
	d.size = Vector3(size * (2.5 if gouge else 1.0), size * 0.8, size)
	d.upper_fade = 0.3
	d.lower_fade = 0.3
	d.albedo_mix = 1.0
	d.cull_mask = 0xFFFFF & ~MECH_LAYERS
	parent.add_child(d)
	var up := normal.normalized()
	var x := along - up * along.dot(up)
	if x.length() < 0.01:
		x = up.cross(Vector3.FORWARD if absf(up.z) < 0.9 else Vector3.RIGHT)
	x = x.normalized()
	d.global_transform = Transform3D(Basis(x, up, x.cross(up)), pos)
	_keep(_decals, d, MAX_DECALS)
	return d


## A spent 57 mm case: a brass cylinder thrown out of the breech with the mech's own velocity.
static func casing(parent: Node, pos: Vector3, basis: Basis, velocity: Vector3) -> RigidBody3D:
	var body := RigidBody3D.new()
	body.mass = 2.2
	body.collision_layer = 16
	body.collision_mask = 1 | 16
	body.continuous_cd = true
	var mesh := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.034
	cyl.bottom_radius = 0.045
	cyl.height = 0.44
	cyl.radial_segments = 10
	cyl.rings = 1
	cyl.material = brass_material()
	mesh.mesh = cyl
	body.add_child(mesh)
	var cs := CollisionShape3D.new()
	var shape := CylinderShape3D.new()
	shape.radius = 0.045
	shape.height = 0.44
	cs.shape = shape
	body.add_child(cs)
	parent.add_child(body)
	body.global_transform = Transform3D(basis * Basis(Vector3.RIGHT, PI * 0.5), pos)
	body.linear_velocity = velocity
	body.angular_velocity = basis.x * randf_range(8.0, 16.0) + basis.y * randf_range(-6.0, 6.0)
	_keep(_casings, body, MAX_CASINGS)
	return body


## A lost armour panel: a copy of its mesh on a rigid body, thrown off the hit.
static func fling(parent: Node, source: MeshInstance3D, velocity: Vector3, spin: Vector3) -> RigidBody3D:
	var body := RigidBody3D.new()
	body.name = "Debris"
	body.collision_layer = 16
	body.collision_mask = 1 | 16
	var aabb := source.get_aabb()
	body.mass = 40.0
	var copy := MeshInstance3D.new()
	copy.mesh = source.mesh
	for i in source.get_surface_override_material_count():
		copy.set_surface_override_material(i, source.get_surface_override_material(i))
	copy.material_override = source.material_override
	body.add_child(copy)
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = aabb.size.max(Vector3.ONE * 0.05)
	cs.shape = box
	cs.position = aabb.get_center()
	body.add_child(cs)
	parent.add_child(body)
	body.global_transform = source.global_transform
	body.linear_velocity = velocity
	body.angular_velocity = spin
	_keep(_debris, body, MAX_DEBRIS)
	return body


## Remembers `node` in `list` and frees the oldest past `cap`, so long fights do not pile up nodes.
static func _keep(list: Array, node: Node, cap: int) -> void:
	list.append(node)
	while list.size() > cap:
		var old: Variant = list.pop_front()
		if is_instance_valid(old):
			(old as Node).queue_free()


static func _orient_up(node: Node3D, dir: Vector3) -> void:
	var up := dir.normalized()
	if up.length() < 0.5:
		return
	var x := up.cross(Vector3.UP if absf(up.y) < 0.95 else Vector3.RIGHT).normalized()
	node.global_basis = Basis(x, up, x.cross(up))
