extends Node
## Loads every data/*.json registry once and hands out entries.
##
## A registry file is {"_about": "...", "entries": {id: {...}}} plus any other top-level blocks
## (tuning.json is only blocks). An entry may say "inherits": "<other id>" to deep-merge itself
## over another entry of the same file; "abstract": true marks a template that ids() skips.
## Adding a mech, map, weapon, theme or sound is one entry in the right file, never code.

signal reloaded

const DATA_DIR := "res://data"

var errors: PackedStringArray = []
var _files: Dictionary = {}
var _resolved: Dictionary = {}


func _init() -> void:
	reload()


func reload() -> void:
	_files.clear()
	_resolved.clear()
	errors.clear()
	for file_name in DirAccess.get_files_at(DATA_DIR):
		if file_name.get_extension() != "json":
			continue
		var path := DATA_DIR.path_join(file_name)
		var json := JSON.new()
		if json.parse(FileAccess.get_file_as_string(path)) != OK:
			errors.append(
				"%s line %d: %s" % [path, json.get_error_line(), json.get_error_message()]
			)
			continue
		if not json.data is Dictionary:
			errors.append("%s: the top level is not an object" % path)
			continue
		_files[file_name.get_basename()] = json.data
	for message in errors:
		push_error("Registry: " + message)
	reloaded.emit()


func has_file(name: String) -> bool:
	return _files.has(name)


func file(name: String) -> Dictionary:
	return _files.get(name, {})


func has_entry(name: String, id: String) -> bool:
	return _raw_entries(name).has(id)


## Entry ids sorted by their "order" field, then by id. Abstract templates are left out.
func ids(name: String, include_abstract: bool = false) -> PackedStringArray:
	var raw := _raw_entries(name)
	var keys: Array = raw.keys()
	if not include_abstract:
		keys = keys.filter(func(k: Variant) -> bool: return not entry(name, str(k)).get("abstract", false))
	keys.sort_custom(
		func(a: Variant, b: Variant) -> bool:
			var oa: float = float(entry(name, str(a)).get("order", 1000.0))
			var ob: float = float(entry(name, str(b)).get("order", 1000.0))
			return oa < ob if oa != ob else str(a) < str(b)
	)
	return PackedStringArray(keys)


## The entry with "inherits" resolved. Returns a copy, so callers may change it freely.
func entry(name: String, id: String) -> Dictionary:
	var key := name + "/" + id
	if not _resolved.has(key):
		_resolved[key] = _resolve(name, id, [])
	var found: Dictionary = _resolved[key]
	return found.duplicate(true)


## A number (or block) from tuning.json by dotted path, e.g. "standin.drive.walk_m_s".
func tune(path: String, fallback: Variant = null) -> Variant:
	var node: Variant = file("tuning")
	for part in path.split("."):
		if not node is Dictionary or not (node as Dictionary).has(part):
			return fallback
		node = (node as Dictionary)[part]
	return node


func tune_f(path: String, fallback: float) -> float:
	return float(tune(path, fallback))


## Dictionaries merge key by key (recursively); anything else in `over` replaces `base`.
static func deep_merge(base: Dictionary, over: Dictionary) -> Dictionary:
	var out := base.duplicate(true)
	for key: Variant in over:
		var value: Variant = over[key]
		if value is Dictionary and out.get(key) is Dictionary:
			out[key] = deep_merge(out[key], value)
		else:
			out[key] = value.duplicate(true) if value is Dictionary or value is Array else value
	return out


func _raw_entries(name: String) -> Dictionary:
	var entries: Variant = file(name).get("entries", {})
	return entries if entries is Dictionary else {}


func _resolve(name: String, id: String, chain: Array) -> Dictionary:
	var raw := _raw_entries(name)
	if not raw.has(id):
		return {}
	var own: Dictionary = raw[id]
	var parent_id := str(own.get("inherits", ""))
	if parent_id == "":
		return own.duplicate(true)
	if parent_id in chain or not raw.has(parent_id):
		push_error("Registry: %s/%s inherits a missing or looping entry '%s'" % [name, id, parent_id])
		return own.duplicate(true)
	chain.append(id)
	var parent := _resolve(name, parent_id, chain)
	parent.erase("abstract")
	var merged := deep_merge(parent, own)
	merged.erase("inherits")
	if not own.get("abstract", false):
		merged.erase("abstract")
	return merged
