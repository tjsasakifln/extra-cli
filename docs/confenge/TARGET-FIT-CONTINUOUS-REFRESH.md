# CONFENGE Target-Fit Continuous Refresh

**Goal:** `CONFENGE-TARGET-FIT-CONTINUOUS-REFRESH-01`  
**Principle:** `TARGET_FIT = derived state of the datalake`  
**Classifier contract:** `TARGET_CONFIRMED` / `TARGET_PROBABLE_RESEARCH` / `TARGET_OUT_OF_SCOPE`  
(`target_fit_evidence`, `target_fit_reason_codes`, `target_fit_confidence`, `target_fit_version`)

This subsystem is a **consumer** of the datalake. ETL success never depends on target-fit.

Sister work: pilot integrity PR `#211` establishes the triangulation classifier.  
**Do not merge this PR before `#211` if the classifier file is not yet on main** (this branch vendors the same `scripts/confenge_universe/target_fit.py` for integration).

---

## What runs

| Component | Role |
|-----------|------|
| CDC (`refresh`) | Detect CNPJ roots affected by new/changed contracts; enqueue `confenge_target_fit_dirty` |
| Worker | Claim dirty rows (`FOR UPDATE SKIP LOCKED`), recompute, publish current/history/events |
| Reconcile | Daily sweep for missed CDC / version drift / orphans |
| Hook | Optional soft notify after datalake commit (`hook_after_datalake.notify_datalake_committed`) |

## When it runs

| Unit | Schedule |
|------|----------|
| `extra-confenge-target-fit-refresh.timer` | every 30 min (safety net) |
| `extra-confenge-target-fit-worker.service` | long-running (optional) |
| `extra-confenge-target-fit-reconcile.timer` | daily ~05:15 |

Prefer: **datalake refresh completed → enqueue** via hook; timer is a net.

## Architecture

```text
ETL COMMIT → watermark published
     ↓  (async, best-effort)
CDC detects dirty CNPJ roots
     ↓
confenge_target_fit_dirty (durable queue)
     ↓
worker: load contracts → fingerprint → classify → transaction
     ↓
confenge_company_target_fit_current  (canonical)
confenge_company_target_fit_history  (append-only)
confenge_target_fit_events           (transitions)
     ↓  on downgrade
confenge_target_fit_downstream_invalidation
     → suppress activation / block EMAIL_SEND_READY
     (never deletes outreach history / Decision Memory)
```

## Modes

| Mode | Behavior |
|------|----------|
| `SHADOW` (default) | Compute + shadow table + history-of-shadow; **no** eligibility mutation |
| `CANARY` | ACTIVE for `hash(company_key) % 100 < TARGET_FIT_CANARY_PERCENT` |
| `ACTIVE` | Updates canonical current + downstream invalidation on downgrade |
| `AUTO_PAUSE` | Anomaly guard or manual pause; worker no-ops materialization |

```bash
export TARGET_FIT_ASYNC_MODE=SHADOW   # default
python -m scripts.confenge_target_fit set-mode ACTIVE --clear-auto-pause
```

## Commands

```bash
python -m scripts.confenge_target_fit refresh
python -m scripts.confenge_target_fit worker
python -m scripts.confenge_target_fit worker --loop
python -m scripts.confenge_target_fit reconcile
python -m scripts.confenge_target_fit status
python -m scripts.confenge_target_fit metrics
python -m scripts.confenge_target_fit explain --cnpj 12345678000199
python -m scripts.confenge_target_fit requeue --cnpj 12345678000199
python -m scripts.confenge_target_fit set-mode SHADOW
python -m scripts.confenge_target_fit shadow-export
python -m scripts.confenge_target_fit version
```

### Detect lag / health

```bash
python -m scripts.confenge_target_fit status
# STATUS: HEALTHY | DEGRADED | STALE | FAILED
# exit 0 / 1 / 2
```

### Explain a CNPJ

```bash
python -m scripts.confenge_target_fit explain --cnpj ...
# current class, version, evidence, fingerprint, history, dirty, freshness
```

### Force reprocess

```bash
python -m scripts.confenge_target_fit requeue --cnpj ...
python -m scripts.confenge_target_fit worker
```

### Pause / resume

```bash
python -m scripts.confenge_target_fit set-mode AUTO_PAUSE
python -m scripts.confenge_target_fit set-mode SHADOW --clear-auto-pause
# or ACTIVE after shadow validation
```

### Rollback

1. `set-mode AUTO_PAUSE` (stop new materializations)
2. History is append-only — **never delete** `confenge_company_target_fit_history`
3. Restore prior class by requeue after classifier fix, or manual SQL from history row
4. Downstream invalidations remain auditable

## Freshness / SEND_READY

```text
source_watermark_target_fit << datalake watermark
  → TARGET_FIT_STALE → EMAIL_SEND_READY blocked

REFRESH_FAILED / RECOMPUTE_REQUIRED
  → fail-closed (no autorun)
```

Feed fields for `confenge.outreach.v1`:

- `target_fit_class`
- `target_fit_confidence`
- `target_fit_version`
- `target_fit_computed_at`
- `target_fit_source_watermark`
- `target_fit_fresh`
- `target_fit_evidence_ids`

Warmbly must **not** rescore. Fail-closed if not `TARGET_CONFIRMED` or not fresh.

## Epistemic rules (do not regress)

- More contracts alone ≠ `TARGET_CONFIRMED`
- Orgão de obras / high value / name "engenharia" / CNAE alone ≠ confirm
- Supply-only contracts never confirm construction
- Consórcios → `CONSORTIUM_EVIDENCE`, conservative
- Downgrades are first-class (not monotonic promotion)
- Filial contract → recompute **CNPJ root** group

## Fingerprint

Semantic fields only (objects, values, status, vigência, CNAE, name, classifier version).  
Ingestion timestamps excluded so clock noise does not force recompute.

## Priority / backpressure

```text
1. activation / send queue (when known)
2. TARGET_CONFIRMED recent
3. new contract events
4. probable
5. out-of-scope
+ fairness for low priority
```

Env:

```text
TARGET_FIT_WORKERS=1
TARGET_FIT_BATCH_SIZE=50
TARGET_FIT_LOCK_TTL_SECONDS=300
TARGET_FIT_MAX_WATERMARK_LAG_SECONDS=7200
TARGET_FIT_CANARY_PERCENT=5
```

## SLO

Target: **95% of companies affected by a datalake cycle reclassified within 30 minutes** of watermark publish (`TARGET_FIT_RECLASS_SLO_MINUTES=30`).  
Lag above `TARGET_FIT_MAX_WATERMARK_LAG_SECONDS` → `STALE` health.

## Logs / storage

- systemd journal: `journalctl -u extra-confenge-target-fit-worker -u extra-confenge-target-fit-refresh`
- DB tables: `confenge_target_fit_*`, `confenge_company_target_fit_*`
- Runtime artifacts: `artifacts/confenge/target-fit/` (not daily bulk git commits)

## What NOT to do

- Do **not** run full national rebuild for every PNCP page
- Do **not** couple ETL transaction to target-fit success
- Do **not** delete outreach / Decision Memory on downgrade
- Do **not** promote to `EMAIL_SEND_READY` from target-fit alone
- Do **not** enable `ACTIVE` before shadow replay looks clean
- Do **not** claim `GO_FOR_CONTROLLED_PILOT` from this workstream

## Verdict of this workstream

```text
TARGET_FIT_ASYNC_READY | TARGET_FIT_ASYNC_NOT_READY
```

Pilot GO/NO-GO remains owned by the integrity recovery track.

## Migrations

```bash
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
# applies 071_confenge_target_fit_continuous_refresh.sql
```

## Install (VPS)

```bash
sudo cp deploy/systemd/extra-confenge-target-fit-*.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now extra-confenge-target-fit-refresh.timer
sudo systemctl enable --now extra-confenge-target-fit-reconcile.timer
# optional long-running worker:
# sudo systemctl enable --now extra-confenge-target-fit-worker.service
```
