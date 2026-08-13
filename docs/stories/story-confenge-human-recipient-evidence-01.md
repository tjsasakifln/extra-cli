# Story: CONFENGE human recipient evidence

**Status:** InProgress
**Branch:** `feat/confenge-human-recipient-evidence-01`
**Base:** `origin/main` at `1ffa079d3e45d06612be0e46c2574fa4b1314e88`
**Capability:** Authoritative, auditable human-recipient resolution for the Warmbly pilot
**DOD item:** `DOD-definition-of-done-extra-1cd551b906` (OPEN; do not accept before main + CI + live evidence)

## Goal

Replace the old functional-mailbox interpretation of `EMAIL_SEND_READY` with a
fail-closed human-recipient contract, execute the full public-source ladder for
currently eligible CONFENGE accounts, and terminate honestly as either:

- `READY_FOR_WARMBLY_IMPORT`: at least 30 unique eligible CNPJs have exactly one
  explicitly published, named, role-proven, company-owned human recipient and
  the official extra-cli feed is published and verified; or
- `NO_GO_CONTACT_EVIDENCE`: the source ladder is exhausted and fewer than 30
  accounts satisfy the contract, with every absence carrying reproducible
  attempts and reason codes.

The work does not modify Warmbly, approve drafts, resume dispatch, or send
messages.

## Reconciled baseline

- extra-cli `origin/main`: `1ffa079d3e45d06612be0e46c2574fa4b1314e88`.
- extra-cli deployed SHA: `fffdd3ff5d08702013fe2e2f405b945be2d7ba39`.
- published generator SHA: `d0ce84741eb12eb115a4bcf73a9fde73d8fd1cfa`.
- published/imported snapshot: `a6c32643e67bcf2f9a1f3a8147d700a605de5de8934a078ddefb8308e8a03e5f`.
- manifest SHA-256: `341052580fe737bb9a70e289825fa56ecd970fefa6c94080ff1332320db2b06a`.
- Warmbly main/runtime: `44bdf5f56c40c2b57328d18b5dfb6ceb650cd4a9`.
- Warmbly DB: 303 target-fit eligible accounts, 32 account-level legacy
  `email_send_ready`, and zero candidates satisfying the literal human contract.
- current request: 30 selected, 8 prepared, 22 blocked by
  `recipient_evidence_date_missing`, 0 approved, 0 sent.
- selected mailbox purposes: UNKNOWN=17, COMERCIAL=4, GENERIC_CONTACT=9;
  explicit recipient names=0/30; evidence date present=8/30.
- the published IP endpoint presents a private-CA certificate that is not
  trusted by the default system trust store.

Detailed CNPJ/contact matrices are intentionally outside Git under
`/tmp/confenge-contact-evidence-protected-20260813/` with mode `0600`:

- `eligible303_accounts.jsonl` — SHA-256
  `7042fdb9867d49849a5d61d5282c52aacc5b135779294657b9ddb2c953e60d5f`;
- `selected30.jsonl` — SHA-256
  `23d27091b82a0ddf43d28d3002b2e4845adb9f54bd177dbcfd5b2ffe77a5b1c4`.

## Acceptance criteria

### Human-recipient contract

- [ ] One active, currently eligible, unique CNPJ per selected account.
- [ ] Exactly one primary recipient per account and 30 distinct nominal emails.
- [ ] Person name and commercially relevant role are explicitly evidenced; no
  value is derived from an email local-part or a company-name pattern.
- [ ] Email is explicitly published by a source tied unambiguously to the CNPJ
  or company, uses a company-owned domain, and passes the existing technical
  checks.
- [x] Generic and functional mailboxes are rejected, including contact,
  commercial, sales, finance, engineering, procurement, and administrative
  aliases.
- [ ] Ownership, commercial suitability, provenance chain, and evidence-date
  semantics are positive; fixture/demo/synthetic/pattern-guess data cannot pass.
- [ ] Suppression, DNC, opt-out, hard bounce, block, provenance taint, domain
  mismatch, and out-of-policy staleness all fail closed.

### Evidence semantics and source ladder

- [ ] Attempts record CNPJ, adapter, source URI/document, declared publication
  date when present, observed time, active-verification time when actually
  performed, result, reason, limitations, content/evidence hash, terminal state,
  and next action.
- [x] `source_published_at`, `observed_at`, and `verified_at` remain distinct;
  observation/import time never fabricates publication freshness.
- [ ] For every unresolved eligible account, the ordered ladder covers official
  company pages, CNPJ-linked administrative documents, PNCP/official procurement
  and transparency portals, professional councils/legitimate associations,
  complementary corporate pages, and registry/QSA corroboration only.
- [x] Aggregators never serve as sole final proof and same-name/group/domain
  similarity never establishes ownership.

### Pipeline, reselection, and publication

- [x] Contact extraction, ranking, terminal states, reason codes, provenance
  preservation, invalidation, and reruns are deterministic and fail closed.
- [ ] Reselection uses only currently eligible accounts with equivalent-or-better
  fit, unique CNPJ, and recorded replacement rationale; target fit is not
  reclassified to fill quota.
- [ ] Two identical runs produce no duplicate contacts, recipient drift, hash
  drift, or artificial evidence-date growth.
- [ ] Publication occurs only if at least 30 accounts satisfy every criterion;
  otherwise no snapshot may advertise READY.
- [ ] Published manifest/chunks pass schema, hash, byte-size, timestamp, HTTPS,
  and Warmbly importer-contract validation against the unchanged Warmbly repo.
- [ ] Final handoff records initial/final/deployed SHA, PR/commits, before/after
  metrics, terminal distribution, substitutions, tests, protected matrix path,
  manifest URL/hash when published, and the terminal result.

### Safety

- [x] Warmbly source repository remains unchanged.
- [x] No message has been sent in baseline reconciliation.
- [x] No approval has been created in baseline reconciliation.
- [ ] Zero sends, zero approvals, dispatch paused, and human approval required
  are reconfirmed at terminal handoff.

## Quality gates

- Focused adversarial tests for every corrected defect.
- Repository formatting/lint/type gates from `docs/DEVELOPMENT.md`.
- `python3 -m pytest tests/ -q --tb=no -x`.
- `python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"` with honest
  external-source result.
- Generated-artifact and PR-reviewability policies against `origin/main`.
- Exact PR HEAD green in canonical GitHub Actions before merge/deploy.
- Deployment SHA equals the validated merged SHA before any publication claim.

## File list

- Contact contract and semantic dates:
  `scripts/confenge_contact_resolution/{models,merge,mailbox_purpose,send_readiness,resolver,enrichment_batch}.py`.
- Adapters and auditable ladder:
  `scripts/confenge_contact_resolution/adapters/*.py` and
  `scripts/confenge_contact_resolution/discovery/{cascade,extract,site_crawl,web_search_providers}.py`.
- Downstream fail-closed projection:
  `scripts/warmbly_bridge/mapping.py`,
  `scripts/confenge_activation/{strict_national_esr,rebuild_national_funnel}.py`,
  and `scripts/confenge/emit_unconditional_go_pack.py`.
- Focused regression tests under `tests/confenge_contact_resolution/`,
  `tests/confenge_activation/`, `tests/confenge_target_fit/`, and
  `tests/warmbly_bridge/`.
- This story.

## Change log

| Date | State | Evidence |
|---|---|---|
| 2026-08-13 | IN_PROGRESS | origin/main, VPS, live manifest, Warmbly runtime and DB baseline reconciled; literal valid recipients 0/30 |
| 2026-08-13 | IN_PROGRESS | strict human-recipient gate, semantic evidence dates, ordered attempt ledger, deterministic single-primary mapping, and downstream ESR propagation implemented; focused tests green |
