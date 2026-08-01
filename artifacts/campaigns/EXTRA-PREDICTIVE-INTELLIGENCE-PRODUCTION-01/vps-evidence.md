# VPS evidence

## Host of record

- SSH alias `ec-prod` reachable.
- PostgreSQL database `pncp_datalake`: **4,479,442** rows in `pncp_supplier_contracts`.
- Organs ~14k; suppliers ~522k.

## What was NOT done (honest)

- Shadow timer was **not** left enabled as production soak evidence.
- VPS system Python lacks `numpy`/`sklearn` (not in project `requirements.txt`).
- No fake prospective soak was recorded.

## What was done

- Production sample exported for offline walk-forward backtests.
- Systemd unit **templates** shipped in-repo:
  - `deploy/systemd/extra-predictive-shadow.service`
  - `deploy/systemd/extra-predictive-shadow.timer`

## Operator enable (later)

```bash
sudo cp deploy/systemd/extra-predictive-shadow.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now extra-predictive-shadow.timer
# also install ML deps in the app venv before relying on train/backtest on-box
```
