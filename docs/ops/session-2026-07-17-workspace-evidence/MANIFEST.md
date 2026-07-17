# Workspace daily evidence pack — 2026-07-17

**Story:** `ROI-cand-workspace-daily-evidence-pack`  
**Candidate:** `cand-workspace-daily-evidence-pack`  
**Cycle:** `cyc-2026-07-17T223227Z`  
**Branch:** `extra-roi/cand-workspace-daily-evidence-pack`  
**Agent:** @dev (Dex)  
**Generated (UTC):** 2026-07-17T22:37:36Z → 2026-07-17T22:37:54Z  
**Mirror:** `output/workspace-evidence-20260717/`

---

## Purpose

Reproducible evidence that the workspace cotidiano CLI
(`python3 -m scripts.workspace`) executes the commands used in daily ops:

- `today`
- `opportunities`
- `dossier`
- `coverage`

No READY seal promotion. No VPS work. No claim of 95% operational coverage.

---

## Environment honesty

| Fact | Value |
|------|-------|
| Local PostgreSQL | **UNAVAILABLE** — `127.0.0.1:5433` connection timeout |
| Mode observed | Offline / session-artifact fallback (`DEGRADED` where applicable) |
| Live canary / VPS | **Not run** (out of scope; still blocked by PRE_VPS_FINAL_READY) |
| LOCAL_RESILIENCE_READY | **NOT claimed** (remains NOT_READY) |
| PRE_VPS_FINAL_READY | **NOT claimed** (remains NOT_READY) |
| Operational coverage ≥95% | **NOT claimed** (commercial signal ~10.61%; see coverage payload) |

---

## Command inventory (exit codes)

Source of truth: `exit_codes.tsv`

| # | Command | Exit | Started UTC | Ended UTC | Verdict |
|---|---------|------|-------------|-----------|---------|
| 01 | `python3 -m scripts.workspace --help` | **0** | 22:37:36Z | 22:37:36Z | PASS |
| 02 | `python3 -m scripts.workspace today --help` | **0** | 22:37:36Z | 22:37:36Z | PASS |
| 03 | `python3 -m scripts.workspace today --json` | **0** | 22:37:36Z | 22:37:40Z | PASS (degraded: `pg_available=false`) |
| 04 | `python3 -m scripts.workspace opportunities --help` | **0** | 22:37:40Z | 22:37:40Z | PASS |
| 05 | `python3 -m scripts.workspace opportunities --status open --limit 5 --json` | **0** | 22:37:40Z | 22:37:43Z | PASS (status=`DEGRADED`, count=5 from session fallback) |
| 06 | `python3 -m scripts.workspace coverage --help` | **0** | 22:37:43Z | 22:37:43Z | PASS |
| 07 | `python3 -m scripts.workspace coverage --json` | **0** | 22:37:43Z | 22:37:47Z | PASS (metrics from session/DB-less path; **not** 95%) |
| 08 | `python3 -m scripts.workspace dossier --help` | **0** | 22:37:47Z | 22:37:47Z | PASS |
| 09 | `python3 -m scripts.workspace dossier offline-no-id-probe --json` | **1** | 22:37:47Z | 22:37:51Z | EXPECTED FAIL — `status=NOT_FOUND` for bogus id (documented, not silent) |
| 10 | `python3 -m scripts.workspace dossier 8504275 --json` | **0** | 22:37:51Z | 22:37:54Z | PASS offline (`status=OK` from session artifacts; `pg_error` present) |

**Squad ranker honesty regression (related fix on this branch):**

| Command | Exit | Notes |
|---------|------|-------|
| `pytest squads/extra-dod-roi/tests/test_squad_smoke.py -v` | **0** | 10 passed (~60s); includes `_story_is_done` / completed E3 skip test |

---

## Key output snippets (honest)

### today (`03`)

- `pg_available`: **false**
- `pg_error`: PostgreSQL timeout on `127.0.0.1:5433`
- sections present: 7 (offline queue construction)
- Full payload: `03-workspace-today-json.payload.json` / `.txt`

### opportunities (`05`)

```json
{
  "status": "DEGRADED",
  "reason": "PostgreSQL unavailable: ... timeout expired",
  "count": 5
}
```

First item id used for dossier: **`8504275`** (session fallback, not live PG).

### coverage (`07`)

- CLI exit 0 with multi-metric payload
- Commercial signal example: `commercial_opportunity_any` **116/1093 ≈ 10.61%**
- Disclaimer in payload: commercial metric does **not** replace operational multi-dimensional coverage contract
- **Forbidden claim not made:** operational coverage ≥ 95%

### dossier invalid id (`09`)

- Exit **1**, JSON `status=NOT_FOUND` — non-silent failure path documented

### dossier real session id (`10`)

- Exit **0**, `status=OK` for id `8504275` via offline session artifacts
- `pg_error` still reported (PG unavailable)

---

## Artifact index

| Path | Role |
|------|------|
| `MANIFEST.md` | This file |
| `exit_codes.tsv` | Machine-readable exit codes |
| `0N-*.txt` | Full stdout/stderr capture per command (`.log` copies local-only; gitignores `*.log`) |
| `0N-*.payload.json` | Parsed JSON bodies where applicable |
| `../../output/workspace-evidence-20260717/*` | Mirror of pack for ops consumers |

Reproduce:

```bash
python3 -m scripts.workspace --help
python3 -m scripts.workspace today --json
python3 -m scripts.workspace opportunities --status open --limit 5 --json
python3 -m scripts.workspace coverage --json
python3 -m scripts.workspace dossier 8504275 --json   # or any known session id
python3 -m scripts.workspace dossier offline-no-id-probe --json  # expect exit 1
```

---

## Claims authorized by this pack

- Workspace cotidiano commands **executed** with **recorded exit codes**
- Offline/degraded behavior is **observable and non-silent**
- Ranker skips completed E3/post-merge candidates when AIOX Done+po_closed evidence exists (`_story_is_done`)

## Claims still forbidden

- LOCAL_RESILIENCE_READY
- PRE_VPS_FINAL_READY
- VPS provisionada/operacional
- Cobertura operacional 95%
- Freshness live garantida por fixtures
- Stories Done sem QA/PO independentes

---

*Evidence only. Independent @qa must review before PO close.*
