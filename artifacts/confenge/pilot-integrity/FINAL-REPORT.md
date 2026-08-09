# FINAL-REPORT — CONFENGE-PILOT-INTEGRITY-RECOVERY-01

## Executive summary

The commercial motor was **not** reliably selecting
`empresa correta → momento correto → serviço correto → contato correto → mensagem específica`.

Adversarial forensics of the 10 EMAIL_SEND_READY Warmbly samples proved:
- **6 FALSE_TARGET** firms (imobiliária, móveis, frota, pneus/importação, metrologia, ônibus, médico) with public contracts that are **not** construction execution.
- **2 TRUE_TARGET** (TRACADO, JATOBETON) with real engineering/pavement evidence.
- **100% REAJUSTE_14133** on Warmbly with empty why_you/micro_offer and near-clone bodies.

## Fixes landed

### extra-cli (`fix/confenge-pilot-target-service-integrity`)
- `scripts/confenge_universe/target_fit.py` + construction integration
- Semantic `send_readiness.py` (COPY_CONTEXT_READY, no total-count fallback)
- Router `service_candidates[]`, reajuste never default
- Adapter signal enrichment (aditivos/glosas/BDI/licitações)
- `config/commercial/confenge_service_v1.yaml` + mapping module
- Adversarial pytest suite (41 tests green in core pack)

### warmbly (`fix/confenge-pilot-service-copy-integrity`)
- Full service aliases + DIAGNOSTICO / INTELIGENCIA_PNCP / BACKOFFICE playbooks
- Strategy: unknown service fail-closed (no REAJUSTE invent)
- Drafts: template+incomplete context → RED needs_review

## Artifacts

- `current-10-forensics.csv` / `CURRENT-10-FORENSICS.md`
- `target-fit-audit.csv`
- `service-routing-audit.json`
- `cross-repo-service-contract.json`
- `new-30-draft-sample.md` / `new-10-human-review.md` (blocked pending clean cycle)
- `GO-NO-GO.md` → **NO_GO**

## Verdict

**NO_GO** for controlled pilot send. Code path hardened; live re-score + clean sample still required.
