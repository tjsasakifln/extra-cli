# DOD ID map — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**As of:** 2026-07-23T20:51Z  
**Source:** `.dod/manifest.yaml` after `dod_controller scan`  
**Machine map:** `dod-id-map.json`

## Controller snapshot

| Metric | Value |
|--------|-------|
| total items | 1361 |
| ACCEPTED | 333 |
| OPEN | 1027 |
| next eligible (global) | `DOD-rol-1-definition-of-done-7d2ae13087` (snapshot integrity — **not** campaign) |
| campaign sequential work | started + **VERIFIED** first backfill item (see below) |

## Core campaign OPEN IDs (concrete)

| Line | ID | Text | Accept now? |
|------|-----|------|-------------|
| 108 | `DOD-definition-of-done-extra-1580defee6` | Coleta de contratos dos últimos três anos, no mínimo | candidate after pack |
| 109 | `DOD-definition-of-done-extra-d213dd4037` | Atualização incremental de contratos após o backfill inicial | candidate (VPS timer + success log) |
| 459 | `DOD-rol-1-definition-of-done-c8d4fd6597` | `capability_monitoring_coverage(historical_contracts) >= 95%` | candidate (dual PASS 100%) |
| 514 | `DOD-rol-1-definition-of-done-925c2e6bed` | Contratos possuem backfill integral mínimo de três anos | candidate |
| **752** | **`DOD-rol-1-definition-of-done-c2443d2b03`** | **O backfill cobre no mínimo os últimos três anos** | **VERIFIED** — accept needs **main** checkout |
| 753 | `DOD-rol-1-definition-of-done-00e53389b2` | A data inicial do backfill é registrada | candidate |
| 754 | `DOD-rol-1-definition-of-done-19ab88eea0` | A data final do backfill é registrada | candidate |
| 764 | `DOD-rol-1-definition-of-done-749585a9b5` | O backfill não reinicia janelas concluídas sem necessidade | candidate |
| 791 | `DOD-rol-1-definition-of-done-495f293b30` | A cobertura de contratos >= 95% é provada por ente aplicável | candidate (dual) |
| 1695 | `DOD-rol-3-definition-of-done-e7c852704e` | O sistema permite consultar contratos dos últimos três anos | candidate |

## Do NOT accept until unblock

| Group | Example IDs / lines | Why |
|-------|---------------------|-----|
| Off-site / backup externo | L1748 `DOD-35-gates-consolidados-82d03a68fd` | `BACKUP_STORAGE_BOX_SSH` empty |
| Soak 7d / freshness 7d continuous | L1370–1375, L1752–1754 | only day 1 observation |
| `VPS_OPERATIONAL` / `PROJECT_DONE` | L1742–1769 | aggregate gates; non-claims |
| Full host reboot | L1362 `DOD-rol-2-definition-of-done-be192a40b8` | only PG restart proven |
| open_tenders 95% | dual open_tenders items | out of campaign scope |

## First sequential accept attempt

**Item:** `DOD-rol-1-definition-of-done-c2443d2b03`

| Gate | Result |
|------|--------|
| state VERIFIED | ok |
| evidence pack complete | ok |
| verify green tests | ok (1 cmd + 6 pytest) |
| CI main 5f92211 | ok (run 30042874795) |
| independent review | ok |
| **main branch** | **DENIED** — currently on `campaign/historical-contracts-operational-closure-01` |

**Next for this item only:** checkout/merge evidence to `main` (or worktree on main with same pack) and re-run:

```bash
python3 tools/dod_controller.py accept DOD-rol-1-definition-of-done-c2443d2b03 --update-dod
```

Do **not** use `--allow-non-main` / `--force` for real ACCEPTED.

## Policy

- One item at a time.
- Never batch-accept.
- Never accept offsite/soak/VPS_OPERATIONAL without evidence.
- `result.json` stays **BLOCKED** until offsite + soak complete.
