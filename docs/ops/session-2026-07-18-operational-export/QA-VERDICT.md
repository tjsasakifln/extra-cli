# QA Verdict — ROI-cand-dyn-slice-d58f00f868f0

**Story:** ROI-cand-dyn-slice-d58f00f868f0  
**Section:** 12.2 Saídas operacionais (export + source health + metadata)  
**Reviewer:** Quinn (@qa) — independent (not implementer)  
**Date:** 2026-07-18  
**Risk level:** HIGH-RISK  
**Reviewed HEAD (at review):** `381f9e1`  
**Module:** `scripts/reports/operational_export_pack.py`

---

## Decision

# **PASS**

All 8 DoD items under this slice are proven with executable evidence.  
No false-green seals (`LOCAL_READY` / `PROJECT_DONE` / coverage 95% / etc.) are asserted as true.

---

## DoD items

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Relatório de source health | **DONE** | `pack/csv/source_health.csv` (1 row, pncp); Excel sheet `source_health`; PDF section “Source health” |
| 2 | Exportação CSV | **DONE** | `pack/csv/source_health.csv` + `editais_sample.csv` + sidecar `metadata.json` |
| 3 | Exportação Excel | **DONE** | `export-*.xlsx` bytes=7908 > 0; sheets `metadata`, `source_health`, `editais_sample` |
| 4 | Relatório PDF | **DONE** | `export-*.pdf` bytes=2247 > 0; text extractable with full metadata block |
| 5 | Todos os relatórios incluem data de geração | **DONE** | `generated_at` in manifest, CSV sidecar, Excel metadata sheet, PDF body |
| 6 | Todos os relatórios incluem versão do universo | **DONE** | `universe_version=sc_public_entities:n=0` in all four surfaces |
| 7 | Todos os relatórios incluem fonte | **DONE** | `source=postgresql+ingestion_runs` in all four surfaces |
| 8 | Todos os relatórios incluem status de confiabilidade | **DONE** | `reliability=DEGRADED` (pack-level + per-source in health) |

**Summary:** 8/8 **DONE**, 0 PARTIAL, 0 FAIL

---

## Commands re-executed by QA

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m pytest tests/test_operational_export_pack.py -q --no-cov -o addopts=
# → 4 passed

python3 -m scripts.reports.operational_export_pack \
  --dsn "$LOCAL_DATALAKE_DSN" --out /tmp/ops-export-qa --json
# → EXIT 0; excel bytes=7908; pdf bytes=2247; source_health rows=1
```

---

## Verification matrix

| Check | Result |
|-------|--------|
| Unit tests | PASS (4/4) |
| Live export against local PG (5433/extra_test) | PASS (exit 0) |
| xlsx bytes > 0 | PASS (7908) |
| pdf bytes > 0 | PASS (2247) |
| PDF text contains generated_at / universe_version / source / reliability | PASS (PyPDF2 extract) |
| Excel metadata sheet has 4 required fields | PASS |
| CSV sidecar metadata.json has 4 required fields | PASS |
| source_health.csv present with reliability column | PASS (pncp, 50% success → DEGRADED) |
| No LOCAL_READY claim as true | PASS — only in `claims_forbidden` / “NÃO afirmar: LOCAL_READY” |
| forbidden_phrase_hits_in_manifest | `[]` |
| Reliability honesty | DEGRADED (not TRUSTED seal); universe n=0 disclosed |

### LOCAL_READY audit

| Location | Occurrence | Verdict |
|----------|------------|---------|
| `claims_forbidden` / `claims.forbidden` | listed as forbidden | OK |
| PDF “NÃO afirmar: LOCAL_READY” | explicit non-claim | OK |
| `claims.allowed` | does **not** include LOCAL_READY | OK |
| Any positive seal assertion | none found | OK |

---

## Code review notes (non-blocking)

| Severity | Note |
|----------|------|
| LOW | `pdf_text_check = path_read_safe(pdf_path)` is dead (result unused); PDF binary is not scanned — only manifest JSON. Acceptable for this slice. |
| LOW | Unit tests cover helpers only (`common_metadata`, `write_excel`, `write_pdf`, forbidden list). Full `build_pack` path is proven by live CLI evidence, not by automated integration test. |
| INFO | Pack reliability correctly DEGRADED when source health < 80% (pncp 50%). No false TRUSTED. |

None of the above blocks the gate.

---

## Claims authorized by this PASS

- Source health report generated from `ingestion_runs`
- CSV + Excel + PDF exports with shared metadata fields
- Unsupported seal claims listed as forbidden

## Claims still forbidden (unchanged)

- `LOCAL_READY`
- cobertura operacional de 95%
- recall de 95%
- `PRE_VPS_FINAL_READY`
- `PROJECT_DONE`
- garantia de vitória
- `LOCAL_RESILIENCE_READY` (superseded → NOT_READY)

---

## Artifacts reviewed

| Path | Role |
|------|------|
| `scripts/reports/operational_export_pack.py` | Implementation |
| `tests/test_operational_export_pack.py` | Unit tests |
| `docs/ops/session-2026-07-18-operational-export/pack/**` | Evidence pack |
| `docs/ops/session-2026-07-18-operational-export/run.json` | Run record |
| `docs/ops/session-2026-07-18-operational-export/MANIFEST.md` | Human index |
| `/tmp/ops-export-qa/**` | QA re-run pack (fresh) |

---

## Gate

| Field | Value |
|-------|-------|
| **verdict** | **PASS** |
| **DoD flip authorization** | YES — 8 items with evidence paths above |
| **Next** | @po close → @devops publish path (no auto-merge) |
| **QA loop** | not required |

---

*Independent QA — Quinn. No application source modified during this review.*
