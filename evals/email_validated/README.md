# EMAIL_VALIDATED gold set and promotion policy

Versioned benchmark for the question:

> este email está associado à pessoa certa, na empresa certa, com evidência suficiente para entrar na lane de revisão humana?

A gold label is a **benchmark verdict**. It is not send authorization and it is not `HUMAN_REVIEW_APPROVED`.

## Versions

| Artifact | Version |
|---|---|
| Policy | `dui.email-validated-promotion.v1` |
| Gold set | `email-validated-gold.v1` |

## Layout

```
evals/email_validated/
  policy/email-validated-promotion.v1.json
  policy/email-validated-promotion.v0.json   # rejected precursor for policy-diff only
  gold/gold-set.v1.jsonl
  gold/gold-set.v1.meta.json
  gold/splits.json
  fixtures/stop-the-line-wrong-person.jsonl
  fixtures/import-sample.json
```

`development` cases were used while writing the policy. `holdout` is frozen and disjoint by `case_id`. Do not tune rules on holdout.

## CLI (offline)

```bash
python3 -m scripts.decision_unit_intelligence.email_validated import \
  --in evals/email_validated/fixtures/import-sample.json \
  --out /tmp/imported.jsonl

python3 -m scripts.decision_unit_intelligence.email_validated evaluate \
  --gold evals/email_validated/gold/gold-set.v1.jsonl

python3 -m scripts.decision_unit_intelligence.email_validated policy-diff \
  --left evals/email_validated/policy/email-validated-promotion.v0.json \
  --right evals/email_validated/policy/email-validated-promotion.v1.json

python3 -m scripts.decision_unit_intelligence.email_validated regression \
  --gold evals/email_validated/gold/gold-set.v1.jsonl
```

CI runs only these offline fixtures. No live web.

## Skew (required)

Track A / PR #392 reported 0 honest `EMAIL_VALIDATED` after rejecting false positives. This set therefore has:

- `VALIDATED_DIRECT` = 0 (declared, not invented)
- `INFERRED_HIGH` = 0 (no domain with two observed person mailboxes)

Precision of `EMAIL_VALIDATED` is the primary metric. Coverage is secondary. Recall is unmeasurable while gold positives are zero.
