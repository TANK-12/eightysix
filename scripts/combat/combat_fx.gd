class_name CombatFx
extends RefCounted
## The look of combat: muzzle blast, tracers, impact sparks and dust, scorch and gouge decals, spent
## casings and flung armour. Everything here is fire-and-forget (it frees itself) and cheap enough for
## the Low preset: CPU particles with small counts, one short-lived light per event. No particle casts a
## shadow (a see-through quad still throws a solid one), and every emitter works in local coordinates:
## in world space a burst's first frame drew at the world origin, the map's spawn on the test range and in the
## menu (Emerson's note 11 after 012: sparks and smoke at the spawn point; images/467 vs 468).

## Scorch marks and wall cracks kept: Settings > Graphics > World > Scorch marks kept (decal_limit per preset, LOOK3);
## this is the fallback when that setting is missing.
const MAX_DECALS := 64
const MAX_CASINGS := 24
const MAX_DEBRIS := 16
## Bullets (every round that is neither a shell nor a 57 mm dart: the 12.7 mm pair at ~16 rounds a second and
## the Legion's machine guns) reuse a ring of this many emitters per kind instead of making new nodes per round,
## and light nothing. Emerson's note 8 (2026-10-02): 12.7 mm ground hits made lag spikes (Medium 44 -> 19 fps).
const BULLET_POOL := 32
## Smoke and dust are big see-through quads, and on the Iris Xe their cost is fill: every layer of every puff is
## blended over every pixel it covers (task 56, 2026-10-07: an HE hit every 0.5 s took the GPU from 17 to 40 ms a
## frame, 54 ms with the camera in the cloud). Each cloud is drawn with SMOKE_THIN of the puffs it asks for, each
## puff a little bigger and more opaque so the cloud covers the same; past SMOKE_BUDGET puffs alive in the scene,
## new clouds thin further (to a quarter at most) the same way.
const SMOKE_THIN := 0.5
const SMOKE_BUDGET := 260
## Render layer 20 holds every mech's meshes: ground decals skip it (so a gouge never paints the feet
## standing in it) and hull scorch marks use only it.
const MECH_LAYER := 1 << 19
## The parts of a Juggernaut that the pilot's own first-person view leaves out (its hull, legs and canopy: see
## MechCombat._tag_mech_layer) sit on this layer instead of MECH_LAYER, and the cockpit camera's mask skips it.
const COCKPIT_SHELL_LAYER := 1 << 9
## Every layer a mech's meshes can be on: what hull scorch marks use, and ground decals leave alone.
const MECH_LAYERS := MECH_LAYER | COCKPIT_SHELL_LAYER

static var _decals: Array = []
static var _marks: Array = []
static var _pools := {}  # pool kind -> {"nodes": Array, "next": int}
static var _casings: Array = []
static var _debris: Array = []
static var _scorch_tex: Texture2D
static var _scorch_nrm: Texture2D
static var _crack_tex: Texture2D
static var _crack_nrm: Texture2D
static var _gouge_tex: Texture2D
static var _smoke_mat: StandardMaterial3D
static var _spark_mat: StandardMaterial3D
static var _brass_mat: StandardMaterial3D
static var _fire_mat: StandardMaterial3D
static var _clod_mat: StandardMaterial3D
static var _smoke_live := 0


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
		# Lit at the corners, not per pixel: a soft puff looks the same and the cloud costs 5 ms less (task 56).
		_smoke_mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
		_smoke_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		_smoke_mat.vertex_color_use_as_albedo = true
		_smoke_mat.albedo_texture = _radial(64, Color(1, 1, 1, 1), Color(1, 1, 1, 0))
		_smoke_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
		_smoke_mat.roughness = 1.0
		# Smoke is a volume, not a surface: no shadow maps on it.
		_smoke_mat.disable_receive_shadows = true
		# Thin dust passes light through it: seen against the sun it glows rather than going black (version 014:
		# the 57 mm's smoke and ground dust read as black blobs from the cockpit, images/453).
		_smoke_mat.backlight_enabled = true
		_smoke_mat.backlight = Color(0.55, 0.52, 0.48)
		# and sky light scattered inside the cloud keeps its shaded side from going black.
		_smoke_mat.emission_enabled = true
		_smoke_mat.emission = Color(0.12, 0.115, 0.11)
		_smoke_mat.emission_energy_multiplier = 1.0
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


## LOOK3: a scorch with a ragged, noisy edge, a charred centre, a ring of thrown soot with rays, and a
## shallow crater in its normal map; built once (128 px) the first time a shell lands.
static func scorch_texture() -> Texture2D:
	if _scorch_tex == null:
		_build_mark(false)
	return _scorch_tex


## A wall hit: a chipped pit with cracks running out from it, over a lighter soot ring.
static func crack_texture() -> Texture2D:
	if _crack_tex == null:
		_build_mark(true)
	return _crack_tex


static func _build_mark(cracks: bool) -> void:
	var n := 128
	var noise := FastNoiseLite.new()
	noise.seed = 86 if cracks else 57
	noise.frequency = 0.06
	noise.fractal_octaves = 4
	var rng := RandomNumberGenerator.new()
	rng.seed = 8601
	var lines := PackedFloat32Array()
	lines.resize(n * n)
	if cracks:
		for b in 9:
			var at := Vector2(n * 0.5, n * 0.5)
			var dir := Vector2.from_angle(TAU * b / 9.0 + rng.randf_range(-0.3, 0.3))
			var steps := rng.randi_range(22, 52)
			for s in steps:
				dir = dir.rotated(rng.randf_range(-0.45, 0.45))
				at += dir
				var i := int(at.y) * n + int(at.x)
				if at.x < 1 or at.y < 1 or at.x >= n - 1 or at.y >= n - 1:
					break
				var w := 1.0 - float(s) / steps
				lines[i] = maxf(lines[i], 0.6 + 0.4 * w)
				lines[i + 1] = maxf(lines[i + 1], 0.5 * w)
	var albedo := Image.create(n, n, false, Image.FORMAT_RGBA8)
	var height := PackedFloat32Array()
	height.resize(n * n)
	for y in n:
		for x in n:
			var p := Vector2(x + 0.5, y + 0.5) / n - Vector2(0.5, 0.5)
			var r := p.length() * 2.0
			var wobble := noise.get_noise_2d(x, y)
			var edge := r + wobble * 0.28
			var rays := 0.5 + 0.5 * sin(p.angle() * 13.0 + wobble * 6.0)
			var a := 0.0
			var c := Color(0.03, 0.025, 0.02)
			if cracks:
				var pit := 1.0 - smoothstep(0.08, 0.24, edge)
				var soot := (1.0 - smoothstep(0.15, 0.85, edge)) * 0.55
				var line := lines[y * n + x]
				a = maxf(maxf(pit, soot * (0.6 + 0.4 * rays)), line * (1.0 - smoothstep(0.7, 1.0, r)))
				c = Color(0.05, 0.045, 0.04).lerp(Color(0.16, 0.14, 0.12), clampf(soot - pit, 0.0, 1.0))
				height[y * n + x] = -pit * 0.8 - line * 0.5
			else:
				var char_ := 1.0 - smoothstep(0.1, 0.45, edge)
				var ring := (1.0 - smoothstep(0.35, 0.95, edge)) * (0.55 + 0.45 * rays)
				a = clampf(maxf(char_ * 0.95, ring * 0.8), 0.0, 1.0)
				c = Color(0.02, 0.018, 0.016).lerp(Color(0.13, 0.11, 0.09), clampf(1.0 - char_ + wobble * 0.3, 0.0, 1.0))
				height[y * n + x] = -(1.0 - smoothstep(0.0, 0.6, r)) + clampf(1.0 - absf(r - 0.62) * 6.0, 0.0, 1.0) * 0.35
			albedo.set_pixel(x, y, Color(c, a))
	var normal := Image.create(n, n, false, Image.FORMAT_RGB8)
	for y in n:
		for x in n:
			var dx := height[y * n + mini(x + 1, n - 1)] - height[y * n + maxi(x - 1, 0)]
			var dy := height[mini(y + 1, n - 1) * n + x] - height[maxi(y - 1, 0) * n + x]
			var v := Vector3(-dx * 4.0, -dy * 4.0, 1.0).normalized()
			normal.set_pixel(x, y, Color(v.x * 0.5 + 0.5, v.y * 0.5 + 0.5, v.z * 0.5 + 0.5))
	albedo.generate_mipmaps()
	normal.generate_mipmaps()
	if cracks:
		_crack_tex = ImageTexture.create_from_image(albedo)
		_crack_nrm = ImageTexture.create_from_image(normal)
	else:
		_scorch_tex = ImageTexture.create_from_image(albedo)
		_scorch_nrm = ImageTexture.create_from_image(normal)


## How many scorch marks stay (the preset's decal_limit). Bullet holes have their own cap (three quarters as
## many), so a long 12.7 mm burst never wipes the shells' scorch marks.
static func decal_limit() -> int:
	var n := int(Settings.get_f("graphics.decal_limit")) if Settings.has_key("graphics.decal_limit") else MAX_DECALS
	return n if n > 0 else MAX_DECALS


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
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.local_coords = true
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
	return _launch(parent, smoke_emitter(amount, size, color, life, speed), pos, dir, life + 0.3)


## smoke()'s emitter, not yet in the tree or emitting, for a caller that changes it first: a property set after
## emitting starts left a dark unmoving blob at the spot (version 014, images/452-457).
static func smoke_emitter(amount: int, size: float, color: Color, life: float = 1.8, speed: float = 2.0) -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.local_coords = true
	var keep := smoke_share(amount, _smoke_live)
	var n := maxi(roundi(amount * keep), 1)
	keep = float(n) / maxf(amount, 1.0)
	color.a = thinned_alpha(color.a, keep)
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * size * (1.25 if keep < 1.0 else 1.0)
	quad.material = smoke_material()
	p.mesh = quad
	p.amount = n
	p.tree_entered.connect(func() -> void: _smoke_live += n)
	p.tree_exiting.connect(func() -> void: _smoke_live -= n)
	p.lifetime = life
	p.one_shot = true
	p.emitting = false
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
	# Nearly every puff leaves in the first frame: from one point, at full strength, they stacked into an opaque
	# dark disc cut off by the ground (version 014's "dome", images/456-470). They start spread over a small
	# ball and fade in over the first 15 % of their life.
	p.emission_shape = CPUParticles3D.EMISSION_SHAPE_SPHERE
	p.emission_sphere_radius = size * 0.3
	var ramp := Gradient.new()
	ramp.offsets = PackedFloat32Array([0.0, 0.15, 1.0])
	ramp.colors = PackedColorArray([Color(color, color.a * 0.35), color, Color(color, 0.0)])
	p.color_ramp = ramp
	p.angle_min = 0.0
	p.angle_max = 360.0
	return p


## The share of a cloud's `amount` puffs to draw with `live` smoke puffs already in the scene (see SMOKE_THIN).
static func smoke_share(amount: int, live: int) -> float:
	var share := SMOKE_THIN
	if live + amount * share > SMOKE_BUDGET:
		share *= clampf(float(SMOKE_BUDGET - live) / (amount * share), 0.5, 1.0)
	return share


## The opacity that keeps a cloud as dense with `keep` of its puffs: n puffs of alpha a stacked cover
## 1 - (1 - a)^n, so a share k of them need 1 - (1 - a)^(1 / k).
static func thinned_alpha(alpha: float, keep: float) -> float:
	if keep >= 1.0:
		return alpha
	return minf(1.0 - pow(1.0 - clampf(alpha, 0.0, 0.99), 1.0 / keep), 0.95)


## Adds a one-shot emitter built off-tree, places it and starts it; it frees itself after `seconds`.
static func _launch(parent: Node, p: CPUParticles3D, pos: Vector3, dir: Vector3, seconds: float) -> CPUParticles3D:
	parent.add_child(p)
	p.global_position = pos
	_orient_up(p, dir)
	p.restart()
	_free_after(p, seconds)
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


## A gun's muzzle blast, seen from any side (Emerson's note 14 after 012: the old flash was a flat cone that read
## as a dim disc from the cockpit and the chase camera): a tongue of burning propellant gas streaming out of the
## bore, a light that throws the flash on the ground and the hull, and for the 57 mm sparks and a smoke puff.
## `size` 1 for the 57 mm, about 0.35 for a 12.7 mm, whose flames come from a pool (16 rounds a second) and
## which skips the sparks and smoke.
static func muzzle(parent: Node, pos: Vector3, dir: Vector3, size: float = 1.0) -> void:
	var gun := size >= 0.5
	var flame: CPUParticles3D = _flame() if gun else _pooled("mg_flame", parent, _flame)
	(flame.mesh as QuadMesh).size = Vector2.ONE * 1.1 * size
	# Flame particles leave at up to 70 m/s per unit size and stop within v^2 / 2a: a tongue about 2.5 m long for
	# the 57 mm and under a metre for the 12.7 mm.
	flame.initial_velocity_min = 2.0 * size
	flame.initial_velocity_max = 70.0 * size
	flame.damping_min = 1000.0 * size
	flame.damping_max = 1000.0 * size
	if gun:
		flame.one_shot = true
		parent.add_child(flame)
		_free_after(flame, 0.4)
	_emit(flame, pos, dir)
	flash_light(parent, pos + dir * 1.2 * size, Color(1.0, 0.7, 0.38), 14.0 * size, 22.0 * size, 0.09 if gun else 0.05)
	if not gun:
		return
	sparks(parent, pos + dir * 0.5, dir, 18, 26.0, 18.0)
	var puff := smoke_emitter(12, 1.4, Color(0.8, 0.78, 0.74, 0.4), 1.6, 9.0)
	puff.spread = 60.0
	_launch(parent, puff, pos + dir * 1.5, dir, 1.9)


## The burning-gas tongue of a muzzle flash: bright additive quads that swell and burn out in 90 ms.
static func _flame() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.local_coords = true
	var quad := QuadMesh.new()
	quad.material = fire_material()
	p.mesh = quad
	p.amount = 12
	p.lifetime = 0.09
	p.explosiveness = 1.0
	p.direction = Vector3.UP
	p.spread = 7.0
	p.gravity = Vector3.ZERO
	var grow := Curve.new()
	grow.add_point(Vector2(0.0, 0.7))
	grow.add_point(Vector2(1.0, 1.5))
	p.scale_amount_curve = grow
	var ramp := Gradient.new()
	ramp.offsets = PackedFloat32Array([0.0, 0.35, 1.0])
	ramp.colors = PackedColorArray([Color(1.0, 0.95, 0.8, 1.0), Color(1.0, 0.6, 0.2, 0.85), Color(0.6, 0.18, 0.04, 0.0)])
	p.color_ramp = ramp
	p.angle_max = 360.0
	p.set_meta("fx", "muzzle_flame")
	return p


## A round's hit: sparks and dust, scaled by the Hit dust setting. A high-explosive shell (`big`) adds a
## fireball and flash scaled by Shell hit size, a dark dust column and, on the ground, thrown clods. A
## `heavy` solid round (a 57 mm dart: no explosive, so no fire) still throws a dirt eruption off the ground
## from its own speed, scaled by the same two settings. Returns every node it made (each frees itself).
static func impact(parent: Node, pos: Vector3, normal: Vector3, metal: bool, big: bool, heavy: bool = false) -> Array:
	var made: Array = []
	var dust := hit_dust()
	var linger := dust_linger(dust)
	var boom := 1.6 if big else 1.0
	if not big and not heavy:
		return bullet_hit(parent, pos, normal, metal)
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
			made.append(dirt_column(parent, pos, normal, size * dust))
	elif heavy and not metal:
		var kick := blast_size() * dust
		made.append(clods(parent, pos, normal, 0.6 * kick))
		made.append(smoke(parent, pos, normal, mini(int(10 * sqrt(kick)), 40), 2.2 * kick, Color(0.42, 0.37, 0.3, 0.65), 2.6 * linger, 5.0 * sqrt(kick)))
	return made


## A bullet's hit: a few sparks and a puff of dust or smoke sized for a 10-45 g round (about a metre, not a
## shell's column), still scaled by the Hit dust setting. Both come from the bullet pools: no new nodes, no light.
static func bullet_hit(parent: Node, pos: Vector3, normal: Vector3, metal: bool) -> Array:
	var dust := hit_dust()
	var spark := _pooled("bullet_spark", parent, _bullet_sparks)
	spark.initial_velocity_max = 16.0 if metal else 9.0
	spark.initial_velocity_min = spark.initial_velocity_max * 0.4
	spark.spread = 70.0 if metal else 45.0
	_emit(spark, pos, normal)
	var puff := _pooled("bullet_puff", parent, _bullet_puff)
	(puff.mesh as QuadMesh).size = Vector2.ONE * (0.45 if metal else 0.8) * dust
	puff.lifetime = (0.9 if metal else 1.4) * dust_linger(dust)
	puff.initial_velocity_max = 3.0 * sqrt(dust)
	puff.initial_velocity_min = puff.initial_velocity_max * 0.3
	var colour := Color(0.25, 0.24, 0.23, 0.55) if metal else Color(0.5, 0.45, 0.38, 0.6)
	puff.color_ramp.set_color(0, colour)
	puff.color_ramp.set_color(1, Color(colour, 0.0))
	_emit(puff, pos, normal)
	return [spark, puff]


## The next emitter in pool `kind` under `parent`, made by `make` the first time (or after the old one went
## with its level). Round-robin: past BULLET_POOL live hits the oldest puff restarts early.
static func _pooled(kind: String, parent: Node, make: Callable) -> CPUParticles3D:
	if not _pools.has(kind):
		_pools[kind] = {"nodes": [], "next": 0}
	var pool: Dictionary = _pools[kind]
	var nodes: Array = pool["nodes"]
	var i: int = pool["next"]
	pool["next"] = (i + 1) % BULLET_POOL
	var old: Variant = nodes[i] if i < nodes.size() else null
	if is_instance_valid(old) and (old as Node).get_parent() == parent:
		return old as CPUParticles3D
	var p: CPUParticles3D = make.call()
	p.one_shot = true
	p.emitting = false
	p.set_meta("fx", kind)
	parent.add_child(p)
	if i < nodes.size():
		nodes[i] = p
	else:
		nodes.append(p)
	return p


static func _emit(p: CPUParticles3D, pos: Vector3, dir: Vector3) -> void:
	p.global_position = pos
	_orient_up(p, dir)
	p.restart()


static func _bullet_sparks() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.local_coords = true
	var streak := BoxMesh.new()
	streak.size = Vector3(0.02, 0.2, 0.02)
	streak.material = spark_material()
	p.mesh = streak
	p.amount = 8
	p.lifetime = 0.4
	p.explosiveness = 0.95
	p.particle_flag_align_y = true
	p.direction = Vector3.UP
	p.gravity = Vector3(0, -14.0, 0)
	p.scale_amount_min = 0.5
	p.scale_amount_max = 1.1
	p.color = Color(1.0, 0.8, 0.45)
	return p


static func _bullet_puff() -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.local_coords = true
	var quad := QuadMesh.new()
	quad.material = smoke_material()
	p.mesh = quad
	p.amount = 5
	p.explosiveness = 0.9
	p.direction = Vector3.UP
	p.spread = 35.0
	p.damping_min = 1.5
	p.damping_max = 3.0
	p.gravity = Vector3(0, 0.4, 0)
	var grow := Curve.new()
	grow.add_point(Vector2(0.0, 0.4))
	grow.add_point(Vector2(1.0, 1.5))
	p.scale_amount_curve = grow
	p.color_ramp = Gradient.new()
	p.angle_max = 360.0
	return p


## A high-explosive shell's fireball: hot quads that swell and burn out in a third of a second, and its flash.
## `size` 1 is about 2 m across.
static func fireball(parent: Node, pos: Vector3, normal: Vector3, size: float) -> Array:
	var p := CPUParticles3D.new()
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.local_coords = true
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


## A high-explosive shell's ground burst throws a dark column of dirt about 12 m up at `amount` 1 (Emerson's note 6
## after 012: he could never tell where his HE landed). Look only, scaled by the two Combat effects sliders.
static func dirt_column(parent: Node, pos: Vector3, normal: Vector3, amount: float) -> CPUParticles3D:
	var a := maxf(amount, 0.3)
	var p := smoke_emitter(mini(int(14 * sqrt(a)), 40), 2.4 * sqrt(a), Color(0.24, 0.2, 0.16, 0.85), 3.0 * dust_linger(hit_dust()), 14.0 * sqrt(a))
	p.spread = 12.0
	p.explosiveness = 0.95
	p.damping_min = 7.0
	p.damping_max = 9.0
	p.gravity = Vector3(0, -1.5, 0)
	p.set_meta("fx", "dirt_column")
	return _launch(parent, p, pos, normal, p.lifetime + 0.3)


## Dirt thrown out of a shell's crater: dark lumps on ballistic arcs. `amount` 1 is 16 clods.
static func clods(parent: Node, pos: Vector3, normal: Vector3, amount: float) -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.local_coords = true
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
	# a shell's mark on a wall (anything steeper than 60 degrees) cracks; on the ground it scorches
	var wall := not gouge and absf(normal.normalized().y) < 0.5 and size >= 0.6
	if gouge:
		d.texture_albedo = gouge_texture()
	else:
		d.texture_albedo = crack_texture() if wall else scorch_texture()
		d.texture_normal = _crack_nrm if wall else _scorch_nrm
		d.normal_fade = 0.3
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
	if size < 0.6:
		_keep(_marks, d, maxi(decal_limit() * 3 / 4, 8))
	else:
		_keep(_decals, d, decal_limit())
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


## A lost armour panel: a copy of its mesh on a rigid body, thrown off the hit. It starts inside the hull it
## came off, so it never collides with `from` (Emerson's note 17: forcing the two apart kicked the mech
## onto its side and down into the ground).
static func fling(parent: Node, source: MeshInstance3D, velocity: Vector3, spin: Vector3, from: PhysicsBody3D = null) -> RigidBody3D:
	var body := RigidBody3D.new()
	body.name = "Debris"
	body.collision_layer = 16
	body.collision_mask = 1 | 16
	if from != null:
		body.add_collision_exception_with(from)
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
