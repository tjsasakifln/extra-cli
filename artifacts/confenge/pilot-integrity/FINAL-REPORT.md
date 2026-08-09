# FINAL-REPORT — CONFENGE-PILOT-INTEGRITY-RECOVERY-01

## Verdict: **NO_GO** (dispatch PAUSED, kill switch ENGAGED)

## Incident

10 Warmbly EMAIL_SEND_READY accounts were REAJUSTE monoculture with empty copy and several non-construction suppliers (imobiliária, móveis, frota, metrologia, médico, etc.).

## Code fixes (committed)

### extra-cli `fix/confenge-pilot-target-service-integrity`
- Triangulated `target_fit_class`
- Semantic EMAIL_SEND_READY + COPY_CONTEXT_READY
- Multi-service router (`service_candidates`, reajuste never default)
- `confenge.service.v1` ontology
- Near-duplicate batch gate
- Adversarial tests

### warmbly `fix/confenge-pilot-service-copy-integrity`
- Full extra-cli service_id aliases
- DIAGNOSTICO / INTELIGENCIA / BACKOFFICE playbooks
- Unknown service → needs_review (never REAJUSTE)
- Incomplete strategy + template → RED

## National offline rescore
48748 rows → CONFIRMED 5606 / RESEARCH 39212 / OUT 3930

## Warmbly local import (evidence)
- Feed: `data/confenge-feeds/pilot-integrity-clean-v1.json`
- 50 leads applied; services multi-family; **REAJUSTE=0**
- **email_send_ready true = 0** (fail-closed)
- Hard ICP FP = 0; borderline = 2
- Kill switch engaged; details in `rebuild-2026-08-09/warmbly-import-evidence.json`

## Remaining blockers for GO
See GO-NO-GO.md — real contacts, deploy, full rebuild optional, operator review.
