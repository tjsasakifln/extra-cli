# OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01 — Status

**Updated:** 2026-07-23  
**Branch:** `campaign/open-tenders-operational-decision-cycle-01`  
**Base:** `origin/main` @ `3e04728e4277320454e5bf218cc008e5000b970f`

## Verdict (this wave)

| Layer | Result |
|-------|--------|
| Baseline inspection | DONE (`baseline.json` + `BASELINE.md`) |
| Structural campaign gate | **PASS** (`make campaign-gate-open-tenders` → 12/12) |
| Unit tests (targeted) | **PASS** (60 weekly/E/policy tests) |
| Coverage evidence projection | **PASS** locally (1093 rows after ON CONFLICT fix) |
| Offline weekly pack + Deliverable E | **PASS** local (`deliverable_e_ok=true`, 4 opps from partial live crawl residue) |
| Complete PNCP 19-modality live collect | **BLOCKED** from this host (API timeouts / partial) |
| Live dual open_tenders coverage ≥95% | **NOT YET** |
| VPS deploy + timer + soak 7d | **NOT YET** (VPS still SHA `5f92211…`, no `extra-weekly` timer) |
| Full campaign PASS | **OPEN / effectively BLOCKED on deploy+network** |

Honest closure for the full goal is still **not PASS**. Material foundation committed on branch `campaign/open-tenders-operational-decision-cycle-01` (`667d972`).

## What changed (implementation)

1. **Canonical collect** — `weekly_cycle` uses `run_pncp_open_monitoring` (aggregated modalities + reconciler on complete only). Removed orphan per-modalidade `crawler.run()` loop as weekly path.
2. **SLA 24h** — default `WEEKLY_PNCP_SLA_HOURS=24` (DOD editais).
3. **CIGA SLA 24h** — `config/source_applicability.yaml` v2.1.1; DOD prevails over prior 48h note.
4. **Deliverable E live** — `from-db` / `audit-db`; operational audit fail-closed on EMPTY; weekly pack emits `deliverable_e.json`.
5. **Profile PENDING** — critical capacity never yields GO/PARTICIPAR (ADR-022).
6. **Snapshot integrity** — `scripts/ops/snapshot_integrity.py`.
7. **systemd** — `extra-weekly.service` + `.timer` (venv, flock, Conflicts with concurrent PNCP crawls).
8. **Gates** — `make campaign-gate-open-tenders` / `release-candidate-open-tenders` without breaking HC targets.

## Evidence paths

- `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/baseline.json`
- `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/campaign-gate.json`
- `specs/003-open-tenders-operational-decision-cycle/spec.md`

## Next operational steps (blocked on deploy / network collect)

1. Merge to main with CI green.
2. Deploy SHA to VPS; enable `extra-weekly.timer`.
3. Run live `python -m scripts.ops.weekly_cycle --strict --force-collect`.
4. Regenerate dual coverage open_tenders + freshness; snapshot integrity.
5. Generate live Deliverable E; human triage.
6. Soak 7 days with timers; then DOD accept only proven items.

## DOD mapping (this wave)

| Item theme | Progress |
|------------|----------|
| Snapshot integrity 100% | Module + gate; **not ACCEPTED** (empty lake) |
| Editais freshness ≤24h | Code/policy aligned; **not ACCEPTED** (no live fresh run) |
| Entregável E | Live path + fail-closed; **not ACCEPTED** without live recs |
| Ciclo semanal | Canonical path + unit; **not ACCEPTED** on VPS |
| Cobertura open_tenders ≥95% | **unchanged 0%** until live collect |
