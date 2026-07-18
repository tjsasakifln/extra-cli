# Session — structured logging DoD §23

**Story:** ROI-cand-dyn-slice-43acf5cce633  
**Cycle:** cyc-2026-07-18T140817Z  
**Branch:** extra-roi/cand-structured-logs

## Items to prove (after independent QA)

- Logs estruturados estão ativos
- timestamp, nível, serviço, fonte, run_id
- Logs não expõem segredos

## Commands

```bash
python3 -m pytest tests/test_structured_logging.py -q --no-cov  # 5 passed
python3 -m scripts.lib.structured_logging --self-check          # ok=true
```

OUT of this slice: journald retention, host metrics, crawler metrics, alerts (later).
