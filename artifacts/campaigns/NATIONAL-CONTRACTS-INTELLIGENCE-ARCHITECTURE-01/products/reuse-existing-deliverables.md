# Reuse Existing Deliverables — Map vs Gaps

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Principle:** Prefer existing scripts/views/CLIs over new platforms.  
**No implementation in this artifact** — design only.

---

## 1. Inventory of reusable assets

### 1.1 DoD deliverable engines (`scripts/ops/`)

| Asset | Path | Product fit | What it already enforces |
|-------|------|-------------|---------------------------|
| **A — Org ranking** | `scripts/ops/deliverable_a_org_ranking.py` | **P4**, P9 | Semântica de valor, ticket formula, zero vs not_consulted, data_quality_limitation, claims_* |
| **B — Competitors** | `scripts/ops/deliverable_b_competitors.py` | **P1**, P2 partial, P9 | Top-N sem padding, deságio fail-closed, active fail-closed, capacity HYPOTHESIS |
| **C — Expiring** | `scripts/ops/deliverable_c_expiring.py` | **P4** playbook, P9 | Janela 90–180, exclude missing vigência, relicitação evidence-class not % |
| **D — Prices** | `scripts/ops/deliverable_d_prices.py` | **P3**, P9 | Dimensões de comparabilidade, INSUFFICIENT_SAMPLE, outliers flagged, ban “preço real” |
| **E — Open editais** | `scripts/ops/deliverable_e_editais.py` | **P9**, cross P2 | Openness proof, GO/REVIEW/NO_GO, disclaimer no victory |
| **Package final** | `scripts/ops/deliverable_package_final.py` | **P9** | PDF+Excel same run_id, reconcile, seções obrigatórias, gate Tiago |

### 1.2 Contract intelligence CLI & views

| Asset | Path / object | Product fit | Notes |
|-------|---------------|-------------|-------|
| CLI | `scripts/contract_intel/cli.py` | P1, P4, C | `historical_contracts`, `competitor_winners`, `expiring_contracts`, manifesto readiness |
| Target universe | `scripts/contract_intel/target_universe.py` | P4, P8 | 200 km Floripa, no silent include without coords |
| View | `v_supplier_winners` | P1, P7 | Rank by value; HHI intra-supplier; winners only |
| View | `v_contract_historical` | P4, P6 | 3y window × raio entities |
| View | `v_expiring_contracts` | P4 | 90–180d |
| View | `v_contracts_canonical` | P7 | Used by competitive_intel_validation |

### 1.3 Competitive intelligence (metrics)

| Asset | Path | Product fit | Notes |
|-------|------|-------------|-------|
| ADR-016 | `_reversa_sdd/adrs/016-competitive-intelligence-market-share.md` | P7 | Market share, award share, HHI; win rate NOT_READY |
| Validation | `scripts/opportunity_intel/competitive_intel_validation.py` | P7 | Read-only schema checks for share/HHI/ranking |
| Runtime metrics | `scripts/consulting_readiness.py` (competitive block) | P7, P9 | `_compute_market_share`, `_compute_award_share`, HHI, supplier ranking |

### 1.4 Buyer / opportunity layers

| Asset | Path | Product fit | Notes |
|-------|------|-------------|-------|
| Buyer intel | `scripts/buyer_intel/cli.py`, `ranking.py` | **P4**, P6 | Perfil órgão, regex AEC, HHI display |
| Opportunity ranking | `scripts/opportunity_intel/ranking.py` | E / P9 | GO/REVIEW/NO_GO rules |
| Opportunity CLI | `scripts/opportunity_intel/cli.py` | E, ops | list/show/explain/coverage/update |
| Radar / scoring | `radar.py`, `scoring.py`, `profile.py` | P2/E | Profile-driven; not full competitor map |

### 1.5 Schema / data

| Asset | Role |
|-------|------|
| `pncp_supplier_contracts` | Primary FACT store for contracts |
| `pncp_raw_bids` | Estimados / editais side |
| `sc_public_entities` | Raio 200 km, entity attributes |
| `db/current-schema.sql` / migrations 026, 030 | Views & contracts |

---

## 2. Product × reuse matrix

| Product | Reuse primary | Reuse secondary | New work needed? |
|---------|---------------|-----------------|------------------|
| **P1 Competitors map** | Deliverable B + `v_supplier_winners` | consulting_readiness ranking | Thin: national dual-filter params; object buckets optional |
| **P2 Entrants radar** | Aggregations on contracts (same as B inputs) | Opportunity radar (dates) | **Yes — query/report product** (no new platform): first_seen, recorrência |
| **P3 Benchmarks** | Deliverable D | bids for estimado/homologado pairs | Taxonomy versioning + unit/quantity when available; join bid↔contract for deságio |
| **P4 Agencies** | Deliverable A + buyer_intel | C + historical view | Wire A outputs to buyer_intel profiles consistently |
| **P5 Partner signals** | Coocorrência SQL on contracts | — | **Yes — labeled signal report only**; no partnership claims |
| **P6 Expansion** | Contracts by uf/objeto | buyer AEC regex | Coverage honesty layer (gaps) |
| **P7 Concentration** | ADR-016 + consulting_readiness + validation | v_supplier_winners HHI | Align HHI scale documentation in client text |
| **P8 SC vs National** | Filters on same engines A/B/HHI | target_universe vs uf/national | **Yes — dual-run orchestration** same deliverables twice |
| **P9 Executive report** | Package final + A–E | P7/P8 summaries | Narrative templates; no new BI platform |

---

## 3. What already exists (do not rebuild)

1. **Fail-closed competitor selection** (no pad to 15) — B.  
2. **Org ranking honesty** (zero vs not consulted) — A.  
3. **Price comparability framework** — D.  
4. **Expiring window + no fake relicitation %** — C.  
5. **Edital openness proof + GO labels** — E.  
6. **Package PDF/Excel reconciliation** — package final.  
7. **HHI / market share / award share** — consulting_readiness + ADR-016.  
8. **200 km universe rules** — target_universe + views 026.  
9. **Buyer AEC scoring** — buyer_intel.  
10. **Claims_allowed / claims_forbidden pattern** — all deliverables A–E + package.

---

## 4. Gaps (honest)

| Gap ID | Description | Blocks | Suggested approach (design) |
|--------|-------------|--------|-----------------------------|
| G1 | Win rate / losers | P1 “true competition” | Keep NOT_READY; optional future bid-result ingest |
| G2 | Consortium/subcontract fields | P5 as “partnerships” | Stay on cooccurrence signals; schema only if source provides |
| G3 | Unit quantities for true unit prices | P3 unit benchmarks | Only ticket/global panels until quantities exist |
| G4 | Entrants product not packaged | P2 | SQL + report schema reusing B identity rules |
| G5 | Dual SC/national orchestration | P8 | Two parameterized runs of A/B/HHI + side-by-side sheet |
| G6 | Object taxonomy single version | P1/P3/P4 consistency | One versioned dictionary shared by buyer_intel + D tipo_obra |
| G7 | Active status as_of sparse | P1 active portfolio | Keep B fail-closed; don’t invent status |
| G8 | Amendments incomplete on base table | C precision | C already models aditivos when supplied; don’t imply full PNCP amendment graph |
| G9 | Modalidade often missing on contracts-only | A-Q7 | Join bids/official_acts when present; else NOT_READY |
| G10 | National series completeness | P6/P8 | Label coverage; never imply full Brazil market |
| G11 | Filial/matriz collapse policy | P1/P7 | Document choice: CNPJ14 vs base8; apply consistently |
| G12 | HHI classification scale clarity | P7 client text | Document whether 0–10000 DOJ-like or other code paths |

---

## 5. Anti-patterns (reject)

| Anti-pattern | Why |
|--------------|-----|
| New “Competitive Intelligence Platform” UI before reusing B/A/D/HHI | Duplicates fail-closed logic |
| SQLite fixture as proof of market readiness | contract_intel explicitly forbids |
| Padding competitor lists | B claims_forbidden |
| Inferring partners from same órgão | limitations.md §2 |
| Using HC backfill process/DB for this campaign | Isolation / STATUS.md |
| Claiming SC coverage from national row counts | P8 / Agents.md seals |

---

## 6. Recommended delivery sequence (reuse-first)

```
[P8 filters] → parameterize A/B/HHI
     ↓
[P1] deliverable B + v_supplier_winners
[P4] deliverable A + buyer_intel + C
[P7] consulting_readiness competitive block
     ↓
[P3] deliverable D (strict comparability)
     ↓
[P2] first_seen report (new thin product on same facts)
[P5] cooccurrence signal report (new thin product)
[P6] UF/object expansion tables with coverage caveats
     ↓
[P9] deliverable_package_final (same run_id)
```

---

## 7. Mapping to campaign gates

| Gate (STATUS.md) | Product design contribution |
|------------------|----------------------------|
| STRATEGIC_PRODUCTS_PASS | This catalog + questions + limitations + reuse map |
| ARCHITECTURE_DECISION_PASS | Prefer additive queries/views; no claim of new platform |
| SC_COVERAGE_ISOLATION_PASS | P8 dual lens + limitations §4 |
| Implementation later | Only after Spec Kit; reuse modules above |

---

## 8. File index (this products/ folder)

| File | Content |
|------|---------|
| `product-catalog.md` | 9 products prioritized with FACT/INDICATOR/INFERENCE |
| `competitors/questions.md` | Competitor hypotheses, SQL sketches, risks |
| `benchmarks/questions.md` | Comparability rules; when NOT comparable |
| `agencies/questions.md` | Agency intelligence questions |
| `limitations.md` | Proof bars; partnership ban; national≠SC |
| `reuse-existing-deliverables.md` | This file — exists vs gaps |

---

## 9. Non-claims for this design package

- Does not implement code, migrations, or backfill.  
- Does not assert current market rankings from live DB.  
- Does not mark DOD items complete.  
- Does not authorize partnership or win-rate metrics.
