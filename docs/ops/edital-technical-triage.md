# Edital technical triage

Source-grounded evidence model for document presence/absence and format variation.

**Criterion of done (consulting, not collection):** download alone is collection; consulting starts when content becomes a **decision** with locators (page/item/cell), checklist, inconsistencies, and human-gated recommendation.

```bash
python3 -m scripts.edital_case --help
python3 -m scripts.edital_case run --case-id DEMO --source /path/to/pack --output /tmp/edital-cases
python3 -m scripts.edital_case verify --case /tmp/edital-cases/demo
```

## What it extracts / checks

- Dates, deadlines, clarification/impugnation windows  
- Participation, consortium, subcontracting  
- Legal / fiscal / labor eligibility and technical qualification signals  
- Guarantees, site visit, declarations, proposal format  
- Sanctions / contractual risk flags (often `NEEDS_HUMAN`)  
- Missing annexes mentioned in text  
- Cross-document inconsistencies (when comparable)  

## Decision output

- Checklist ≥ 20 points (`CHECKLIST_ITEMS` currently 36)  
- Findings with `locator` + excerpt citation integrity (`verify`)  
- Recommendation `GO` | `REVIEW` | `NO_GO` — fail-closed; incomplete Extra profile blocks GO  
- Reports: MD / HTML / XLSX / PDF under `case/reports/`  

## Spreadsheet annexes in the case pack

Planilhas (`.xlsx`/`.xlsm`) are stored as content-addressed objects (bare SHA, no suffix). Extraction loads bytes into openpyxl via `BytesIO` so sheet/cell locators work on the shipped path — not only when the file happens to keep a `.xlsx` filename on disk.

## Non-claims

- Does **not** issue legal opinions or professional seals  
- `NO_GO` / `REVIEW` must remain evidence-backed  
- Distinguishes missing attachment vs download failure  
- PDF text extraction is not OCR-complete until OCR path is used  
- Full engineering BDI arithmetic audit remains `scripts.budget_audit` (planilha cells are available in the edital case; deep arithmetic is the budget pipeline)  


## Evidence pack

Campaign: `artifacts/campaigns/DOC-DEEP-ANALYSIS-DECISION-INTEL-01/`  
ADR: `docs/architecture/adr/ADR-031-edital-case-evidence-model.md`
