# Handoff — CONFENGE human recipient evidence

**Date:** 2026-08-13  
**Terminal result:** `NO_GO_CONTACT_EVIDENCE`  
**Pull request:** [#352](https://github.com/tjsasakifln/extra-cli/pull/352)  
**Initial extra-cli SHA:** `1ffa079d3e45d06612be0e46c2574fa4b1314e88`  
**Reconciled base SHA:** `2f89fb363abc2bc56568dd0ae11afe554cbcb4c4`  
**Validated feature commits:** `40b1784b159906d58ddfb1bbd11c7ba744837426`, `66b67c5e86f7045428df44cffe54c78b4e3ce7f0`

The exact merged `origin/main` and deployed SHA are recorded in the terminal
deployment comment on PR #352. This document deliberately does not predict a
merge SHA before GitHub creates it.

## Decision

The reachable public-source ladder and all currently eligible reselection
candidates were examined. Only one of 303 eligible unique CNPJs has a complete,
explicitly published named-human chain. Twenty-nine additional valid accounts
would be required. No rule was relaxed, no readiness snapshot was published,
and the currently published Warmbly feed remains unchanged.

## Authority reconciliation

- Published/imported snapshot before and after:
  `a6c32643e67bcf2f9a1f3a8147d700a605de5de8934a078ddefb8308e8a03e5f`.
- Live manifest URL: `https://159.195.18.88:8443/manifest.json`; downloaded
  SHA-256 `341052580fe737bb9a70e289825fa56ecd970fefa6c94080ff1332320db2b06a`.
- Manifest declares generator repo SHA
  `d0ce84741eb12eb115a4bcf73a9fde73d8fd1cfa`, 401,923 leads and 402 chunks.
- The endpoint certificate chains to the private `Warmbly Confenge Feed CA`;
  default system TLS validation fails. The hash above was obtained only as an
  explicit diagnostic with certificate verification disabled and is not a
  public-HTTPS readiness claim.
- Extra VPS began at `.deployed_sha`
  `fffdd3ff5d08702013fe2e2f405b945be2d7ba39`; the target-fit refresh timer was
  active and its last service result was successful.
- Warmbly `origin/main` remained
  `44bdf5f56c40c2b57328d18b5dfb6ceb650cd4a9`. The VPS separately reported
  `.deployed_sha` `81d83429316aa6241cc81b3ac8e761bfc59c2487`, 17 commits behind that main,
  with a pre-existing dirty operational worktree. Warmbly was not modified.

## Before and after

| Measure | Reconciled before | Terminal after |
|---|---:|---:|
| Eligible CNPJs | 303 | 303 examined / 303 unique |
| Literal valid human accounts | 0 | 1 |
| Complete / incomplete account evidence | 0 / 303 | 1 / 302 |
| Current Warmbly selection | 30 | unchanged by this work |
| Names in current selection | 0 / 30 | 0 / 30 |
| Explicitly functional/generic boxes in current selection | 13 by stored labels; 30 non-human in literal audit | 15 by conservative parser; 30 non-human in literal audit |
| Emails found in source run | — | 192 |
| Nominal emails found | — | 3, all belonging to the same eligible account |
| Non-nominal emails rejected | — | 189 |
| Publishable principal recipients | 0 | 1 |
| Missing principals to reach 30 | 30 | 29 |

Current Warmbly database reconciliation found 30 touchpoints in
`NEEDS_REVIEW`, 30/30 with a populated legacy `source_date`, but 0/30 names and
therefore 0/30 literal human-recipient chains. Strict mailbox purposes were
UNKNOWN=15, COMERCIAL=4, GENERIC_CONTACT=10 and FINANCEIRO=1. The source dates
do not cure missing identity/provenance semantics.

No substitution was enacted and target fit was not changed. The one complete
account is outside the original selected 30 and could be a legitimate
replacement only as part of a future complete cohort; the other 29 required
replacements do not exist in the examined evidence.

## Source-ladder evidence

The run recorded 1,813 source attempts with unique hashes and no missing
reason, observation timestamp or terminal state. Terminal distribution:

- `CONTACT_READY`: 1;
- `CONTACT_FOUND_NOT_SENDABLE`: 77;
- `CONTACT_EXHAUSTED`: 173;
- `CONTACT_EXTERNAL_BLOCKER`: 52.

All 303 accounts reached the official-site step. The other five ladder steps
were recorded for all 302 unresolved accounts: administrative/process docs,
PNCP/procurement/transparency, councils/associations, complementary company
pages and registry/QSA corroboration. The 52 external blockers retain explicit
next actions; they were not mislabeled as exhaustion.

The sole complete account was corroborated by its official corporate site,
which publishes its directors, technical functions and nominal company-domain
mailboxes, and by public administrative records tied to the exact CNPJ. The
pipeline selects exactly one deterministic principal and retains the other
nominal observations only as auditable candidates.

## Idempotence and protected evidence

Detailed CNPJ/contact evidence is intentionally outside Git at
`/tmp/confenge-contact-evidence-protected-20260813/` with directories mode
`0700` and files mode `0600`.

- Operational matrix:
  `operational-matrix-final.jsonl`, SHA-256
  `d487c7d43042d789831f439db5ce0cb1d9151fd6f51121b051624814ef3150f6`.
- Sanitized operational summary:
  `operational-summary-final.json`, SHA-256
  `cf1b04a95e0543984c6cd49470b32d1c2c852472ba8e480460641884215218ef`.
- Final idempotence checksum set:
  `authoritative-v8-idempotence-final2.sha256`, SHA-256
  `48b43a436746b09ff6ea6371a7c725a59db46b0fde7910e55e0f3848f83d061f`.

Two complete cache-signed runs over the same 303 inputs produced identical
hashes for candidates, verified/review/rejected/no-contact partitions, attempt
ledger, terminal ledger and both Warmbly projections. Each checkpoint ended
with 303 unique completions, zero failures; the enrollable projection contains
one row and one principal account. No evidence date grew between runs.

## Code and validation

Implemented fail-closed mailbox purpose, named-person evidence, exact CNPJ and
domain ownership, provenance/date separation, source-ladder terminality,
deterministic principal selection, cache invalidation and public-document SSRF
protection. Search snippets and registries cannot be final email proof.

Validation performed:

- migrations: 77 already applied, zero errors;
- focused contact/bridge tests: 156 passed;
- post-review focused regressions: 32 passed;
- Ruff lint and changed-file formatting: passed;
- source contracts: 15/15 passed offline;
- generated-artifact policy and PR-reviewability policy: passed;
- gitleaks: no leak; Bandit: zero high-severity findings;
- CodeRabbit local review: all 17 reported findings evaluated and actionable
  findings fixed; a final recheck was rate-limited after the free allowance;
- GitHub required checks on exact PR heads: see PR #352;
- local full suite: final result recorded in the terminal PR comment;
- golden path: `PARTIAL`, not promoted to success. PNCP resumed successfully,
  PCP hit an existing upsert failure, ComprasGov returned success-zero,
  contracts freshness was stale and one evidence mapping remained unmapped.

## Safety and publication

- New manifest/chunks: not generated or published because the 30-account gate
  failed.
- Warmbly import validation: no new payload exists to import; the strict bridge
  and mapping contract tests passed against the unchanged Warmbly source.
- Draft approvals: zero.
- Approved touchpoints: zero.
- Dispatch sends and sent touchpoints: zero.
- `CONFENGE_REQUIRE_HUMAN_APPROVAL=true`, `CONFENGE_SENDING_PAUSED=true`,
  `CONFENGE_AUTO_SEND_ENABLED=false`; database dispatch control is paused.
- No email or WhatsApp message was sent.

## Required external action

Obtain explicitly published primary-source identity, commercially suitable
role and nominal company-domain email evidence for at least 29 additional
currently eligible CNPJs, prioritizing the 52 accounts whose terminal records
identify inaccessible or failed public documents.
