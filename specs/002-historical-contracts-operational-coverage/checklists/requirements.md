# Requirements checklist — Spec 002

- [x] Spec states VPS cutover in scope (not future-only)
- [x] success_zero requires checkpoint proof (not CLI flags alone)
- [x] Export/restore fail-closed requirements documented
- [x] Single writer invariant documented
- [x] Dual ≥95% without denominator games
- [x] Incremental freshness ≤168h
- [x] systemd/venv/calendars/OnFailure
- [x] Backup off-site + restore separate DB
- [x] Soak 7d
- [x] DOD sequential accept only with evidence
- [ ] All acceptance gates green on VPS SHA (open until ops complete)
- [ ] PR #121 remains isolated with renumber plan
