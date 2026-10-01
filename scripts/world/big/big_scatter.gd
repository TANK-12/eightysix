class_name BigScatter
extends RefCounted
## Grass, shrubs, pebbles and boulders for the big map's 1 m tiles (lane B5). Where each piece goes is
## worked out on the worker thread from the tile's own heights, normals and splat (no terrain
## queries): never on roads or in the water, less grass in town and in craters, nothing on steep
## ground. Each 64 m quarter of a tile gets one MultiMesh per kind (so the draw range works per
## quarter, as the small map's 64 m chunks), filled straight from a transform buffer.
## Counts per 128 m tile from the map entry's "scatter" block; Settings > Graphics > Grass and shrub
## density draws a share of them.

const SUB_M := 64
## kind: [draw range (m), steepest normal.y, grass-like (thinned in town and craters), shadows]
const KINDS := {
	"grass": [60.0, 0.84, true, false],
	"shrub": [170.0, 0.72, false, true],
	"pebbles": [90.0, 0.72, false, true],
}


## {kind: [PackedFloat32Array per quarter (12 floats per piece, local to the tile)], "boulders": [Transform3D]}
static func plan(t: Dictionary, cfg: Dictionary, water_level: float) -> Dictionary:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(Vector2i(int(t["tx"]), int(t["tz"]))) + int(cfg.get("seed", 0))
	var out := {}
	for kind: String in KINDS:
		var spec: Array = KINDS[kind]
		var quarters: Array = []
		var count := int(cfg.get(kind + "_per_tile", 0)) / 4
		for q in 4:
			var buf := PackedFloat32Array()
			var ox := (q % 2) * SUB_M
			var oz := (q / 2) * SUB_M
			for i in count:
				var x := ox + rng.randf() * SUB_M
				var z := oz + rng.randf() * SUB_M
				var nrm := _spot(t, x, z, float(spec[1]), bool(spec[2]), water_level, rng)
				if nrm == Vector3.ZERO:
					continue
				var s := rng.randf_range(0.7, 1.3)
				var up := Vector3.UP.lerp(nrm, 0.6 if kind == "grass" else 0.3).normalized()
				var b := Basis(Quaternion(Vector3.UP, up)) * Basis(Vector3.UP, rng.randf() * TAU)
				b = b.scaled(Vector3(s, s, s))
				var o := Vector3(x, height(t, x, z) - 0.05, z)
				buf.append_array([b.x.x, b.y.x, b.z.x, o.x, b.x.y, b.y.y, b.z.y, o.y, b.x.z, b.y.z, b.z.z, o.z])
			quarters.append(buf)
		out[kind] = quarters
	var boulders: Array[Transform3D] = []
	for i in int(cfg.get("boulders_per_tile", 0)):
		var x := rng.randf() * 128.0
		var z := rng.randf() * 128.0
		if _spot(t, x, z, 0.72, false, water_level, rng) == Vector3.ZERO:
			continue
		var b := Basis.from_euler(Vector3(rng.randf_range(-0.15, 0.15), rng.randf() * TAU, rng.randf_range(-0.15, 0.15)))
		boulders.append(Transform3D(b, Vector3(x, height(t, x, z), z)))
	out["boulders"] = boulders
	return out


## Bilinear height inside tile data at local (x, z) metres.
static func height(t: Dictionary, x: float, z: float) -> float:
	var n := int(t["n"])
	var step := float(t["step"])
	var fx := clampf(x / step, 0.0, n - 1.001)
	var fz := clampf(z / step, 0.0, n - 1.001)
	var xi := int(fx)
	var zi := int(fz)
	var h: PackedFloat32Array = t["heights"]
	var i := zi * n + xi
	return lerpf(lerpf(h[i], h[i + 1], fx - xi), lerpf(h[i + n], h[i + n + 1], fx - xi), fz - zi)


static func _spot(t: Dictionary, x: float, z: float, steep: float, grassy: bool, water_level: float, rng: RandomNumberGenerator) -> Vector3:
	var n := int(t["n"])
	var k := clampi(int(roundf(z)), 0, n - 1) * n + clampi(int(roundf(x)), 0, n - 1)
	var s: PackedByteArray = t["splat"]
	if s[k * 4] > 60 or height(t, x, z) < water_level + 0.3:
		return Vector3.ZERO
	var nrm: Vector3 = (t["normals"] as PackedVector3Array)[k]
	if nrm.y < steep:
		return Vector3.ZERO
	if grassy and (rng.randf() < s[k * 4 + 3] / 255.0 * 0.8 or rng.randf() < s[k * 4 + 2] / 255.0 * 0.9 or rng.randf() < s[k * 4 + 1] / 255.0 * 0.5):
		return Vector3.ZERO
	return nrm


## The scatter nodes for one tile under `parent` (placed at the tile's corner), from plan().
static func build(parent: Node3D, plan_data: Dictionary, meshes: Dictionary, boulders: Array, density: float) -> void:
	for kind: String in KINDS:
		var spec: Array = KINDS[kind]
		var variants: Array = meshes[kind]
		var quarters: Array = plan_data[kind]
		for q in quarters.size():
			var buf: PackedFloat32Array = quarters[q]
			if buf.is_empty():
				continue
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = variants[(q + int(parent.position.x / 128.0) * 3 + int(parent.position.z / 128.0)) % variants.size()]
			mm.instance_count = buf.size() / 12
			mm.buffer = buf
			mm.visible_instance_count = int(mm.instance_count * density)
			var mmi := MultiMeshInstance3D.new()
			mmi.multimesh = mm
			mmi.set_meta("scatter", true)
			mmi.visibility_range_end = float(spec[0])
			mmi.visibility_range_end_margin = float(spec[0]) * 0.2
			mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if spec[3] else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			parent.add_child(mmi)
	var i := 0
	for xf: Transform3D in plan_data["boulders"]:
		var node := (boulders[i % boulders.size()] as Node3D).duplicate() as Node3D
		node.transform = xf
		parent.add_child(node)
		i += 1


## Kit meshes for each kind (a few variants each), and boulder prototypes (bodies to duplicate).
static func prototypes() -> Dictionary:
	var meshes := {}
	for kind: String in KINDS:
		var list: Array = []
		for v in (3 if kind != "shrub" else 6):
			var node := Kit.build(kind, v)
			list.append((node.get_node("Mesh") as MeshInstance3D).mesh)
			node.free()
		meshes[kind] = list
	var boulders: Array = []
	for v in 6:
		boulders.append(Kit.build("boulder", 100 + v))
	return {"meshes": meshes, "boulders": boulders}
