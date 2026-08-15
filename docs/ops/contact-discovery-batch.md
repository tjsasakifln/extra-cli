# Contact discovery — durable batch

Additive job bus around shipped `run_account`. Does not change
`web_discovery.py` planner/crawler/heuristics.

Job type: `CONFENGE_CONTACT_DISCOVERY`

## Operator commands

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"

python3 -m scripts.decision_unit_intelligence batch enqueue \
  --cohort COHORT_ID --cnpjs 11222333000181,44555666000177 \
  --search-backend off --service reajuste_14133

python3 -m scripts.decision_unit_intelligence batch worker --loop --max-jobs 100
python3 -m scripts.decision_unit_intelligence batch progress --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch inspect --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch failures --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch retry --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch resume --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch cancel --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch publish --cohort COHORT_ID
python3 -m scripts.decision_unit_intelligence batch kill-switch --enable --reason pause --actor ops
```

Outputs live under `output/contact-discovery/` (gitignored).
A snapshot is approved only when the denominator closes, every account is
terminal or a nominal blocker, hashes reconcile, and there are no duplicates.

429 / timeout / budget / source-block keep their reason codes. They never
become “sem contato encontrado”.
