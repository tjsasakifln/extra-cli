# QA Verdict — DoD §12.2 analytical reports (8)

**Story:** `ROI-cand-dyn-slice-19ce6ecf8869`  
**Candidate:** `cand-dyn-slice:19ce6ecf8869`  
**Reviewer:** Quinn (@qa) / independent adversarial auditor (NOT implementer)  
**Date:** 2026-07-18  
**Reviewed commit:** `c704840d04ee57c585c36a98c9c6c38218d256af` (`c704840`)  
**Overall:** **CONCERNS**

---

## Mission scope (DoD §12.2 report items only)

| # | Item | Verdict | Evidence |
|---|------|---------|----------|
| 1 | Relatório de contratos por ente | **DONE** | CSV + manifest; honest empty (`n_contratos=0`, `note=schema_fallback`); no completeness claim |
| 2 | Relatório de contratos por fornecedor | **DONE** | CSV + manifest; honest empty (`n=0`); no completeness claim |
| 3 | Relatório de concorrentes | **DONE** | 6 rows; `provenance=fallback_orgao_not_supplier`; limitation in manifest |
| 4 | Relatório de concentração | **DONE** | HHI computed with explicit caveat **NOT market HHI**; `reliability=DEGRADED` |
| 5 | Relatório de referências de valores | **DONE** | 4 modalidades; `valor_semantica=valor_total_estimado`; disclaimer NOT homologado |
| 6 | Relatório de completude | **DONE** | per-field %; mix OK/BELOW_95; not sold as operational 95% |
| 7 | Relatório de coverage | **DONE** | every row claims NOT operational coverage; `operational_coverage_strict=0.0` |
| 8 | Relatório de recall | **DONE** | `status=NOT_READY`, `gold_sample_size=0`, `recall_pct` empty; forbidden claim lists recall 95% |

**Score:** 8/8 DONE (report-generator capability) · 0 FAIL · residual concerns below.

---

## Commands re-executed (independent)

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m pytest tests/test_operational_reports.py -q --no-cov -o addopts=
# → 2 passed

python3 -m scripts.reports.operational_reports --dsn "$LOCAL_DATALAKE_DSN" --out /tmp/ops-reports-qa --json
# → exit 0, reliability=DEGRADED, 8 CSVs + manifest.json
```

Session pack under review: `docs/ops/session-2026-07-18-operational-reports/`  
(`run.json`, `pytest.log` exit 0, `reports/*.csv`, `reports/manifest.json`).

---

## Falsification attempts

| Attack | Result |
|--------|--------|
| Invented operational 95% | **Blocked.** `operational_coverage_strict` pct=0.0; claim column says NOT operational / campaign_truth ~0%. Manifest forbids `operational coverage 95%`. |
| Fake HHI as market truth | **Blocked.** Manifest limitation: `Concentration based on orgao editais fallback — NOT market HHI`. Metric is `n_editais` from orgao fallback, not supplier market share. |
| Recall green without gold | **Blocked.** `status=NOT_READY`, gold_sample_size=0, recall_pct empty. Manifest forbids `recall 95%`. |
| Empty contracts as full coverage | **Blocked.** Contract CSVs show 0; coverage `contracts_rows` numerator=0; no FULL/COMPLETE claim on empty tables. |

---

## Residual concerns (do not block report-generator DONE; block over-claims)

### C1 — HIGH residual: contract SQL vs real schema mismatch

`pncp_supplier_contracts` columns (live extra_test):

- `orgao_cnpj`, `orgao_nome`, `fornecedor_cnpj`, `fornecedor_nome`, `valor_total`, …

Code primary queries reference **non-existent** columns:

- `orgao_razao_social`, `ni_fornecedor`, `cnpj_fornecedor`, `nome_fornecedor`, `valor_global`, `valor_homologado`, `valor_contratado`

Observed: primary SELECT fails → `schema_fallback` COUNT path.

| Implication | Detail |
|-------------|--------|
| Empty table today | Fallback COUNT=0 looks honest (acceptable for generator DONE). |
| When contracts land | Grouping-by-ente/fornecedor will **not** work until SQL aligns with schema — still emit schema_fallback aggregate, not the intended report. |

**Recommendation (@dev follow-up, not this flip blocker for empty-state generator):** rewrite contract queries to real column names; add integration test that inserts 1 contract row and asserts grouping.

### C2 — MEDIUM: counts semantics

`counts.contratos_por_ente=1` / `contratos_por_fornecedor=1` count the zero-row fallback line, not contracts. CSV content is clear (`0`); operators reading only `counts` may misread.

### C3 — MEDIUM: HHI `defensability=MEDIUM` on orgao proxy

With ≥3 orgaos, code sets `defensability=MEDIUM` even when mass is `n_editais` from **buyers**, not suppliers. Manifest caveat saves honesty; defensability label is slightly optimistic → prefer `LOW` whenever `fallback_orgao_not_supplier` / orgao-editais mass is used.

### C4 — LOW: test depth

- `test_write_reports_creates_eight_files` — fixture only (good for writer).
- `test_recall_not_ready_without_gold` — **tautology** (asserts a hand-built dict, does not call `report_recall` against DB/fake conn).

No live-PG integration test in suite. Re-run by QA against extra_test compensates for this review.

### C5 — reliability correctly DEGRADED

Manifest `reliability=DEGRADED` with limitations list — correct; must not be flipped to TRUSTED while gold/contracts/HHI caveats remain.

---

## Per-item detail

### 1. Contratos por ente — DONE

- Artifact: `relatorio_contratos_por_ente.csv`
- Content: `n_contratos=0, note=schema_fallback`
- Table exists, n=0 contracts
- Does not claim full coverage
- Residual: C1 schema mismatch

### 2. Contratos por fornecedor — DONE

- Artifact: `relatorio_contratos_por_fornecedor.csv`
- Content: `n=0`
- Honest empty; residual C1

### 3. Concorrentes — DONE

- 6 rows, all `fallback_orgao_not_supplier` (órgãos ≠ fornecedores)
- Limitation recorded — not presented as true supplier competitors

### 4. Concentração — DONE

- HHI_0_10000 ≈ 1836.73 on `n_editais` orgao mass
- Explicit **NOT market HHI** limitation
- Residual: C3 defensability MEDIUM

### 5. Referências de valores — DONE

- Semantics labeled `valor_total_estimado`
- Disclaimer `NOT homologado/contratado/pago`

### 6. Completude — DONE

- Field-level fill rates on `pncp_raw_bids` (n_active=8)
- Status OK only for fields actually ≥95% fill; overall BELOW_95
- Not conflated with operational coverage 95%

### 7. Coverage — DONE

- Presence/signal metrics + strict operational row at 0%
- Forbidden 95% operational claim honored

### 8. Recall — DONE (capability = report NOT_READY)

- Explicit `NOT_READY` without gold sample
- **DoD item “recall report exists” may flip; DoD item “recall ≥95%” must stay open** (L1093 / L1723)

---

## Flip authorization (exact)

### Authorized to flip (report generator only)

| Line (approx) | DoD text |
|---------------|----------|
| L937 | Relatório de contratos por ente. |
| L938 | Relatório de contratos por fornecedor. |
| L939 | Relatório de concorrentes. |
| L940 | Relatório de concentração. |
| L941 | Relatório de referências de valores. |
| L942 | Relatório de completude. |
| L943 | Relatório de coverage. |
| L944 | Relatório de recall. |

Flip text must cite: module `scripts/reports/operational_reports.py`, session `docs/ops/session-2026-07-18-operational-reports/`, reliability DEGRADED, this QA CONCERNS, commit `c704840`.

### Must stay open

- L945+ source health, CSV/Excel/PDF exports, metadata fields (data/versão universo/fonte/confiabilidade universais) — **out of this slice**
- Any claim of operational coverage 95%, recall 95%, LOCAL_READY, PRE_VPS, PROJECT_DONE
- Market-true HHI / true supplier competitor ranking without contract mass
- Recall ≥95% gold-sample items (L1093, L1723)

---

## Decision

| Field | Value |
|-------|-------|
| **Overall** | **CONCERNS** |
| **Story status** | InReview → **Done** (CONCERNS allows close; residual follow-ups) |
| **DoD 8 report generators** | Flip authorized with DEGRADED + limitations |
| **False-green risk** | Controlled if flip text does not invent 95%/market HHI/recall green |
| **Rework required before flip?** | No for empty-state generator DONE; **yes** before trusting contract reports with non-empty `pncp_supplier_contracts` (C1) |

**Next:** @po close story + flip L937–L944 only with honest evidence language; register C1 as follow-up; @devops publish path after PO.

---

## Self-QA check

| Check | Result |
|-------|--------|
| Independent of implementer | ✅ adversarial auditor, not delivery-engineer |
| Re-ran pytest + generator | ✅ |
| Inspected CSV bodies not only manifests | ✅ |
| Attempted falsification of 95%/HHI/recall/empty-as-full | ✅ all blocked |
| Did not modify application source | ✅ |
| Did not flip DoD.md | ✅ PO authority |
| Did not git commit/push | ✅ |
