# Coverage Contract — Formal Metrics

**Status:** Active  
**Module:** `scripts/coverage/coverage_contract.py`  
**CLI:** `python -m scripts.coverage.coverage_contract_cli report`  
**SLA config:** `config/coverage_slas.yaml`  
**Denominator:** fixed canonical universe (1093 when seed matches)

---

## Principle

**Commercial signal is not coverage.**

The platform tracks several related but distinct metrics. Conflating “entities
with a recent commercial opportunity” with “monitoring coverage” produces
misleading dashboards and false confidence. This contract forbids that
conflation.

| Allowed | Forbidden |
|---------|-----------|
| Call commercial signal a *commercial signal* | Call commercial signal “coverage” |
| Keep denominator fixed at universe size | Shrink denominator to inflate % |
| Mark missing registry as `NOT_READY` | Invent `0%` as if measured |
| Compute recall from stratified sample | Derive recall from DB opportunity counts |

---

## The 5+1 Metrics

### 1. `entities_with_recent_commercial_signal` *(commercial signal — NOT coverage)*

| | |
|--|--|
| **Kind** | `commercial_signal` |
| **Formula** | entities with ≥1 OPEN / UPCOMING / RECENT matched opportunity ÷ 1093 |
| **Target** | none (signal, not SLA) |
| **Legacy alias** | `commercial_opportunity_any` (backward compat only) |
| **Headline?** | Yes — session pipeline headline uses this name |

Renamed from `commercial_opportunity_any`. The alias remains in payloads for
backward compatibility but must never be labeled coverage.

### 2. `source_mapping_coverage` *(coverage)*

| | |
|--|--|
| **Kind** | `coverage` |
| **Formula** | entities with an explicit source-registry record ÷ denominator |
| **Target** | **100%** |
| **Source** | `data/entity_source_registry.jsonl` |

A registry row with `status=source_not_identified` **still counts** as mapped
(the mapping decision was made). If the registry file is missing, the metric is
`NOT_READY` with an explicit reason — never reported as 0% covered.

### 3. `operational_source_coverage` *(coverage)*

| | |
|--|--|
| **Kind** | `coverage` |
| **Formula** | entities with ≥1 official source that is mapped + accessible + collected + normalized + reconciled + verified within SLA + recent evidence ÷ denominator |
| **Target** | **95%** |
| **Source** | `coverage_evidence` / `entity_coverage` (DB); session artifacts with honest limitations if DB down |

### 4. `freshness_coverage` *(coverage)*

| | |
|--|--|
| **Kind** | `coverage` |
| **Formula** | entities verified within the applicable SLA window ÷ denominator |
| **Target** | derived from SLA config |
| **Source** | `entity_coverage.last_seen_at` / `coverage_evidence.observed_at` |

### 5. `opportunity_recall` *(recall)*

| | |
|--|--|
| **Kind** | `recall` |
| **Formula** | true positives in stratified benchmark sample ÷ sample positives |
| **Target** | set by benchmark design |
| **Source** | `data/benchmarks/opportunity_recall_sample.json` (or path override) |

**Never** computed from database opportunity counts. Without a stratified
sample the metric is `NOT_READY`.

### +1. `required_field_completeness` *(completeness)*

| | |
|--|--|
| **Kind** | `completeness` |
| **Formula** | mean over records of (present decision fields ÷ 17 fields) |
| **Decision fields** | entity, cnpj, process, edital, objeto, modalidade, situacao, datas, valor, local, url, docs, fonte, collected_at, commercial_class, sector_class, ranking_evidence |
| **Absence** | explicit — missing key / null / empty ≠ invented value |

---

## SLA Windows (`config/coverage_slas.yaml`)

```yaml
open_opportunities_hours: 24
official_diaries_hours: 24
contracts_amendments_hours: 72
historical_consolidated_days: 7
cadastral_data_days: 30
```

Entity-level freshness and operational gates use these windows. Do not hardcode
SLA durations in callers.

---

## Denominator Policy

Resolution order:

1. `scripts.lib.universe.load_canonical_universe` (seed spreadsheet)
2. DB: `sc_public_entities WHERE is_active AND raio_200km`
3. CSV: `config/target_entities_200km.csv`
4. Constant `FIXED_CANONICAL_DENOMINATOR = 1093` (last resort, stamped)

When the resolved count equals 1093, the report stamps `fixed_canonical: true`.
**Never change the denominator to improve a percentage.**

---

## CLI

```bash
# JSON report
python -m scripts.coverage.coverage_contract_cli report \
  --output output/coverage/contract-report.json

# Human table
python -m scripts.coverage.coverage_contract_cli report --format table

# Offline (session artifacts / CSV only)
python -m scripts.coverage.coverage_contract_cli report --offline --format table
```

Every metric is printed with `numerator / denominator / pct`. Commercial signal
rows are tagged `SIGNAL`, never `coverage`.

---

## Session Pipeline Integration

`scripts/coverage/session_coverage_pipeline.py` writes:

- `methodology.headline_metric = entities_with_recent_commercial_signal`
- `methodology.headline_metric_legacy_alias = commercial_opportunity_any`
- `methodology.headline_is_coverage = false`

Both the new metric id and the legacy alias appear in the metrics array with the
same numerator for backward compatibility.

---

## Report Schema (minimal)

```json
{
  "headline_metric": "entities_with_recent_commercial_signal",
  "headline_is_coverage": false,
  "denominator": {"value": 1093, "source": "...", "fixed_canonical": true},
  "slas": {"open_opportunities_hours": 24, "...": "..."},
  "metrics": {
    "entities_with_recent_commercial_signal": {
      "kind": "commercial_signal",
      "is_coverage_metric": false,
      "status": "READY",
      "numerator": 116,
      "denominator": 1093,
      "pct": 10.61
    },
    "source_mapping_coverage": {"kind": "coverage", "status": "NOT_READY", "...": "..."},
    "operational_source_coverage": {"kind": "coverage", "...": "..."},
    "freshness_coverage": {"kind": "coverage", "...": "..."},
    "opportunity_recall": {"kind": "recall", "...": "..."},
    "required_field_completeness": {"kind": "completeness", "...": "..."},
    "commercial_opportunity_any": {
      "alias_of": "entities_with_recent_commercial_signal",
      "is_coverage_metric": false
    }
  },
  "legacy_aliases": {
    "commercial_opportunity_any": "entities_with_recent_commercial_signal"
  }
}
```

---

## Tests

```bash
pytest tests/unit/coverage/test_coverage_contract.py -v
```

Covers metric names, commercial≠coverage, fixed denominator, SLA load,
explicit field absence, and full report schema.
