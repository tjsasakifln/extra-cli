# COMMERCIAL_AUTHORITY/1.0

Additive, machine-readable contract over the last fully proven
`confenge.outreach.v1` publication. It does **not** replace
`PNCP_CONTRACT_FRESHNESS/1.0`.

**Scope of this contract:** last-good aging / admission vs already-bound
transport. It does **not** decide which plane governs a commercial cycle.
That is `CONFENGE_COMMERCIAL_PLANE_OPERATING_AUTHORITY/1.0`
(`docs/contracts/confenge-commercial-plane/v1/operating-authority.json`,
ADR-039 Accepted/Effective).

**SUPERSEDED row:** “Live PNCP not `FRESH` → refuse new facts” no longer
governs commercial publication. New publication is fail-closed on Data Lake
integrity, membership and the source-health *envelope*; live PNCP `FRESH`
neither authorizes nor blocks it.

## Two planes

| Plane | Contract | Question |
|---|---|---|
| Source operational health | `PNCP_CONTRACT_FRESHNESS/1.0` | Is the crawler/maintenance plane healthy? Default SLO: 6 h target / 24 h hard. Statuses `FRESH\|DEGRADED\|STALE\|UNKNOWN`. Never fabricated to permit outbound. |
| Commercial authority | `COMMERCIAL_AUTHORITY/1.0` | May the last publication-ready population still sustain new admissions and/or already-bound transport? |

A failed next crawl, lock-busy, incomplete window, same-snapshot replay or
process restart **degrades source health**. It does **not** promote a new feed,
does **not** mutate `current`, and does **not** rewrite a previously proven
population into "never valid".

## Policy `COMMERCIAL_AUTHORITY_POLICY/1.0`

Inclusive upper bounds on the age of `validated_at` (last-good `generated_at`):

| Age | State | New admission | Already-bound first-touch transport |
|---|---|---|---|
| `0 ≤ age ≤ 24 h` | `CURRENT` | allowed | allowed |
| `24 h < age ≤ 72 h` | `DEGRADED` | allowed only when that lead's evidence bundle is still valid and there is no drift | allowed |
| `72 h < age ≤ 7 d` | `FROZEN_FOR_NEW_ADMISSION` | forbidden | allowed if every other gate still passes |
| `age > 7 d` | `EXPIRED` | forbidden | forbidden |
| missing/mismatched binding | `UNKNOWN` | forbidden | forbidden |

Suppression, opt-out, DNC, hard bounce, party-role conflict, deactivation,
recipient/evidence expiry and explicit revocation **always win** over grace.
Email/recipient TTLs are not lengthened by this policy.

## Binding

Authority is bound to all of:

- `basis_source_run_id`
- `basis_snapshot_hash`
- `basis_membership_hash`
- `basis_publication_semantic_hash`
- `producer_identity` (when present)

A membership, source-run, snapshot or semantic-hash mismatch yields `UNKNOWN`
and both flags false. Never reuse authorization across a divergent basis.

## Warmbly compatibility

Existing field meanings stay fail-closed:

- `authoritative_source_freshness.status` remains PNCP source health.
- `FRESH` is **not** redefined as commercial `CURRENT`.
- Unknown new fields must be ignored by an older consumer; they must not
  silently authorize transport.

New consumers should read `commercial_authority` for admission/transport
eligibility of the last-good snapshot, and `source_operational_health` for
incident/SLO.

## New promotion vs last-good

| Event | New promotion | Last-good `current` | Commercial authority |
|---|---|---|---|
| Candidate not publication-ready | refuse | unchanged | recomputed from last-good |
| Live PNCP not `FRESH` | refuse new facts | unchanged | last-good policy |
| Same snapshot + same semantics | skip (`SAME_SNAPSHOT_NOT_FRESHNESS`) | unchanged | last-good policy |
| Integrity of last-good holds, source stale | n/a | unchanged | policy on last-good age |
| Root deactivated | explicit revocation in feed | promoted only with the delta | that root cannot ride grace |

Terminal extra-cli state for this contract is `READY_FOR_FINAL_CONVERGENCE`.
It does **not** emit `GO_FOR_CONTROLLED_EMAIL_PILOT`.
