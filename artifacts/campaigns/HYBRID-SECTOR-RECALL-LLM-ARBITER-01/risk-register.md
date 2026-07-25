# Risk Register — HYBRID-SECTOR-RECALL-LLM-ARBITER-01

| ID | Risk | Severity | Mitigation |
|----|------|----------|------------|
| R1 | Insufficient gold labels for 99% CI | HIGH | Honest `BLOCKED_INSUFFICIENT_STATISTICAL_POWER`; never fabricate 99% |
| R2 | Silent discard of candidates | CRITICAL | Lineage on every record; union merge; no RRF exclusion |
| R3 | LLM error → false NO_MATCH | CRITICAL | Fail-closed to REVIEW; fake provider in CI |
| R4 | Keyword absence treated as NO_MATCH | HIGH | Zero-match rescue + semantic + metadata channels |
| R5 | Freeze RC v2 mutation | CRITICAL | Phase-0 checksums; isolation gate |
| R6 | Paid LLM in default CI | MEDIUM | Offline-only workflow; operational gate separate |
| R7 | Stacked PR merged to main early | HIGH | PR target = #131 branch only |
| R8 | Review queue overflow discard | HIGH | preserve_and_flag + OPERATIONALLY_BLOCKED_REVIEW_VOLUME |
| R9 | Prompt injection alters policy | HIGH | Untrusted source data; evidence validation; injection suite |
| R10 | Champion regression on precision | MEDIUM | Shadow replay; challenger promotion criteria |
