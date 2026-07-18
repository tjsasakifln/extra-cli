# Host monitor session — DoD §23

Story ROI-cand-dyn-slice-eb87220940fd · cycle cyc-2026-07-18T141528Z

## Commands
```bash
python3 -m pytest tests/test_host_monitor.py -q --no-cov
python3 -m scripts.ops.host_monitor --json
```

## Items in scope after QA
- journald retention configured (in-repo; applied_on_host may be false)
- disk / memory / load monitored
- postgres growth / dead tuples / autovacuum when DSN available
- Tiago health command: `python -m scripts.ops.host_monitor`
