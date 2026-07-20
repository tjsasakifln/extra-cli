# Proposed DoD §29 flips — PENDING @qa authorization

**Do NOT apply until independent @qa verdict is PASS|CONCERNS|WAIVED.**

Story: `ROI-cand-dyn-slice-cb906bb58392`  
Session: `docs/ops/session-2026-07-20-rastreabilidade-ledger/`  
Tests: 19 passed

## Lines to change in `DOD.md` (~1515–1522)

Replace:

```markdown
- [ ] Cada execução possui erros.
```

with:

```markdown
- [x] Cada execução possui erros. Evidência: `scripts/ops/run_execution_ledger.py` (`errors[]` always) + `tests/test_run_execution_ledger.py` (19 ledger suite passed) + `docs/ops/session-2026-07-20-rastreabilidade-ledger/` (sample-ledger.jsonl, verify-invariants.json) + story ROI-cand-dyn-slice-cb906bb58392
```

Replace:

```markdown
- [ ] Cada relatório referencia runs de origem.
```

with:

```markdown
- [x] Cada relatório referencia runs de origem. Evidência: `report_run_links` in run_execution_ledger + decision_pack/weekly_cycle wire + session sample-ledger.jsonl + tests (report_paths always link run_id) + story ROI-cand-dyn-slice-cb906bb58392
```

Replace:

```markdown
- [ ] Mudanças manuais são auditáveis.
```

with:

```markdown
- [x] Mudanças manuais são auditáveis. Evidência: `record_manual_mutation` + CLI mutation + sample-mutations.jsonl + tests + story ROI-cand-dyn-slice-cb906bb58392
```

Replace:

```markdown
- [ ] Overrides manuais possuem motivo.
```

with:

```markdown
- [x] Overrides manuais possuem motivo. Evidência: `scripts/lib/manual_override_ledger.py` fail-closed + `record_manual_override` + sample-overrides.jsonl + tests + story ROI-cand-dyn-slice-cb906bb58392
```

Replace:

```markdown
- [ ] Overrides manuais possuem data.
```

with:

```markdown
- [x] Overrides manuais possuem data. Evidência: required field `data` (ISO) + tests test_new_override_requires_data + sample-overrides.jsonl + story ROI-cand-dyn-slice-cb906bb58392
```

Replace:

```markdown
- [ ] Overrides manuais possuem autor.
```

with:

```markdown
- [x] Overrides manuais possuem autor. Evidência: fail-closed blank autor + demo-override-reject.json + tests + sample-overrides.jsonl + story ROI-cand-dyn-slice-cb906bb58392
```

## Leave OPEN (do not flip)

```markdown
- [ ] A evidência de coverage pode ser reconstruída.
- [ ] A evidência de freshness pode ser reconstruída.
```

## Claims still forbidden after flip

- Full §29 complete
- LOCAL_READY / 95% / PRE_VPS_FINAL_READY / VPS ops
