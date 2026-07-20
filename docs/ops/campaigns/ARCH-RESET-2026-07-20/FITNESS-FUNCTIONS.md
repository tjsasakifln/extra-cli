# Architecture fitness functions — ARCH-RESET-2026-07-20

**Principle:** simple, useful, fail-closed checks. Not a second governance framework.

Implementation lands primarily in PR B/C (tests) and may start as **advisory** scripts under `scripts/architecture/`. This PR A defines the contract.

## Required checks

| # | Function | Intent | Suggested signal |
|---|----------|--------|------------------|
| 1 | One canonical weekly product entrypoint | Prevent dual product pipelines | `docs/canonical-entry-points.yaml` + Makefile: exactly one command classed `canonical` for weekly ops |
| 2 | One canonical source registry | Avoid dual registries | Single module path declared + imported by weekly path |
| 3 | One canonical coverage contract | Collapse multiplicity | Single public API for operational coverage % |
| 4 | One canonical freshness contract | Collapse multiplicity | Single public API for freshness gate |
| 5 | One official weekly pack generator | Single delivery path | weekly_cycle owns pack `run_id` |
| 6 | Same `run_id` across pack artifacts | Reconciliation | Manifest lists MD/CSV/Excel/PDF with shared run_id |
| 7 | No LLM module computes coverage/freshness | Determinism | Static import/grep denylist on coverage/freshness entrypoints |
| 8 | No doc presents fixture as live | Honesty | Claim-language / session scanners |
| 9 | No report presents stale as current without flag | Honesty | Status/freshness fields required |
| 10 | No `unknown` status shown as open | Fail-closed | Decision + status mappers |
| 11 | No expired tender recommended PARTICIPAR | Fail-closed | Decision tests (see #52) |
| 12 | No probabilistic merge overrides conflicting CNPJ | Identity safety | Entity resolution tests |
| 13 | New dependency has license record | Supply chain | requirements change → license note in PR template |
| 14 | No alternate pipeline without ADR | Architecture | New orchestrator modules require ADR link |
| 15 | DoD `[x]` not granted by file presence alone | Evidence | Checklist: evidence path + command + date |

## Non-goals

- Replacing pytest.  
- Scoring agents or ROI campaigns.  
- Blocking development on advisory inventory drift during early PRs (start WARN, graduate to FAIL after PR C).

## Minimal implementation sketch

```text
scripts/architecture/
  inventory_baseline.py      # regenerate baseline.json
  fitness_check.py           # advisory → fail-closed later
tests/architecture/
  test_fitness_entrypoint_canonical.py
  test_fitness_no_llm_coverage.py
```

PR A ships `inventory_baseline.py` only (no production behavior change).
