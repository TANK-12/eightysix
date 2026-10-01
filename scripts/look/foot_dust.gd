class_name FootDust
extends Node
## Dust kicked up by the Juggernaut's feet at a run (lane B4), from tuning.json "foot_dust". Each
## planted step (the mech's stepped signal) above min_speed_m_s throws one puff from that foot,
## bigger and thicker the faster the mech goes, kicked back against the run; how much depends on the
## ground under the foot (Sfx.surface_of, the same surfaces the footsteps use). Puffs are
## CombatFx.smoke, like the skid's, drawn with their own material (ragged noisy edges rather than a
## disc, soft where they meet the ground, fading out as the camera gets close), and at most
## max_live are alive at once.

static var _material: StandardMaterial3D

var mech: RigidBody3D
var level: Node
var _cfg: Dictionary = {}
var _live_until: Array[int] = []  # msec ticks when each live puff ends


## Adds a FootDust to a mech that has a stepped signal (it puffs into the mech's parent).
static func attach(to: RigidBody3D) -> FootDust:
	var dust := FootDust.new()
	dust.name = "FootDust"
	dust.mech = to
	to.add_child(dust)
	return dust


func _init() -> void:
	_cfg = Registry.tune("foot_dust", {})


func _ready() -> void:
	if mech != null and mech.has_signal("stepped"):
		mech.connect("stepped", _on_stepped)


## What one step throws at this speed on this surface: {} for nothing, else amount, size (m),
## life (s), rise (m/s) and colour (alpha is how thick).
static func plan(speed: float, surface: String) -> Dictionary:
	var c: Dictionary = Registry.tune("foot_dust", {})
	var lo := float(c.get("min_speed_m_s", 5.0))
	var share := float(c.get("surfaces", {}).get(surface, 0.0))
	if speed < lo or share <= 0.0:
		return {}
	var k := clampf(inverse_lerp(lo, float(c.get("full_speed_m_s", 18.0)), speed), 0.0, 1.0)
	var col: Array = c.get("colour", [0.6, 0.55, 0.47, 0.3])
	var thick := lerpf(0.45, 1.0, k) * share
	return {
		"amount": roundi(lerpf(_lo(c, "amount", 2.0), _hi(c, "amount", 5.0), k)),
		"size": lerpf(_lo(c, "size_m", 1.0), _hi(c, "size_m", 2.2), k),
		"life": lerpf(_lo(c, "life_s", 1.2), _hi(c, "life_s", 2.4), k),
		"rise": lerpf(_lo(c, "rise_m_s", 1.0), _hi(c, "rise_m_s", 3.0), k),
		"colour": Color(float(col[0]), float(col[1]), float(col[2]), float(col[3]) * thick),
	}


## Throws one puff at a foot planted at `at` while the mech moves at `velocity`. Returns the
## particles, or null for none (too slow, hard ground, or max_live already in the air).
func puff(at: Vector3, velocity: Vector3, surface: String) -> Node3D:
	var p := plan(velocity.length(), surface)
	if p.is_empty() or level == null or not Settings.get_b("graphics.foot_dust"):
		return null
	var now := Time.get_ticks_msec()
	_live_until = _live_until.filter(func(t: int) -> bool: return t > now)
	if _live_until.size() >= int(_cfg.get("max_live", 24)):
		return null
	_live_until.append(now + int(float(p["life"]) * 1000.0))
	var flat := Vector3(velocity.x, 0.0, velocity.z)
	var back := -flat.normalized() if flat.length() > 0.1 else Vector3.ZERO
	var dir := (Vector3.UP + back * float(_cfg.get("kick_back", 0.8))).normalized()
	var fx := CombatFx.smoke(level, at + Vector3.UP * 0.15, dir, int(p["amount"]), float(p["size"]), p["colour"], float(p["life"]), float(p["rise"]))
	(fx.mesh as QuadMesh).material = material()
	return fx


## The smoke material with a ragged cloud texture, soft ground contact and a near-camera fade.
static func material() -> StandardMaterial3D:
	if _material != null:
		return _material
	var c: Dictionary = Registry.tune("foot_dust", {})
	_material = CombatFx.smoke_material().duplicate() as StandardMaterial3D
	_material.albedo_texture = cloud_texture(64)
	_material.proximity_fade_enabled = true
	_material.proximity_fade_distance = float(c.get("soft_ground_m", 0.8))
	_material.distance_fade_mode = BaseMaterial3D.DISTANCE_FADE_PIXEL_ALPHA
	_material.distance_fade_min_distance = float(c.get("camera_fade_m", [1.5, 7.0])[0])
	_material.distance_fade_max_distance = float(c.get("camera_fade_m", [1.5, 7.0])[1])
	return _material


## White with alpha: a radial falloff broken up by noise, so a puff has no clean round edge.
static func cloud_texture(size: int) -> ImageTexture:
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.09
	noise.fractal_octaves = 3
	noise.seed = 7
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var half := size * 0.5
	for y in size:
		for x in size:
			var r := Vector2(x + 0.5 - half, y + 0.5 - half).length() / half
			var n := noise.get_noise_2d(x, y) * 0.5 + 0.5
			var a := clampf(1.0 - r * (0.55 + 1.0 * n), 0.0, 1.0)
			img.set_pixel(x, y, Color(1, 1, 1, a * a * (0.55 + 0.45 * n)))
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


func _on_stepped(leg_name: String) -> void:
	if level == null:
		level = mech.get_parent()
	for leg: Dictionary in mech.get("legs"):
		if str(leg["name"]) == leg_name:
			var foot: Vector3 = leg.get("foot", mech.global_position)
			puff(foot, mech.linear_velocity, _surface_under(foot))
			return


func _surface_under(at: Vector3) -> String:
	var q := PhysicsRayQueryParameters3D.create(at + Vector3.UP * 0.6, at + Vector3.DOWN * 0.8, 1)
	q.exclude = [mech.get_rid()]
	var hit := mech.get_world_3d().direct_space_state.intersect_ray(q)
	return Sfx.surface_of(hit.get("collider")) if not hit.is_empty() else "dirt"


static func _lo(c: Dictionary, key: String, fallback: float) -> float:
	var a: Variant = c.get(key, [fallback, fallback])
	return float(a[0])


static func _hi(c: Dictionary, key: String, fallback: float) -> float:
	var a: Variant = c.get(key, [fallback, fallback])
	return float(a[1])
