# Canonical entity linkage (migration 061)

Additive linkage layer for auditable identity resolution. Does **not** create a
parallel operational coverage authority.

## Rules

- Strong key conflicts are never auto-merged
- CNPJ8 is **not** an unequivocal business identity alone
- Heuristics produce **review** outcomes, not facts
- Unresolved opportunities/contracts/suppliers remain in denominators
- No invented bid-participation edges

## Module

```bash
python -m scripts.linkage --help
```

Rollback / forward-fix: documented in migration 061 header comments.
