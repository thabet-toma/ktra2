# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

**Layout: single-context.** One context, one glossary at the repo root, one decisions folder.

## Before exploring, read these

- **`ARCHITECTURE.md`** at the repo root — the app map, dependency graph, and cross-cutting rules. Always start here.
- **`docs/modules/<module>.md`** — the files, models, services, endpoints and must-not-break rules for the module you're about to touch.
- **`CONTEXT.md`** at the repo root — the domain glossary (ubiquitous language). Does not exist yet; `/domain-modeling` creates it lazily.
- **`docs/decisions/`** — this repo's ADR folder. Read the decision records that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

Note: `CLAUDE.md` names `ARCHITECTURE.md` + `docs/modules/<module>.md` as the mandatory context read before any task. That rule wins — the files above are additive to it, not a replacement.

## File structure

```
/
├── ARCHITECTURE.md                    ← app map + cross-cutting rules (authoritative)
├── CONTEXT.md                         ← domain glossary (created lazily by /domain-modeling)
├── docs/
│   ├── modules/<module>.md            ← per-module contracts
│   ├── decisions/                     ← ADRs live here (NOT docs/adr/)
│   │   ├── attachments_model.md
│   │   ├── orphan_apps.md
│   │   └── payment_model_unification.md
│   └── agents/                        ← this folder
└── <django apps at the repo root>     ← no src/ directory; frontend_v2/ has no src/ either
```

New ADRs go in `docs/decisions/`. Do not create `docs/adr/`.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md` — and, until that file exists, the terms already used in `ARCHITECTURE.md` and `docs/modules/`. Don't drift to synonyms the project avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing decision record in `docs/decisions/`, surface it explicitly rather than silently overriding:

> _Contradicts `docs/decisions/payment_model_unification.md` — but worth reopening because…_

## After changing code

Per `CLAUDE.md`: update `ARCHITECTURE.md` and `docs/modules/<module>.md` when a **description** in them changes, add a line to `docs/CHANGELOG.md`, then run `python manage.py sync_docs`. Docs reference `` `file.py` (`symbol`) `` — never line numbers.
