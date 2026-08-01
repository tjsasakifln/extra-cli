# Engineering budget, compositions and BDI audit

**Criterion of done:** spreadsheets become decision intel when items, units, quantities, prices, charges and BDI are normalized, arithmetic is checked, and findings cite **cells**.

```bash
python3 -m scripts.budget_audit --help
python3 -m scripts.budget_audit run --case-id DEMO --source planilha.xlsx --output /tmp/budget-cases
python3 -m scripts.budget_audit verify --case /tmp/budget-cases/demo
```

Prefer fixture builders (`tests/budget_audit/build_fixtures.py`) over committed bulk workbooks.

## Pipeline

`create → ingest → map → audit → compare? → references? → report → verify`

| Stage | Output |
|-------|--------|
| map | normalized budget items, compositions, BDI components, social charges |
| audit | arithmetic, compositions, BDI structure, materiality |
| compare | item match between workbooks (code/unit/description) |
| references | SINAPI/SICRO-style manifest (month, locality, tax regime) |
| report | MD / HTML / PDF / XLSX with reconciliation checksums |

## Non-claims (ADR-030)

- Arithmetic / structure only — **never** legal / illegal / abusive BDI without human normative review  
- BDI ≠ margin; system does not invent internal costs or win probability  
- Missing formula cache is never treated as zero  

## Evidence pack

Campaign: `artifacts/campaigns/DOC-DEEP-ANALYSIS-DECISION-INTEL-01/`  
ADR: `docs/architecture/adr/ADR-032-budget-audit-evidence-model.md`
