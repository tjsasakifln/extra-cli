# Acceptance — CMI 47 items

Each item accepted via `dod_controller.py accept` after verify with item-specific `cmi_item_proofs --item ALIAS` and package material under `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`.

See acceptance-matrix.md and acceptance-manifest.json.

## Integrity rebind

- main_sha: `ea25c0ff3a382c7df11316344ba129942f40b572`
- package hashes recomputed and bound to final-package
- adversarial-review.json expanded to §17 attack records
- PRs: 151–154 documented (max-3 exceeded for rebind/integrity only)

## Terminal honesty (post-skeptic)

- **terminal_state:** `FAILED_PREMORTEM` (`SECTION_18_PR_BUDGET_EXCEEDED`)
- **PRs:** [151, 152, 153, 154, 155, 156, 157] (count=7 > max 3)
- **main tip at honesty write:** `b2eaa52a3dc1bb829c49e128913190ad3902aac5`
- **verified operational main:** `71566879eaca70b9cfc4810ba49032578171d840`
- **BUNDLE_ACCEPTED:** not authorized under OBJECTIVE §18/§32
- Floors numerically met; controller accepts retained; campaign success claim withdrawn
