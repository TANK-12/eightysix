"""
The World Codex: an additive-only, structured memory of every character,
location, faction and world-fact the story has established. This -- not just
the sliding window of recent chapters -- is what stops chapter 40 from
forgetting a character introduced in chapter 3.

Nothing here is ever *deleted* automatically; entries are only added to or
refined. The user can still hand-edit the raw JSON in the UI.
"""


def default_codex():
    """Always a FRESH dict -- never share one mutable dict between projects."""
    return {"characters": {}, "locations": {}, "factions": {}, "facts": []}


def _merge_desc(old, new):
    new = (new or "").strip()
    if not new:
        return old
    if not old:
        return new
    if new.lower() in old.lower():
        return old
    return (old + " " + new).strip()


def merge_codex(codex, update, chapter_n):
    """Additive merge of a normalised codex delta (see jsonrepair.coerce_*)."""
    update = update or {}

    for name, info in (update.get("characters") or {}).items():
        name = (name or "").strip()
        if not name:
            continue
        entry = codex["characters"].setdefault(
            name, {"desc": "", "traits": [], "relationships": {},
                   "status": "", "first_chapter": chapter_n, "last_chapter": chapter_n})
        if chapter_n:
            entry["last_chapter"] = max(entry.get("last_chapter", chapter_n), chapter_n)
        entry["desc"] = _merge_desc(entry.get("desc", ""), info.get("desc", ""))
        for t in info.get("traits") or []:
            t = (t or "").strip()
            if t and t not in entry["traits"]:
                entry["traits"].append(t)
        for other, rel in (info.get("relationships") or {}).items():
            other, rel = (other or "").strip(), (rel or "").strip()
            if other and rel:
                entry["relationships"][other] = rel
        st = (info.get("status") or "").strip()
        if st:
            entry["status"] = st

    for bucket in ("locations", "factions"):
        for name, info in (update.get(bucket) or {}).items():
            name = (name or "").strip()
            if not name:
                continue
            entry = codex[bucket].setdefault(
                name, {"desc": "", "first_chapter": chapter_n, "last_chapter": chapter_n})
            if chapter_n:
                entry["last_chapter"] = max(entry.get("last_chapter", chapter_n), chapter_n)
            entry["desc"] = _merge_desc(entry.get("desc", ""), info.get("desc", ""))

    for fact in update.get("facts") or []:
        fact = (fact or "").strip()
        if fact and not any(fact.lower() == f.lower() for f in codex["facts"]):
            codex["facts"].append(fact)


def codex_is_empty(codex):
    return not any(codex.get(k) for k in ("characters", "locations", "factions", "facts"))


def format_codex(codex, max_chars=4000, current_chapter=None):
    """Compact rendering for both the in-prompt block and the UI viewer.

    If `current_chapter` is given, characters not seen for a while are tagged
    OFFSCREEN so the model doesn't forget they exist / silently drop them."""
    lines = []
    if codex.get("facts"):
        lines.append("World facts & rules:")
        lines += [f"  - {f}" for f in codex["facts"]]
    if codex.get("characters"):
        lines.append("Characters:")
        for name, e in codex["characters"].items():
            seg = [f"  - {name}: {e.get('desc', '').strip()}"]
            if e.get("traits"):
                seg.append(f"traits: {', '.join(e['traits'])}")
            if e.get("status"):
                seg.append(f"status: {e['status']}")
            rel = e.get("relationships") or {}
            if rel:
                seg.append("relationships: " + "; ".join(f"{k} = {v}" for k, v in rel.items()))
            last = e.get("last_chapter")
            if current_chapter and last and (current_chapter - last) >= 5:
                seg.append(f"OFFSCREEN since ch {last}")
            lines.append(" | ".join(seg))
    for bucket, header in (("locations", "Locations:"), ("factions", "Factions:")):
        if codex.get(bucket):
            lines.append(header)
            for name, e in codex[bucket].items():
                lines.append(f"  - {name}: {e.get('desc', '').strip()}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n  ...(codex trimmed for THIS prompt only; full codex is saved on disk)"
    return text


def apply_reconcile(codex, ops):
    """Apply a list of reconciliation ops from the continuity auditor.

    ops items: {"kind": "merge", "from": A, "into": B}
               {"kind": "status", "name": N, "value": S}
               {"kind": "fix", "name": N, "value": D}
    Returns a short log of what changed.
    """
    log = []
    chars = codex["characters"]
    for op in ops or []:
        k = op.get("kind")
        if k == "merge":
            a, b = (op.get("from") or "").strip(), (op.get("into") or "").strip()
            if a in chars and b and a != b:
                src = chars.pop(a)
                dst = chars.setdefault(b, {"desc": "", "traits": [], "relationships": {},
                                           "status": "", "first_chapter": src.get("first_chapter", 0),
                                           "last_chapter": src.get("last_chapter", 0)})
                dst["desc"] = _merge_desc(dst.get("desc", ""), src.get("desc", ""))
                for t in src.get("traits", []):
                    if t not in dst["traits"]:
                        dst["traits"].append(t)
                dst["relationships"].update(src.get("relationships", {}))
                dst["status"] = src.get("status") or dst.get("status", "")
                log.append(f"merged '{a}' into '{b}'")
        elif k == "status":
            n = (op.get("name") or "").strip()
            if n in chars and op.get("value"):
                chars[n]["status"] = op["value"].strip()
                log.append(f"status of '{n}' -> {op['value'].strip()}")
        elif k == "fix":
            n = (op.get("name") or "").strip()
            if n in chars and op.get("value"):
                chars[n]["desc"] = op["value"].strip()
                log.append(f"corrected '{n}'")
    return log


def codex_stats(codex):
    return {
        "characters": len(codex.get("characters", {})),
        "locations": len(codex.get("locations", {})),
        "factions": len(codex.get("factions", {})),
        "facts": len(codex.get("facts", [])),
    }
