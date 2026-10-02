class_name Squad
extends Node
## The player's squad (lane A5): allied Juggernauts from data/squad.json, spawned in formation beside the
## player when a level registers (Game.register_level calls Squad.attach), up to Settings gameplay.squad_size.
## Each member is a full physics Juggernaut with a SquadPilot. Orders come from the order keys (1 follow,
## 2 hold, 3 attack, 4 regroup) in the field and in the Handler view (a pad's d-pad there only), to the whole
## squad or the one member picked with select next / previous. The Handler view (Tab) is its command screen.

signal order_given(kind: String, who: String)

const SPAWN_LIFT_M := 3.2  # dropped onto its legs from this high, as the player's mech is
const TOAST_S := 2.5
const ORDER_ACTIONS := {"order_follow": "follow", "order_hold": "hold", "order_attack": "attack", "order_regroup": "regroup"}
const ORDER_WORDS := {"follow": "follow me", "hold": "hold position", "attack": "attack", "regroup": "regroup on me", "move": "move to the marked point"}

var leader: RigidBody3D
var level: Node
var members: Array[RigidBody3D] = []
var pilots: Array[SquadPilot] = []
var selected := -1  # -1: the whole squad; otherwise one member's index
var last_order := "follow"
var handler: HandlerView
var _toast: Label
var _toast_s := 0.0


## Builds the squad for a level that has a player "mech", unless the map turns squads off ("squad": false in
## data/maps.json, e.g. the test benches) or gameplay.squad_size is 0. Returns null when there is none.
static func attach(level_node: Node) -> Squad:
	if level_node == null or not ("mech" in level_node) or level_node.get("mech") == null:
		return null
	var map_id := Game.pending_map
	if Registry.has_entry("maps", map_id) and not bool(Registry.entry("maps", map_id).get("squad", true)):
		return null
	var count := int(Settings.get_f("gameplay.squad_size")) if Settings.has_key("gameplay.squad_size") else 0
	if count <= 0:
		return null
	var s := Squad.new()
	s.name = "Squad"
	s.level = level_node
	s.leader = level_node.get("mech") as RigidBody3D
	level_node.add_child(s)
	s.spawn(count)
	return s


func _ready() -> void:
	add_to_group("squad")
	if level == null:
		level = get_parent()
	handler = HandlerView.new()
	handler.squad = self
	add_child(handler)
	var layer := CanvasLayer.new()
	layer.layer = 5
	add_child(layer)
	_toast = Label.new()
	_toast.name = "OrderToast"
	_toast.anchor_left = 0.5
	_toast.anchor_right = 0.5
	_toast.anchor_top = 0.72
	_toast.anchor_bottom = 0.72
	_toast.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_toast.add_theme_font_size_override("font_size", 22)
	_toast.add_theme_color_override("font_color", Color(0.85, 0.95, 1.0))
	_toast.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	_toast.add_theme_constant_override("outline_size", 6)
	_toast.visible = false
	layer.add_child(_toast)


## Spawns the first `count` squad entries in their formation slots round the leader.
func spawn(count: int) -> void:
	var ids := Registry.ids("squad")
	var yaw := Basis(Vector3.UP, SquadPilot._yaw(leader.global_transform.basis))
	for i in mini(count, ids.size()):
		var id := ids[i]
		var e := Registry.entry("squad", id)
		var mech_id := str(e.get("mech", "juggernaut_m2"))
		if not MechBuilder.can_build(mech_id):
			push_warning("Squad: %s's mech '%s' cannot be built" % [id, mech_id])
			continue
		var m := MechBuilder.build(mech_id)
		m.set("is_player", false)
		m.name = "Squad_" + id
		m.set_meta("squad_id", id)
		m.add_to_group("squad_mech")
		var slot: Array = e.get("slot", [0.0, 0.0, 15.0])
		var at := leader.global_position + yaw * Vector3(float(slot[0]), 0.0, float(slot[2]))
		var ground := at.y - SPAWN_LIFT_M
		if level.has_method("ground_height"):
			ground = float(level.call("ground_height", at.x, at.z))
		m.position = Vector3(at.x, ground + SPAWN_LIFT_M, at.z)
		m.basis = yaw
		var pilot := SquadPilot.new()
		pilot.setup(id, m, self)
		m.add_child(pilot)
		level.add_child(m)
		members.append(m)
		pilots.append(pilot)


func callsign(index: int) -> String:
	return str(Registry.entry("squad", pilots[index].id).get("callsign", pilots[index].id))


## Who the next order goes to: the picked member, or every living one.
func addressed() -> Array[SquadPilot]:
	var out: Array[SquadPilot] = []
	for i in pilots.size():
		if (selected < 0 or selected == i) and pilots[i].alive():
			out.append(pilots[i])
	return out


## Gives an order ("follow", "hold", "move", "regroup", "attack") to the addressed members. "move" needs a
## point; "attack" picks the Legion nearest the leader's gun line when no target is given.
func give_order(kind: String, point: Variant = null, what: Node3D = null) -> void:
	if kind == "attack" and what == null:
		what = aimed_legion()
		if what == null:
			_show("No Legion in sight to attack")
			return
	for p: SquadPilot in addressed():
		p.give(kind, point, what)
	last_order = kind
	var who := "Squad" if selected < 0 else callsign(selected)
	_show("%s: %s" % [who, ORDER_WORDS.get(kind, kind)])
	order_given.emit(kind, who)


## The Legion closest to the leader's heading (within 25 degrees, 1500 m) that anyone in the squad can see.
func aimed_legion() -> Node3D:
	var best: Node3D = null
	var best_angle := deg_to_rad(25.0)
	var fwd := SquadPilot._flat(-leader.global_transform.basis.z).normalized()
	for n: Node in get_tree().get_nodes_in_group("legion"):
		var u := n as Node3D
		if not SquadPilot._legion_alive(u):
			continue
		var to := SquadPilot._flat(u.global_position - leader.global_position)
		if to.length() > 1500.0 or not seen(u):
			continue
		var angle := fwd.angle_to(to.normalized())
		if angle < best_angle:
			best = u
			best_angle = angle
	return best


## Whether any living squad member has a clear line of sight to `u` (what the Handler view may show).
func seen(u: Node3D) -> bool:
	for p: SquadPilot in pilots:
		if p.alive() and p.can_see(u):
			return true
	return false


## One row per member for the mission summary: callsign, whether it is still fighting, armour left (0-1), 57 mm shots.
func report() -> Array:
	var out: Array = []
	for i in pilots.size():
		var p := pilots[i]
		var combat := p.mech.get_node_or_null("Combat") if is_instance_valid(p.mech) else null
		var armour := float(combat.damage.total_fraction()) if combat != null and combat.get("damage") != null else 0.0
		out.append({"callsign": callsign(i), "alive": p.alive(), "armour": snappedf(armour, 0.01), "shots": p.shots})
	return out


func select_next(step: int) -> void:
	var n := pilots.size()
	if n == 0:
		return
	selected = posmod(selected + 1 + step, n + 1) - 1
	_show("Orders to: " + ("whole squad" if selected < 0 else callsign(selected)))


func _show(text: String) -> void:
	_toast.text = text
	_toast.visible = true
	_toast_s = TOAST_S


func _process(delta: float) -> void:
	if _toast_s > 0.0:
		_toast_s -= delta
		if _toast_s <= 0.0:
			_toast.visible = false


func _unhandled_input(event: InputEvent) -> void:
	if Game.is_paused() or Game.is_photo() or pilots.is_empty():
		return
	# A pad's d-pad and L1/R1 already work the grapple and the view in the field, so on a pad the orders
	# only go out from the Handler view; the keyboard's 1-4 work everywhere.
	if not handler.is_open and not event is InputEventKey and not event.is_action_pressed("handler_view"):
		return
	if event.is_action_pressed("handler_view"):
		get_viewport().set_input_as_handled()
		handler.toggle()
		return
	for action: String in ORDER_ACTIONS:
		if event.is_action_pressed(action):
			get_viewport().set_input_as_handled()
			give_order(ORDER_ACTIONS[action])
			return
	if event.is_action_pressed("order_select_next"):
		select_next(1)
	elif event.is_action_pressed("order_select_prev"):
		select_next(-1)
