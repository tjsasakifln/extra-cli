# CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

Vertical: concorrentes, vencedores e semântica de valores (DOD §10.1/§10.2/§11.1).

## Status

**BUNDLE_ACCEPTED** — 47 itens promovidos.

## Reproduce

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
export REQUIRE_REAL_DB=1
python3 -m scripts.ops.contract_market_intelligence run --dsn "$LOCAL_DATALAKE_DSN" \
  --out artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package
python3 -m scripts.ops.cmi_item_proofs --all
python3 -m pytest tests/test_cmi_contract_market_intelligence.py -q -o addopts=''
```
