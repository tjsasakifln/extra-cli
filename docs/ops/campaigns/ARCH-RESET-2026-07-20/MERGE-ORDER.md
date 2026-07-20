# Recommended merge order — ARCH-RESET-2026-07-20

**Rule:** never merge PR **#60** *after* PR **#62** if #60 still contains pre-honesty
`KEEP_CURRENT_STACK` / completed-dbt claims. As of tip `728ee82`, **#60 is re-honest**
and aligned with #62 on E/G.

## Safe order (preferred)

```text
#54 baseline
 → #55 characterization
 → #56 entrypoints + verify
 → #62 skeptic remediation (suite evidence, fitness, interfaces, DOD policy)
 → #57 OCDS
 → #58 quality contract
 → #60 spikes EGHJ (honest E/G as of 728ee82)
 → #59 live weekly proof
 → #61 docs rebaseline
 → #52 decision (MERGE_CANDIDATE after suite honesty)
 → thin #53 ledger
```

## Why #62 before #60 is preferred

| PR | Role |
|----|------|
| **#62** | Full suite log, security audit, Protocol adapters, fitness automation, DOD ID/gate policy, spike honesty evaluators |
| **#60** | Spike code for E/G/H/J + ADRs 026–029; **must** carry same E/G honesty as #62 |

If #60 is merged first, ensure tip includes commit  
`fix(spike): honest E/G decisions — REJECTED_WITHOUT_EXPERIMENT / DEFERRED_NO_CORPUS`  
(SHA `728ee82` or later). Then #62 can land without re-introducing theater.

## Supersede map (E/G)

| Artifact | Honest status | Authority |
|----------|---------------|-----------|
| Spike E | `REJECTED_WITHOUT_EXPERIMENT` | ADR-026 (rewritten) + DECISION.md on #60/#62 |
| Spike G | `DEFERRED_NO_CORPUS` | ADR-027 (rewritten) + DECISION.md on #60/#62 |
| Synthetic PDF microbench | exploratory only | **not** adoption proof |
| 5-dict “dbt corpus” | design notes only | **not** SCD2 experiment |

## Forbidden order

```text
#60 (pre-728ee82 dishonest tip)  →  #62
```

would allow KEEP_CURRENT / fake dbt experiment to overwrite remediation.

## Human blockers remain

- 21 full-suite failures still open (logged, not green)
- No LOCAL_READY / 95% claims
- No auto-merge
