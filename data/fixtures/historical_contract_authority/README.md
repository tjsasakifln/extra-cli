# historical_contract_authority fixtures

Cases are built in `scripts/historical_contract_authority/cases.py` so Git does not hold PDFs or bulk JSON.

```bash
python3 -m scripts.historical_contract_authority --mode fixture --as-of 2026-08-17T12:00:00Z
python3 -m scripts.historical_contract_authority --mode fixture --case handoff_ready
```
