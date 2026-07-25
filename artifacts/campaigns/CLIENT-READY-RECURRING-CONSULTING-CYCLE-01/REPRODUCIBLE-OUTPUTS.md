# Reproducible outputs (not versioned)

Heavy pack outputs (PDF, XLSX, full dossiers, deliverable dumps, pack-rc/pack-verify
duplicates, monthly cycle-state) were removed from Git per
`docs/generated-artifacts-policy.md`.

## How to regenerate

```bash
# Isolated DSN only (ports 5436/5438/5439) — never production/VPS
export LOCAL_DATALAKE_DSN=postgresql://...@127.0.0.1:5439/extra_client_ready
make client-ready-pack   # or campaign Makefile targets documented in campaign STATUS
```

## What remains in Git

- `user-acceptance.json` (PENDING_HUMAN), claims/non-claims, manifests, checksums
- Small JSON evidence (coverage, isolation, migrations, quality)
- Specs, migrations 060/061, Python modules, tests

## Checksums

If `pack/checksums.json` is present, verify regenerated files against it after a
local/CI pack run. Do not re-commit regenerated binaries without policy exception.
