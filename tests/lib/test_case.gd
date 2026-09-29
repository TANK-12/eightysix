extends RefCounted
## Base for the project's own tests. The assert names match GUT's (assert_eq, assert_almost_eq,
## assert_true ...) so switching to GUT later only means changing `extends` to GutTest.

var failures: PackedStringArray = []
var asserts := 0
var tree: SceneTree


func before_all() -> void:
	pass


func before_each() -> void:
	pass


func after_each() -> void:
	pass


func after_all() -> void:
	pass


func _fail(text: String, msg: String) -> void:
	failures.append(text + ((" (" + msg + ")") if msg != "" else ""))


func assert_true(v: bool, msg: String = "") -> void:
	asserts += 1
	if not v:
		_fail("expected true", msg)


func assert_false(v: bool, msg: String = "") -> void:
	asserts += 1
	if v:
		_fail("expected false", msg)


func assert_eq(got: Variant, want: Variant, msg: String = "") -> void:
	asserts += 1
	if not _equal(got, want):
		_fail("expected %s, got %s" % [str(want), str(got)], msg)


func assert_ne(got: Variant, other: Variant, msg: String = "") -> void:
	asserts += 1
	if _equal(got, other):
		_fail("expected anything but %s" % str(other), msg)


func assert_almost_eq(got: Variant, want: Variant, tolerance: Variant, msg: String = "") -> void:
	asserts += 1
	var ok := false
	if got is Vector3:
		ok = ((got as Vector3) - (want as Vector3)).length() <= float(tolerance)
	else:
		ok = absf(float(got) - float(want)) <= float(tolerance)
	if not ok:
		_fail("expected %s ± %s, got %s" % [str(want), str(tolerance), str(got)], msg)


func assert_between(got: float, low: float, high: float, msg: String = "") -> void:
	asserts += 1
	if got < low or got > high:
		_fail("expected %s between %s and %s" % [str(got), str(low), str(high)], msg)


func assert_gt(got: float, than: float, msg: String = "") -> void:
	asserts += 1
	if not got > than:
		_fail("expected %s > %s" % [str(got), str(than)], msg)


func assert_lt(got: float, than: float, msg: String = "") -> void:
	asserts += 1
	if not got < than:
		_fail("expected %s < %s" % [str(got), str(than)], msg)


func assert_has(container: Variant, item: Variant, msg: String = "") -> void:
	asserts += 1
	var found := false
	if container is Dictionary:
		found = (container as Dictionary).has(item)
	elif container is Array or container is PackedStringArray:
		found = item in container
	elif container is String:
		found = (container as String).contains(str(item))
	if not found:
		_fail("%s does not contain %s" % [str(container).left(120), str(item)], msg)


func assert_not_null(v: Variant, msg: String = "") -> void:
	asserts += 1
	if v == null:
		_fail("expected a value, got null", msg)


func fail_test(msg: String) -> void:
	asserts += 1
	_fail("failed", msg)


func physics_frames(count: int) -> void:
	for i in count:
		await tree.physics_frame


static func _equal(a: Variant, b: Variant) -> bool:
	if (a is float or a is int) and (b is float or b is int):
		return is_equal_approx(float(a), float(b))
	return typeof(a) == typeof(b) and a == b
