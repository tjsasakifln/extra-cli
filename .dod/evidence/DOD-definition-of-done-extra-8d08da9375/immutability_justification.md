# Immutability justification

- Evidence and verify_result were produced against campaign HEAD `475aa50c7ab7ddfd93dd832ee4e8c53314bcacd4` (PR #127, CI green).
- Subsequent commits on this branch only add: DOD checkbox flips, evidence packs metadata, executive HTML, and harness state — no product code change that invalidates the proofs.
- After merge to `main`, CI of the merge commit re-proves the branch; re-verify optional if HEAD product tree differs.
