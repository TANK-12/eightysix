"""The agent loop: one user message in, events out, tools in between.

    agent = Agent(conversation)
    for event in agent.run("open firefox and find my lecture notes"):
        ...

Events are plain dicts, the same for the terminal, the Forge page and the
OpenAI-compatible endpoint Nyarch talks to:

    {"type": "route",  "tier": "small", "toolsets": [...], "fast": bool}
    {"type": "model",  "tier": "small", "model": "Qwen3_5-2B..."}
    {"type": "text",   "delta": "..."}             streamed reply text
    {"type": "tool",   "id", "name", "args"}       a call is starting
    {"type": "result", "id", "name", "ok", "result"}
    {"type": "escalate", "from": "small", "to": "medium", "why": "..."}
    {"type": "done",   "text": "...", "stats": {...}}
    {"type": "error",  "message": "..."}

What keeps small models on the rails, in the order it happens:
fast path (no model) -> only the relevant tools -> tool calls repaired
(names fuzzy-matched, arguments coerced, calls found in plain text when the
server did not parse them) -> error messages that say how to fix the call ->
a nudge when the model refuses instead of acting -> loop guard for the same
call twice -> escalation to the next model size after two failures -> a
final "say what you did" pass with tools off when steps run out.
"""

from __future__ import annotations

import difflib
import json
import re
import threading
import time
import uuid
from typing import Iterator

from . import llm, prompts, registry, router, settings, spelling
from .conversation import Conversation
from .sysutil import clip

registry.load_all()

MAX_STEPS = {"tiny": 6, "small": 8, "medium": 10, "large": 14}
RESULT_LIMIT = {"tiny": 3000, "small": 3500, "medium": 7000, "large": 10000}
# Characters of full messages sent; older ones are folded into a summary.
# These are floors: bigger tiers get as much as their model's context window
# holds (history_limit). Emerson (2026-09-27): "tons of context for my AIs
# except for the 0.8", so tiny stays fixed.
HISTORY_LIMIT = {"tiny": 12000, "small": 16000, "medium": 24000, "large": 40000}
CONTEXT_RESERVE = 12000  # tokens kept free for the system prompt, tools and reply
CHARS_PER_TOKEN = 2.8  # low on purpose: code and JSON pack fewer per token


def history_limit(tier: str, model: str) -> int:
    """Characters of history for this tier: its model's window less the
    reserve, never below the table; tiny always uses the table."""
    floor = HISTORY_LIMIT[tier]
    if tier == "tiny" or not model:
        return floor
    window = llm.forge_jan.context_size(model)
    if not window:
        return floor
    return max(floor, int((window - CONTEXT_RESERVE) * CHARS_PER_TOKEN))


REPLY_TOKENS = {"tiny": 700, "small": 900, "medium": 1400, "large": 1800}
THINK_TOKENS = 2000  # added to the reply budget when thinking is on
# A whole file does not fit in REPLY_TOKENS: a write cut off inside the call
# arrives with empty arguments (Emerson's platformer, 2026-09-27: fourteen
# empty write_file calls, then "I created it"). The turn is asked again once
# with this much more room; still too long, it is written in parts.
WRITE_TOKENS = 6000
WRITE_TOOLS = {"write_file", "append_file", "edit_file"}
NOT_SAVED = "\n\n(No file was saved: every write this turn failed.)"
# Small talk ("hey", "thanks"): the last few plain turns and a short reply.
SMALL_TALK_TURNS = 6
SMALL_TALK_TOKENS = 200
SUMMARY_SYSTEM = (
    "You keep the memory of a chat between a user and their assistant Acchan. "
    "Merge the earlier summary (if any) and the new part into one short summary of "
    "at most 8 lines: facts about the user, what was asked, what was done (files, "
    "apps, results) and anything still open. Plain sentences, no preamble."
)

REFUSAL = re.compile(
    r"\b(i can(no|')t|i am (not able|unable)|i'm (not able|unable)|i don'?t have (access|the ability)|"
    r"as an ai|i do not have (access|the ability)|you (can|could|should) (open|click|press|run|use))\b",
    re.I,
)
TEXT_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
# Qwen3.5's own format, which small models also write as plain text:
# <tool_call><function=name><parameter=key>value</parameter></function></tool_call>
XML_CALL = re.compile(
    r"<tool_call>\s*<function=([\w.-]+)>(.*?)</function>\s*(?:</tool_call>|$)", re.S
)
XML_PARAM = re.compile(r"<parameter=([\w-]+)>\s*(.*?)\s*</parameter>", re.S)
LEFTOVER = re.compile(r"</?(tool_call|function|parameter)[^>]*>", re.S)
# "Let me open that" with no tool call: nothing happened, but it sounds done.
CLAIM = re.compile(
    r"^\W*(sure[,!.]?\s*)?(let me|i'?ll|i will|i'?m going to|opening|checking|"
    r"i'?ve (opened|started|closed|launched|played|switched|created|checked|found|moved|set)|"
    r"i (opened|started|closed|launched|switched|created|checked|moved|set)|done[.!])",
    re.I,
)
# Words that mean the user wants something done after seeing a list.
MORE_TO_DO = re.compile(
    r"\bopen\b(?!\s*(?:right now|now|at the moment)?\W*$)|\b(play|close|switch|move|copy|delete|trash|rename|edit|write|run|read|"
    r"summari[sz]e|then|focus|launch|start)\b",
    re.I,
)
JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def calls_in_text(text: str) -> list[dict]:
    """Tool calls a model wrote as text instead of as structured calls."""
    found = []
    for name, body in XML_CALL.findall(text):
        if not registry.resolve_name(name):
            continue
        args: dict = {}
        for key, value in XML_PARAM.findall(body):
            try:
                args[key] = json.loads(value)
            except ValueError:
                args[key] = value
        found.append({"id": "", "name": name, "arguments": json.dumps(args)})
    if found:
        return found
    for pattern in (TEXT_CALL, JSON_BLOCK):
        for raw in pattern.findall(text):
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            name = obj.get("name") or obj.get("tool") or obj.get("function")
            args = (
                obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
            )
            if isinstance(name, str) and registry.resolve_name(name):
                found.append(
                    {
                        "id": "",
                        "name": name,
                        "arguments": (
                            json.dumps(args) if not isinstance(args, str) else args
                        ),
                    }
                )
        if found:
            break
    return found


def repeats(content: str, messages: list[dict]) -> bool:
    """True when a reply is (nearly) word for word an earlier one."""
    if len(content) < 40:
        return False
    return any(
        m["role"] == "assistant"
        and len(m.get("content") or "") >= 40
        and difflib.SequenceMatcher(None, content, m["content"]).ratio() > 0.9
        for m in messages
    )


def strip_calls(text: str) -> str:
    text = TEXT_CALL.sub("", text)
    text = XML_CALL.sub("", text)
    text = re.sub(r"<tool_call>.*", "", text, flags=re.S)  # a cut-off call
    text = LEFTOVER.sub("", text)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.strip()


def reply_budget(tier: str, think: bool, roomy: bool) -> int | None:
    """Tokens one reply may use: None (no cap) unless Settings has a
    reply_limit, which never goes below the tier's old REPLY_TOKENS."""
    limit = int(settings.load().get("reply_limit") or 0)
    if limit <= 0:
        return None
    return (
        max(REPLY_TOKENS[tier], limit)
        + (THINK_TOKENS if think else 0)
        + (WRITE_TOKENS if roomy else 0)
    )


class Agent:
    def __init__(
        self,
        conversation: Conversation,
        cwd: str | None = None,
        forced_tier: str | None = None,
    ):
        self.conv = conversation
        self.cwd = cwd
        self.forced_tier = forced_tier
        self.stop_event = threading.Event()
        # None: follow the Settings toggle; True/False: this request only.
        self.thinking: bool | None = None
        # False sends greetings through the full loop (for timing the old way).
        self.small_talk = True
        self.offered: list[str] | None = None  # the 0.8B's short tool list

    def stop(self) -> None:
        self.stop_event.set()

    # --------------------------------------------------------------- helpers
    def _messages(self, tier: str, toolsets: list[str]) -> list[dict]:
        # The working folder travels in the first user message, not the system
        # prompt: an identical system prompt + tools prefix is reused from
        # llama.cpp's prompt cache across conversations and folders.
        system = prompts.system_prompt(
            tier,
            toolsets,
            model=llm.model_for(tier),
            summary=self.conv.summary,
            only=self._offered(tier),
        )
        history = self.conv.trimmed(history_limit(tier, llm.model_for(tier)))
        return [{"role": "system", "content": system}, *history]

    def _fold_history(self, tier: str) -> Iterator[dict]:
        """When the chat outgrows this model's budget, fold the oldest turns
        into the running summary instead of silently dropping them."""
        conv = self.conv
        budget = history_limit(tier, llm.model_for(tier))
        if conv.unsummarised() <= budget:
            return
        cut = conv.fold_point(int(budget * 0.6))
        if cut <= conv.summary_upto:
            return
        old = conv.messages[conv.summary_upto : cut]
        each = max(150, 10000 // max(1, len(old)))
        lines = []
        for m in old:
            text = m.get("content") or ""
            if m.get("tool_calls"):
                fn = m["tool_calls"][0]["function"]
                text = (text + f" [called {fn['name']} {fn['arguments']}]").strip()
            if text:
                lines.append(f"{m['role']}: {clip(text, each)}")
        earlier = f"Earlier summary:\n{conv.summary}\n\n" if conv.summary else ""
        yield {"type": "memory", "folded": len(old)}
        try:
            summary = llm.complete(
                tier,
                SUMMARY_SYSTEM,
                earlier + "New part of the chat:\n" + "\n".join(lines),
                max_tokens=300,
            )
        except llm.LLMError:
            return  # plain trimming still keeps the request within budget
        if summary:
            conv.summary = strip_calls(summary)
            conv.summary_upto = cut

    def _offered(self, tier: str) -> list[str] | None:
        return self.offered if tier == "tiny" else None

    def _run_tool(self, name: str, args_raw, tier: str) -> tuple[bool, str]:
        try:
            result = registry.call(name, args_raw)
            entry = registry.TOOLS.get(registry.resolve_name(name) or "")
            # A list the user asked for is shown whole, so it may run longer.
            limit = RESULT_LIMIT[tier] * (4 if entry and entry.show else 1)
            return True, clip(result, limit)
        except registry.ToolError as exc:
            return False, f"ERROR: {exc}"

    # ------------------------------------------------------------------ run
    def run(self, text: str) -> Iterator[dict]:
        started = time.monotonic()
        self.stop_event.clear()
        first = not any(m["role"] == "user" for m in self.conv.messages)
        # Typos fixed once, for routing and for the model alike.
        text = spelling.correct(text)
        stored = f"(Working folder: {self.cwd})\n{text}" if self.cwd and first else text
        self.conv.add({"role": "user", "content": stored})

        # Which model: the size picked in the app, else the one this chat
        # settled on, else the default start (one model, no switching).
        # "switch" is the old per-message choice.
        mode = self.forced_tier
        sticky = mode not in (*llm.TIERS, "switch")
        if mode in llm.TIERS:
            tier = mode
        elif sticky:
            tier = self.conv.tier or llm.START_TIER
        else:
            tier = ""

        if router.asks_model(text):
            size = tier or llm.START_TIER
            reply = (
                f"I'm running on {llm.model_for(size)}, the {llm.SIZE_LABEL[size]} "
                "model, locally through Jan."
            )
            yield {"type": "route", "tier": size, "toolsets": [], "fast": True}
            self.conv.add({"role": "assistant", "content": reply})
            self.conv.save()
            yield {"type": "text", "delta": reply}
            yield {
                "type": "done",
                "text": reply,
                "stats": {
                    "seconds": round(time.monotonic() - started, 2),
                    "fast": True,
                },
            }
            return

        fast = router.fast_path(text)
        if fast:
            yield {"type": "route", "tier": "none", "toolsets": [], "fast": True}
            replies, failed = [], None
            for call in fast:
                cid = uuid.uuid4().hex[:8]
                yield {"type": "tool", "id": cid, "name": call.tool, "args": call.args}
                ok, result = self._run_tool(call.tool, call.args, "medium")
                yield {
                    "type": "result",
                    "id": cid,
                    "name": call.tool,
                    "ok": ok,
                    "result": result,
                }
                if not ok:
                    failed = (call, result)
                    break
                replies.append(call.reply.replace("{result}", result))
            if failed is None:
                reply = " ".join(replies)
                self.conv.add({"role": "assistant", "content": reply})
                self.conv.save()
                yield {"type": "text", "delta": reply}
                yield {
                    "type": "done",
                    "text": reply,
                    "stats": {
                        "seconds": round(time.monotonic() - started, 2),
                        "fast": True,
                    },
                }
                return
            # The quick way failed; let a model try, knowing what happened.
            call, error = failed
            self.conv.add(
                {
                    "role": "user",
                    "content": f"(Note: a direct {call.tool} {json.dumps(call.args)} attempt failed with: {error[:300]}. Try another way.)",
                }
            )

        if self.small_talk and router.is_small_talk(text):
            yield from self._small_talk(tier or llm.START_TIER, started, sticky)
            return

        chosen = router.plan(text, self.conv.toolsets, tier or None)
        tier = tier or chosen.tier
        toolsets = chosen.toolsets
        self.conv.toolsets = [t for t in toolsets]
        self.offered = (
            router.rank_tools(text, toolsets, router.TINY_TOOLS) if toolsets else None
        )
        yield {"type": "route", "tier": tier, "toolsets": toolsets, "fast": False}
        think = settings.load()["thinking"] if self.thinking is None else self.thinking

        failures = 0
        nudged = False
        claimed = False
        roomy = False  # asked again with WRITE_TOKENS more room
        wrote = None  # None: no write tried; False: all failed; True: one worked
        called = False  # a tool ran during this message
        last_call = None
        streak: list[str] = []  # names of the calls in a row
        steps = 0
        stats: dict = {"prompt_tokens": 0, "completion_tokens": 0}
        final = ""
        retried = False
        retry_note: list[dict] = []
        yield from self._fold_history(tier)
        while True:
            if self.stop_event.is_set():
                final = final or "(stopped)"
                break
            if steps >= MAX_STEPS[tier]:
                final = yield from self._wrap_up(tier, toolsets)
                break
            steps += 1
            yield {"type": "model", "tier": tier, "model": llm.model_for(tier)}
            buffer: list[str] = []
            thoughts: list[str] = []

            def on_text(delta: str) -> None:
                buffer.append(delta)

            def on_reasoning(delta: str) -> None:
                thoughts.append(delta)

            messages = self._messages(tier, toolsets)
            if retry_note:
                messages += retry_note
                retry_note = []
            try:
                reply = llm.stream(
                    tier,
                    messages,
                    tools=(
                        prompts.tool_schemas(toolsets, only=self._offered(tier))
                        if toolsets
                        else None
                    ),
                    max_tokens=reply_budget(tier, think, roomy),
                    thinking=think,
                    on_text=on_text,
                    stop_event=self.stop_event,
                    on_reasoning=on_reasoning,
                )
            except llm.LLMError as exc:
                nxt = llm.next_tier(tier)
                if nxt and "not answering" not in str(exc):
                    yield {
                        "type": "escalate",
                        "from": tier,
                        "to": nxt,
                        "why": str(exc)[:200],
                    }
                    tier = nxt
                    continue
                yield {"type": "error", "message": str(exc)}
                self.conv.save()
                return
            stats["prompt_tokens"] += reply.usage.get("prompt_tokens", 0)
            stats["completion_tokens"] += reply.usage.get("completion_tokens", 0)
            if reply.reasoning.strip():
                yield {"type": "thinking", "text": reply.reasoning.strip()}

            # Calls written as text count even when no tools were offered,
            # as long as they name a real tool (the 0.8B does this).
            calls = reply.tool_calls or calls_in_text(reply.content)
            content = strip_calls(reply.content)

            if not calls:
                if toolsets and not nudged and REFUSAL.search(content) and steps <= 2:
                    # The small-model reflex: apologising instead of acting.
                    nudged = True
                    self.conv.add({"role": "assistant", "content": content})
                    self.conv.add(
                        {
                            "role": "user",
                            "content": "You do have tools for this. Call the right tool now instead of explaining.",
                        }
                    )
                    continue
                if toolsets and not called and not claimed and CLAIM.search(content):
                    # Said it would act (or that it had) without a call.
                    claimed = True
                    best = (
                        ", ".join((self._offered(tier) or [])[:2]) or "the right tool"
                    )
                    self.conv.add({"role": "assistant", "content": content})
                    self.conv.add(
                        {
                            "role": "user",
                            "content": f"Nothing happened: you did not call a tool. Call it now (probably {best}).",
                        }
                    )
                    continue
                if not content:
                    failures += 1
                    nxt = llm.next_tier(tier)
                    if failures >= 2 and nxt:
                        yield {
                            "type": "escalate",
                            "from": tier,
                            "to": nxt,
                            "why": "empty replies",
                        }
                        tier, failures = nxt, 0
                        if not toolsets:
                            toolsets = router.plan(text, [], tier).toolsets
                            self.conv.toolsets = toolsets
                    continue
                if not retried and repeats(content, self.conv.messages):
                    # Small models copy an earlier reply word for word.
                    retried = True
                    retry_note = [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": "That repeats an earlier reply. Write something new.",
                        },
                    ]
                    continue
                if wrote is False:
                    content += NOT_SAVED
                final = content
                yield {"type": "text", "delta": content}
                self.conv.add({"role": "assistant", "content": content})
                break

            call = calls[0]  # one at a time: small models chain better that way
            name = registry.resolve_name(call["name"]) or call["name"]
            try:
                args = registry.parse_arguments(call["arguments"])
            except registry.ToolError:
                args = {}
            cut = (
                not args
                and name in registry.TOOLS
                and (reply.finish == "length" or name in WRITE_TOOLS)
            )
            if cut and not roomy:
                roomy = True
                if name in WRITE_TOOLS:
                    wrote = bool(wrote)  # tried; not saved (yet)
                continue
            signature = (name, json.dumps(args, sort_keys=True))
            cid = call.get("id") or uuid.uuid4().hex[:8]
            self.conv.add(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": [
                        {
                            "id": cid,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args, ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
            yield {"type": "tool", "id": cid, "name": name, "args": args}
            streak = (streak if streak and streak[-1] == name else []) + [name]
            if cut:
                ok, result = (
                    False,
                    f"ERROR: The {name} call was cut off: the text is too long for one reply. Write it in parts: write_file with the first part (about 150 lines), then append_file with each next part.",
                )
                failures += 1
            elif signature != last_call and len(streak) >= 3:
                ok, result = (
                    False,
                    f"ERROR: You called {name} three times in a row. Stop calling it and answer the user now with what you have.",
                )
                failures += 1
            elif signature == last_call:
                ok, result = (
                    False,
                    "ERROR: You already made this exact call and have its result above. Do not repeat it: answer the user now, or try something different.",
                )
                failures += 1
            else:
                ok, result = self._run_tool(name, args, tier)
                if name not in registry.TOOLS:
                    failures += 1
                elif not ok:
                    failures += 1
                else:
                    failures = 0
            last_call = signature
            if name in WRITE_TOOLS:
                wrote = bool(wrote) or ok
            # A tool from a toolset we did not offer (the model knew its name
            # from an example or the fuzzy match): offer that toolset from now on.
            used = registry.TOOLS.get(name)
            if used and used.toolset not in toolsets:
                toolsets = toolsets + [used.toolset]
                self.conv.toolsets = toolsets
            if used and self.offered is not None and name not in self.offered:
                self.offered.append(name)
            self.conv.add({"role": "tool", "tool_call_id": cid, "content": result})
            yield {
                "type": "result",
                "id": cid,
                "name": name,
                "ok": ok,
                "result": result,
            }
            if ok and used and used.show and not called and not MORE_TO_DO.search(text):
                # The user asked to see a list: give them the real one, whole,
                # instead of a small model's retelling of it.
                final = result
                yield {"type": "text", "delta": final}
                self.conv.add({"role": "assistant", "content": final})
                called = True
                break
            called = called or ok
            nxt = llm.next_tier(tier)
            if failures >= 2 and nxt:
                yield {
                    "type": "escalate",
                    "from": tier,
                    "to": nxt,
                    "why": "two failed tool calls",
                }
                tier, failures = nxt, 0

        if sticky:
            self.conv.tier = tier  # a step up holds for the rest of the chat
        self.conv.save()
        stats["seconds"] = round(time.monotonic() - started, 2)
        stats["tier"] = tier
        yield {"type": "done", "text": final, "stats": stats}

    def _small_talk(self, tier: str, started: float, sticky: bool) -> Iterator[dict]:
        """One light call for a greeting. "hey" used to take the full loop:
        the Think setting (up to 2000 more tokens), the whole history with its
        tool results, a history summary first, and a step up to a bigger model
        (another model load) after an empty or failed reply. None of that
        here: the chat's own model, no tools, no thinking, a short reply."""
        yield {"type": "route", "tier": tier, "toolsets": [], "fast": False}
        yield {"type": "model", "tier": tier, "model": llm.model_for(tier)}
        recent = [
            {"role": m["role"], "content": clip(m["content"], 400)}
            for m in self.conv.messages
            if m["role"] in ("user", "assistant")
            and m.get("content")
            and not m.get("tool_calls")
        ][-SMALL_TALK_TURNS:]
        system = prompts.system_prompt(tier, [], model=llm.model_for(tier))
        try:
            reply = llm.stream(
                tier,
                [{"role": "system", "content": system}, *recent],
                max_tokens=SMALL_TALK_TOKENS,
                thinking=False,
                stop_event=self.stop_event,
            )
        except llm.LLMError as exc:
            yield {"type": "error", "message": str(exc)}
            self.conv.save()
            return
        final = strip_calls(reply.content) or "Hi! What can I do for you?"
        yield {"type": "text", "delta": final}
        self.conv.add({"role": "assistant", "content": final})
        if sticky:
            self.conv.tier = tier
        self.conv.save()
        stats = {
            "prompt_tokens": reply.usage.get("prompt_tokens", 0),
            "completion_tokens": reply.usage.get("completion_tokens", 0),
            "seconds": round(time.monotonic() - started, 2),
            "tier": tier,
            "small_talk": True,
        }
        yield {"type": "done", "text": final, "stats": stats}

    def _wrap_up(self, tier: str, toolsets: list[str]):
        """Steps ran out: ask for a plain summary with tools switched off."""
        self.conv.add(
            {
                "role": "user",
                "content": "Stop using tools now. In one or two sentences, tell me what you did and what (if anything) is left.",
            }
        )
        try:
            reply = llm.stream(
                tier,
                self._messages(tier, toolsets),
                tools=None,
                max_tokens=200,
                stop_event=self.stop_event,
            )
            text = strip_calls(reply.content) or "I ran out of steps before finishing."
        except llm.LLMError as exc:
            text = f"I ran out of steps ({exc})."
        self.conv.add({"role": "assistant", "content": text})
        yield {"type": "text", "delta": text}
        return text
