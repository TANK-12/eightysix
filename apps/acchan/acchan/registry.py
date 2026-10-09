"""The tool registry: every action Acchan can take, declared once.

A tool is a plain function in a module under `acchan/tools/`, decorated with
`@tool(...)`. Its JSON schema comes from the signature: `Annotated[type, "what
it means"]` gives the description, a default makes it optional. Dropping a new
module into `tools/` is the whole job of adding a tool; `load_all()` finds it.

The same registry feeds three consumers, so they can never disagree:
the agent loop (OpenAI-style `tools` for Jan), the MCP server (Nyarch, Claude
Code), and the prompt builder (the one-line catalogue small models read).

Small models get arguments wrong in predictable ways -- a number as a string,
a missing optional, a slightly wrong tool name -- so `call()` coerces and
fuzzy-matches before giving up, and every failure message says what to do
instead. That message goes back to the model, which usually fixes itself on
the next step.
"""

from __future__ import annotations

import difflib
import importlib
import inspect
import json
import pkgutil
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

TYPE_NAMES = {str: "string", int: "integer", float: "number", bool: "boolean"}


class ToolError(Exception):
    """A tool failed in a way the model can act on. The message is shown to it."""


@dataclass
class Tool:
    name: str
    toolset: str
    description: str
    func: Callable[..., Any]
    properties: dict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    example: dict | None = None
    risky: bool = False
    # A list the user asked to see: its output is the reply, word for word,
    # so a small model cannot shorten it or make lines up.
    show: bool = False
    # Natural ways to ask for it ("could you open {name}"), read by
    # acchan/phrases.py; a {slot} is a parameter name. An entry may be a
    # (phrase, fixed_args) pair. Risky tools get none.
    phrases: list = field(default_factory=list)
    # May it run from a spoken command nobody reads back first?
    # "ok": yes (fast path, phrases and the agent for a spoken request);
    # "fast": only from the fast path or a phrase, where code checks the
    # arguments first, never picked by the model for a spoken request;
    # "no" (the default): never, the reply asks for a yes in Acchan.
    voice: str = "no"

    def schema(self) -> dict:
        """OpenAI `tools` entry."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": self.required,
                },
            },
        }

    def signature(self) -> str:
        """`name(path, lines?)` -- the compact form small models read best."""
        parts = [p if p in self.required else p + "?" for p in self.properties]
        return f"{self.name}({', '.join(parts)})"


TOOLS: dict[str, Tool] = {}
TOOLSETS: dict[str, str] = {}  # toolset -> one-line summary, from each module
KEYWORDS: dict[str, tuple[str, ...]] = {}  # toolset -> words that suggest it
EXAMPLES: dict[str, list[tuple[str, str, dict]]] = {}  # toolset -> few-shot lines
COMPANIONS: dict[str, tuple[str, ...]] = {}  # toolset -> tools from other sets it needs
VOICE_LEVELS = ("ok", "fast", "no")  # see Tool.voice


def _param_schema(annotation: Any) -> dict:
    description = ""
    if typing.get_origin(annotation) is typing.Annotated:
        annotation, *meta = typing.get_args(annotation)
        description = " ".join(str(m) for m in meta if isinstance(m, str))
    schema: dict[str, Any] = {}
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        choices = list(typing.get_args(annotation))
        schema = {"type": TYPE_NAMES.get(type(choices[0]), "string"), "enum": choices}
    elif origin in (list, tuple):
        inner = (typing.get_args(annotation) or (str,))[0]
        schema = {"type": "array", "items": {"type": TYPE_NAMES.get(inner, "string")}}
    elif origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        schema = _param_schema(args[0]) if args else {"type": "string"}
    else:
        schema = {"type": TYPE_NAMES.get(annotation, "string")}
    if description:
        schema["description"] = description
    return schema


def tool(
    toolset: str,
    example: dict | None = None,
    risky: bool = False,
    show: bool = False,
    phrases: list | None = None,
    voice: str = "no",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function as a tool. The docstring's first paragraph is the
    description the model sees, so write it as an instruction."""
    if voice not in VOICE_LEVELS:
        raise ValueError(f"voice must be one of {VOICE_LEVELS}, not {voice!r}")
    if risky and voice != "no":
        raise ValueError("a risky tool cannot run from voice: leave voice at 'no'")

    def wrap(func: Callable[..., Any]) -> Callable[..., Any]:
        hints = typing.get_type_hints(func, include_extras=True)
        properties, required = {}, []
        for name, param in inspect.signature(func).parameters.items():
            properties[name] = _param_schema(hints.get(name, str))
            if param.default is inspect.Parameter.empty:
                required.append(name)
        doc = inspect.getdoc(func) or func.__name__
        TOOLS[func.__name__] = Tool(
            name=func.__name__,
            toolset=toolset,
            description=doc.split("\n\n")[0].replace("\n", " "),
            func=func,
            properties=properties,
            required=required,
            example=example,
            risky=risky,
            show=show,
            phrases=[] if risky else list(phrases or []),
            voice=voice,
        )
        return func

    return wrap


def load_all() -> dict[str, Tool]:
    """Import every module in acchan.tools (idempotent)."""
    from . import tools as package

    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        summary = getattr(module, "TOOLSET_SUMMARY", "")
        name = getattr(module, "TOOLSET", info.name)
        if summary:
            TOOLSETS[name] = summary
        KEYWORDS[name] = tuple(getattr(module, "TOOLSET_KEYWORDS", ()))
        EXAMPLES[name] = list(getattr(module, "TOOLSET_EXAMPLES", []))
        COMPANIONS[name] = tuple(getattr(module, "TOOLSET_COMPANIONS", ()))
    return TOOLS


def resolve_name(name: str) -> str | None:
    """The registered tool a model meant by `name`, or None."""
    if name in TOOLS:
        return name
    clean = name.strip().lower().replace("-", "_").replace(" ", "_")
    clean = clean.split(".")[-1]  # "functions.read_file" / "files.read_file"
    if clean in TOOLS:
        return clean
    close = difflib.get_close_matches(clean, TOOLS, n=1, cutoff=0.75)
    return close[0] if close else None


def _coerce(value: Any, schema: dict) -> Any:
    kind = schema.get("type")
    if kind == "integer" and not isinstance(value, bool):
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
        if isinstance(value, float) and value.is_integer():
            return int(value)
    if kind == "number" and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    if kind == "boolean" and isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "on")
    if (
        kind == "string"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return str(value)
    if kind == "string" and isinstance(value, list):
        return " ".join(str(v) for v in value)
    if kind == "array" and isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except ValueError:
            pass
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


def parse_arguments(raw: Any) -> dict:
    """Tool arguments as a dict, whatever shape the model sent them in."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    text = str(raw).strip()
    try:
        value = json.loads(text)
    except ValueError:
        # Trailing garbage after the object is the common small-model slip.
        end = text.rfind("}")
        try:
            value = json.loads(text[: end + 1]) if end > 0 else {}
        except ValueError:
            raise ToolError(
                'Arguments were not valid JSON. Send an object like {"path": "~/notes.txt"}.'
            )
    if not isinstance(value, dict):
        raise ToolError("Arguments must be a JSON object, not a list or a value.")
    return value


def call(name: str, arguments: Any) -> str:
    """Run a tool and return its result as text. Raises ToolError with a
    message written for the model."""
    real = resolve_name(name)
    if real is None:
        close = difflib.get_close_matches(name, TOOLS, n=3, cutoff=0.4)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise ToolError(f"There is no tool called {name!r}.{hint}")
    entry = TOOLS[real]
    args = parse_arguments(arguments)
    # Drop keys the tool does not take; map a lone unknown key onto a lone
    # missing required one (models often say "file" for "path").
    unknown = [k for k in args if k not in entry.properties]
    missing = [k for k in entry.required if k not in args]
    if len(unknown) == 1 and len(missing) == 1:
        args[missing[0]] = args.pop(unknown[0])
        missing = []
    for key in unknown:
        args.pop(key, None)
    if missing:
        raise ToolError(
            f"{real} needs {', '.join(missing)}. Call it as {entry.signature()}."
        )
    args = {k: _coerce(v, entry.properties[k]) for k, v in args.items()}
    try:
        result = entry.func(**args)
    except ToolError:
        raise
    except FileNotFoundError as exc:
        raise ToolError(
            f"Not found: {exc.filename or exc}. Check the path with list_dir or find_files."
        )
    except PermissionError as exc:
        raise ToolError(f"Permission denied: {exc.filename or exc}.")
    except TypeError as exc:
        raise ToolError(f"Wrong arguments for {entry.signature()}: {exc}")
    except Exception as exc:  # a tool bug must not kill the conversation
        raise ToolError(f"{real} failed: {type(exc).__name__}: {exc}")
    if result is None:
        return "done"
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=1, default=str)
