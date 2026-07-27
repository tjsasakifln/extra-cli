# DOD-rol-1-definition-of-done-bcbbd65023

**Alias:** CMI-11.1-20

**Criterion:** O sistema não chama percentil de contratos globais de “preço real praticado” sem base técnica.

**Weight:** 5

**Campaign:** CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

**Proof:** shipped vertical `scripts/ops/contract_market_intelligence.py` + `tests/test_cmi_contract_market_intelligence.py` + operational_reports repair.

**Commands:**

```bash
python3 -m scripts.ops.contract_market_intelligence audit-unit
REQUIRE_REAL_DB=1 python3 -m pytest tests/test_cmi_contract_market_intelligence.py -q --tb=line -o addopts=''
python3 -m scripts.ops.contract_market_intelligence run --dsn "$LOCAL_DATALAKE_DSN" --out /tmp/cmi-run
```
