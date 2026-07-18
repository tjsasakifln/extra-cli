# Ops gate monitor — DoD §23

Story ROI-cand-dyn-slice-3a89d28fa518 · cyc-2026-07-18T143244Z

## Commands
```bash
python3 -m pytest tests/test_ops_gate_monitor.py -q --no-cov
python3 -m scripts.ops.ops_gate_monitor --json
```

## Monitored (capability)
- freshness_by_source
- coverage_by_capability
- last_valid_backup
- migration_failures
- delayed_timers

Do not claim 95% coverage or VPS timer health from repo presence alone.
