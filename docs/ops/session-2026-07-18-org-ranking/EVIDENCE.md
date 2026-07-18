# Evidence — ROI-cand-dyn-slice-8d8c11884fa6 (Entregável A)

## Commands
```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 scripts/reports/org_ranking.py --uf SC --limit 20
python3 scripts/reports/deliverable_orgaos_ranking.py --uf SC --output docs/ops/session-2026-07-18-org-ranking/deliverable-a.json
python3 -m scripts.ops.deliverable_a_org_ranking fixture --out docs/ops/session-2026-07-18-org-ranking/fixture-a.json
python3 -m scripts.ops.deliverable_a_org_ranking audit-fixture
python3 -m pytest tests/test_deliverable_a_org_ranking.py -q --tb=short --no-cov
```

## Live DSN result
- opportunity_intel / pncp_supplier_contracts / pncp_raw_bids: **0 rows**
- org_ranking status=**INSUFFICIENT** (honest; no fake market)

## Fixture
- Schema proves all 10 DoD field requirements with zero vs not_consulted + data quality warning
