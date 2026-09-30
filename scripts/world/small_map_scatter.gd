class_name SmallMapScatter
extends RefCounted
## Scatter for the small map (lane B3): grass, shrubs and loose stones drawn as one MultiMesh per
## terrain chunk each (only drawn near the camera, fading out), and boulders and concrete debris as
## solid bodies sharing a few meshes. Nothing lands in the water, on roads, on steep slopes or inside
## a building's footprint. Settings > Graphics > Grass and shrub density changes the drawn share live.

const GRASS_RANGE_M := 60.0
const PEBBLE_RANGE_M := 90.0
const SHRUB_RANGE_M := 170.0
const VARIANTS := 6

var multimeshes: Array[MultiMesh] = []
var full_counts: Array[int] = []
var bodies := 0


func _init(parent: Node3D, terrain: SmallMapTerrain, entry: Dictionary, avoid: Array[Rect2]) -> void:
	var cfg: Dictionary = entry.get("scatter", {})
	var rng := RandomNumberGenerator.new()
	rng.seed = int(entry.get("seed", 1)) + 700
	var holder := Node3D.new()
	holder.name = "Scatter"
	parent.add_child(holder)
	var grass := _variants("grass", 3)
	var shrubs := _variants("shrub", VARIANTS)
	var pebbles := _variants("pebbles", 3)
	var chunks := terrain.chunk_count()
	for cz in chunks:
		for cx in chunks:
			var x0 := cx * SmallMapTerrain.CHUNK_M - terrain.half
			var z0 := cz * SmallMapTerrain.CHUNK_M - terrain.half
			var k := cz * chunks + cx
			_chunk(holder, terrain, rng, grass[k % grass.size()], int(cfg.get("grass_per_chunk", 1200)), x0, z0, "grass", GRASS_RANGE_M, avoid)
			_chunk(holder, terrain, rng, shrubs[k % shrubs.size()], int(cfg.get("shrubs_per_chunk", 60)), x0, z0, "shrub", SHRUB_RANGE_M, avoid)
			_chunk(holder, terrain, rng, pebbles[k % pebbles.size()], int(cfg.get("pebbles_per_chunk", 10)), x0, z0, "pebbles", PEBBLE_RANGE_M, avoid)
	_solids(holder, terrain, rng, "boulder", int(cfg.get("boulders", 200)), avoid, false)
	_solids(holder, terrain, rng, "debris_chunk", int(cfg.get("debris", 80)), avoid, true)
	apply_density()
	Settings.changed.connect(_on_setting)


func apply_density() -> void:
	var d := clampf(Settings.get_f("graphics.foliage_density"), 0.0, 1.0)
	for i in multimeshes.size():
		multimeshes[i].visible_instance_count = int(full_counts[i] * d)


func disconnect_settings() -> void:
	if Settings.changed.is_connected(_on_setting):
		Settings.changed.disconnect(_on_setting)


func _on_setting(key: String, _value: Variant) -> void:
	if key == "graphics.foliage_density":
		apply_density()


func _variants(id: String, count: int) -> Array[Mesh]:
	var out: Array[Mesh] = []
	for v in count:
		var node := Kit.build(id, v)
		out.append((node.get_node("Mesh") as MeshInstance3D).mesh)
		node.free()
	return out


## Is (x, z) a fair place for scatter of this kind? Returns the ground normal, or ZERO when not.
func _spot(terrain: SmallMapTerrain, x: float, z: float, kind: String, avoid: Array[Rect2], rng: RandomNumberGenerator) -> Vector3:
	if absf(x) > terrain.half - 6.0 or absf(z) > terrain.half - 6.0:
		return Vector3.ZERO
	if terrain.road_edge_at(x, z) < 1.5 or terrain.water_edge_at(x, z) < (0.5 if kind == "grass" else 2.0):
		return Vector3.ZERO
	var nrm := terrain.normal_at(x, z)
	var steep := 0.84 if kind == "grass" else 0.72
	if nrm.y < steep and kind != "debris_chunk":
		return Vector3.ZERO
	var s := terrain.splat_at(x, z)
	if kind == "grass" and (rng.randf() < s.a * 0.8 or rng.randf() < s.b * 0.9):
		return Vector3.ZERO
	if kind == "debris_chunk" and s.a < 0.3 and s.b < 0.3:
		return Vector3.ZERO
	var p := Vector2(x, z)
	for r in avoid:
		if r.has_point(p):
			return Vector3.ZERO
	return nrm


func _chunk(holder: Node3D, terrain: SmallMapTerrain, rng: RandomNumberGenerator, mesh: Mesh, count: int, x0: float, z0: float, kind: String, reach: float, avoid: Array[Rect2]) -> void:
	var xfs: Array[Transform3D] = []
	var tones := PackedColorArray()
	var size := float(SmallMapTerrain.CHUNK_M)
	for i in count:
		var x := x0 + rng.randf() * size
		var z := z0 + rng.randf() * size
		var nrm := _spot(terrain, x, z, kind, avoid, rng)
		if nrm == Vector3.ZERO:
			continue
		var s := rng.randf_range(0.7, 1.3)
		var up := Vector3.UP.lerp(nrm, 0.6 if kind == "grass" else 0.3).normalized()
		var b := Basis(Vector3.UP, rng.randf() * TAU)
		var tilt := Quaternion(Vector3.UP, up)
		b = Basis(tilt) * b
		xfs.append(Transform3D(b.scaled(Vector3(s, s, s)), Vector3(x, terrain.height_at(x, z) - 0.05, z)))
		tones.append(Color(rng.randf(), 0, 0))
	if xfs.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = xfs.size()
	for i in xfs.size():
		mm.set_instance_transform(i, xfs[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.set_meta("kind", "shrubs" if kind == "shrub" else kind)
	mmi.visibility_range_end = reach
	mmi.visibility_range_end_margin = reach * 0.2
	mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if kind == "grass" else GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	holder.add_child(mmi)
	multimeshes.append(mm)
	full_counts.append(xfs.size())


func _solids(holder: Node3D, terrain: SmallMapTerrain, rng: RandomNumberGenerator, id: String, count: int, avoid: Array[Rect2], near_ruins: bool) -> void:
	var protos: Array[Node3D] = []
	for v in VARIANTS:
		protos.append(Kit.build(id, 100 + v))
	var placed := 0
	var tries := 0
	while placed < count and tries < count * 40:
		tries += 1
		var x := rng.randf_range(-terrain.half, terrain.half)
		var z := rng.randf_range(-terrain.half, terrain.half)
		if _spot(terrain, x, z, id, avoid, rng) == Vector3.ZERO:
			continue
		if near_ruins and terrain.road_edge_at(x, z) < 3.0:
			continue
		var node := protos[placed % protos.size()].duplicate() as Node3D
		node.position = Vector3(x, terrain.height_at(x, z), z)
		node.rotation = Vector3(rng.randf_range(-0.15, 0.15), rng.randf() * TAU, rng.randf_range(-0.15, 0.15))
		holder.add_child(node)
		placed += 1
	bodies += placed
	for p in protos:
		p.free()
