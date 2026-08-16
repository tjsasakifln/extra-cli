# `publication-value-score/1.0`

Machine-readable twin: [`publication-value-score-v1.json`](publication-value-score-v1.json)

Weighted geometric mean of the ten named components, using only **KNOWN**
values. Weights are data. Absence is never stored as `0`.

| Component | Weight | Role |
|-----------|--------|------|
| `commercial_relevance` | 0.09 | editorial size of the instrument |
| `demand_fit` | 0.10 | thematic fit to public-contract technical analysis |
| `insight_or_anomaly_strength` | 0.22 | verifiable technical signal |
| `documentary_richness` | 0.10 | known official fields + sourced documents |
| `comparability` | 0.07 | versioned peer sample only; else UNKNOWN |
| `freshness` | 0.09 | observation age vs payload `as_of` |
| `defensibility` | 0.10 | sourced evidence on fired insight detectors |
| `citation_potential` | 0.07 | official source + stable identity + dated refs |
| `editorial_maintenance_cost` | 0.08 | inverted maintenance burden |
| `reputational_sensitivity` | 0.08 | inverted reputational exposure; never an accusation |

```
score = exp( Σ w_i · ln(clamp(c_i, 0.05, 1.0)) / Σ w_i )
        for i where status(c_i) == KNOWN
```

Atypical is not an accusation. A potential adjustment is not a right.
