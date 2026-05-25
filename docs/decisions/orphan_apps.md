# Orphan Frontend Apps — Decision

> **Status:** documented · 2026-05-25 (task6 P-K-2)
> **Owner approval required to delete.**

Two directories under the repo root are not part of the ERP and never have been:

| Directory | What it is | Why it's here |
|-----------|------------|---------------|
| `frontend/` | Default Create-React-App scaffold. Not the live frontend (that is `frontend_v2/`). | Left behind from an early prototype. |
| `smart-product-search-platform/` | A standalone Next.js mini-app for a product-search demo. | Spun off as a separate experiment that never landed in the ERP. |

Both are already `.gitignored` (see `.gitignore` lines 41–45). New clones do **not** pull them.

## Recommendation

**Move out of this repo.** Neither directory is exercised by `manage.py`, `vite`, `pytest`, the CI workflow, or any code in `frontend_v2/`. Keeping them inside the worktree:

- Confuses `density-audit.cjs` (the script ignores `node_modules` but walks every other directory).
- Lengthens `grep -r` and IDE-index runs by ~10 MB.
- Makes the repo look like it ships two extra apps when it doesn't.

## Options

1. **Move out + delete locally.** Owner copies the directories to a separate repo (or backs them up), then `rm -rf` them from this worktree. They stay gitignored so a future clone is clean.
2. **Status quo (gitignored).** Leave them on disk; they don't ship in any sense, but they take up the index and disk space.

This document is a placeholder pending owner decision — no automated action is taken here.
