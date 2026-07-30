# Plan — 007 confenge commercial activation outcome loop

## Architecture

Reuse `scripts/commercial_leads/*` and `scripts/ops/confenge_commercial_cycle.py`.

```
SOURCE (read-only snapshot DB)
    → discover candidates (SQL prefilter documented)
    → expand full supplier history (set-based)
    → official registry resolve (RFB extract)
    → sector fit + signals + score
    → Top20 + Top10 gate
    → dossiers + kits
    → persist commercial_* (STATE)
    → exports + canonical coverage + delta
```

## Workstreams

| W | Work | Files |
|---|------|-------|
| W1 | Spec Kit freeze | `specs/007-.../*` |
| W2 | Canonical coverage single-truth | `scripts/commercial_leads/canonical_coverage.py`, wire pipeline/exports/final_status |
| W3 | Default cycle FULL_POPULATION + RC paths | `confenge_commercial_cycle.py`, Makefile env |
| W4 | Dossiers Top20 + kits Top5 | `dossiers.py`, `outreach_kits.py`, export_all |
| W5 | Outcome/review CLI completeness | `review.py`, workspace hooks |
| W6 | Snapshot export full history + manifest hash | historical_snapshot / export path |
| W7 | Official registry ingest + resolution states | official_cnpj, supplier_registry |
| W8 | Adversarial tests | `tests/test_confenge_activation_*` |
| W9 | Dual real execution + soak non-interference | ops evidence |
| W10 | TIAGO-REVIEW package | human-review artifacts |

## Performance

- No full 4.4M row load into Python lists for scoring of all rows.
- Discovery prefilter SQL; history expansion by CNPJ batches.
- Indexes on `fornecedor_cnpj`, dates.
- Checkpoints for registry ingest.

## Data isolation

- STATE never production host; SOURCE restored snapshot on allowlisted local port preferred.
- `verify-soak-non-interference` before/after VPS-side evidence pulls only.

## Testing

Unit + PG integration + adversarial list from campaign §15. No skip/xfail theater.

## Delivery

Entry: `make confenge-commercial-cycle` only.
