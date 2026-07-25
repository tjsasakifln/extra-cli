# Handoff — Sector Recall Operational Validation (next PR)

**Do not execute this campaign inside PR #135.**

PR #135 delivers only a **disabled technical foundation**:

- `foundation_pr_status=READY_TO_MERGE_AS_DISABLED_FOUNDATION` (merge candidate into #131 branch)
- `operational_pipeline_status=BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS`
- defaults offline: `operational.enabled=false`, `llm.provider=fake`, `retrieval.semantic.provider=lexical_fuzzy_hash`
- real operational gold corpus remains empty (`records: []`)
- no RC v3, no #131 accept/merge, no VPS/prod/soak

---

## Next branch

```text
campaign/sector-recall-operational-validation-01
```

## Future base

Branch of **PR #131** (`campaign/client-ready-recurring-consulting-cycle-01`) **after** it has received the merge of PR #135.

Do **not** base on main while #131 remains open with `CHANGES_REQUESTED_RECALL_ASSURANCE`.

---

## Scope (operational validation only — next PR)

1. **Real public corpus capture** — PNCP / public sources only; no invented objects; no Extra-private data.
2. **Provenance + dual human labeling** — independent dual review, adjudications, annotation artifacts.
3. **Real embedding benchmark** — SentenceTransformer / OpenAI-compatible (not `lexical_fuzzy_hash` as semantic claim).
4. **Real LLM operational validation** — stratified ≥200 samples, human review; not FakeLLM.
5. **REVIEW queue analysis** — capacity only when universe is non-empty and evaluable.
6. **Shadow replay on real windows** — multi-window; promotion only with Level C evidence.
7. **Decision on RC v3** — only after operational gates can honestly clear; never from synthetic Level B.

---

## Explicit non-goals for the next PR (until evidence)

- Claiming recall/precision from empty or synthetic corpus
- Filling quotas with LLM-as-human labels
- Auto-accepting #131
- Generating RC v3 without READY operational evidence
- Production / VPS / soak activation of the hybrid challenger while `operational.enabled=false` is the product default

---

## Entry points (after branch exists)

```bash
# Ensure real corpus scaffold then capture real rows outside this foundation PR
python -m scripts.ops.campaign_hybrid_sector_recall \
  --corpus tests/fixtures/hybrid_sector/real_operational_corpus.json \
  --split locked \
  --out artifacts/campaigns/SECTOR-RECALL-OPERATIONAL-VALIDATION-01

# Paid paths only with explicit flags + operational.enabled=true in a non-default config
```

---

## Exit criteria (next PR — not #135)

Operational pipeline may leave `BLOCKED_INSUFFICIENT_REAL_GOLD_CORPUS` only when Level C gold quotas, dual review, real embeddings, real LLM validation, review capacity, and full suite are honestly green. Only then consider `READY_FOR_RECALL_ASSURANCE_REVIEW` and any RC v3 discussion.
