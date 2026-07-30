# CONFENGE-OFFICIAL-IDENTITY-TO-REVIEWED-PIPELINE-01 — STATUS

**Date:** 2026-07-30  
**Depends on:** PR `#179` merged (Top10 official RFB gate)

## What already exists (reuse)

| Capability | Path |
|------------|------|
| Official CNPJ ingest (fail-closed) | `scripts/ops/confenge_official_cnpj.py` |
| Registry ingest + resume | `scripts/ops/confenge_registry_ingest.py` |
| Top10 official gate | `scripts/commercial_leads/top10_gate.py` |
| Fallback ≠ official | `is_official_registry_source` in `supplier_registry.py` |
| Commercial states / review | `scripts/commercial_leads/review.py` |

## Blocker (honest)

```
BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE
```

until a versioned RFB / government-authority extract is staged at:

- `data/official_cnpj/*.jsonl` + provenance manifest, **or**
- `CONFENGE_OFFICIAL_CNPJ_JSONL` env pointing to authorized snapshot

**Do not** use BrasilAPI/MinhaReceita as silent official.

## Unblock commands (when dataset available)

```bash
# Stage extract + manifest with authority=receita_federal_dados_abertos, dataset_hash, extracted_at
python3 -m scripts.ops.confenge_official_cnpj ingest --dsn "$DSN"
python3 -m scripts.ops.confenge_registry_ingest ...   # if needed for candidates
make confenge-commercial-cycle   # reprocess Top20/Top10
```

## Terminal states

| State | Condition |
|-------|-----------|
| `READY_FOR_COMMERCIAL_REVIEW` | Top20 generated; Top10 may still fail official gate |
| `CONFENGE_COMMERCIAL_READY` | Top10 official identity + **human Tiago ACCEPTED** (never forged) |

## Current claim

Infrastructure ready; **official bulk not staged in this environment** → commercial terminal remains not READY.
Soak untouched.
