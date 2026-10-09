# How the docs library works

date: 2026-09-29 · for: Emerson and Claude

This folder is where important text documents for Emerson and Claude go:
results worth keeping (scores, benchmarks, measurements, test figures),
plans, decisions, reference notes and anything either of you will want to
read later.

- One folder per topic (`Scores/`, `Notes/`, a project name, ...). Make a new
  folder when no existing one fits.
- File names start with the date: `YYYY-MM-DD-short-name.md` (or `.txt`).
- Near the top: a title line and `date: YYYY-MM-DD · for: Emerson / Claude / both`.
- Claude saves useful results here without being asked, so Emerson can ask
  for them later ("what were the codec scores?").
- Nothing here is deleted; an outdated doc gets a newer dated doc beside it.

The Claude app's **Docs** section (the "docs" button) shows this library plus
the docs that already live elsewhere (session briefs, app manifests and WIP
files, Claude's self notes and memory, model folders), all dated and newest
first. Where it looks is declared in `~/Forge/apps/claude/doc_sources.json`.
