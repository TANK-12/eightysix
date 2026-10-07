extends "res://tests/lib/test_case.gd"
## Relay task 56 (2026-10-07): shell smoke made the GPU the bottleneck (an HE hit every 0.5 s: 17 -> 40 ms a
## frame). Clouds draw half their puffs, each bigger and more opaque, and thin further past a scene-wide budget.
## tools/bot/smoke_cost.json measures the frame cost on the real GPU; these check the arithmetic and the count.

var holder: Node3D


func before_each() -> void:
	holder = Node3D.new()
	tree.root.add_child(holder)


func after_each() -> void:
	holder.free()


func test_a_thinned_cloud_stays_as_dense() -> void:
	for a: float in [0.35, 0.6, 0.7]:
		var full := 1.0 - pow(1.0 - a, 10)
		var thin := 1.0 - pow(1.0 - CombatFx.thinned_alpha(a, 0.5), 5)
		assert_almost_eq(thin, full, 0.01, "5 puffs at the thinned alpha cover what 10 at %.2f did" % a)
	assert_eq(CombatFx.thinned_alpha(0.5, 1.0), 0.5, "a cloud kept whole keeps its alpha")
	assert_lt(CombatFx.thinned_alpha(0.85, 0.25), 0.951, "never fully opaque")


func test_clouds_thin_more_past_the_budget() -> void:
	assert_eq(CombatFx.smoke_share(20, 0), CombatFx.SMOKE_THIN, "a quiet scene draws SMOKE_THIN of the puffs")
	var busy := CombatFx.smoke_share(20, CombatFx.SMOKE_BUDGET)
	assert_almost_eq(busy, CombatFx.SMOKE_THIN * 0.5, 0.001, "past the budget, half again and no less")
	assert_between(CombatFx.smoke_share(20, CombatFx.SMOKE_BUDGET - 5), CombatFx.SMOKE_THIN * 0.5, CombatFx.SMOKE_THIN, "near the budget, in between")


func test_live_puffs_are_counted_in_and_out() -> void:
	var before := CombatFx._smoke_live
	var p := CombatFx.smoke(holder, Vector3.ZERO, Vector3.UP, 20, 2.0, Color(0.5, 0.45, 0.4, 0.7))
	assert_eq(p.amount, 10, "20 asked, 10 drawn")
	assert_gt(p.color_ramp.get_color(1).a, 0.7, "each puff more opaque")
	assert_eq(CombatFx._smoke_live, before + 10, "counted in when it enters the tree")
	p.free()
	assert_eq(CombatFx._smoke_live, before, "counted out when it leaves")


func test_smoke_is_lit_per_vertex() -> void:
	assert_eq(CombatFx.smoke_material().shading_mode, BaseMaterial3D.SHADING_MODE_PER_VERTEX, "corner lighting: same look, 5 ms less in a barrage")
