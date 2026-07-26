# Onda Zero — Ownership Manifest

**Campaign:** `EDITAL-RELEVANCE-RECALL-95-01`  
**Date:** 2026-07-26  
**Canonical base:** `main` @ `tjsasakifln/extra-cli`  
**Authority:** `DOD.md`

## Exact DOD item

§8.4 — **“Recall de editais relevantes >= 95% na amostra-ouro.”**

Only this acceptance state may change. No other DOD line is claimed.

## Real dependencies

| ID | Dependency | Role |
|----|------------|------|
| P1 | Public real gold corpus with dual independent labels + adjudication | Denominator / labels |
| P2 | Fail-closed evaluator running canonical classifier | Gate |

Subordinate: sampling plan, freeze manifests, development-only repair, adversarial tests, CI on exact SHA, independent review, serial DOD/handoff.

## Canonical flow (existing)

```
public inventory (PNCP API / SC Compras public API snapshot / CIGA DOM public zip)
  → dual independent labels (RELEVANT|IRRELEVANT|UNDECIDABLE) + adjudication
  → split development | locked_holdout (freeze hashes before classifier edit)
  → scripts/ops/sector_classifier.py + config/client_profiles/extra.yaml
  → scripts/coverage/edital_relevance_recall.py evaluate (fail-closed)
  → recall = TP / adjudicated RELEVANT  (UNDECIDABLE out of denominator)
```

Not used as recall proxy: DB presence, `success_zero`, capture identity/URL/hash, operational queues, system class for selection.

## Development vs holdout

| Set | Purpose | Access |
|-----|---------|--------|
| `evals/edital_relevance/pilot_36.jsonl` | Schema + dual-label validation | All squads |
| `evals/edital_relevance/development.jsonl` | Diagnosis, rules, adversarial tests | Repair may inspect |
| `evals/edital_relevance/locked_holdout.jsonl` + manifest | Sole final proof | Sealed pre-repair; Repair never opens until final automated run |

## Exclusive file ownership (≤4 tracks)

| Track | Branch (logical) | Exclusive paths |
|-------|------------------|-----------------|
| WT1 Corpus | `campaign/edital-relevance-corpus-01` | `evals/edital_relevance/**`, `docs/ops/campaigns/EDITAL-RELEVANCE-RECALL-95-01/corpus-*`, `scripts/campaigns/edital_relevance/**` |
| WT2 Evaluator | `campaign/edital-relevance-evaluator-01` (integrated on same PR branch) | `scripts/coverage/edital_relevance_recall.py`, `tests/coverage/test_edital_relevance_recall.py`, fixtures, Makefile target |
| WT3 Repair (conditional) | after frozen baseline | `scripts/ops/sector_classifier.py`, `config/client_profiles/extra.yaml`, `tests/test_sector_classifier_adversarial.py` only if misses prove need |
| WT4 QA/Accept | serial at end | `docs/ops/campaigns/EDITAL-RELEVANCE-RECALL-95-01/review/**`, small evidence manifests, campaign handoff |

**Serial-only (no parallel ownership):** `DOD.md`, ADR index/ADRs, canonical handoffs.

## Test commands per track

```bash
# Corpus integrity (schema/labels)
python3 -m scripts.coverage.edital_relevance_recall validate-corpus \
  --corpus evals/edital_relevance/pilot_36.jsonl

# Evaluator unit gates
python3 -m pytest tests/coverage/test_edital_relevance_recall.py -q

# Baseline / final (holdout only for accept)
python3 -m scripts.coverage.edital_relevance_recall evaluate \
  --corpus evals/edital_relevance/locked_holdout.jsonl \
  --manifest evals/edital_relevance/locked_holdout-manifest.json \
  --profile config/client_profiles/extra.yaml \
  --output /tmp/edital-relevance-recall-result.json

# Classifier + consumer
python3 -m pytest tests/test_sector_classifier_adversarial.py -q
python3 -m pytest tests/test_live_consulting_pack.py -q -k sector 2>/dev/null || true

# Full suite (CI SHA)
python3 -m scripts.ops.run_full_suite
```

## Risks

| Risk | Mitigation |
|------|------------|
| Leakage development↔holdout | Evaluator fails on shared official_id; freeze before repair |
| Overfitting / memorization | No ID/URL/org rules; adversarial tests from development misses only |
| Selection by system class | Provenance field; forbidden_proxy checks |
| Dual-label bias | Two independent criteria docs; adjudicate all disagreements |
| File collision | Exclusive ownership; stop wave on collision |
| Claim capture recall as relevance | Explicit metric name `relevance_recall`; separate from capture |

## Integration order

1. Onda zero (this doc)  
2. Pilot 36 + baseline zero-change  
3. Evaluator + unit tests  
4. Expand/freeze development + locked_holdout  
5. Baseline on development  
6. Conditional repair + adversarial tests  
7. Single final holdout evaluate  
8. Full suite + CI green on exact SHA  
9. Independent review  
10. Serial DOD §8.4 + handoff  
11. **STOP**

## Do-not-touch (unless proven necessary + explicit notice)

`scripts/coverage/dual_capability_coverage.py`, `config/source_applicability.yaml`, `db/migrations/**`, `deploy/**`, `scripts/commercial_leads/**`, `scripts/budget_audit/**`, `scripts/bid_readiness/**`, `scripts/ops/hybrid_sector/**` wholesale, CONFENGE-COMMERCIAL-READY-01 artifacts, VPS/timers/backup, PR#133, unrelated Makefile targets, dashboards, CTO Autopilot.

## Stop criterion

- **SUCCESS:** §8.4 proven on locked_holdout ≥95%, independent review, CI green exact SHA, on `main`, DOD+handoff only that line; stop.  
- **BLOCKED:** cannot obtain authorized public corpus / dual labels / strata — record blocker; stop.  
- **FAIL:** holdout <95% — record FN; do not retune on same sealed holdout; stop.  

No continuation into general backlog.
