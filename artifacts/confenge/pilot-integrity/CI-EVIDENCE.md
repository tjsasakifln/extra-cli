# CI-EVIDENCE

## extra-cli PR #211

- Branch: `fix/confenge-pilot-target-service-integrity`
- HEAD: `{
  "timestamp_utc": "2026-08-10T01:15:16Z",
  "extra_cli_pr": 211,
  "extra_cli_branch": "fix/confenge-pilot-target-service-integrity",
  "extra_cli_head": "560b59c9ff9e024981272f302199e22989182d72",
  "warmbly_pr": 34,
  "warmbly_branch": "fix/confenge-pilot-service-copy-integrity",
  "warmbly_head": "be082d329d4c0abdca8a97f49c0324130b53d68f",
  "vps_extra_worktree_head": "560b59c9ff9e024981272f302199e22989182d72",
  "vps_main_deploy_head": "0b3fce71 (NOT this PR — production not redeployed this round)",
  "match_note": "PR heads are bound; VPS production deploy SHA is NOT updated to PR heads — no false MATCH for runtime"
}
`
- Local: `ruff check` confenge scope PASS; pytest confenge suites **214 passed**
- Actions: Lint (ruff) PASS on push of 560b59c9; remaining jobs recorded in rebuild-2026-08-10/extra-cli-ci-checks.txt

## warmbly PR #34

- Branch: `fix/confenge-pilot-service-copy-integrity`
- HEAD: be082d32
- Local: `gofmt` clean; `go test ./...` PASS; `make lint` PASS
- Actions: Go CI PASS, CONFENGE product acceptance PASS, CI Status PASS

## Required approve-fail-closed tests

- `TestStructuralApproveBlockersIncompleteCopyContext`
- `TestStructuralApproveBlockersUnknownService`
- `TestStructuralApproveBlockersMissingFields`
- `TestReviewDraftApproveFailsIncompleteAndUnknown`
- `TestReviewDraftApproveSucceedsAfterCompleteRepair`
- `TestEnrollRejectsNonApprovedStructurally`
