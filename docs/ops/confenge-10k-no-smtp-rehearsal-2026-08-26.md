# CONFENGE 10k no-SMTP feed rehearsal — 2026-08-26

Status: **PASS for synthetic feed production**. This is not a live source run, campaign action, provider benchmark, SMTP authorization, or send-rate claim.

The compact machine-readable evidence is
[`confenge-10k-no-smtp-rehearsal-2026-08-26.json`](confenge-10k-no-smtp-rehearsal-2026-08-26.json).
The generated corpora and 314 chunk payloads are intentionally not committed;
they are deterministic derivatives of
[`tests/fixtures/confenge_scale_10k_recipe.json`](../../tests/fixtures/confenge_scale_10k_recipe.json).

## Result

- 10,000 accounts in each authoritative snapshot, split evenly across supplier confirmed, buyer conflict, direct person, role mailbox, generic mailbox, company freemail, shared mailbox conflict, no public email, stale evidence, and suppression.
- 157 chunks per snapshot; 10,000/10,000 membership coverage; 6,000 preferred routes.
- Discovery terminals: 8,000 `RESOLVED`, 1,000 `NOT_FOUND`, 1,000 `SUPPRESSED`.
- Refresh changed exactly 10%: 1,000 additions, 1,000 removals, and 1,000 explicit `SUPPRESSED` deactivations. Omission grants no authority.
- Replays passed 2x and 10x with zero duplicate, orphan, or silent-loss count.
- Producer report duration was 289.097 s. `/usr/bin/time` measured 267.94 s wall and 310,452 KiB maximum RSS.
- Provider send invocations: zero.

## Version bindings

| Snapshot | Run ID | Snapshot hash | Feed identity SHA-256 |
|---|---|---|---|
| v1 | `run-863b0abcbaa0e637` | `b8c9fb3cdad7c006e4d0ef634eea607cc01c370fda352ba68dbae3041a262a19` | `2cbdf370508439610ac2ff04670b60a9cd985c8f35f6297db7245d40e86f28a2` |
| v2 | `run-f48073c9f1d66736` | `06bc3e5d73960f633866c2115a46a146455f13437e0c2da713e3d57fad002e6a` | `c4f3efba9397030608fdd0800282d5cc9cf84e52dc01507c58744c873a213f5d` |

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

## Reproduction

```bash
python -m scripts.ops.confenge_scale_rehearsal \
  --out-dir /tmp/confenge-extra-10k \
  --repeat 10
python -m pytest tests/test_confenge_scale_rehearsal.py -q
```

The run is local and synthetic. It does not call a live target-fit pipeline,
publish a live manifest, mutate Warmbly production, or contact a provider.
