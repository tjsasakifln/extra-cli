# DoD map — primary items → evidence

Story: `ROI-cand-dyn-slice-cb906bb58392`  
Session: `docs/ops/session-2026-07-20-rastreabilidade-ledger/`  
Tests: 19 passed (`pytest.log`)

| dod_item_id | Text | Status for QA | Evidence |
|-------------|------|---------------|----------|
| `dod:610fa35b3acc` | Cada execução possui erros. | **PROPOSED flip** | `sample-ledger.jsonl` (errors always list); tests `test_record_always_has_errors_list`, `test_errors_key_present_when_none_passed`, `test_ok_run_has_empty_errors`; `verify-invariants.json` missing_errors_field=[] |
| `dod:2f9641cb6f62` | Cada relatório referencia runs de origem. | **PROPOSED flip** | `sample-ledger.jsonl` report_run_links; tests `test_report_paths_always_link_run_id`, `test_cli_record_and_verify`; decision_pack + weekly_cycle wire |
| `dod:e852338b9064` | Mudanças manuais são auditáveis. | **PROPOSED flip** | `sample-mutations.jsonl`; `test_manual_mutation_auditable`; CLI `mutation` |
| `dod:54eb08c0fd66` | Overrides manuais possuem motivo. | **PROPOSED flip** | `sample-overrides.jsonl`; `test_new_override_requires_motivo`; `test_record_manual_override_missing_motivo_fails` |
| `dod:0a8c05b28dae` | Overrides manuais possuem data. | **PROPOSED flip** | `sample-overrides.jsonl` field `data`; `test_new_override_requires_data` |
| `dod:3545156c47d7` | Overrides manuais possuem autor. | **PROPOSED flip** | `sample-overrides.jsonl`; `demo-override-reject.json`; `test_new_override_requires_autor`; `test_cli_override_missing_autor_rejected` |
| `dod:e12bd0136330` | A evidência de coverage pode ser reconstruída. | **OPEN** | not in scope / not proven |
| `dod:40ffb2a2ae53` | A evidência de freshness pode ser reconstruída. | **OPEN** | not in scope / not proven |
