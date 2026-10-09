"""
Optional idea-spark lookup via DuckDuckGo's free Instant Answer API
(no key, no account). Best for well-known concepts — mythologies, historical
eras, tropes. Only the typed query ever leaves the machine.
"""

import requests


def lookup(query, timeout=12):
    query = (query or "").strip()
    if not query:
        return ""
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=timeout,
            headers={"User-Agent": "NovelForge/1.0 (+local idea lookup)"},
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return f"(lookup failed: {e}\nCheck your internet connection.)"

    lines = []
    if data.get("Heading"):
        lines.append(f"# {data['Heading']}")
    if data.get("AbstractText"):
        lines.append(data["AbstractText"])
        if data.get("AbstractURL"):
            lines.append(f"(source: {data['AbstractURL']})")
    if data.get("Definition"):
        lines.append(data["Definition"])
    related = []
    for topic in data.get("RelatedTopics", []):
        if isinstance(topic, dict) and topic.get("Text"):
            related.append(f"- {topic['Text']}")
        elif isinstance(topic, dict) and topic.get("Topics"):
            for sub in topic["Topics"][:4]:
                if sub.get("Text"):
                    related.append(f"- {sub['Text']}")
    if related:
        lines.append("\nRelated:")
        lines.extend(related[:10])
    return "\n\n".join(lines) if lines else "(No instant answer — try a broader or more common term.)"
