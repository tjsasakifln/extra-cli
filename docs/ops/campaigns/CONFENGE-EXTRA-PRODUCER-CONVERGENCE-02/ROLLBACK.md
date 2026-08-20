# ROLLBACK

Trigger immediately if: migration breaks existing reads; consumer view
allows write; source failure becomes `NO_MATCH_CONFIRMED`;
`national_claim_authorized` appears without an integral official universe;
CNPJ/secret leak; hashes non-deterministic; import/service break; deployed
SHA diverges from main.

## Procedure

1. Keep `/var/lock/confenge-production-deploy`.
2. Restore previous code SHA (`bbc4b6b7db295909d773f5a0e1f3314085a2f26c`
   was on the host at preflight; capture the live previous SHA again
   immediately before deploy).
3. Prefer code rollback while leaving additive 097/098 schema in place
   (097/098 are additive; consumers of older tables are unaffected).
4. Run 098 then 097 down only after proving no dependent consumer/rows
   and after a `pg_dump`. Never delete rows to make rollback “pass”.
5. Restore dump if needed; rerun prior smoke; record before/after/cause.

## Scripts

- Code: `git -C /opt/extra-consultoria checkout <previous_sha>`
- Schema down: `db/rollback/098_national_coverage_consumer_select_only_rollback.sql`
  then `db/rollback/097_national_coverage_rollback.sql`
