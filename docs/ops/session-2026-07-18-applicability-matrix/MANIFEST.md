# Evidence §7.2 applicability matrix (first 8)

Story ROI-cand-dyn-slice-59661d935e79
Module scripts/coverage/applicability_matrix.py

Items: editais/contratos decision, capability variance, justification, validated_at, decision_source, multi-source combination, min combination explicit.

```bash
python3 -m pytest tests/test_applicability_matrix.py -q --no-cov -o addopts=
python3 -m scripts.coverage.applicability_matrix --limit-entities 30 --out docs/ops/session-2026-07-18-applicability-matrix/out --json
```
Gate zero_necessary_unknowns=true on sample.
