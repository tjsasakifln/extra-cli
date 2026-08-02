See canonical runbook: `docs/ops/decision-outcome-memory-runbook.md`

Summary:

1. Apply migrations including `068_decision_outcome_memory.sql`
2. Set `LOCAL_DATALAKE_DSN`
3. Use `python -m scripts.decision_memory --client-id …`
4. Extra review uses PG when DSN present; `--artifact-only` for non-canonical
5. Corrections = supersession events, never UPDATE/DELETE
6. Import default dry-run; `--apply` for persistence
