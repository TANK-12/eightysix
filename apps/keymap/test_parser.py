"""Tests the parser and vars-resolution against the real Hyprland config on
this machine -- there's no fixture copy, since the whole point is that this
tool has to stay correct against files that change over time."""

from pathlib import Path

from parser import parse_binds_file, resolve_vars_target

HYPR = Path.home() / ".config" / "hypr"
SHARED_KEYBINDS = HYPR / "hyprland" / "keybinds.lua"
CAELESTIA_KEYBINDS = HYPR / "caelestia-keybinds.lua"
VARIABLES = HYPR / "variables.lua"
BRAIN_KEYBINDS = Path.home() / ".config" / "Brain_Shell" / "Brain_ShellKeybinds.lua"


def test_finds_known_static_bind():
    binds = parse_binds_file(SHARED_KEYBINDS)
    terminal_binds = [
        b for b in binds if b.kind == "literal" and b.key_display == "SUPER + T"
    ]
    assert (
        terminal_binds
    ), "expected a literal SUPER + T bind in the shared keybinds file"
    assert terminal_binds[0].editable
    assert terminal_binds[0].edit_old_text == '"SUPER + T"'


def test_flags_loop_generated_binds_as_non_editable():
    binds = parse_binds_file(SHARED_KEYBINDS)
    generated = [b for b in binds if b.kind == "generated"]
    assert (
        generated
    ), "expected at least one loop-generated bind (workspace focus, etc.)"
    assert all(not b.editable for b in generated)


def test_descriptions_are_extracted():
    binds = parse_binds_file(SHARED_KEYBINDS)
    described = [b for b in binds if b.description == "App: Terminal"]
    assert described


def test_caelestia_uses_vars_indirection():
    binds = parse_binds_file(CAELESTIA_KEYBINDS)
    kinds = {b.kind for b in binds}
    assert "vars" in kinds
    terminal = [b for b in binds if b.key_display == "vars.kbTerminal"]
    assert terminal
    assert not terminal[0].editable  # resolved separately, against variables.lua


def test_resolve_vars_target_single_literal():
    resolved = resolve_vars_target("vars.kbTerminal", VARIABLES)
    assert resolved is not None
    _file, _line, old_text, display = resolved
    assert display == "SUPER + T"
    assert old_text == '"SUPER + T"'


def test_resolve_vars_target_table_value_is_not_editable():
    # kbPrevWs is an array of alternate combos in variables.lua, not a single literal.
    resolved = resolve_vars_target("vars.kbPrevWs", VARIABLES)
    assert resolved is None


def test_brain_shell_binds_are_all_literal():
    binds = parse_binds_file(BRAIN_KEYBINDS)
    assert binds
    assert all(b.kind == "literal" and b.editable for b in binds)


def test_create_bind_wrapper_plumbing_is_excluded():
    binds = parse_binds_file(CAELESTIA_KEYBINDS)
    assert not any(b.key_display == "key" for b in binds)
