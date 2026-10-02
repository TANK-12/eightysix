class_name HangarStage
extends Node3D
## The Hangar's 3D stage (lane A4 part 7; PLAN "Show off the Juggernaut"): a lit hangar with the real
## Juggernaut standing in it under the same physics as in the field, an orbit camera, light presets
## from data/hangar.json and part picking (name and realistic mass). Used by the Hangar screen
## (scripts/ui/hangar.gd, the camera is the player's) and behind the main menu (scripts/ui/main_menu.gd,
## the camera sways slowly by itself). The mech is not a player mech, so no input drives it.

signal mech_changed(mech_id: String)
signal light_changed(light_id: String)

const WORLD_LAYER := 1
const MECH_LAYER := 2
const HITBOX_LAYER := 4
const CONCRETE := "res://assets/kit/textures/concrete/"
const HIGHLIGHT_COLOR := Color(1.0, 0.62, 0.12)

var mech: RigidBody3D
var mech_id := ""
var light_id := ""
var camera: Camera3D
var yaw := 0.0
var pitch := -0.2
var distance := 12.5
var focus_offset := Vector3.ZERO
## Share of the picture width the mech is moved to the right of centre (the Hangar's side panels, the menu's buttons).
var shift_x := 0.0
var showcase := false
var age_s := 0.0

var _cfg: Dictionary = {}
var _orbit: Dictionary = {}
var _menu: Dictionary = {}
var _env: Environment
var _env_node: WorldEnvironment
var _lights: Node3D
var _room: Node3D
var _grade_cache: Dictionary = {}
var _highlighted: Array[MeshInstance3D] = []
var _settle_s := 1.2
var _showcase_t := 0.0


func _ready() -> void:
	_cfg = Registry.file("hangar").get("stage", {})
	_orbit = _cfg.get("orbit", {})
	_menu = Registry.file("hangar").get("menu", {})
	_settle_s = float(_cfg.get("settle_s", 1.2))
	_build_room()
	_env = Environment.new()
	_env.background_mode = Environment.BG_COLOR
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.tonemap_mode = Environment.TONE_MAPPER_AGX
	_env.ssao_enabled = Settings.get_b("graphics.ssao")
	_env.glow_enabled = Settings.get_b("graphics.glow")
	_env.glow_intensity = 0.5
	_env.glow_hdr_threshold = 1.6
	_env_node = WorldEnvironment.new()
	_env_node.environment = _env
	add_child(_env_node)
	_lights = Node3D.new()
	_lights.name = "Lights"
	add_child(_lights)
	camera = Camera3D.new()
	camera.name = "HangarCamera"
	camera.fov = float(_orbit.get("fov_deg", 45.0))
	camera.near = 0.1
	camera.far = 160.0
	add_child(camera)
	camera.make_current()
	reset_view()
	set_light(Settings.get_s("hangar.light"))


## A new camera view: the start pose from hangar.json (or the menu's, when `showcase`).
func reset_view() -> void:
	focus_offset = Vector3.ZERO
	if showcase:
		yaw = deg_to_rad(float(_menu.get("yaw_deg", 150.0)))
		pitch = deg_to_rad(float(_menu.get("pitch_deg", -7.0)))
		distance = float(_menu.get("distance_m", 13.0))
		camera.fov = float(_menu.get("fov_deg", 42.0))
	else:
		yaw = deg_to_rad(float(_orbit.get("start_yaw_deg", 148.0)))
		pitch = deg_to_rad(float(_orbit.get("start_pitch_deg", -12.0)))
		distance = float(_orbit.get("start_distance_m", 12.5))
		camera.fov = float(_orbit.get("fov_deg", 45.0))
	_place_camera()


# --- the mech ----------------------------------------------------------------------------------


## Builds `id` standing on the floor (the one before is freed). Returns false if it cannot be built.
func set_mech(id: String) -> bool:
	if not MechBuilder.can_build(id):
		return false
	clear_highlight()
	if mech != null:
		remove_child(mech)
		mech.free()
		mech = null
	mech = MechBuilder.build(id)
	if mech == null:
		return false
	mech_id = id
	var def := Registry.entry("mechs", id)
	var stance: Dictionary = def.get("stance", {})
	mech.position = Vector3(0.0, float(stance.get("height_m", 2.3)) + 0.9, 0.0)
	mech.rotation.y = 0.0
	add_child(mech)
	age_s = 0.0
	mech.visible = false
	mech_changed.emit(id)
	return true


## True once the mech has had time to settle on its legs (it is hidden until then).
func settled() -> bool:
	return mech != null and age_s >= _settle_s


## Part ids with their masses for the current mech: [{id, label, kind, mass_kg, count}] in the mech's
## own order, identical parts (the four rams, say) folded into one row with a count.
func part_rows() -> Array:
	var def := Registry.entry("mechs", mech_id)
	var ids: Array = []
	for placement: Dictionary in def.get("parts", []):
		ids.append(str(placement["part"]))
	for leg_name: String in def.get("legs", {}):
		var leg: Dictionary = def["legs"][leg_name]
		for seg: String in ["upper", "lower", "foot"]:
			ids.append(str(leg[seg]))
		for act_id: String in leg.get("actuators", []):
			ids.append(str(act_id))
	var rows: Array = []
	for id: String in ids:
		var info := part_info(id)
		if float(info["mass_kg"]) <= 0.0:
			continue
		rows.append(info)
	return rows


## Total mass of the standing mech in kg (the physics body's, summed from its parts).
func total_mass_kg() -> float:
	return mech.mass if mech != null else 0.0


## What the Hangar shows about a part: label, kind, group, mass, health, armour and the mass note.
func part_info(part_id: String) -> Dictionary:
	var part := Registry.entry("parts", part_id)
	var kind := str(part.get("kind", "other"))
	return {
		"id": part_id,
		"label": short_label(str(part.get("label", part_id))),
		"kind": kind,
		"group": group_of(kind),
		"mass_kg": float(part.get("mass_kg", 0.0)),
		"health": float(part.get("health", 0.0)),
		"armour_mm": float(part.get("armour_mm", 0.0)),
		"note": str(part.get("mass_note", "")),
	}


## "Juggernaut Model 2: canopy" or "Juggernaut Model 2 thigh (FR)" -> "Canopy", "Thigh (FR)".
static func short_label(label: String) -> String:
	var text := label
	if text.begins_with("Juggernaut Model 2"):
		text = text.trim_prefix("Juggernaut Model 2").trim_prefix(":").strip_edges()
	if text == "":
		return label
	# "sidepanel.R" -> "sidepanel (R)", "pod_tub" -> "pod tub"
	var side := RegEx.create_from_string("\\.([A-Za-z]{1,2})$").search(text)
	if side != null:
		text = text.substr(0, side.get_start()) + " (" + side.get_string(1) + ")"
	text = text.replace("_", " ")
	return text.substr(0, 1).to_upper() + text.substr(1)


## The Hangar's group for a part kind (hangar.json "groups": {id: {label, kinds}}); "other" when unlisted.
static func group_of(kind: String) -> String:
	var groups: Dictionary = Registry.file("hangar").get("groups", {})
	for id: String in groups:
		if kind in (groups[id] as Dictionary).get("kinds", []):
			return id
	return "other"


## The standing mech's size from its model meshes, in metres (x width, y height, z length); zero before it settles.
func model_size() -> Vector3:
	if mech == null:
		return Vector3.ZERO
	var box := AABB()
	var first := true
	for node: Node in mech.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null or not _is_model_mesh(mi):
			continue
		var b := mi.global_transform * mi.get_aabb()
		box = b if first else box.merge(b)
		first = false
	return box.size


# --- picking -----------------------------------------------------------------------------------


## The part under a point of the viewport, as part_info() plus "shape": the CollisionShape3D; {} when none.
func pick(screen_point: Vector2) -> Dictionary:
	if mech == null or camera == null or not camera.is_inside_tree():
		return {}
	var from := camera.project_ray_origin(screen_point)
	var to := from + camera.project_ray_normal(screen_point) * 80.0
	var query := PhysicsRayQueryParameters3D.create(from, to, MECH_LAYER | HITBOX_LAYER)
	query.collide_with_areas = true
	var hit := camera.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return {}
	var body := hit["collider"] as CollisionObject3D
	if body == null:
		return {}
	var owner_id := body.shape_find_owner(int(hit["shape"]))
	var shape := body.shape_owner_get_owner(owner_id) as CollisionShape3D
	if shape == null or not shape.has_meta("part_id"):
		return {}
	var info := part_info(str(shape.get_meta("part_id")))
	info["shape"] = shape
	info["point"] = hit["position"]
	return info


## Lights the mesh of `part_id` in amber (every copy of it: both blades, the four rams). Returns how many meshes lit.
func highlight(part_id: String) -> int:
	clear_highlight()
	if mech == null:
		return 0
	var part := Registry.entry("parts", part_id)
	var collider: Variant = part.get("collider")
	var names: Array = []
	if collider is Dictionary and (collider as Dictionary).has("hulls_from"):
		names.append(_flat_name(str((collider as Dictionary)["hulls_from"])))
	var overlay := StandardMaterial3D.new()
	overlay.albedo_color = Color(HIGHLIGHT_COLOR, 0.55)
	overlay.emission_enabled = true
	overlay.emission = HIGHLIGHT_COLOR
	overlay.emission_energy_multiplier = 1.4
	overlay.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	overlay.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	for node: Node in mech.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null or not _is_model_mesh(mi):
			continue
		if _flat_name(mi.name) in names:
			mi.material_overlay = overlay
			_highlighted.append(mi)
	return _highlighted.size()


func clear_highlight() -> void:
	for mi in _highlighted:
		if is_instance_valid(mi):
			mi.material_overlay = null
	_highlighted.clear()


func highlighted_count() -> int:
	return _highlighted.size()


## The glb's node names turn "." into "_" on import, and the parts' "hulls_from" keep it.
static func _flat_name(text: String) -> String:
	return text.replace(".", "_").to_lower()


## The placeholder box meshes ("Mesh_*", "Leg_*") are hidden; the model's own meshes are not.
static func _is_model_mesh(mi: MeshInstance3D) -> bool:
	return not (mi.name.begins_with("Mesh_") or mi.name.begins_with("Leg_"))


# --- the camera --------------------------------------------------------------------------------


func orbit(d_yaw: float, d_pitch: float) -> void:
	yaw += d_yaw
	pitch = clampf(pitch + d_pitch, deg_to_rad(float(_orbit.get("min_pitch_deg", -80.0))), deg_to_rad(float(_orbit.get("max_pitch_deg", 25.0))))
	_place_camera()


func zoom(factor: float) -> void:
	distance = clampf(distance * factor, float(_orbit.get("min_distance_m", 3.5)), float(_orbit.get("max_distance_m", 24.0)))
	_place_camera()


## Moves the point the camera circles, in the camera's ground plane, within max_pan_m of the mech.
func pan(right: float, up: float) -> void:
	var basis := Basis(Vector3.UP, yaw)
	focus_offset += basis * Vector3(right, 0.0, 0.0) + Vector3.UP * up
	focus_offset = focus_offset.limit_length(float(_orbit.get("max_pan_m", 4.0)))
	_place_camera()


func focus_point() -> Vector3:
	var f: Array = (_menu if showcase else _orbit).get("focus", [0.0, 1.7, 0.0])
	return Vector3(float(f[0]), float(f[1]), float(f[2])) + focus_offset


func _place_camera() -> void:
	if camera == null:
		return
	var f := focus_point()
	var offset := Basis(Vector3.UP, yaw) * (Basis(Vector3.RIGHT, pitch) * Vector3(0.0, 0.0, distance))
	camera.global_position = f + offset
	camera.look_at(f, Vector3.UP)
	# Moving the whole camera sideways (not turning it) keeps the picture undistorted: the mech
	# lands `shift_x` of the picture width right of centre.
	if shift_x != 0.0:
		var aspect := 16.0 / 9.0
		var vp := get_viewport()
		if vp != null and vp.get_visible_rect().size.y > 0.0:
			aspect = vp.get_visible_rect().size.x / vp.get_visible_rect().size.y
		var width := 2.0 * distance * tan(deg_to_rad(camera.fov) * 0.5) * aspect
		camera.global_position -= camera.global_basis.x * shift_x * width


func _process(delta: float) -> void:
	if mech == null:
		return
	age_s += delta
	if not mech.visible and age_s >= _settle_s:
		mech.visible = true
	if showcase:
		_showcase_t += delta
		var period := maxf(float(_menu.get("period_s", 48.0)), 1.0)
		var base := deg_to_rad(float(_menu.get("yaw_deg", 150.0)))
		yaw = base + deg_to_rad(float(_menu.get("sway_deg", 26.0))) * sin(_showcase_t * TAU / period)
		_place_camera()


# --- light presets -----------------------------------------------------------------------------


func light_ids() -> PackedStringArray:
	return Registry.ids("hangar")


## Switches to light preset `id` (falls back to the first one when unknown). Returns the id used.
func set_light(id: String) -> String:
	var ids := light_ids()
	if ids.is_empty():
		return ""
	if not id in ids:
		id = ids[0]
	var def := Registry.entry("hangar", id)
	for child in _lights.get_children():
		_lights.remove_child(child)
		child.queue_free()
	var bg := Color(str(def.get("background", "#000000")))
	_env.background_color = bg
	var amb: Dictionary = def.get("ambient", {})
	_env.ambient_light_color = Color(str(amb.get("color", "#202020")))
	_env.ambient_light_energy = float(amb.get("energy", 0.5))
	_env.tonemap_exposure = float(def.get("exposure", 1.0)) * Settings.get_f("graphics.brightness")
	var fog: Dictionary = def.get("fog", {})
	_env.fog_enabled = not fog.is_empty()
	if _env.fog_enabled:
		_env.fog_light_color = Color(str(fog.get("color", "#101820")))
		_env.fog_density = float(fog.get("density", 0.01))
	var grade: Dictionary = def.get("grade", {})
	if grade.is_empty():
		_env.adjustment_enabled = false
	else:
		_env.adjustment_enabled = true
		_env.adjustment_color_correction = _grade_lut(id, grade)
	var shadows := Settings.get_f("graphics.shadow_distance") > 0.0
	for spec: Dictionary in def.get("lights", []):
		_add_light(spec, shadows)
	light_id = id
	light_changed.emit(id)
	return id


func _grade_lut(id: String, grade: Dictionary) -> Texture3D:
	if not _grade_cache.has(id):
		_grade_cache[id] = FilmGrade.lut(grade)
	return _grade_cache[id]


func _add_light(spec: Dictionary, shadows: bool) -> void:
	var kind := str(spec.get("kind", "omni"))
	var light: Light3D
	match kind:
		"spot":
			var spot := SpotLight3D.new()
			spot.spot_range = float(spec.get("range", 30.0))
			spot.spot_angle = float(spec.get("angle", 40.0))
			spot.spot_angle_attenuation = 0.8
			light = spot
		"sun":
			var sun := DirectionalLight3D.new()
			sun.directional_shadow_max_distance = 60.0
			light = sun
		_:
			var omni := OmniLight3D.new()
			omni.omni_range = float(spec.get("range", 20.0))
			light = omni
	light.light_color = Color(str(spec.get("color", "#ffffff")))
	light.light_energy = float(spec.get("energy", 1.0))
	light.shadow_enabled = bool(spec.get("shadow", false)) and shadows
	light.position = _vec(spec.get("at", [0, 0, 0]))
	_lights.add_child(light)
	if kind == "sun":
		light.look_at(light.position + _vec(spec.get("look", [0, -1, 0])), Vector3.UP)
	elif spec.has("look"):
		light.look_at(_vec(spec["look"]), Vector3.UP)
	if bool(spec.get("lamp", false)):
		_add_lamp(spec, light.light_color)


## A glowing fixture where a lamp light hangs, so the light has a visible source.
func _add_lamp(spec: Dictionary, color: Color) -> void:
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(2.4, 0.18, 0.5)
	mi.mesh = box
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 2.2
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mi.material_override = mat
	mi.position = _vec(spec.get("at", [0, 0, 0]))
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_lights.add_child(mi)
	if spec.has("look"):
		mi.look_at(_vec(spec["look"]), Vector3.UP)


# --- the room ----------------------------------------------------------------------------------


func _build_room() -> void:
	var room_cfg: Dictionary = _cfg.get("room", {})
	var w := float(room_cfg.get("width_m", 40.0))
	var l := float(room_cfg.get("length_m", 52.0))
	var h := float(room_cfg.get("height_m", 15.0))
	_room = Node3D.new()
	_room.name = "Room"
	add_child(_room)
	var floor_mat := _concrete(Color(0.55, 0.56, 0.58), 0.62, Vector3(w, l, 1.0) / 6.0)
	var wall_mat := _concrete(Color(0.34, 0.36, 0.39), 0.85, Vector3(l, h, 1.0) / 6.0)
	var steel := StandardMaterial3D.new()
	steel.albedo_color = Color(0.2, 0.21, 0.23)
	steel.metallic = 0.6
	steel.roughness = 0.5
	# floor: a thick slab on the world layer, its top face at y = 0
	var slab := StaticBody3D.new()
	slab.name = "Floor"
	slab.collision_layer = WORLD_LAYER
	slab.collision_mask = 0
	var slab_shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(w, 1.0, l)
	slab_shape.shape = box
	slab_shape.position = Vector3(0.0, -0.5, 0.0)
	slab.add_child(slab_shape)
	_room.add_child(slab)
	_box(Vector3(w, 0.2, l), Vector3(0, -0.1, 0), floor_mat)
	# walls and ceiling (visual only); the +z wall has the big door opening (the "background" shows through)
	_box(Vector3(w, h, 0.6), Vector3(0, h / 2.0, -l / 2.0), wall_mat)
	_box(Vector3(0.6, h, l), Vector3(-w / 2.0, h / 2.0, 0), wall_mat)
	_box(Vector3(0.6, h, l), Vector3(w / 2.0, h / 2.0, 0), wall_mat)
	_box(Vector3(w, 0.6, l), Vector3(0, h + 0.3, 0), wall_mat)
	var door_w := 16.0
	var door_h := 10.0
	var side := (w - door_w) / 2.0
	_box(Vector3(side, h, 0.6), Vector3(-(door_w + side) / 2.0, h / 2.0, l / 2.0), wall_mat)
	_box(Vector3(side, h, 0.6), Vector3((door_w + side) / 2.0, h / 2.0, l / 2.0), wall_mat)
	_box(Vector3(door_w, h - door_h, 0.6), Vector3(0, door_h + (h - door_h) / 2.0, l / 2.0), wall_mat)
	# ceiling trusses and wall ribs: the steel that gives the room its scale
	for i in 7:
		var z := -l / 2.0 + 4.0 + float(i) * (l - 8.0) / 6.0
		_box(Vector3(w, 0.5, 0.5), Vector3(0, h - 0.4, z), steel)
		_box(Vector3(0.6, h, 0.7), Vector3(-w / 2.0 + 0.5, h / 2.0, z), steel)
		_box(Vector3(0.6, h, 0.7), Vector3(w / 2.0 - 0.5, h / 2.0, z), steel)
	_floor_markings(w, l)


func _floor_markings(w: float, l: float) -> void:
	var yellow := StandardMaterial3D.new()
	yellow.albedo_color = Color(0.78, 0.6, 0.12)
	yellow.roughness = 0.7
	var white := StandardMaterial3D.new()
	white.albedo_color = Color(0.7, 0.7, 0.68)
	white.roughness = 0.7
	# the bay: a yellow rectangle round the Juggernaut, white centre line to the door
	for edge: Array in [[Vector3(14.0, 0.02, 0.18), Vector3(0, 0.01, -7.0)], [Vector3(14.0, 0.02, 0.18), Vector3(0, 0.01, 7.0)], [Vector3(0.18, 0.02, 14.0), Vector3(-7.0, 0.01, 0)], [Vector3(0.18, 0.02, 14.0), Vector3(7.0, 0.01, 0)]]:
		_box(edge[0], edge[1], yellow)
	_box(Vector3(0.2, 0.02, l / 2.0 - 7.0), Vector3(0, 0.01, 7.0 + (l / 2.0 - 7.0) / 2.0), white)
	_box(Vector3(0.2, 0.02, l / 2.0 - 7.0), Vector3(0, 0.01, -7.0 - (l / 2.0 - 7.0) / 2.0), white)
	# hazard stripes along the side walls
	for sx: float in [-1.0, 1.0]:
		_box(Vector3(0.5, 0.02, l - 2.0), Vector3(sx * (w / 2.0 - 1.4), 0.01, 0), yellow)


func _box(size: Vector3, at: Vector3, mat: Material) -> void:
	var mi := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mi.mesh = box
	mi.material_override = mat
	mi.position = at
	_room.add_child(mi)


func _concrete(tint: Color, roughness: float, uv_scale: Vector3) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = tint
	mat.roughness = roughness
	mat.uv1_triplanar = true
	mat.uv1_scale = uv_scale
	var color_path := CONCRETE + "color.jpg"
	if ResourceLoader.exists(color_path):
		mat.albedo_texture = load(color_path)
		mat.normal_enabled = true
		mat.normal_texture = load(CONCRETE + "normal.jpg")
		mat.roughness_texture = load(CONCRETE + "roughness.jpg")
	return mat


static func _vec(a: Variant) -> Vector3:
	var list: Array = a
	return Vector3(float(list[0]), float(list[1]), float(list[2]))
