# Alert pipeline — DoD §23

Story ROI-cand-dyn-slice-70c8a181a45d · cyc-2026-07-18T144059Z

## Commands
```bash
python3 -m pytest tests/test_alert_pipeline.py -q --no-cov
python3 -m scripts.ops.alert_pipeline --self-check
python3 -m scripts.ops.alert_pipeline --status
```

Also fixes duplicate DoD line "Último backup válido é monitorado" if still open.
