# ROI-cand-dyn-slice-b84aad7b10ee

## Status
**Draft** — `po_validated=false`, `qa_verdict=PENDING`

## Objective
Reconstruct snapshot/recall evidence packages deterministically (DoD §29 PARTIAL).

## Code (provisional, process debt)
- `scripts/ops/evidence_reconstruct.py`
- tests: `tests/test_evidence_reconstruct.py`

## Why not force-next ranking[0]
force-next always selects current ranking[0]. While cycle-1 story
`ROI-cand-dyn-slice-cb906bb58392` is open, ranking[0] remains that candidate.
Cycle-2 used exclude-list after rerank for `b84aad7b10ee`.

## Next human steps
1. @po validate cycle-1 story Ready (or reject provisional code)
2. Complete SDC for cycle-1
3. force-next / rerank → cycle-2 becomes ranking[0]
4. @po Ready for this story → @dev/@qa

## PR recommendation
**BLOCKED_HUMAN** on PR #51 until @po/@qa path is real.
