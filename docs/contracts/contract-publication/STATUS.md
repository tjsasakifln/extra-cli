# Status — contract publication candidate engine (#414)

Date: 2026-08-16
Producer SHA: recorded at runtime in each run (`git rev-parse HEAD`).
Branch: `feat/inbound-candidates-414`

## Honest result

- Golden corpus: labeled **fixture**. Not official. Not a web publication.
  10 records → `EDITORIAL_REVIEW` 7, `HOLD_FOR_DATA` 1, `REJECT` 2.
  Shortlist (quality-first, no padding): value/term, exceptional, peer,
  BDI, reajuste, NOT_COMPARABLE + BDI, sensitive/rescission.
- Official live path: **OFFICIAL_DATA_UNAVAILABLE**. There is no versioned
  official projection authorized for this producer on `origin/main`, and
  this worktree does not invent SQL against other goals' tables.
- Canary: the golden shortlist is whatever `EDITORIAL_REVIEW` the gates
  allow. Fewer than 5 is success if the rest fail closed.
- Integration with merged #400 / #415 on `origin/main`: **not proven**.
  Export shape matches the consumer contract Goal 03 already documented.
  Peer groups are accepted only via the versioned interface or a labeled
  fixture.

## Recommendation

`NEEDS_DATA` for official ranking. `EXPAND` only after a versioned official
snapshot exists and a human editorial pass reviews `EDITORIAL_REVIEW` packs.
