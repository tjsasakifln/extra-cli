# Real contract relevance corpus (CONFENGE)

## Sets

| File | Role |
|------|------|
| `development-real-v1.jsonl` | Rule development only |
| `validation-real-v1.jsonl` | Validation during tuning |
| `holdout-real-v1.jsonl` | Frozen holdout — dual human labels required |

## Schema (each line)

```json
{
  "contrato_id": "...",
  "objeto_contrato_original": "...",
  "orgao": "...",
  "uf": "SC",
  "data": "2025-01-15",
  "source_snapshot": "...",
  "stratum": "engenharia_obras_claras",
  "reviewer_1_label": null,
  "reviewer_1_reason": null,
  "reviewer_2_label": null,
  "reviewer_2_reason": null,
  "adjudicated_label": null,
  "adjudicator": null,
  "reviewed_at": null
}
```

Labels: `RELEVANT` | `NOT_RELEVANT` | `REVIEW`

**Agents must never fill human label fields.**

Smoke set `../holdout-v1.jsonl` is `SMOKE_ADVERSARIAL_SET` only — not a performance claim.
