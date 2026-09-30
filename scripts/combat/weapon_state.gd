class_name WeaponState
extends RefCounted
## One weapon's magazine, reserve, reload and rate of fire, from its data/weapons.json entry. Pure
## logic (no nodes), so the rules are unit-tested on their own: a shot needs a round in the magazine
## and the breech cycled; an empty magazine starts the reload by itself; "Next ammunition type"
## swaps the magazine for the new type (a reload), because a loaded round cannot change type.
## Reserve rounds are shared by every type; gameplay.ammo "unlimited" never empties the reserve.

var id := ""
var def: Dictionary = {}
var magazine := 0
var magazine_size := 0
var reserve := 0
var unlimited := false
var ammo_types: PackedStringArray = []
var loaded_ammo := ""
var selected_ammo := ""

var _cycle_left := 0.0
var _reload_left := -1.0


func _init(weapon_id: String, weapon_def: Dictionary, unlimited_reserve: bool = false) -> void:
	id = weapon_id
	def = weapon_def
	magazine_size = int(def.get("magazine", 1))
	magazine = magazine_size
	reserve = int(def.get("reserve", 0))
	unlimited = unlimited_reserve
	ammo_types = PackedStringArray((def.get("ammo", {}) as Dictionary).keys())
	loaded_ammo = str(def.get("default_ammo", ammo_types[0] if ammo_types.size() > 0 else ""))
	selected_ammo = loaded_ammo


func reloading() -> bool:
	return _reload_left >= 0.0


## 0 while not reloading, then rises to 1 as the reload finishes.
func reload_fraction() -> float:
	if not reloading():
		return 0.0
	return 1.0 - _reload_left / maxf(float(def.get("reload_s", 1.0)), 0.001)


func can_fire() -> bool:
	return magazine > 0 and _cycle_left <= 0.0 and not reloading()


## The round's ammo entry (plus "id"), or {} when the weapon cannot fire this tick.
func fire() -> Dictionary:
	if not can_fire():
		return {}
	magazine -= 1
	_cycle_left = float(def.get("cycle_s", 0.5))
	var ammo: Dictionary = (def.get("ammo", {}) as Dictionary).get(loaded_ammo, {}).duplicate()
	ammo["id"] = loaded_ammo
	if magazine == 0:
		start_reload()
	return ammo


## Starts a reload; false when one is running, the magazine is already full of the selected type,
## or there is nothing left in reserve.
func start_reload() -> bool:
	if reloading():
		return false
	if magazine >= magazine_size and selected_ammo == loaded_ammo:
		return false
	if reserve <= 0 and not unlimited:
		return false
	_reload_left = float(def.get("reload_s", 1.0))
	return true


func select_next_ammo() -> String:
	if ammo_types.size() < 2:
		return selected_ammo
	var i := ammo_types.find(selected_ammo)
	selected_ammo = ammo_types[(i + 1) % ammo_types.size()]
	if selected_ammo != loaded_ammo:
		start_reload()
	return selected_ammo


## Advances the timers; returns true on the tick a reload completes.
func tick(dt: float) -> bool:
	_cycle_left = maxf(_cycle_left - dt, 0.0)
	if not reloading():
		return false
	_reload_left -= dt
	if _reload_left > 0.0:
		return false
	_reload_left = -1.0
	# A type change unloads what is in the breech back to the reserve first.
	if selected_ammo != loaded_ammo:
		reserve += magazine
		magazine = 0
		loaded_ammo = selected_ammo
	var take := magazine_size - magazine
	if not unlimited:
		take = mini(take, reserve)
		reserve -= take
	magazine += take
	return true
