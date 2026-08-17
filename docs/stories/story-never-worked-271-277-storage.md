# Story: Never-worked storage and backup contracts (#271 #277)

**Status:** InProgress
**Branch:** `feat/never-worked-storage-backup`
**Base:** `origin/main`
**Capability:** in-repo blob CAS + backup inventory/restore proof

## Goal

Ship the implementable in-repo slice of the two highest-criticality
never-worked P2 ops issues after the 2026-08-16 filter (unused P0/P1
exhausted). Residual live destination, credentials, RPO/RTO and off-site
VPS ACs stay on the GitHub issues. No `VPS_OPERATIONAL` claim.

## Locked issues

1. #271 — store/get/head by SHA-256, read-after-write, corruption detect,
   blobs outside PostgreSQL/Git, unavailability does not lose metadata or
   mark job success, secrets/signed URLs redacted from logs.
2. #277 — inventory + checksum of PostgreSQL dump, blobs and manifests;
   restore recovers job + metadata + chosen blob with identical hash;
   simulated VPS loss; backup/restore failure emits an alert; report
   records duration, version and artifacts.

## Scope

### IN

- `scripts/ops/blob_cas.py` filesystem/object-storage interface
- `scripts/ops/backup_integrity.py` inventory/checksum/restore/report
- Fixture-driven tests that call the shipped functions

### OUT

- Live off-site copy, human destination/credential/RPO/RTO approval
- VALIDATE measurement (#252 #254 #255 #260 #334 #335) — other PR
- Auto-close of GitHub issues
- Protocol/AIOX/hook edits

## Residual (stay on the issues)

- Human destination/RPO/RTO/retention: decided under `PREAPPROVED-EXTRA-002-2026-08-17` (see `docs/ops/extra-002-recovery-policy.md` and EXTRA-002 follow-up).
- Recurring timer enable on the VPS after merge/deploy.
- Second green restore before any retention purge.
