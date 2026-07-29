# Quickstart — CONFENGE commercial activation cycle

## Prerequisites

- Isolated Postgres on allowlisted port (5433/5441).
- Authenticated snapshot of `pncp_supplier_contracts` (full history).
- Official CNPJ extract (RFB) or blocked honestly.

## Env

```bash
export CONFENGE_COMMERCIAL_STATE_DSN='postgresql://test:test@127.0.0.1:5433/confenge_commercial_activation'
export CONFENGE_COMMERCIAL_SNAPSHOT='/path/to/snapshot-manifest.json'
export CONFENGE_COMMERCIAL_OUT='artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run'
export CONFENGE_POPULATION_MODE=FULL_POPULATION
export CONFENGE_RUN_MODE=RC
```

## Run

```bash
make confenge-commercial-cycle
# or
python3 -m scripts.ops.confenge_commercial_cycle \
  --dsn "$CONFENGE_COMMERCIAL_STATE_DSN" \
  --snapshot-manifest "$CONFENGE_COMMERCIAL_SNAPSHOT" \
  --out "$CONFENGE_COMMERCIAL_OUT" \
  --population-mode FULL_POPULATION \
  --run-mode RC
```

## Second run (idempotency)

Repeat the same command; expect stable ranking + empty/justified delta.

## Review (human)

Open `TIAGO-REVIEW.md`, `top20-dossiers/`, `top5-outreach-kits/`.  
Do not auto-send messages. Only Tiago fills acceptance.

## Coverage gate

```bash
python3 -c '
from pathlib import Path
import json
from scripts.commercial_leads.canonical_coverage import reconcile_coverage_artifacts
out=Path("artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run")
arts={n: json.loads((out/n).read_text()) for n in ["run-result.json","queue-summary.json"] if (out/n).exists()}
print(reconcile_coverage_artifacts(arts))
'
```
