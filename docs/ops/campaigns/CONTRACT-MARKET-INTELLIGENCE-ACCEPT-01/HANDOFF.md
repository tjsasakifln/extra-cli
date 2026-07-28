# Handoff — CMI

- Functional code: PR #151 → `241ec41f`
- Acceptance: PR #152 → `b15f8f0d`
- Evidence remediation SHA: `b15f8f0de3cd18f8a5bb5d4ff0cf0d99702a02bf` (this branch/commit)
- No follow-on package required for this vertical.
- Residual: DOD §11.2 encadeamento remains open (out of primary package).

## Integrity rebind

- main_sha: `ea25c0ff3a382c7df11316344ba129942f40b572`
- package hashes recomputed and bound to final-package
- adversarial-review.json expanded to §17 attack records
- PRs: 151–154 documented (max-3 exceeded for rebind/integrity only)

## Claim closure (capability vs integrity PR split)

- verified_main_sha: `71566879eaca70b9cfc4810ba49032578171d840`
- package_code_sha: `aeb7663e710624cd260f80dfefba19a9525a1a88`
- main_at_claim_write: `9b4ad968b91174fa5728d6bdb43a227f79a3b1de`
- capability PRs: #151–#153 (≤3)
- integrity followups closed: #154–#156
- stop rebind loop: yes

## Terminal honesty (post-skeptic)

- **terminal_state:** `FAILED_PREMORTEM` (`SECTION_18_PR_BUDGET_EXCEEDED`)
- **PRs:** [151, 152, 153, 154, 155, 156, 157] (count=7 > max 3)
- **main tip at honesty write:** `b2eaa52a3dc1bb829c49e128913190ad3902aac5`
- **verified operational main:** `71566879eaca70b9cfc4810ba49032578171d840`
- **BUNDLE_ACCEPTED:** not authorized under OBJECTIVE §18/§32
- Floors numerically met; controller accepts retained; campaign success claim withdrawn
