# DOD-rol-1-definition-of-done-7d7b10b055

**Alias:** CMI-11.1-05

**Criterion:** Os quatro campos não são intercambiáveis.

**Weight:** 5

**Campaign:** CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

**Proof:** shipped vertical `scripts/ops/contract_market_intelligence.py` + `tests/test_cmi_contract_market_intelligence.py` + operational_reports repair.

**Commands:**

```bash
python3 -m scripts.ops.contract_market_intelligence audit-unit
REQUIRE_REAL_DB=1 python3 -m pytest tests/test_cmi_contract_market_intelligence.py -q --tb=line -o addopts=''
python3 -m scripts.ops.contract_market_intelligence run --dsn "$LOCAL_DATALAKE_DSN" --out /tmp/cmi-run
```
