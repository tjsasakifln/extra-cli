# Corporate email patterns (`email_patterns`)

Isolated engine: **OBSERVED same-domain person emails → supported pattern → INFERRED candidate**.

A pattern is not an observation. MX is not a mailbox. SMTP accept is not identity.
Catch-all lowers evidentiary value. One example cannot yield high certainty.

## Model

| Layer | States | Epistemic class |
|---|---|---|
| Pattern | `PATTERN_OBSERVED`, `PATTERN_STRONG`, `PATTERN_AMBIGUOUS` | `INFERRED` or `CORROBORATED` — never `OBSERVED` |
| Candidate | `INFERRED_PATTERN_EMAIL`, `INFERRED_PATTERN_MX_OK`, `INFERRED_PATTERN_CATCH_ALL`, `INFERRED_PATTERN_REJECTED` | always `INFERRED` |
| Grade | `INFERRED_HIGH` (strong + MX, not catch-all), else `INFERRED_UNVERIFIED` | still `INFERRED` |

Supported shapes, only when actually observed: `first.last`, `firstlast`, `first_initial+last`, `first+last_initial`, `last.first`, `first`, `first.compoundlast`, and **aliases that were observed** (not invented).

Provenance on every pattern: supporting emails, people, source URLs, `observed_at`, domain, exclusions, conflicts.

## Invariants

- Ingest drops non-`OBSERVED`, generic/role/brand, third-party professional, freemail, and wrong-domain rows.
- Candidates only for already known/corroborated people who do not already own an observed mailbox.
- No blind walk of unused `KNOWN_PATTERNS`. Per-person budget (default 2).
- Brazilian folding: accents, particles (`da/de/do/das/dos/e`), compound surnames, titles, abbreviations.
- Homonyms are not merged across accounts.
- `assert_pattern_not_promoted_to_observed` refuses pattern → `OBSERVED`.
- Warmbly / `confenge.outreach.v1`: every `INFERRED_PATTERN_*` is `CANDIDATE_UNVERIFIED`, `email_safe=false`, `auto_send=false`. Not `EMAIL_VALIDATED`.

## CLI

```bash
python3 -m scripts.decision_unit_intelligence.email_patterns run --input in.json --out out.json
python3 -m scripts.decision_unit_intelligence.email_patterns fixtures
python3 -m scripts.decision_unit_intelligence.email_patterns canary \
  --observations scripts/decision_unit_intelligence/data/track_a_30.observations.json \
  --out /tmp/email-patterns-canary
```

## Canary (Track A 30)

The first 30 of the 100-account commercial cohort publishes almost only generic/role mail.
Incremental reachable rate from this path is **0** until named OBSERVED mailboxes exist.
That is fail-closed, not a skip.

Recommendation: **conditional GO** — ship the engine, do not send, human-audit the 30-candidate pack
before any operator treats `INFERRED_HIGH` as a working address.
