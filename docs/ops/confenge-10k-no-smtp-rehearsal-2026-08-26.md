# CONFENGE 10k no-SMTP feed rehearsal — 2026-08-26

Status: **PASS for synthetic feed production**. This is not a live source run, campaign action, provider benchmark, SMTP authorization, or send-rate claim.

The compact machine-readable evidence is
[`confenge-10k-no-smtp-rehearsal-2026-08-26.json`](confenge-10k-no-smtp-rehearsal-2026-08-26.json).
The generated corpora and 436 chunk payloads are intentionally not committed;
they are deterministic derivatives of
[`tests/fixtures/confenge_scale_10k_recipe.json`](../../tests/fixtures/confenge_scale_10k_recipe.json).

## Result

- 10,000 accounts in each authoritative snapshot, split evenly across supplier confirmed, buyer conflict, direct person, role mailbox, generic mailbox, company freemail, shared mailbox conflict, no public email, stale evidence, and suppression.
- 218 chunks per snapshot; 10,000/10,000 membership coverage; 5,000 preferred routes.
- Discovery terminals: 8,000 `RESOLVED`, 1,000 `NOT_FOUND`, 1,000 `SUPPRESSED`.
- Refresh changed exactly 10%: 1,000 additions, 1,000 removals, and 1,000 explicit `SUPPRESSED` deactivations. Omission grants no authority.
- Replays passed 2x and 10x with zero duplicate, orphan, or silent-loss count.
- Producer report duration was 377.292 s. `/usr/bin/time` measured 347.55 s wall and 414,448 KiB maximum RSS.
- Provider send invocations: zero.

## Version bindings

| Snapshot | Run ID | Snapshot hash | Feed identity SHA-256 |
|---|---|---|---|
| v1 | `run-0090f1f29493978f` | `bd3f549dfa5ccebbdedc0523b03a4354eb79aaafab2b2580bf031830b430afa5` | `4e9ad2b9c85aa29253156bd971f4d4ddb285df5c39d61565038918af205b0e90` |
| v2 | `run-5f781a4c0267d13c` | `5d8a2af75996a6e6bfe692797230ae4cf5e8e9c1441227081c240c7c110e241c` | `8c41dd866435e14e49945a16f3a046adfd67d44500bf8bc2d887e461bdeefa58` |

Recipe SHA-256: `ffae0ccc6147834d89ab0442e1e05800fc287185421ce73ae917d98dba54075a`.

## Findings and owner fixes

The first cross-repo canary rejected synthetic company names containing digits
through the normal copy guard (`unsupported_specific_fact`). The generator now
uses deterministic alphabetic labels; no Warmbly validation was bypassed.

The first refresh attempt then exposed an invalid producer state:
`NOT_ACTIONABLE` is not a Warmbly activation state. The producer now emits the
canonical terminal `SUPPRESSED`, and Warmbly preflights the complete
deactivation allowlist before chunk import.

The producer evidence type is the canonical `CONTRACT`; synthetic provenance
remains explicit in the recipe, envelope, and `.example` source URLs instead of
inventing a consumer-only evidence type.

The recipient-attribution policy introduced by #512 initially demoted every
synthetic route because the old corpus declared association without carrying
the witnessed page bytes that prove the exact CNPJ-mailbox tuple. The generator
now uses the production evidence builders for that attestation. Five thousand
routes remain preferred; the shared-mailbox-conflict scenario stays blocked
because its mailbox domain does not match the independently attested company.

## Reproduction

```bash
python -m scripts.ops.confenge_scale_rehearsal \
  --out-dir /tmp/confenge-extra-10k \
  --repeat 10
python -m pytest tests/test_confenge_scale_rehearsal.py -q
```

The run is local and synthetic. It does not call a live target-fit pipeline,
publish a live manifest, mutate Warmbly production, or contact a provider.
