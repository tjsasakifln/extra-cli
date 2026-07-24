# Checklist — Canonical Entity Linkage

- [x] Fresh migrate + second migrate idempotent on isolated DSN
- [x] Strong keys never auto-merged when conflicting
- [x] Exact/deterministic separated from heuristic in metrics
- [x] Every stored link has classification, score, reason_codes, rule_version, run_id, source ids
- [x] Ambiguous/unresolved retained in denominators
- [x] Re-run same run_id does not duplicate relations
- [x] Workspace entity / competitors / expiring-contracts JSON paths work
- [x] Dossier with claims and non_claims
- [x] production_touched=false
- [x] Precision auto-accepted ≥99% on exact-only policy (sample)
- [ ] Independent review closed
- [ ] Main+CI+DOD ACCEPTED
