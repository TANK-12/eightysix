# 2026-09-26 — Forge .gitignore and index cleanup (session ejb-57)

Emerson ran `git init` + `git add -A` in `~/Forge` (no commits yet) and staged
7,875 files, including a 2 GB model and a vendored VS Code server.

## Ask ledger

1. Add a sensible `.gitignore` to `~/Forge`.
2. Remove from git the files that should not have been added. Unstage only
   (`git rm --cached`): every file stays on disk.

## Owns

- `~/Forge/.gitignore` (new)
- the git index of `~/Forge`

## State

- 1 .gitignore: done+checked. `git ls-files -ci --exclude-standard` = 0 and
  `git status` shows no untracked leftovers. The one false positive the dry
  run could have hit (acchan `tests/results/*.log`, cited in its WIP) is
  re-included on purpose.
- 2 untrack: done+checked. 5,240 files unstaged (7,875 -> 2,635, ~99 MB);
  all still on disk; `git gc --prune=now` took `.git` from 2.8 GB to 70 MB
  with 0 staged blobs missing. No commit made; that is Emerson's call.
- Docs: CLAUDE.md and README.md "no version control" notes corrected;
  PROGRESS.json status + `session_2026_09_26_gitignore_work`
  (`session_57_work` moved to the archive to keep it under 40 KB).
- Open: ignored downloads (ai-studio models/bin 2.7 GB, openvscode-server
  244 MB) and `backups/` exist only on this disk; git does not protect them.
