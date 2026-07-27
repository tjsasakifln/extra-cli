# DOD-rol-1-definition-of-done-7fc5475f5f

**Alias:** CMI-10.1-02

**Criterion:** O sistema não afirma conhecer todos os concorrentes quando a fonte não expõe participantes.

**Weight:** 5

**Campaign:** CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

**Proof:** shipped vertical `scripts/ops/contract_market_intelligence.py` + `tests/test_cmi_contract_market_intelligence.py` + operational_reports repair.

**Commands:**

```bash
python3 -m scripts.ops.contract_market_intelligence audit-unit
REQUIRE_REAL_DB=1 python3 -m pytest tests/test_cmi_contract_market_intelligence.py -q --tb=line -o addopts=''
python3 -m scripts.ops.contract_market_intelligence run --dsn "$LOCAL_DATALAKE_DSN" --out /tmp/cmi-run
```
