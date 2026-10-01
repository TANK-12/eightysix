class_name GrimeBuildup
extends Node
## Dust and mud building up on the Juggernaut over a sortie (lane B4), from tuning.json
## "grime_buildup". Ground covered (dirt far more than rock, more at a run), hard landings and skids
## add dirt on top of each material's finish grime through Finish.set_extra, so it shows on the
## same mottled layer and mattes the paint. A new mech starts at the finish's own wear; Settings >
## Gameplay > Dirt builds up (mech.grime_buildup) off washes it and stops it.

const POLL_S := 0.25  # how often the run is measured
const SLIDE_FROM := 0.3  # telemetry slide amount above which the feet skid (as MechSounds)
const REAPPLY_STEP := 1.0 / 64.0  # materials are touched only when the dirt moves this much

var mech: RigidBody3D
var mats: Array = []  # the finish's materials (those Finish.apply_to has marked)
var extra := 0.0  # sortie dirt, 0..max_extra
var _cfg: Dictionary = {}
var _applied := 0.0
var _poll := 0.0


## Adds a GrimeBuildup to a mech whose finish is already applied (after _wire_shine).
static func attach(to: RigidBody3D) -> GrimeBuildup:
	var g := GrimeBuildup.new()
	g.name = "GrimeBuildup"
	g.mech = to
	g.mats = finished_materials(to)
	to.add_child(g)
	return g


## Every material under node that carries a finish (one entry per material, not per surface).
static func finished_materials(node: Node) -> Array:
	var found: Array = []
	for n: Node in node.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		if mi.mesh == null:
			continue
		for i in mi.mesh.get_surface_count():
			var mat := mi.get_surface_override_material(i) as StandardMaterial3D
			if mat != null and mat.has_meta("finish_grime") and not found.has(mat):
				found.append(mat)
	return found


func _init() -> void:
	_cfg = Registry.tune("grime_buildup", {})


func _ready() -> void:
	if mech == null:
		return
	if mech.has_signal("landed"):
		mech.connect("landed", _on_landed)
	Settings.changed.connect(_on_setting_changed)


## Grime from covering `metres` of `surface` at `speed` m/s.
static func gain(metres: float, surface: String, speed: float) -> float:
	var c: Dictionary = Registry.tune("grime_buildup", {})
	var per_km := float(c.get("per_km", {}).get(surface, 0.0))
	var s: Array = c.get("speed_m_s", [4.0, 18.0])
	var f: Array = c.get("speed_factor", [0.5, 1.4])
	var k := clampf(inverse_lerp(float(s[0]), float(s[1]), speed), 0.0, 1.0)
	return metres / 1000.0 * per_km * lerpf(float(f[0]), float(f[1]), k)


## Grime from one landing at impact_speed m/s (downward).
static func landing_gain(impact_speed: float) -> float:
	var l: Dictionary = Registry.tune("grime_buildup", {}).get("landing", {})
	var k := inverse_lerp(float(l.get("from_m_s", 4.0)), float(l.get("full_m_s", 12.0)), impact_speed)
	return clampf(k, 0.0, 1.0) * float(l.get("max", 0.03))


## Grime from `seconds` of skidding on `surface`.
static func skid_gain(seconds: float, surface: String) -> float:
	return seconds * float(Registry.tune("grime_buildup", {}).get("skid_per_s", {}).get(surface, 0.0))


## Adds grime (capped at max_extra) unless the setting is off.
func add(amount: float) -> void:
	if not Settings.get_b("mech.grime_buildup"):
		return
	extra = minf(extra + maxf(amount, 0.0), float(_cfg.get("max_extra", 0.45)))
	if absf(extra - _applied) >= REAPPLY_STEP or extra >= float(_cfg.get("max_extra", 0.45)):
		_apply()


## Covering ground: what gain() gives for it.
func travel(metres: float, surface: String, speed: float) -> void:
	add(gain(metres, surface, speed))


## Figures for a bot run's samples (scripts/core/bot.gd).
func bot_sample() -> Dictionary:
	return {"grime_extra": snappedf(extra, 0.001)}


## Back to the finish's own wear.
func reset() -> void:
	extra = 0.0
	_apply()


func _apply() -> void:
	_applied = extra
	var weights: Dictionary = _cfg.get("weights", {})
	var rough := float(_cfg.get("roughness_gain", 0.0))
	for m: Variant in mats:
		var mat := m as StandardMaterial3D
		var w := float(weights.get(Finish._base_name(mat.resource_name), 1.0))
		Finish.set_extra(mat, extra * w, rough)


func _physics_process(delta: float) -> void:
	_poll += delta
	if _poll < POLL_S or mech == null:
		return
	var dt := _poll
	_poll = 0.0
	if not Settings.get_b("mech.grime_buildup") or not _grounded():
		return
	var speed := Vector2(mech.linear_velocity.x, mech.linear_velocity.z).length()
	if speed < 0.5:
		return
	var surface := _surface_under()
	travel(speed * dt, surface, speed)
	if mech.has_method("telemetry"):
		var t: Dictionary = mech.call("telemetry")
		if float(t.get("slide", 0.0)) > SLIDE_FROM or bool(t.get("skidding", false)):
			add(skid_gain(dt, surface))


func _grounded() -> bool:
	for leg: Dictionary in mech.get("legs"):
		if leg.get("contact", false):
			return true
	return false


func _surface_under() -> String:
	var at := mech.global_position
	var q := PhysicsRayQueryParameters3D.create(at, at + Vector3.DOWN * 6.0, 1)
	q.exclude = [mech.get_rid()]
	var hit := mech.get_world_3d().direct_space_state.intersect_ray(q)
	return Sfx.surface_of(hit.get("collider")) if not hit.is_empty() else "dirt"


func _on_landed(impact: float) -> void:
	add(landing_gain(impact))


func _on_setting_changed(key: String, value: Variant) -> void:
	if key == "mech.grime_buildup" and not bool(value):
		reset()
