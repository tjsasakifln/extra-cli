# Data quality contract comparison — ARCH-RESET PR F

## Options evaluated

| Option | Fits 10 critical checks? | Local fail-closed | Dual truth risk | New dep | Cognitive cost |
|--------|--------------------------|-------------------|-----------------|---------|----------------|
| **Python/SQL native (existing + this contract)** | Yes | Yes | Low | None | Low — already in repo |
| dbt tests | Yes if models exist | Yes offline | **High** if second transform line | dbt-core + adapters | High |
| Soda Core OSS | Yes | Yes | Medium (second DSL) | soda-core | Medium-high |

## Ten critical checks

1. freshness_editais  
2. freshness_contratos  
3. identifier_completeness  
4. official_url_present  
5. closing_date_present  
6. duplicate_detection  
7. unknown_status_not_open  
8. coverage_by_capability (computable; **not** auto-claim 95%)  
9. volume_drop_alert  
10. run_reference_integrity  

## Decision

**`ADOPT_PYTHON_SQL_NATIVE`** as the **single canonical quality contract**.

- Encode check IDs in `scripts/quality/canonical_checks.py`.  
- Reuse existing `freshness_gate`, `coverage_contract`, `source_contract_tests` as engines behind the contract over time (Branch by Abstraction).  
- **Do not** adopt Soda and dbt simultaneously.  
- dbt tests: `REFERENCE_ONLY` until a dbt snapshot spike (PR E) is accepted.  
- Soda Core: **`REJECTED_SPIKE` for production now** — adds DSL without reducing existing Python surface; revisit only if check authoring cost dominates.

## Cost argument

- Repo already has ~1800 LOC coverage_contract + freshness_gate + source_contract_tests.  
- Adding Soda/dbt without removing Python paths = **two contracts**.  
- Canonical IDs first enable later engine swap without dual forever.

## Evidence

- Fixture suite: `python3 -c "from scripts.quality.canonical_checks import run_all_fixture_suite; ..."`  
- Tests: `tests/test_canonical_quality_checks.py`
