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


## Emerson's note 8 (2026-10-02): 12.7 mm hits on the ground made huge lag spikes. A bullet's hit reuses pooled
## emitters (no new nodes past the pool, no light) and its dust is sized for a bullet, well under a dart's.
func test_bullet_hits_reuse_a_pool_and_light_nothing() -> void:
	for i in 200:
		CombatFx.impact(holder, Vector3(i, 0, 0), Vector3.UP, i % 3 == 0, false, false)
	assert_lt(holder.get_child_count(), 2 * CombatFx.BULLET_POOL + 1, "200 bullets make no more than the two pools")
	for n: Node in holder.get_children():
		assert_false(n is OmniLight3D, "a bullet's hit lights nothing")
	var last := CombatFx.impact(holder, Vector3(5, 0, 5), Vector3.UP, false, false, false)
	assert_true((last[1] as CPUParticles3D).emitting, "a reused puff plays again")
	assert_almost_eq((last[1] as Node3D).global_position.x, 5.0, 0.01, "at the new hit, not where it last played")


func test_a_bullet_puff_is_far_smaller_than_a_dart_kick() -> void:
	Settings.set_value("fx.blast_size", 1.6, false)
	Settings.set_value("fx.hit_dust", 1.6, false)
	var bullet := CombatFx.impact(holder, Vector3.ZERO, Vector3.UP, false, false, false)
	var dart := CombatFx.impact(holder, Vector3.ZERO, Vector3.UP, false, false, true)
	assert_lt(_biggest_quad(bullet), _biggest_quad(dart) * 0.5, "a 45 g bullet raises under half a 1.2 kg dart's dust")
	assert_lt(_longest_life(bullet), 2.5, "and it settles in a couple of seconds")


## Emerson's note 14 (2026-10-02): his muzzle flashes looked weak. The 57 mm's is a flame tongue a couple of metres
## long with a strong light; the 12.7 mm's comes from a pool.
func test_the_57_mm_flash_is_a_flame_tongue_with_a_light() -> void:
	CombatFx.muzzle(holder, Vector3(0, 2.5, 0), Vector3.FORWARD)
	var flames := _named(holder.get_children(), "muzzle_flame")
	assert_eq(flames.size(), 1, "one flame")
	var f := flames[0] as CPUParticles3D
	var reach := f.initial_velocity_max * f.initial_velocity_max / (2.0 * f.damping_max)
	assert_gt(reach, 1.5, "the tongue reaches past 1.5 m")
	assert_lt(reach, 4.0, "and stays under 4 m")
	var lights := holder.get_children().filter(func(n: Node) -> bool: return n is OmniLight3D)
	assert_gt((lights[0] as OmniLight3D).omni_range, 15.0, "its light reaches the ground around the mech")


func test_machine_gun_flashes_come_from_the_pool() -> void:
	for i in 100:
		CombatFx.muzzle(holder, Vector3(i * 0.1, 2, 0), Vector3.FORWARD, 0.35)
	var flames := _named(holder.get_children(), "mg_flame")
	assert_lt(flames.size(), CombatFx.BULLET_POOL + 1, "100 shots, no more flames than the pool")


## Emerson's note 6 (2026-10-02): he could not tell where his shells landed. An HE ground burst throws a dirt
## column about 12 m up; shells get a bright tracer with a trail (Settings > Shell tracers), bullets keep theirs.
func test_an_he_ground_burst_throws_a_dirt_column() -> void:
	var nodes := _made(1.0, 1.0, false, true)
	var cols := _named(nodes, "dirt_column")
	assert_eq(cols.size(), 1, "a column of dirt")
	var c := cols[0] as CPUParticles3D
	var rise := c.initial_velocity_max * c.initial_velocity_max / (2.0 * c.damping_min)
	assert_gt(rise, 8.0, "it climbs past 8 m")
	assert_lt(rise, 20.0, "and under 20 m")
	assert_eq(_named(_made(1.0, 1.0, true, true), "dirt_column").size(), 0, "no dirt off steel")


## The width of each tracer box a round of `ammo` gets under Shell tracers `style`.
func _tracers(ammo: Dictionary, style: String) -> Array:
	Settings.set_value("fx.shell_tracer", style, false)
	var p := Projectile.spawn(holder, Vector3.ZERO, Vector3(0, 0, -1000), ammo, null, 1.0, [])
	var boxes := p.find_children("*", "MeshInstance3D", true, false).map(func(m: Node) -> float: return ((m as MeshInstance3D).mesh as BoxMesh).size.x)
	p.free()
	Settings.set_value("fx.shell_tracer", Settings.default_of("fx.shell_tracer"), false)
	return boxes


func test_shell_tracers_follow_the_setting() -> void:
	var dart: Dictionary = Registry.entry("weapons", "gun_57mm")["ammo"]["apfsds"]
	var ball: Dictionary = Registry.entry("weapons", "mg_12_7")["ammo"]["ball"]
	assert_eq(Settings.default_of("fx.shell_tracer"), "bright", "bright by default")
	var bright := _tracers(dart, "bright")
	var normal := _tracers(dart, "normal")
	assert_eq(bright.size(), 2, "bright: a head and a trail")
	assert_eq(normal.size(), 1, "normal: one tracer")
	assert_almost_eq(float(bright.max()) / float(normal[0]), 3.0, 0.01, "the bright head is three times as thick")
	assert_eq(_tracers(dart, "off").size(), 0, "off: none")
	assert_eq(_tracers(ball, "off").size(), 1, "a 12.7 mm bullet keeps its tracer whatever the setting")
