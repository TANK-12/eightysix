"""Finds every keybind declaration in a Hyprland Lua config file.

Scans for `hl.bind(...)` and `create_bind(...)` call sites (the latter is
Caelestia's own thin wrapper around `hl.bind`, used for every one of its
binds instead of calling `hl.bind` directly). For each call, classifies the
first argument -- the key combo -- as:

  literal   a plain quoted string: `hl.bind("SUPER + T", ...)`.
  vars      a `vars.something` reference whose value lives in a separate
            variables file, resolved by `resolve_vars_target`.
  generated anything else: string concatenation, loop variables, table
            literals with more than one combo. These are real keybinds and
            are still returned, but are not single-value edit targets --
            see the plan's "What editable actually means here" section for
            why that boundary exists.

This is a small hand-written scanner rather than a Lua parser or a bag of
regexes: the files only use a narrow grammar subset (balanced parens/braces,
quoted strings with backslash escapes, `--` line comments), and a real
scanner handles nested calls and multi-line calls correctly, which regex
does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CALL_HEAD = re.compile(r"\b(hl\.bind|create_bind)\s*\(")
DESCRIPTION = re.compile(r'description\s*=\s*"((?:[^"\\]|\\.)*)"')


@dataclass
class Bind:
    file: Path
    start_line: int
    end_line: int
    raw: str
    description: str | None
    kind: str  # "literal" | "vars" | "generated"
    key_display: str
    editable: bool
    edit_file: Path | None = None
    edit_line: int | None = None
    edit_old_text: str | None = (
        None  # exact substring to match+replace, quotes included
    )


def _skip_ws_and_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            i += 1
        elif text.startswith("--", i):
            nl = text.find("\n", i)
            i = n if nl == -1 else nl + 1
        else:
            break
    return i


def _scan_string(text: str, i: int) -> int:
    """text[i] is a quote character. Returns index just past the closing quote."""
    quote = text[i]
    i += 1
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return n  # unterminated; treat as running to EOF rather than looping forever


def _find_call_close_paren(text: str, open_paren_idx: int) -> int:
    """Given the index of a call's opening '(', return the index of the
    matching ')', skipping over strings, comments, and nested (), {}."""
    i = open_paren_idx + 1
    depth = 1
    n = len(text)
    while i < n and depth > 0:
        c = text[i]
        if c in "\"'":
            i = _scan_string(text, i)
            continue
        if text.startswith("--", i):
            nl = text.find("\n", i)
            i = n if nl == -1 else nl + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        i += 1
    return i - 1  # index of the matching ')'


def _first_arg_span(
    text: str, open_paren_idx: int, close_paren_idx: int
) -> tuple[int, int]:
    """Returns (start, end) of the first top-level argument, exclusive of the
    delimiting comma, inside a call's parens."""
    i = open_paren_idx + 1
    depth = 0  # relative to just inside the call's own parens
    n = close_paren_idx
    start = _skip_ws_and_comments(text, i)
    i = start
    while i < n:
        c = text[i]
        if c in "\"'":
            i = _scan_string(text, i)
            continue
        if text.startswith("--", i):
            nl = text.find("\n", i)
            i = n if nl == -1 or nl > n else nl + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            return start, i
        i += 1
    return start, n


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def parse_binds_file(path: Path) -> list[Bind]:
    text = path.read_text(encoding="utf-8")
    binds: list[Bind] = []

    for m in CALL_HEAD.finditer(text):
        open_paren = m.end() - 1
        close_paren = _find_call_close_paren(text, open_paren)
        arg_start, arg_end = _first_arg_span(text, open_paren, close_paren)
        first_arg = text[arg_start:arg_end].strip()
        raw = text[m.start() : close_paren + 1]

        # Skip create_bind's own internal `hl.bind(key, action, get_flags(key))` --
        # that's the wrapper's plumbing, not a user-facing keybind. `key` there is
        # always a bare loop variable, never a quoted literal or `vars.` reference.
        if first_arg == "key":
            continue

        desc_match = DESCRIPTION.search(raw)
        description = desc_match.group(1) if desc_match else None

        if first_arg[:1] in "\"'" and first_arg[-1:] == first_arg[0]:
            kind = "literal"
            key_display = first_arg[1:-1]
            editable = True
            edit_file, edit_line, edit_old = path, _line_of(text, arg_start), first_arg
        elif re.fullmatch(r"vars\.[A-Za-z_][A-Za-z0-9_]*", first_arg):
            kind = "vars"
            key_display = first_arg
            editable = False  # resolved by resolve_vars_target() against the caller-supplied vars file
            edit_file = edit_line = edit_old = None
        else:
            kind = "generated"
            key_display = first_arg
            editable = False
            edit_file = edit_line = edit_old = None

        binds.append(
            Bind(
                file=path,
                start_line=_line_of(text, m.start()),
                end_line=_line_of(text, close_paren),
                raw=raw,
                description=description,
                kind=kind,
                key_display=key_display,
                editable=editable,
                edit_file=edit_file,
                edit_line=edit_line,
                edit_old_text=edit_old,
            )
        )

    return binds


def resolve_vars_target(
    field_ref: str, vars_file: Path
) -> tuple[Path, int, str, str] | None:
    """field_ref is e.g. "vars.kbTerminal". Looks up `kbTerminal = ...` in
    vars_file. Returns (file, line, old_text, resolved_display) if the value
    is a single quoted literal (editable), or None if it's a table (multiple
    combos -- generated/view-only, same reasoning as loop-generated binds)."""
    field = field_ref.split(".", 1)[1]
    text = vars_file.read_text(encoding="utf-8")
    m = re.search(rf"\b{re.escape(field)}\s*=\s*", text)
    if not m:
        return None
    value_start = m.end()
    value_start = _skip_ws_and_comments(text, value_start)
    if text[value_start] not in "\"'":
        return None  # table literal or expression -- not a single editable value
    value_end = _scan_string(text, value_start)
    old_text = text[value_start:value_end]
    return vars_file, _line_of(text, value_start), old_text, old_text[1:-1]
