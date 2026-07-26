# Independent adversarial review — CONFENGE gold standard

Verdict: **CODE_HARDENED_BUT_COMMERCIAL_PASS_BLOCKED**

## F-GOLD-01 (CRITICAL) — FIXED_IN_CODE_PENDING_REAL_RERUN

- Reviewer: data-methodology-reviewer
- Evidence: Pre-gold pipeline used filter_relevant then sector ratio on filtered set
- Impact: False STRONG_ENGINEERING_FIT at scale
- Fix: two-stage full history — implemented in pipeline.py + sector_fit v2

## F-GOLD-02 (HIGH) — OPEN

- Reviewer: sector-domain-reviewer
- Evidence: CNAE not loaded in previous pipeline path
- Impact: CONFIRMED path unused; contract-only STRONG inflated
- Fix: supplier_registry + load_registry_map — schema ready; coverage still BLOCKED

## F-GOLD-03 (HIGH) — FIXED_POLICY

- Reviewer: commercial-validity-reviewer
- Evidence: Agent precision figures without dual human labels
- Impact: False commercial confidence
- Fix: null metrics until dual human review

## F-GOLD-04 (HIGH) — FIXED_IN_CODE_PENDING_REAL_RERUN

- Reviewer: skeptical-red-team
- Evidence: FULL_POPULATION meant prefilter not full snapshot
- Impact: False completeness claim
- Fix: explicit discovery_mode/history_expansion_mode — implemented

## F-GOLD-05 (MEDIUM) — OPEN

- Reviewer: evidence-audit-reviewer
- Evidence: result.json/queue-summary still bound to pre-gold run SHA
- Impact: Evidence lag until re-execution
- Fix: re-run pipeline on authenticated snapshot after merge of code

## F-GOLD-06 (MEDIUM) — OPEN

- Reviewer: database-isolation-reviewer
- Evidence: enforce_source_readonly often False in cycle
- Impact: Isolation not fully proven in CI
- Fix: live role tests with DSN

