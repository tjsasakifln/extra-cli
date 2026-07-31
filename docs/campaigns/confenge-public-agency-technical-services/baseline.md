# Baseline — CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01

**Campaign:** `CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01`  
**Mode:** AUTONOMOUS / FAIL-CLOSED / REAL-DATA / HUMAN-APPROVAL-BEFORE-OUTREACH  
**Operator:** Tiago Sasaki  
**Brand:** CONFENGE  
**Canonical repo:** github.com/tjsasakifln/extra-cli  
**Baseline captured (UTC):** 2026-07-30T22:52:18Z  

---

## 1. Repository truth at baseline

| Field | Value |
|-------|--------|
| Branch (implementation) | `campaign/confenge-public-agency-technical-services-01` |
| Worktree | `.worktrees/pag-public-agency` |
| `origin/main` HEAD | `8ff80eef188974d2c17cb8716e74700fef3e9b12` |
| Tip commit subject | `fix(universe): RealDictCursor support for weekly open-tenders collect (#182)` |
| Working tree (worktree) | clean at branch creation |
| Operator workspace branch (dirty, **not** used) | `feat/public-process-documents-coverage` @ `484fa764…` with unrelated process_documents edits |

### Open PRs (collision inventory)

| PR | Title | State | Collision risk |
|----|-------|-------|----------------|
| #184 | feat(process_documents): documentos públicos… | draft | Low — different domain |
| #183 | feat(registry): CONFENGE official RFB CNPJ mirror | open | Medium on commercial registry only; do not modify registry ingest |
| #133 | [DRAFT][BLOCKED] bid submission readiness | blocked draft | **Do not touch** |

**Policy:** no soak changes; no PR #133 work; no cosmetic DOD percentage inflation.

---

## 2. What already exists (supplier commercial path)

### Code (implemented)

- **Canonical entry:** `make confenge-commercial-cycle` → `python3 -m scripts.ops.confenge_commercial_cycle`
- **Core package:** `scripts/commercial_leads/` (pipeline, scoring, signals, exports, dossiers, identity, profile, snapshot, isolation, top10_gate, supplier_registry, …)
- **Profile:** `config/commercial_profiles/confenge.yaml` v2.0.0 — **supplier-oriented**
- **Critical exclusion:** `exclusions.drop_public_organs: true` + organ name markers (prefeitura, município, autarquia, …)
- **Migrations:** `062_commercial_leads_ledger.sql`, `063_supplier_registry.sql` (supplier CNPJ queue)
- **Signals/scoring:** explainable multi-signal scoring for **fornecedores** (private companies as suppliers to government)
- **Exports:** leads.csv/json, explanations, evidence-ledger, dossiers, kits — supplier semantics
- **Gates:** large confenge make gate surface (registry, holdout, freeze, snapshot binding, soak non-interference)
- **IBGE population:** `config/municipio_population.yaml` (SC Censo 2022; used for entity matching thresholds, not commercial agency scoring)

### Proven in tests

- Extensive `tests/commercial_leads/` suite (signals, scoring, isolation, persistence, sector fit, review states)
- Confenge gates under `scripts/ops/confenge_*` with machine-evidence under `artifacts/campaigns/CONFENGE-COMMERCIAL-*`

### Proven with real data (historical, supplier only)

- Authenticated snapshot + real run artifacts under `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/` and activation campaign
- Prior `run-result.json` shows `status=BLOCKED` with 20 supplier leads ranked — **supplier vertical only**
- **Must not** reuse those SHA/bindings as evidence of this new campaign

### Documented / DOD (not public-agency)

- `DOD.md` §2.7 *Inteligência comercial CONFENGE* targets **empresas** (PJ suppliers), not contracting agencies as prospects
- Gate `CONFENGE_COMMERCIAL_READY` is supplier-queue readiness
- No PAG-* items exist yet

### Explicit non-existence at baseline

| Capability | Status |
|------------|--------|
| PUBLIC_AGENCY_PROSPECT entity type | **Absent** |
| public_agency_leads queue | **Absent** |
| Legal thresholds YAML (art. 75 I/II 2026) | **Absent** |
| Object class ENGINEERING_SERVICE / OTHER_SERVICE / REQUIRES_HUMAN… | **Absent** (supplier relevance classifier only) |
| Fragmentation / DIRECT_CONTRACTING_SUM_UNKNOWN | **Absent** |
| Art. 117 fiscal-support language gates | **Absent** |
| Conflict-of-interest gate for operator public role | **Absent** |
| Public-agency service catalog (planejamento, orçamento, fiscalização, …) | **Absent** (supplier offers differ) |
| TARGET=public-agencies on commercial cycle | **Absent** |
| Proactive institutional prospecting of municípios | **Absent** (organs dropped) |
| PAG section in DOD | **Absent** |

---

## 3. Canonical flow today (suppliers)

```
snapshot manifest (authenticated)
  → confenge_commercial_cycle (--dsn state, --snapshot-manifest)
    → apply migrations 062/063
    → discover_candidate_suppliers (pncp_supplier_contracts, fornecedor_cnpj)
    → drop public organs
    → signals + sector_fit + scoring
    → rank Top N
    → export leads/dossier/kit under CONFENGE_COMMERCIAL_OUT
    → run-result.json + cycle-manifest (git_sha bound)
```

Human review → outreach **manual only**. No auto-contact.

---

## 4. Gaps for this campaign

1. **Semantic inversion:** today organs are *excluded*; we need organs as *prospects* without polluting supplier leads.
2. **Legal model:** temporal thresholds, strict “inferior to”, object classification, sum/fragmentation, art. 117.
3. **Separate scoring/signals** for institutional need (small municipality + engineering procurement distress), not supplier “pain of bidding”.
4. **Service catalog** for technical services to the Administration (ETP, TR, orçamento, apoio à fiscalização, …).
5. **Integrity:** COI states, institutional contacts only, prohibited legal marketing language.
6. **Artifacts namespace:** `public-agency-*` files + dossiers/kit under `public-agencies/` without breaking supplier exports.
7. **Real SC Top 20:** needs agency universe from contracts (orgao_*) + IBGE population bands ≤50k priority.

---

## 5. Architectural decisions (integration, not parallel product)

| Decision | Choice |
|----------|--------|
| Entry point | Keep `make confenge-commercial-cycle`; add `TARGET=suppliers\|public-agencies\|all` (default `suppliers`) |
| Package layout | New `scripts/public_agency/` companion package — **does not** mix types into `commercial_leads` lead rows |
| Config | `config/legal/direct_contracting_thresholds.yaml`, `config/commercial/public_agency_*.yaml` |
| DB | Prefer read of existing `pncp_supplier_contracts` **by orgao_*** (buyer side). Optional additive migration `068_public_agency_leads.sql` only if persistence required for parity; MVP may export without write if DSN missing |
| Data sources | PNCP historical contracts (buyer), IBGE population YAML, optional official registry — no fragile national scrape as MVP critical path |
| Pricing | Scope/effort based; ceiling only as eligibility filter → `POTENTIALLY_ELIGIBLE_FOR_DIRECT_CONTRACTING` |
| Outreach | Generate queue + messages; **never** send |
| DOD | New section PAG-1…PAG-25; states honest; no ACCEPTED without ACCEPTED-class evidence |

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Reclassifying organs into supplier queue | Hard separation of entity_type + export paths + tests |
| Claiming “dispensa garantida” | Blocklist + only POTENTIALLY_ELIGIBLE… |
| Fracionamento as pricing hack | Fragmentation detector + sum-unknown refusal |
| Operator COI with public duties | conflict states default PENDING; human clear only |
| Env without snapshot/DSN | Fail-closed taxonomy; fixtures for unit tests; real run when DSN available |
| Collision with #183 registry | Do not change supplier registry ingest |
| False Top 20 padding | Publishability gates; NO_PUBLISHABLE_LEADS allowed |

---

## 7. Execution plan

1. ✅ Baseline (this file)
2. Legal/compliance pure modules + YAML + boundary tests
3. Entity/signals/scoring/publishability + catalog
4. Pipeline + exports + dossiers + kit + proposal
5. Wire TARGET into cycle + Makefile
6. Docs + DOD PAG items
7. Fixture tests + supplier regression
8. Real SC run (or honest env failure + partial real-data proof if DB has SC buyer rows)
9. Final report + PR prep (no auto-merge)

---

## 8. Distinction matrix (for acceptance honesty)

| Layer | Supplier vertical | Public-agency vertical (this campaign) |
|-------|-------------------|----------------------------------------|
| Código existente | Yes | Starting now |
| Capacidade implementada | Yes | Target of campaign |
| Comprovada em testes | Yes (commercial_leads) | Required for READY |
| Comprovada com dados reais | Partially (historical runs) | Required for Top 20 / insufficiency claim |
| Só documentado | Some DOD open items | Forbidden as sole proof |
| DOD ACCEPTED | Some commercial items open | PAG items start non-ACCEPTED |

---

## 9. Non-goals (reaffirmed)

No auto-outreach, no SaaS portal, no automated legal opinion guaranteeing direct contracting, no fiscal substitution, no invented credentials, no soak/PR#133, no PROJECT_DONE / COMMERCIAL_VERTICAL_ACCEPTED claims.
