# TASK6 Baseline Metrics — 2026-05-24 01:05

## Backend
- `manage.py check`: 0 issues
- `makemigrations --check`: No changes detected (no drift)
- `Logistics models default=1 on tenant`: Confirmed existing (P-C target)
- `Logistics models default=1 on currency`: Confirmed existing (P-C target)

## Frontend
- `tsc --noEmit`: 41 errors (baseline)
- `vite build`: success (3395 modules)
- `console.log` in `services/` + `components/`: 0 (already cleaned in prior phases)
- `: any` in `*.tsx` components: 16 occurrences

## Project State
- Branch: `claude/task6` (created 2026-05-24)
- Git status: clean (task6.md and notes_extract.txt untracked)
- Active: main worktree, branch worktree

## PDF Error Scenarios (documented)
VII-1: AccountingJournalEntryPage hooks violation (line 444) — confirmed
VII-2: autoDisableScheduler 404 every minute — confirmed
VII-3: site.webmanifest missing 192px icon — confirmed
VII-4: Django ValidationError → 500 — confirmed in logistics models
VII-5: DealForm workflow error console-only — confirmed (line 506-509)
VII-6: cost-centers 500 on tenant without seed — confirmed (no seed command exists)
