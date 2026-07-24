# Command inventory — contracts / coverage / ops deliverables

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Base:** `origin/main` @ `a38981b`  
**Canonical meta-entry points:** `docs/canonical-entry-points.yaml`, `docs/DEVELOPMENT.md`

All commands assumed from repo root with `PYTHONPATH=.` or `python3 -m`.

---

## 1. Environment / DSN

```bash
# Default local test (HC and general ops on main paths)
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"

# This campaign isolated DB (schema checks only — do not point HC backfill here)
export NI_DSN="postgresql://test:test@127.0.0.1:5435/extra_national_intelligence_test"
```

---

## 2. Schema / migrations

```bash
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m scripts.ops.schema_audit   # if used in gates
```

---

## 3. Crawl — contracts

### 3.1 Multi-source monitor (registry)

```bash
# Full window (default CONTRACTS_FULL_DAYS=90)
python3 -m scripts.crawl.monitor --source contracts --mode full --dsn "$LOCAL_DATALAKE_DSN"

# Incremental (default 3 days)
python3 -m scripts.crawl.monitor --source contracts --mode incremental --dsn "$LOCAL_DATALAKE_DSN"

# Coverage report only (no crawl)
python3 -m scripts.crawl.monitor --report-coverage --dsn "$LOCAL_DATALAKE_DSN"

# Optional: --output-json PATH, --strict, --date-from/--date-to (backfill), --limit
```

**Notes**

- Source name in registry: `contracts` → module `contracts_crawler`.
- Crawler-native mode `backfill_3y` is implemented in `contracts_crawler.py`; monitor argparse lists `full|incremental|dry-run|template|selenium|detect|backfill` — verify mode mapping when invoking long backfills (prefer dedicated pilot/runner for national volume).
- Checkpoints: `data/contracts_checkpoints/contracts_{mode}.json`.
- **Do not** write `hc_closure_*` checkpoints from this campaign.

### 3.2 90-day pilot (memory-safe national path)

```bash
PYTHONPATH=. python3 scripts/crawl/run_contracts_90d_pilot.py \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --output-json output/contracts/pilot-90d-next30d.json
```

### 3.3 Ops thin pilot wrapper

```bash
python3 -m scripts.ops.run_contracts_pilot
# env: DATABASE_URL / LOCAL_DATALAKE_DSN, CONTRACTS_FULL_DAYS
# writes: output/contracts/pilot-90d-next30d.json
```

### 3.4 Related PNCP / crawl

```bash
python3 -m scripts.crawl.monitor --source pncp --mode full|incremental
python3 -m scripts.crawl.monitor --source all --mode incremental   # if registry supports all
# Other sources: sc_compras, ciga, transparencia, … (bids / hybrid — not contracts lake)
```

Env prefix for contracts crawler: `CONTRACTS_BASE`, `CONTRACTS_PAGE_SIZE`, `CONTRACTS_WINDOW_DAYS`, `CONTRACTS_FULL_DAYS`, `CONTRACTS_INCREMENTAL_DAYS`, `CONTRACTS_BACKFILL_YEARS`, `CONTRACTS_CHECKPOINT_DIR`, `CONTRACTS_PERSIST_EACH_WINDOW`, …

---

## 4. Coverage

### 4.1 Dual capability (canonical)

```bash
python3 -m scripts.coverage.dual_capability_coverage \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --capability both \
  --output-dir output/coverage

# Single capability
python3 -m scripts.coverage.dual_capability_coverage \
  --dsn "$LOCAL_DATALAKE_DSN" \
  --capability historical_contracts

# Fail if gate < 95%
python3 -m scripts.coverage.dual_capability_coverage --dsn "$LOCAL_DATALAKE_DSN" --require-gate

# Identity stamps (optional)
# --seed PATH --expected-entity-count N --expected-seed-sha256 … --expected-canonical-ids-sha256 …
# --json-stdout
```

### 4.2 Coverage contract / validation helpers

```bash
python3 -m scripts.coverage.coverage_contract_cli   # indicator catalog / contract CLI
python3 -m scripts.coverage.validate_coverage
python3 -m scripts.coverage.freshness_by_entity      # ADR-028 freshness packs
python3 -m scripts.coverage.session_coverage_pipeline
python3 -m scripts.ops.probe_entity_success_zero     # success_zero probe evidence
```

### 4.3 Golden path (includes dual coverage)

```bash
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
# dual-only switches exist in golden_path: --execute-coverage-only / --execute-dual-coverage-only (see module)
```

---

## 5. Contract intel CLI

```bash
python3 -m scripts.contract_intel.cli historico [--limit N] [--format table|json|csv] [--output PATH]
python3 -m scripts.contract_intel.cli fornecedores [--limit N] …
python3 -m scripts.contract_intel.cli ativos [--limit N] …          # expiring-style view
python3 -m scripts.contract_intel.cli manifesto [--format table|json] [--output-csv gaps]
python3 -m scripts.contract_intel.cli stats
python3 -m scripts.contract_intel.cli precos --orgao CNPJ [--periodo years]
python3 -m scripts.contract_intel.cli desagio [--modalidade NAME]
```

DSN via environment / module defaults; readiness threshold 0.95 for manifesto exit.

Target universe helper: `scripts/contract_intel/target_universe.py` (Haversine / seed).

---

## 6. Workspace CLI (facade)

```bash
# See scripts/workspace/cli.py — commands include today, opportunities, coverage,
# competitors, expiring-contracts, prices, contracts, dossier, decide, …
python3 -m scripts.workspace.cli --help
```

Uses `pncp_supplier_contracts` for contracts/competitors/prices sections when PG available.

---

## 7. Ops deliverables A–E + package

```bash
python3 -m scripts.ops.deliverable_a_org_ranking --help
python3 -m scripts.ops.deliverable_b_competitors --help
python3 -m scripts.ops.deliverable_c_expiring --help
python3 -m scripts.ops.deliverable_d_prices --help
python3 -m scripts.ops.deliverable_e_editais --help
python3 -m scripts.ops.deliverable_package_final --help
```

Typically support fixture/audit modes and live DSN; empty lake → `INSUFFICIENT` (fail-closed honesty).

---

## 8. Weekly / commercial ops

```bash
make extra-weekly
# or
python3 -m scripts.ops.weekly_cycle --strict

python3 -m scripts.ops.strategic_monthly_monitor
python3 -m scripts.ops.crawler_monitor
python3 -m scripts.ops.health
```

Weekly cycle reuses `pncp_supplier_contracts` with explicit freshness labeling (`pncp_contracts` run identity).

---

## 9. Reports

```bash
python3 -m scripts.reports.contratos_report
python3 -m scripts.reports.concorrentes_report
python3 -m scripts.reports.valores_report
python3 -m scripts.reports.org_ranking
python3 -m scripts.reports.panorama --output-excel
python3 -m scripts.reports.coverage_weekly
python3 -m scripts.reports.coverage_gaps
python3 -m scripts.reports.executive_report
python3 -m scripts.reports.operational_export_pack
```

---

## 10. Opportunity intel (adjacent)

```bash
python3 -m scripts.opportunity_intel.cli list --status open --limit 20
python3 -m scripts.opportunity_intel.cli show ID
python3 -m scripts.opportunity_intel.cli explain ID
python3 -m scripts.opportunity_intel.cli coverage
python3 -m scripts.opportunity_intel.cli source-health
python3 -m scripts.opportunity_intel.cli update --source pncp
python3 -m scripts.opportunity_intel.cli export --format csv -o opportunities.csv
python3 -m scripts.opportunity_intel.manifest
```

---

## 11. Universe / utilities

```bash
# Canonical universe load authority
# scripts.lib.universe.load_canonical_universe
# fixtures/canonical_universe_r0.xlsx  OR private Extra - alvos…xlsx
# CANONICAL_UNIVERSE historical constant = 1093 (derive from loader, do not hardcode in new code)

python3 -m scripts.universe_tools   # snapshot helpers if needed
```

---

## 12. Tests (contracts / coverage / deliverables)

```bash
python3 -m pytest tests/ -q --tb=no -x
# focused (examples present in tree):
# tests/test_contract_intel_truth_v1.py
# tests/test_contract_date_semantics.py
# dual_capability / freshness tests under tests/
```

---

## 13. DOD / campaign controllers (not product, process)

```bash
python3 tools/dod_controller.py scan|status|next|…
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

---

## 14. Systemd (VPS — deploy artifacts)

Deploy unit names under `deploy/systemd/` include crawl timers (e.g. `extra-crawl-pncp.*`). Contracts-specific unit names should be confirmed in that directory before claiming production schedule.

---

## 15. Explicit non-commands for this campaign

| Action | Reason |
|--------|--------|
| HC 3y backfill against 5433 | Owned by parallel HC campaign |
| Writing `data/contracts_checkpoints/hc_closure_*` | Protected path |
| Claiming 95% coverage without dual report + acceptance | DOD / ADR-030 |
| National product backfill on NI DSN without architecture decision | Campaign scope gate |
