# UNIVERSE-RECONCILIATION

## Numbers under investigation (host-of-record, 2026-08-10)

| Label | Value | Source |
|------|------:|--------|
| National supplier roots (`pncp_supplier_contracts.fornecedor_cnpj_8`, len=8, ≠00000000) | 513650 | Live SQL |
| Target-fit SHADOW rows (distinct `cnpj_raiz`) | 512350 | `confenge_target_fit_shadow` |
| TARGET_CONFIRMED | 8348 | shadow_class |
| TARGET_PROBABLE_RESEARCH (pre-reclass) | 411610 | shadow_class |
| TARGET_OUT_OF_SCOPE | 92392 | shadow_class |
| Historical "48,748 construction-eligible" | 48748 | 2026-08-07 construction filter / eligibility helper (narrower ICP) |
| Artifact "511,645 supplier roots" | 511645 | Full reconcile snapshot earlier same day (supplier table grew) |
| CONFIRMED+PROBABLE "419,362" | ~419958 | 8348+411610 pre-reclass; **not** equal to construction-only 48k |

## What each population means

### 1. ~48,748 (historical construction-eligible)

- **Not** all PNCP suppliers.
- Construction/engineering **eligibility** filter from `confenge_universe` / construction assessor.
- Used in early commercial readiness goals as the ICP-relevant denominator.
- Unit: CNPJ root with positive construction signals (contracts/CNAE/sector).

### 2. ~511,645 → ~513,650 supplier roots

- **All** distinct supplier CNPJ roots observed in `pncp_supplier_contracts`.
- Includes materials-only, commerce, fleet, medical, consortia members as suppliers, etc.
- Unit: CNPJ root (8 digits), matrix/branch collapsed.
- Temporal: cumulative PNCP contracts in the datalake as of crawl watermark.

### 3. ~419k CONFIRMED+PROBABLE (pre-v2)

- Materialized target-fit classes under **confenge-target-fit-v1**.
- **Bug:** ~361,675 PROBABLE rows carried only `default_research` with **empty evidence**.
- Absence of evidence was incorrectly treated as PROBABLE.
- **Fix (v2):** `TARGET_INSUFFICIENT_EVIDENCE` + reclassify path; PROBABLE requires positive ICP evidence (CNAE eng, execution object, activity, sector+corroboration).

### 4. TARGET_CONFIRMED = 8,348

- Triangulated construction/engineering execution evidence (contracts + sector/CNAE paths).
- All CONFIRMED rows have non-empty evidence payloads (live check).
- This is the population for contact enrichment (not PROBABLE, not all suppliers).

## Consortia

- Consortium contracts add `CONSORTIUM_EVIDENCE` notes and **do not** alone confirm member ICP.
- Members with only consortium notes and empty evidence reclassify to INSUFFICIENT.

## Coverage invariants

```
0 <= coverage_ratio <= 1
materialized_valid_roots <= canonical_roots
orphan_materialized_roots = 0  (live check: 0)
duplicate_cnpj_root = 0
```

Prior artifact `materialized=511646 / canonical=511645` (ratio>1) was an overcount/orphan race;
accounting now clamps ratio and fails FULLY_RECONCILED when orphans/dups exist.

## Construction subsegments (classifier signals)

Positive execution markers include: obra, empreitada, pavimentação, terraplenagem,
saneamento, infraestrutura, fundações (obra), edificação, serviços/projetos de engenharia.
Supply-only (materiais, frota, medicamentos) → OUT_OF_SCOPE.

## False positives addressed

- `default_research` PROBABLE inflation
- sector POSSIBLE without evidence
- consortium-only PROBABLE
