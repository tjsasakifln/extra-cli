# Session evidence — data reliability (DoD §2.4)

**Story:** ROI-cand-dyn-slice-49022ba84875  
**Cycle:** cyc-2026-07-18T135908Z  
**Branch:** extra-roi/cand-data-reliability  
**Date:** 2026-07-18

## DoD items proven

1. O sistema permite identificar quando um dado não é confiável.
2. O sistema não esconde limitações atrás de scores ou percentuais genéricos.

## Commands

```bash
python3 -m pytest tests/test_data_reliability.py tests/test_claim_language.py -q
# 18 passed

python3 -m scripts.lib.data_reliability --demo --json
# TRUSTED / DEGRADED / UNTRUSTED / UNKNOWN cases

python3 -m scripts.lib.data_reliability --pct 95 --json
# percentage_check.ok=false (sem denominador N) → exit 2
```

## Artifacts

- pytest.log / pytest.exit
- demo.json
- bare-pct.json

## Claims still forbidden

- LOCAL_READY / PRE_VPS / 95% operational coverage
- Bare percentage without N and limitations
