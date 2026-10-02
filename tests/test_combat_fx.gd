extends "res://tests/lib/test_case.gd"
## Emerson's ask (2026-10-02): bigger 57 mm explosions on a slider, and bigger, longer hit dust. Both are
## look only: CombatFx makes particles, lights and meshes, never bodies or areas, so damage and push stay
## where the ammo data puts them.

const KEYS := ["fx.blast_size", "fx.hit_dust"]

var holder: Node3D


func before_each() -> void:
	holder = Node3D.new()
	tree.root.add_child(holder)


func after_each() -> void:
	for key: String in KEYS:
		Settings.set_value(key, Settings.default_of(key), false)
	holder.free()


func _made(blast: float, dust: float, metal: bool, big: bool) -> Array:
	Settings.set_value("fx.blast_size", blast, false)
	Settings.set_value("fx.hit_dust", dust, false)
	return CombatFx.impact(holder, Vector3.ZERO, Vector3.UP, metal, big)


static func _named(nodes: Array, fx: String) -> Array:
	return nodes.filter(func(n: Node) -> bool: return str(n.get_meta("fx", "")) == fx)


static func _biggest_quad(nodes: Array) -> float:
	var best := 0.0
	for n: Node in nodes:
		if n is CPUParticles3D and (n as CPUParticles3D).mesh is QuadMesh:
			best = maxf(best, ((n as CPUParticles3D).mesh as QuadMesh).size.x)
	return best


static func _longest_life(nodes: Array) -> float:
	var best := 0.0
	for n: Node in nodes:
		if n is CPUParticles3D:
			best = maxf(best, (n as CPUParticles3D).lifetime)
	return best


func test_sliders_exist_and_default_bigger_than_before() -> void:
	for key: String in KEYS:
		assert_true(Settings.has_key(key), "%s is a setting" % key)
		assert_eq(Settings.item(key).get("type"), "slider", "%s is a slider" % key)
		assert_gt(float(Settings.default_of(key)), 1.0, "%s starts bigger than the old look (1.0)" % key)


func test_blast_size_scales_the_shell_explosion() -> void:
	var small := _made(1.0, 1.0, false, true)
	var fire_small := _named(small, "fireball")
	assert_eq(fire_small.size(), 1, "an HE hit has a fireball")
	var r1 := ((fire_small[0] as CPUParticles3D).mesh as QuadMesh).size.x
	var big := _made(2.0, 1.0, false, true)
	var r2 := (((_named(big, "fireball")[0]) as CPUParticles3D).mesh as QuadMesh).size.x
	assert_almost_eq(r2 / r1, 2.0, 0.01, "twice the slider, twice the fireball")
	var light1 := (_named(small, "flash")[0] as OmniLight3D).omni_range
	var light2 := (_named(big, "flash")[0] as OmniLight3D).omni_range
	assert_almost_eq(light2 / light1, 2.0, 0.01, "and twice the flash's reach")


func test_hit_dust_is_bigger_and_lasts_longer() -> void:
	var low := _made(1.0, 1.0, false, false)
	var high := _made(1.0, 2.0, false, false)
	assert_almost_eq(_biggest_quad(high) / _biggest_quad(low), 2.0, 0.01, "dust puffs grow with the slider")
	assert_gt(_longest_life(high), _longest_life(low) * 1.4, "and hang in the air longer")
	var shell_low := _made(1.0, 1.0, false, true)
	var shell_high := _made(1.0, 2.0, false, true)
	assert_gt(_named(shell_high, "clods").size(), 0, "a shell on the ground throws clods of dirt")
	assert_gt(_longest_life(shell_high), _longest_life(shell_low) * 1.4, "a shell's dust column lasts longer too")


func test_a_dart_on_the_ground_kicks_dirt_but_no_fire() -> void:
	Settings.set_value("fx.blast_size", 1.0, false)
	Settings.set_value("fx.hit_dust", 1.0, false)
	var dart := CombatFx.impact(holder, Vector3.ZERO, Vector3.UP, false, false, true)
	assert_eq(_named(dart, "fireball").size(), 0, "a solid round has nothing to burn")
	assert_eq(_named(dart, "clods").size(), 1, "but throws dirt off the ground")
	var bullet := CombatFx.impact(holder, Vector3.ZERO, Vector3.UP, false, false, false)
	assert_eq(_named(bullet, "clods").size(), 0, "a 12.7 mm bullet does not")
	Settings.set_value("fx.blast_size", 2.0, false)
	var bigger := CombatFx.impact(holder, Vector3.ZERO, Vector3.UP, false, false, true)
	assert_almost_eq(_biggest_quad(bigger) / _biggest_quad(dart), 2.0, 0.01, "the dart's dirt kick follows Shell hit size")
	var on_steel := CombatFx.impact(holder, Vector3.ZERO, Vector3.UP, true, false, true)
	assert_eq(_named(on_steel, "clods").size(), 0, "no dirt off steel")


func test_effects_are_look_only() -> void:
	for nodes: Array in [_made(3.0, 3.0, false, true), _made(3.0, 3.0, true, true), _made(3.0, 3.0, false, false)]:
		for n: Node in nodes:
			assert_false(n is PhysicsBody3D or n is Area3D, "%s is not a body or area: no extra damage or push" % n.name)
