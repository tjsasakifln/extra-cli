# Crawler metrics — DoD §23

Story ROI-cand-dyn-slice-268ae33837e7 · cyc-2026-07-18T142435Z

## Commands
```bash
python3 -m pytest tests/test_crawler_monitor.py -q --no-cov
python3 -m scripts.ops.crawler_monitor --json
python3 -m scripts.ops.crawler_monitor --json --seed-demo
```

## Monitored
duration, success_rate, volume, http_403, http_429, http_5xx, timeouts

Empty history → overall=unknown (honest).
