"""Talking to Jan: model tiers, per-request settings, streaming with tools.

Four tiers, smallest first. Each is one Jan model id, chosen in the app's own
Jan settings (~/.config/forge/jan/acchan.json, shared with every Forge app's
Jan panel through shared/forge_jan.py):

    tiny    0.8B  the default: one model for everything, tools included
    small   2B    the first step up when the 0.8B fails twice
    medium  4B    vision (look_at_screen), and the next step up
    large   9B    the last rung

By default a chat stays on one model (START_TIER, the 0.8B) so Jan is not
loading a different model for every message; it steps up a size only after
two failures and then stays there for that chat (see agent.py).

Settings that shape a reply -- temperature, penalties, thinking, the prompt
cache -- travel with each request, so they apply only to Acchan's (and
Nyarch's, through Acchan) calls and never touch the user's own Jan model
settings. The 2B ships with presence_penalty -0.4, which makes small models
repeat themselves in tool loops; every request here sets it back to 0.

Memory bandwidth, not compute, limits generation on this laptop (DDR4-3200),
so: thinking off, short max_tokens, and `cache_prompt` with a prompt whose
start never changes between turns so llama.cpp reuses its KV cache.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(
    0, os.environ.get("FORGE_SHARED_DIR", str(Path.home() / "Forge" / "shared"))
)
import forge_jan  # noqa: E402

BASE_URL: str = os.environ.get("JAN_BASE_URL") or forge_jan.BASE_URL
TIERS = ("tiny", "small", "medium", "large")
SIZE_LABEL = {"tiny": "0.8B", "small": "2B", "medium": "4B", "large": "9B"}
# First available wins. The Qwen3_5-4B-IQ4_XS entry keeps its old id (other
# Forge apps ask for it by name) but since 2026-09-24 holds the Q4_K_M file:
# benchmarked on this laptop, IQ4_XS read prompts at 43 tok/s against 81 for
# Q4_K_M, so the I-quant format, not the size, was the bottleneck.
# 2B/4B/9B prefer their long-context copies (forge_jan.long_entries, made at
# startup), used once Jan lists them; tiny keeps the plain 0.8B.
BASE_MODELS = {
    "small": "Qwen3_5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M",
    "medium": "Qwen3_5-4B-IQ4_XS",
    "large": "Qwen3_5-9B-Q4_K_M",
}
DEFAULT_MODELS = {
    "tiny": ["qwen35-0_8b-spectralquant-calib360-q4_k_m"],
    **{
        tier: [base + forge_jan.LONG_SUFFIX, base] for tier, base in BASE_MODELS.items()
    },
}
START_TIER = os.environ.get("ACCHAN_START_TIER", "tiny")
VISION_TIERS = ("medium", "small")  # models on disk that carry an mmproj
JAN = forge_jan.AppJan("acchan", roles=TIERS)

# Per-request sampling, per tier. Low temperature for tool choice; the tiny
# model also gets a firmer repeat penalty, as it loops more readily.
SAMPLING = {
    "tiny": {"temperature": 0.35, "top_p": 0.9, "top_k": 20, "repeat_penalty": 1.1},
    "small": {"temperature": 0.3, "top_p": 0.9, "top_k": 20},
    "medium": {"temperature": 0.3, "top_p": 0.9, "top_k": 20},
    "large": {"temperature": 0.3, "top_p": 0.95, "top_k": 20},
}
COMMON = {
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "repeat_penalty": 1.05,
    "cache_prompt": True,
}


class LLMError(Exception):
    pass


def model_for(tier: str) -> str:
    """The user's choice for this tier, else the first default Jan has."""
    chosen = JAN.settings()["models"].get(tier)
    if chosen:
        return chosen
    choices = DEFAULT_MODELS[tier]
    try:
        have = set(forge_jan.models())
    except Exception:
        have = set()
    return next((m for m in choices if m in have), choices[-1])


def available() -> list[str]:
    try:
        return forge_jan.models(refresh=True)
    except Exception:
        return []


def next_tier(tier: str) -> str | None:
    index = TIERS.index(tier)
    return TIERS[index + 1] if index + 1 < len(TIERS) else None


@dataclass
class Reply:
    """What one model call produced."""

    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    finish: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    reasoning: str = ""  # the model's thinking, when thinking was on


LANE = threading.Lock()  # one request at a time: two in flight froze this laptop


def stream(
    tier: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int | None = 700,
    thinking: bool = False,
    model: str | None = None,
    timeout: float = 300.0,
    on_text=None,
    stop_event: threading.Event | None = None,
    on_reasoning=None,
) -> Reply:
    """One streamed completion. `on_text(delta)` sees content as it arrives.
    Tool calls are assembled from their deltas and returned whole."""
    chosen = model or model_for(tier)
    body: dict = {
        "model": chosen,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        **COMMON,
        **SAMPLING.get(tier, SAMPLING["small"]),
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    if max_tokens:  # None or 0: no cap, the model stops by itself or at its window
        body["max_tokens"] = max_tokens
    if tools:
        body["tools"] = tools
        body["parallel_tool_calls"] = False
    reply = Reply(model=chosen)
    calls: dict[int, dict] = {}
    request = urllib.request.Request(
        BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if not LANE.acquire(timeout=120):
        raise LLMError("Jan is busy with another request from Acchan")
    try:
        with JAN.using(chosen):
            try:
                response = urllib.request.urlopen(request, timeout=timeout)
            except urllib.error.HTTPError as exc:
                detail = exc.read()[:300].decode("utf-8", "replace")
                raise LLMError(f"Jan said {exc.code}: {detail}") from exc
            except (urllib.error.URLError, OSError) as exc:
                raise LLMError(f"Jan is not answering at {BASE_URL}: {exc}") from exc
            with response:
                for raw in response:
                    if stop_event is not None and stop_event.is_set():
                        reply.finish = "stopped"
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if chunk.get("usage"):
                        reply.usage = chunk["usage"]
                    if chunk.get("timings"):
                        reply.timings = chunk["timings"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        thought = delta.get("reasoning_content")
                        if thought:
                            reply.reasoning += thought
                            if on_reasoning:
                                on_reasoning(thought)
                        text = delta.get("content")
                        if text:
                            reply.content += text
                            if on_text:
                                on_text(text)
                        for part in delta.get("tool_calls") or []:
                            slot = calls.setdefault(
                                part.get("index", 0),
                                {"id": "", "name": "", "arguments": ""},
                            )
                            slot["id"] = part.get("id") or slot["id"]
                            fn = part.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
                        if choice.get("finish_reason"):
                            reply.finish = choice["finish_reason"]
    finally:
        LANE.release()
    reply.tool_calls = [calls[i] for i in sorted(calls) if calls[i]["name"]]
    return reply


def complete(tier: str, system: str, user: str, max_tokens: int = 300, **kw) -> str:
    """A one-shot, non-tool completion: the text only."""
    reply = stream(
        tier,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        **kw,
    )
    return reply.content.strip()


def describe_image(image_b64: str, question: str, mime: str = "image/png") -> str:
    """Ask a vision-capable tier about one image."""
    last: Exception | None = None
    for tier in VISION_TIERS:
        try:
            reply = stream(
                tier,
                [
                    {
                        "role": "system",
                        "content": "You describe images accurately and briefly. Read any visible text exactly.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                            },
                            {"type": "text", "text": question},
                        ],
                    },
                ],
                max_tokens=500,
            )
            if reply.content.strip():
                return reply.content.strip()
        except LLMError as exc:
            last = exc
    raise LLMError(f"no vision model answered: {last}")
