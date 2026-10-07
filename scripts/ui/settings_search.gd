extends RefCounted
## Settings search (lane A7, Emerson: "things there are hard to find"): every setting and every key
## binding whose words hold all the words typed, best first. A setting matches on its label, help,
## group, page, section, key and option labels; a binding on its action's label, group and help.
## The label counts most, so "fog" lists Fog before the settings that only mention fog in their help.

const MIN_CHARS := 2


## Matches for `query`: {"kind": "item", "key", "section", "page", "path"} or {"kind": "action",
## "action", "scheme", "section", "page", "path"}, in order of score then menu order. Items hidden
## behind an off toggle (visible_if) and pages hidden the same way are left out, as on the pages.
static func find(query: String) -> Array:
	var words := _words(query)
	if words.is_empty() or query.strip_edges().length() < MIN_CHARS:
		return []
	var found: Array = []
	var order := 0
	for section: Dictionary in Settings.sections():
		for page: Dictionary in section.get("pages", []):
			if str(page.get("visible_if", "")) != "" and not Settings.get_b(str(page["visible_if"])):
				continue
			var path := "%s  ›  %s" % [section.get("label", ""), page.get("label", "")]
			var where := "%s %s" % [section.get("label", ""), page.get("label", "")]
			for group: Dictionary in page.get("groups", []):
				for it: Dictionary in group.get("items", []):
					if str(it.get("visible_if", "")) != "" and not Settings.get_b(str(it["visible_if"])):
						continue
					var base := {"section": str(section["id"]), "page": str(page["id"]), "path": path}
					if str(it.get("type", "")) == "keybinds":
						var scheme := str(it.get("scheme", "standard"))
						for action in Controls.actions_for_scheme(scheme):
							var info := Controls.action_info(action)
							var label := str(info.get("label", action))
							var rest := "%s %s %s %s" % [info.get("group", ""), info.get("help", ""), action, where]
							var s := _score(words, label, rest)
							if s > 0:
								found.append(base.merged({"kind": "action", "action": action, "scheme": scheme, "score": s, "order": order}))
							order += 1
						continue
					var rest := "%s %s %s %s %s" % [it.get("help", ""), group.get("label", ""), it.get("key", ""), where, _option_words(it)]
					var s := _score(words, str(it.get("label", "")), rest)
					if s > 0:
						found.append(base.merged({"kind": "item", "key": str(it["key"]), "score": s, "order": order}))
					order += 1
	found.sort_custom(
		func(a: Dictionary, b: Dictionary) -> bool:
			return a["score"] > b["score"] or (a["score"] == b["score"] and a["order"] < b["order"])
	)
	return found


## 0 when a word is missing; otherwise every word in the label is worth 3, a label that starts with the
## first word 2 more, and a word found only in the rest 1.
static func _score(words: PackedStringArray, label: String, rest: String) -> int:
	var l := label.to_lower()
	var r := rest.to_lower()
	var score := 0
	for w in words:
		if l.contains(w):
			score += 3
		elif r.contains(w):
			score += 1
		else:
			return 0
	if l.begins_with(words[0]):
		score += 2
	return score


static func _words(query: String) -> PackedStringArray:
	var out := PackedStringArray()
	for w in query.to_lower().split(" ", false):
		out.append(w.strip_edges())
	return out


static func _option_words(it: Dictionary) -> String:
	var key := str(it.get("key", ""))
	if not Settings.has_key(key) or str(it.get("type", "")) != "choice":
		return ""
	var parts := PackedStringArray()
	for o: Array in Settings.options_for(key):
		parts.append(str(o[1]) if o.size() > 1 else str(o[0]))
	return " ".join(parts)
