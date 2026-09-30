class_name LegRams
extends RefCounted
## A leg's hydraulic rams (lane A2 part 5; Emerson: "a charged jump separates the pistons from the
## legs"). In the model each knee ram's cylinder is mounted on the thigh and its rod on the shin, and
## they aim at each other (B1's ram_*_tgt track constraints). The game moves the legs by IK, so each
## frame a ram part rides its segment to its mount, then turns about that mount to aim at the other
## part's mount: the rod slides in the cylinder instead of the two coming apart.


## `rest`: the part's rest transform in the body. `carry` / `carry_scaled`: how its segment moved
## (now * rest^-1), without and with the leg-length stretch. `mount` / `aim`: its own mount and the
## other part's mount at rest (body frame); `aim_now`: where that other mount is now.
static func pose(rest: Transform3D, carry: Transform3D, carry_scaled: Transform3D, mount: Vector3, aim: Vector3, aim_now: Vector3) -> Transform3D:
	var xf := carry * rest
	var mount_now := carry_scaled * mount
	xf.origin += mount_now - carry * mount
	var had := (carry.basis * (aim - mount)).normalized()
	var want := (aim_now - mount_now).normalized()
	if had.length() < 0.5 or want.length() < 0.5:
		return xf
	var turn := Basis(Quaternion(had, want))
	return Transform3D(turn, mount_now - turn * mount_now) * xf
