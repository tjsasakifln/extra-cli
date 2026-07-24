# Strategic data assets — national contracts intelligence products

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Base:** `origin/main` @ `a38981b`  
**Stance:** inventory of *what the lake can become* — not claims of readiness, 95%, or live national completeness.

---

## 1. Primary asset: `pncp_supplier_contracts`

| Property | Detail |
|----------|--------|
| Grain | One row per `contrato_id` (PNCP `numeroControlePNCP`) |
| National? | Yes — FKs to SC entity universe dropped (050/055/056); soft CNPJ8 joins remain |
| Core dimensions | orgao (CNPJ/name), fornecedor (CNPJ/name), objeto, valor_total, vigencia (inicio/fim), UF, municipio, dates, source |
| Volume signals (external notes) | Campaign safety notes cite ~2.27M rows / ~2.5 GB on live-class DBs; DOD historical ops cites ~217k in older packs — treat volume as environment-specific |
| Semantic value | `valor_total` ← PNCP valorGlobal ≈ **CONTRATADO/global ceiling**, not paid/praticado |
| Date richness (post-051) | assinatura vs publicação fonte vs event date vs vigencia vs crawl windows |

**Product power:** multi-year, multi-UF supplier–agency contract graph for B2G market intelligence.

---

## 2. Identity / universe assets

| Asset | Strategic role |
|-------|----------------|
| Seed universe 200 km / 1093 | Extra Construtora commercial law denominator (coverage + client packs) |
| `sc_public_entities` | Operational entity master for SC analytics joins |
| `enriched_entities` | CNAE / natureza for supplier sectorization |
| `entity_hierarchy` / aliases | Matching hierarchy for coverage inheritance |
| CNPJ8 soft keys | National organs/suppliers join when present; no hard membership required |

**Product power:** switch between **client-scoped** (200 km) and **national market** views without forking the lake — if architecture defines scope filters explicitly.

---

## 3. Evidence / metrology assets

| Asset | Strategic role |
|-------|----------------|
| `coverage_evidence` | Audit trail of monitoring per entity×source×capability |
| dual coverage engine | Fail-closed 95% gates for editais vs contracts |
| freshness SLAs | Operational trust (24h tenders / 7d contracts) |
| success_zero proofs | Distinguishes “no contracts” from “we never checked” |
| source applicability policy | Avoid false readiness on non-applicable sources |

**Product power:** sell **auditável** coverage and monitoring SLAs as a product, not just data dumps.

---

## 4. Product families derivable from national contracts

### 4.1 Agencies / buying organs (campaign folder `products/agencies/`)

| Product | Inputs | Description |
|---------|--------|-------------|
| Org ranking by spend | orgao_cnpj, valor_total, counts, time window | Who buys how much in a sector/UF |
| Org portfolio | objeto text + categories | What categories each agency contracts |
| Agency loyalty / concentration | HHI-like on suppliers per orgao | Supplier lock-in maps |
| Renewal pipeline | data_fim windows 90–180–365 | Business development calendar |
| Cross-UF expansion map | uf × orgao | National footprint of a buyer class |

**Existing scaffolds:** deliverable A, `v_contract_intel_*`, org_ranking reports, weekly pack.

### 4.2 Competitors / suppliers (campaign folder `products/competitors/`)

| Product | Inputs | Description |
|---------|--------|-------------|
| Winner leaderboards | fornecedor_cnpj, counts, valor | Top contractors by market slice |
| Market share proxies | share of valor_total by supplier in slice | Observational only (not full bid market) |
| Cross-agency reach | distinct orgao count | Geographic/commercial breadth |
| Concentration (HHI) | value shares per supplier | Competitive intensity |
| Head-to-head co-occurrence | same orgao over time | Rivalry graphs |
| Capacity hypothesis layer | needs extra evidence | Must stay labeled HYPOTHESIS (deliverable B rule) |

**Existing scaffolds:** deliverable B, contract_intel fornecedores, workspace competitors, concorrentes_report.  
**Limit:** PNCP contracts show winners of contracts, not full bidder lists for all modalities.

### 4.3 Benchmarks / prices (campaign folder `products/benchmarks/`)

| Product | Inputs | Description |
|---------|--------|-------------|
| Ticket distributions | valor_total by category keywords | P25/P50/P75 panels |
| Comparable groups | tipo, UF, porte, period | Fail-closed price refs (deliverable D) |
| Temporal price evolution | period slices | Inflation/market movement signals |
| Est vs homolog vs contract | need bids+contracts same certame | True deságio — **mostly not implemented** without match |
| Category taxonomy | objeto NLP/keywords | Today: crude keyword buckets in percentis view |

**Existing scaffolds:** deliverable D, `v_contract_intel_percentis`, precos/desagio CLI.  
**Hard constraint:** never brand heterogeneous valor_total as “preço real praticado”.

### 4.4 Administrative contract follow-up (DoD scope, partial code)

| Product | Inputs | Gap |
|---------|--------|-----|
| Vigência / renewal alerts | data_fim + amendments | Amendments not first-class model |
| Aditivos / reajustes | PNCP acts / other sources | Partial (official_acts migration 052 exists) |
| Relicitação signals | expiry + new open tenders | Needs OI + contracts fusion |
| Sanções | sanctions crawler present in crawl tree | Integration depth TBD |

### 4.5 Cross-capability fusion products

| Product | Lakes |
|---------|-------|
| Bid → contract lineage | `pncp_raw_bids` + contracts on control numbers / objects |
| Open pipeline + history | opportunity_intel + contracts by orgao |
| Extra profile scoring on historical wins | client profile (ADR-022) + contracts |
| Sector market packs | demo_b2g_setorial + national filters |

---

## 5. Secondary lakes that multiply contracts value

| Lake / module | Multiplier |
|---------------|------------|
| `pncp_raw_bids` | Pre-contract funnel; estimado vs later contract |
| `opportunity_intel` | Live open pipeline + ranking |
| Official acts / DOM / CIGA / SC Compras | Local completeness beyond PNCP |
| Entity Source Registry | Applicability & portal targeting |
| Client profiles | Commercial ranking law |

National contracts alone are a **supply-side winner graph**; with bids they become a **procurement lifecycle graph**.

---

## 6. What already exists vs what is national-product-shaped

| Layer | Exists on main | National product ready? |
|-------|----------------|-------------------------|
| Ingest national contracts | Yes (crawler + FK drops + pilot) | Operational path exists; volume/SLA ops open |
| SC 200 km analytics views | Yes | Yes for SC client slice |
| Dual coverage metrology | Yes | Engine yes; 95% live open |
| Deliverables A–D schemas | Yes | Schema/fixture; live often INSUFFICIENT |
| National agency/competitor/benchmark SKUs | Partial code only | **No** unified product layer |
| Spec 003 | Placeholder | To define SoT |
| HC bulk historical load | Parallel process | Builds lake depth; not product packaging |

---

## 7. Strategic constraints (product honesty)

1. **National rows ≠ Extra coverage.** Coverage is seed-entity evidence.  
2. **valor_total ≠ preço praticado.**  
3. **Winners ≠ all competitors.**  
4. **success_zero is a product feature** (“we proved empty”) — store and expose it.  
5. **Scope labels required:** UF / radius / sector / years must travel with every export.  
6. **Concurrent HC load** can change lake stats mid-product; pin `as_of` + run_id.  
7. **Do not invent 95%** for national products without dual (or separately defined) metrology.

---

## 8. Suggested product packaging axes (for later architecture)

Without implementing:

1. **Scope selector:** Extra-200km | UF | multi-UF | BR  
2. **Time selector:** 90d | 1y | 3y | custom  
3. **Object filter:** profile keywords / CNAE / engineering flag  
4. **Output SKUs:** agencies pack, competitors pack, benchmarks pack, renewal pack, audit coverage pack  
5. **Evidence sidecar:** dual coverage slice + presence + limitations JSON next to every commercial Excel/PDF  

These align with campaign directories under  
`artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/products/{agencies,competitors,benchmarks}/`.

---

## 9. Asset inventory checklist (code-backed)

- [x] National-capable contracts table + upsert  
- [x] Date semantics columns (051)  
- [x] Soft CNPJ8 keys + indexes  
- [x] Typed crawl FetchResult / success_zero path  
- [x] Dual coverage engine for historical_contracts  
- [x] SC analytics views + contract_intel CLI  
- [x] Deliverable schemas A–D  
- [x] Weekly pack reuse of lake  
- [ ] Unified national product query API  
- [ ] Certame-level bid–contract deságio pipeline  
- [ ] First-class amendments / administrative follow-up model  
- [ ] Spec 003 filled + ADRs for national architecture  
- [ ] Isolation of product analytics from HC backfill process
