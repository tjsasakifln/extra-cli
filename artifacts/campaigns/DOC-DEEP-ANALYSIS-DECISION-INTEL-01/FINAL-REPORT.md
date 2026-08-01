# DOC-DEEP-ANALYSIS-DECISION-INTEL-01 — Final report

## Thesis

**Baixar PDF é coleta. Consultoria começa quando o conteúdo vira decisão.**

This campaign proves that the shipped modules `scripts/edital_case` and `scripts/budget_audit` turn multi-document packs into decision-support deliverables with locators (page / item / cell), fail-closed recommendations, and independent `verify PASS`.

## What was proven (fixture / deterministic)

| Pipeline | Verify | Decision output | Locators |
|----------|--------|-----------------|----------|
| `edital_case` multi-doc pack (5 files) | **PASS** (62 citations, 0 fabricated) | **REVIEW** + disclaimer + 36-point checklist + 48 findings + 1 inconsistency | `page:N` on checklist/findings |
| `budget_audit` golden workbook | **PASS** + report reconciliation **PASS** | 12 items, 8 BDI components, 31 findings, arithmetic 22 checks | sheet!cell on findings |

### Suite

- `tests/edital_case/` — **31 passed** (includes regression `test_profile_fit_binds_excerpt_to_source_document`)
- `tests/budget_audit/` + prior combined run — **51 passed** (full edital+budget before fix; budget unchanged)

### Code fix (citation integrity)

- **Bug:** `aderencia_perfil` bound the “objeto” excerpt to `docs[0]` even when the hit lived in a later document (e.g. aviso vs edital) → `verify` reported fabricated citations.
- **Fix:** bind evidence to the document that owns the hit; snap excerpt windows to token boundaries.
- **Files:** `scripts/edital_case/analyze.py`, `scripts/edital_case/extract.py`, `tests/edital_case/test_analysis.py`

## DoD §2.6 mapping (fixture-proven capability)

State for claimed items: **TESTED_WITH_FIXTURES** → eligible for `[x]` after main+CI with evidence pack below.

**Not claimed:** 95% coverage, live ente crawl, legal/parecer, BDI “abusivo/legal”, GO automatic without profile elicitation.

### Triagem de edital

All checklist categories (36 items ≥ 15–20) exercised via `CHECKLIST_ITEMS` + fixture run: objeto/perfil, datas, modalidade/julgamento/disputa, participação/consórcio/subcontratação, habilitação jurídica/fiscal/trabalhista, qualificação EF/técnica, garantias, visita, proposta, orçamento/regime/reajuste, sanções/riscos, inconsistências, pendências, disclaimer não-jurídico.

Evidence: `evidence/edital_checklist.json`, `evidence/edital_recommendation.json`, `evidence/edital-executive-summary.md`, `evidence/edital_verification.json`.

### Análise técnica aprofundada + planilha/BDI

- Case multi-doc with hash/origin inventory  
- Missing annex detection  
- Cross-document inconsistency (dates/fields)  
- Page/cell provenance  
- Normalize items/units/prices; compositions; BDI components distinguished; arithmetic materiality  
- Reference compare path (SINAPI-style manifest) without inventing official tables  

Evidence: `evidence/edital_*`, `evidence/budget_*`, `acceptance-manifest.json`.

### §2.2 product bullets

- Triagem inicial de edital  
- Análise técnica aprofundada de edital quando solicitada  
- Análise de planilha orçamentária, composições e BDI quando documentos disponíveis  

## How to reproduce

```bash
# Unit/E2E tests (shipped path)
python3 -m pytest tests/edital_case/ tests/budget_audit/ -q --tb=no

# Budget golden (same path as tests/budget_audit/test_pipeline_e2e.py)
python3 -c "from tests.budget_audit.build_fixtures import build_golden; ..."  # or pytest tests/budget_audit/test_pipeline_e2e.py -q

# Edital multi-doc: use fixtures under tests/edital_case/fixtures/
# create→ingest→analyze→report→verify via scripts.edital_case pipeline APIs
```

## Honesty

- Fixture packs, not live PNCP/VPS case.  
- `sample_planilha.xlsx` inside edital_case yields text extraction limits (`EXTRACTION_FAILED` for PDF-style text path); full sheet/cell intelligence is in `budget_audit`.  
- Recommendation remains human-gated; profile incompleteness forces **REVIEW**, never silent GO.

## Artifacts

See `acceptance-manifest.json` for SHA-256 of every evidence file in this pack.
