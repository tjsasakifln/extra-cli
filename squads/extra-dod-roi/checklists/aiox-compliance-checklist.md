# AIOX Compliance Checklist (fool-proof)

Mandatory for every extra-dod-roi cycle. Any NO = STOP.

## Selection

- [ ] Work came from `force-next` or `run-cycle` (not ad-hoc)
- [ ] Candidate id == `state/rankings/latest.json` selected_id
- [ ] Ranking not stale (HEAD/DOD/age)
- [ ] No artificial unlock by weakening AC

## Story

- [ ] Story file exists under docs/stories/
- [ ] `.aiox/state/stories/{id}.json` exists
- [ ] Status Draft until @po
- [ ] @po set Ready + po_validated=true before code
- [ ] risk_level set (STANDARD or HIGH-RISK, never silent FAST for secrets/infra)

## Implementation

- [ ] Branch is not main
- [ ] @dev only; scope_files respected
- [ ] Tests/lint gates updated honestly
- [ ] Status InReview before QA

## QA independence

- [ ] @qa != implementer
- [ ] Verdict PASS|CONCERNS|FAIL|WAIVED recorded
- [ ] FAIL returns to @dev (no claim inflation)

## Close & publish

- [ ] @po closed (po_closed=true)
- [ ] DoD checkboxes only with evidence after acceptable QA
- [ ] @devops only for push/PR
- [ ] Draft PR; no auto-merge; no force-push
- [ ] force-next re-run for next ROI

## Forbidden

- [ ] No self-QA
- [ ] No DoD READY seal restore without new proof
- [ ] No fixture-as-live-coverage
- [ ] No parallel "side project" while cycle active
