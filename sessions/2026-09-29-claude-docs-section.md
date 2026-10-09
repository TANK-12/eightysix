# Claude app Docs section and the docs library rule — session "Docs"

Emerson, 2026-09-29.

## Ledger
- A1 "important text documents for me and claude to read have a section in the claude app" -> Docs page in apps/claude. [core]
- A2 "are dated and foldered" -> every doc shows a date and sits in a folder tree; new ones go in ~/Forge/docs/library/<topic>/YYYY-MM-DD-name.md. [core]
- A3 "make it rule" -> "Docs library" section in ~/.claude/CLAUDE.md, forge-session skill, memory. [core]
- A4 "scores and other things that seem useful to me are stored and I can ask" -> rule says store results there by default. [core]
- A5 "mostly read only, just quickly make it" -> read-only viewer, defaults assumed. [constraint]

## State
- A1 done + checked: tests/test_docs_library.py 5 passed; screenshot on a test server.
- A2 done + checked: dated by name, header or last change (italics when guessed).
- A3 done: CLAUDE.md, forge-session SKILL.md, memory important-docs-dated-and-foldered.md.
- A4 done: in the rule and the library's how-it-works doc.
- A5 done: nothing writes or deletes docs.
