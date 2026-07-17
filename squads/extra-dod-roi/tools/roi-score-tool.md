# roi-score-tool

Deterministic ROI scoring tool for extra-dod-roi.

## Entry

```bash
python scripts/score_roi.py --weights data/roi-weights.yaml --input candidates.json
```

## Purpose

Score UNLOCKED candidates with versioned weights. Used by `*rank-next` and planner tasks.
Does not mutate product code.

## Inputs

- candidates JSON array with `value` and `cost` dimension maps (0–5)
- optional weights path (default `data/roi-weights.yaml`)

## Outputs

- ranked candidates with `roi`, `value_sum`, `cost_sum`, detail breakdowns
