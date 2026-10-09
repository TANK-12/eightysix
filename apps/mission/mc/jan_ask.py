"""Ask Jan (the local model) about a session's conversation: free, private,
and it never reaches the session. Mission Control has its own Jan model
setting (role "ask", shared/forge_jan.py), loads it only for the question and
lets the shared idle watcher release it. Jan is never started from here."""

from __future__ import annotations

from mc.actions import ActionError

CONTEXT_CHARS = 7000
SYSTEM = (
    "You help Emerson keep track of his Claude Code sessions. Below is the end"
    " of one session's conversation: what Emerson or the board asked, what"
    " Claude wrote, and the tools it ran. Answer his question about it in a"
    " few short plain sentences. Say what is done, what is in progress and"
    " anything that waits on him. If the conversation does not say, say so;"
    " never guess."
)


def context(events: list[dict], limit: int = CONTEXT_CHARS) -> str:
    """The conversation as short plain lines, newest kept when it is long."""
    lines: list[str] = []
    for ev in events:
        kind = ev.get("type")
        if kind == "forge_user":
            lines.append(f"Emerson: {ev.get('text', '')}")
        elif kind == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if block.get("type") == "text":
                    lines.append(f"Claude: {block.get('text', '')}")
                elif block.get("type") == "tool_use":
                    data = block.get("input") or {}
                    brief = next(
                        (
                            str(data[k])
                            for k in ("description", "command", "file_path", "query")
                            if data.get(k)
                        ),
                        "",
                    )
                    lines.append(f"(ran {block.get('name')}: {brief[:160]})")
        elif kind == "forge_sys":
            lines.append(f"({ev.get('text', '')})")
    out: list[str] = []
    used = 0
    for line in reversed(lines):
        line = line if len(line) <= 1500 else line[:1500] + "…"
        if used + len(line) > limit:
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(reversed(out))


def ask(jan, question: str, events: list[dict]) -> dict:
    """Jan's answer: {"answer", "model"}, or an ActionError saying why not."""
    from mc import borrow

    borrow.setup()
    import forge_jan  # pyright: ignore[reportMissingImports]

    if forge_jan.router_url() is None:
        raise ActionError(
            503, "Jan is not running. Open Jan first; Mission Control never starts it."
        )
    model = jan.model_for("ask")
    if not model:
        raise ActionError(503, "Jan has no models to answer with")
    talk = context(events) or "(nothing said yet)"
    try:
        with jan.using(model):
            answer = forge_jan.chat_messages(
                model,
                [
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": f"Conversation:\n{talk}\n\nQuestion: {question}",
                    },
                ],
                temperature=0.3,
                max_tokens=500,
                timeout=120.0,
            )
    except forge_jan.JanError as e:
        raise ActionError(503, f"Jan could not answer: {e}")
    return {"answer": answer, "model": model}
