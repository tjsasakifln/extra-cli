# FINAL-REPORT — CONFENGE National Commercial Reservoir

**As of pack generation (pre/post deploy refresh on host)**

## Terminal intent

**Terminal state:** `EXTERNAL_BLOCKER_REQUIRES_TIAGO` (public-email yield)

`NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY=false` because:

- `EMAIL_SEND_READY=60` < `MIN_OPERATIONAL_RESERVE=900`
- Continuous network enrichment running over CONFIRMED (checkpoint resume; no Top-N cap)
- `process_documents` lake empty — process-admin source ladder not yet producing national yield
- Human review sample ready but blocked until reservoir healthy

### One action for Tiago

Authorize / provision **public process-document harvest** at national scale for TARGET_CONFIRMED
(PNCP anexos + processos administrativos already supported by `scripts/confenge_process_enrichment`),
then re-run continuous enrichment until ESR ≥ 900 **or** accept EXTERNAL_BLOCKER with documented yield.

Human review (when healthy):

```bash
python -m scripts.confenge.human_review \
  --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json \
  --reviewer tiago
```

## Live post-reclass classes

CONFIRMED=8348, PROBABLE=24984,
OUT=92392, INSUFFICIENT=386626
