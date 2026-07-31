# SECURITY-REVIEW

## Controls preserved / extended

| Control | Status |
|---------|--------|
| CSRF | preserved |
| Local bind default | preserved |
| Command allowlist (argv list, no shell) | adapters + job_runner |
| Parameter schema | capability params |
| Path allowlist + traversal | artifact_reader / security.safe_join |
| Secret redaction | redaction.py + public_params |
| Formula injection | neutralize_formula_injection |
| No WhatsApp/email APIs | preserved |
| No auto-DOD / no auto-outreach | preserved |
| No silent REAL→fixture fallback | enforced in runner + tests |
| Correction overlay non-destructive | apply_corrections_to_source writes sibling |

## Adversarial tests

`tests/command_center/test_adversarial_security.py`:

- command/arg injection
- path traversal / outside allowlist
- secret leakage in manifest
- formula injection
- fixture fallback absence
- correction does not rewrite source
