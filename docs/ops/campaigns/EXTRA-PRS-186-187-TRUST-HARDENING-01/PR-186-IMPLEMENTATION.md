# PR #186 Implementation — Trust Hardening

**Branch:** `feat/extra-local-command-center`  
**Baseline HEAD:** `0913b2f5c7fef41ae830c40478342822d5737767`

## Changes by workstream

### A1 Brand
- Removed invented SVGs (`logo-confenge.svg`, `logo-confenge-white.svg`) and non-canonical white PNG.
- Installed official `web-cfg` asset byte-for-byte:
  - path: `apps/command-center/public/brand/logo-confenge.png`
  - SHA-256: `e6af0125c73edd476cff82ab4ea1de3e459fbdbde63b886f6c55f8a93531505b`
  - dims: 800×208
- Sidebar uses official color logo on a light plate (no CSS invert).
- Logo once in shell; Home header logo removed.
- Unit test pins checksum marker on `BrandLogo`.

### A2 Status tokens
- Full semantic tokens in `tokens.css` for light/dark: healthy, running, attention, blocked-human/technical/external, partial, no-data, unknown (bg/fg/border).
- `StatusBadge` uses `normalizeAttentionKind` — never blind-casts; unknown → “Status desconhecido”.
- Technical codes no longer clutter the primary badge by default.

### A4 Home hierarchy
- Backend `overview` priorities: human reviews → blocked → failed → partial → running (grouped) → warnings → advanced caps.
- Duplicate review quick-actions removed.
- “Iniciar novo trabalho” moved above secondary modules.
- Accessible labels for open/compare/review actions.
- Action cards are real links (no nested fake buttons).

### A5–A6 Reviews
- Contract: `reviews`, `page_count`, `total_count`, `limit`, `offset` (+ `count` alias = total).
- `COUNT(*)` via `store.count_reviews`; index on `(status, ts)`.
- Unique partial index on `job_id`.
- GET `/api/reviews` is side-effect free.
- POST `/api/reviews/reconcile` (CSRF) for idempotent BLOCKED_HUMAN enqueue + audit.

### A7 Health
- States: Verificando… / Local OK / Degradado / Offline.
- Payload includes `ok`, `degraded`, `services`.

### A8 Dates
- `lib/format.ts`: pt-BR absolute + relative; ISO in `title` only.

### A9 Routes / errors
- Catch-all → `NotFoundPage` (no silent Home redirect).
- Global + page `ErrorBoundary` with retry, safe technical detail, secret redaction.
- Route census Playwright suite.

### A10 Palette / search
- Command palette: aria-modal, focus return, empty state, AbortController, active index clamp, canonical route list.
- Search: `ArtifactSearchIndex` TTL catalog — no per-request full rglob.

### A11 HTTP client
- Timeout, AbortSignal, typed `ApiError`, single CSRF refresh on 403 for mutations, humanized errors.

### A12 XLSX
- Reject `.xls` with clear message; windowed read-only openpyxl; cell neutralization; guaranteed close.

### A13 Responsive
- Scrim + Escape + body scroll lock for mobile nav; topbar collapses secondary actions at 768/390.

### A15 Headers
- CSP, Permissions-Policy, COOP, X-Frame-Options, nosniff, Referrer-Policy, no-store.

## Tests added
- `tests/command_center/test_trust_hardening.py`
- `apps/command-center/src/components/BrandLogo.test.tsx`
- `apps/command-center/e2e/route-census.spec.ts`
- `apps/command-center/e2e/visual-matrix.spec.ts`
- npm scripts: `test:visual`, `test:a11y`, `test:routes`
