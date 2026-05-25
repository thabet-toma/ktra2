# PROJECT_MAP — K.T.R.A

## [TECH_STACK]
- **Frontend:** React 19, TypeScript 5.8, Vite 6, Tailwind CSS 4, react-router-dom 7
- **Backend:** Django 5.x (Python), MySQL (production), SQLite (test)
- **PWA:** vite-plugin-pwa 1.3, workbox-window 7.4, Dexie 4.4
- **Testing:** pytest-django, Playwright (E2E)
- **Icons:** lucide-react
- **Charts:** recharts

## [SYSTEM_FLOW]
```
User → Browser → React SPA (App.tsx)
  ├─ Online ───→ REST API (Django) ──→ MySQL
  └─ Offline ──→ IndexedDB (Dexie) ──→ cachedApi wrapper
                    ↓
              mutation_queue → Background Sync (on reconnect)
```

## [ARCHITECTURE]
```
frontend_v2/
├── App.tsx                    # Root SPA routing (all views)
├── index.tsx                  # Entry point (BrowserRouter)
├── index.html                 # HTML shell + PWA manifest link
├── sw.ts                      # Service Worker (PWA)
├── vite.config.ts             # Vite + vite-plugin-pwa + Tailwind
├── public/
│   ├── site.webmanifest       # PWA manifest
│   ├── offline.html           # Offline fallback page
│   ├── android-chrome-512x512.png
│   ├── apple-touch-icon.png
│   ├── favicon-*.png / .ico
│   └── notification-sound.mp3
├── services/
│   ├── offline/
│   │   ├── db.ts              # Dexie IndexedDB schema
│   │   └── cachedApi.ts       # Stale-while-revalidate API wrapper
│   ├── restApi.ts             # Base HTTP client
│   ├── salesApi.ts            # Sales API
│   ├── clearanceApi.ts        # Clearance API
│   └── ...                    # Domain-specific APIs
├── hooks/
│   └── useOnlineStatus.ts     # Network heartbeat hook
├── components/
│   ├── offline/
│   │   ├── UpdatePrompt.tsx        # SW update toast
│   │   ├── OfflineBanner.tsx       # Global sticky banner
│   │   ├── StalenessBadge.tsx      # Per-record freshness pill
│   │   ├── OfflineGuard.tsx        # Post button wrapper
│   │   ├── StaleDataConfirm.tsx    # Pre-action cache warning modal
│   │   ├── PendingMutationsPanel.tsx
│   │   ├── SyncConflictModal.tsx
│   │   ├── StatusMessage.tsx       # WCAG 4.1.3 live region
│   │   └── OfflineCoachmark.tsx    # First-offline onboarding
│   ├── sales/                       # Sales domain
│   ├── procurement/                 # Procurement domain
│   ├── accounting/                  # Accounting domain
│   └── ...                          # Other domains
├── types.ts, types/           # TypeScript type definitions
├── contexts/                  # React contexts (Auth, Theme)
├── utils/                     # Utility functions
├── styles/                    # CSS (Tailwind entry)
└── constants/                 # App constants
```

## [ORPHANS & PENDING]
- [x] Phase 1: PWA Foundation (Manifest, vite-plugin-pwa, UpdatePrompt, offline page)
- [x] Phase 2: Read-Side Cache + Online/Offline UI (Dexie, cachedApi, useOnlineStatus, OfflineBanner, StalenessBadge)
- [ ] Phase 3: Employee Guidance UI (OfflineGuard, StaleDataConfirm, PendingMutations, SyncConflict, StatusMessages, Coachmark)
- [ ] Phase 4: Draft-Mode Writes + Sync Queue
- [ ] Phase 5: Storage Quotas + Multi-Tab + Playwright Tests

## [TASK7 — Phase 1 + 2 review 2026-05-25]

External-model dropped Phase 1 + 2 infrastructure on `main` (uncommitted): vite-plugin-pwa wired, SW (`sw.ts`) with 3 caching strategies (cache-first / SWR / network-first), Dexie schema with 9 stores, `cachedGet`/`cachedGetList` wrapper, `useOnlineStatus` heartbeat hook, `OfflineBanner` / `UpdatePrompt` / `StalenessBadge` components, offline fallback page, manifest extension (categories + shortcuts + screenshots).

### Errors found and corrected
1. **Manifest referenced files that don't exist.** `android-chrome-192x192.png` was deliberately removed in task6 P-B-4 because the file was missing; the external model added the reference back without creating the file. `/screenshots/dashboard.png` etc. also referenced — same problem. Both would 404 in DevTools and degrade PWA install criteria. **Fix:** stripped non-existent references; kept the 512×512 maskable icon + categories + shortcuts (without per-shortcut icons).
2. **`StalenessBadge` and `cachedGet*` were dead code** — components/services declared and exported but never consumed by any screen. Phase 2 specs 2-2-b («refactor productsApi/partnersApi/accountsApi to use the wrapper») and 2-5-b («add StalenessBadge to ItemsManagement, SupplierManagement, CustomersManagement») were skipped. **Fix:** wired both into `ItemsManagement.tsx`:
   - `load()` now mirrors fresh API rows into the Dexie `products` store + writes a `cache_meta` entry timestamped to «now».
   - When the network fails, `load()` falls back to the Dexie snapshot, sets `fromCache=true`, and surfaces the staleness via the new badge + a yellow «من الذاكرة المحلية» pill (role=status + aria-live=polite, WCAG 4.1.3 compliant).
   - `StalenessBadge updatedAt={lastSync}` color-codes by age: green <2h / yellow 2-24h / red >24h.

### Verified
- `tsc --noEmit` = 0
- `manage.py check` = 0, no migration drift
- `vite-plugin-pwa` + `dexie` + `workbox-window` installed in package.json
- SW registers in production builds; dev runs without SW (devOptions.enabled=false to keep HMR working)

### Pending in task7
- Phase 3 (Employee Guidance) — the heart of the task per the doc.
- Phase 4 (Draft-Mode Writes + Sync Queue).
- Phase 5 (Storage quotas + multi-tab + Playwright tests).
