# Implementation Plan — 006 Canonical Entity Linkage

## Architecture

```
opportunity_intel ──exact cnpj──► canonical_organs
        │                                │
        │ same orgao_cnpj_8              │
        ▼                                ▼
pncp_supplier_contracts ──► opportunity_contract_links (claim=similarity)
        │
        ▼
canonical_suppliers + observed_supplier_relations (claim=fact on winner identity)
        │
        ▼
scripts.workspace entity|competitors|expiring-contracts
        │
        ▼
dossier HTML/JSON/CSV
```

## Layers

1. **keys.py** — pure normalize/validate CNPJ/CPF/IBGE
2. **resolve.py** — pure LinkDecision
3. **pipeline.py** — DB I/O, run_id, idempotent upserts
4. **isolation.py** — refuse soak/prod
5. **dossier.py** — consultative artifact
6. **migration 061** — tables + unique indexes

## Migration reservation

- Sibling campaign reserved `060` for national intel layers
- This campaign: `061_canonical_entity_linkage.sql`

## Test strategy

- Pure unit tests for keys/resolve/isolation (always)
- real_db marked pipeline test when LINKAGE_TEST_DSN set
- Make targets: campaign-gate / release-candidate / verify-isolated

## Performance

Priority queries ≤60s on isolated snapshot (observed ~0.1s on 5k operational subset).
