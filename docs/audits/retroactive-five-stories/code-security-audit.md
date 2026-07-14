# Code Security Audit — Retroactive 5 Stories (1.1–1.5)

> Commit `d2ff075` | 2026-07-13 | Epic: Technical Debt Elimination
> Auditor: Claude Code

---

## Executive Summary

**181 files changed** (31,728 insertions, 5,891 deletions). Audit focused on Python source files across 5 stories (1.1–1.5). Below are findings classified by severity and origin.

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 6 |
| MEDIUM | 10 |
| LOW | 12 |
| INFO | 9 |

---

## CRITICAL

### C-01: Reconciliation calls undeployed DB function (Story 1.4)

**File:** `scripts/opportunity_intel/reconciliation.py:299`
**Code:**
```python
cursor.execute(
    "SELECT fn_record_snapshot_membership(%s, %s, %s::jsonb)",
    (run_id, source, json.dumps(payload, default=str)),
)
```
**Problem:** The function `fn_record_snapshot_membership` is called but no corresponding migration creates it. Migration `031_source_snapshot_reconciliation.sql` exists, but there is no `fn_record_snapshot_membership` in the `KNOWN_FUNCTIONS` set of `audit_sql_references.py`, and no migration file defines it. Without this function, `reconcile()` and `record_memberships()` silently fail with a psycopg2 error caught at the caller level (`pncp_audit.py:236` catches `Exception` and logs it).

**Risk:** The entire reconciliation algorithm (Story 1.4) is a no-op at runtime. All 7 rules of the reconciliation algorithm are inoperative. `memberships_recorded` always returns 0, inactivation never fires, reactivation never fires.

**Fix:** Either implement `fn_record_snapshot_membership` as a migration, or verify the function exists in the schema BEFORE this commit was created.

**Severity:** CRITICAL | **Origin:** INTRODUCED-BY-STORY (Story 1.4)

---

## HIGH

### H-01: Bare default DSN still in legacy db/datalake-sc-200km.py (SEC-03 carryover)

**Files:** `scripts/datalake-sc-200km.py` and 8+ other scripts still define:
```python
dsn = os.getenv("LOCAL_DATALAKE_DSN",
    "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres")
```
**Problem:** `config/settings.py` was fixed (SEC-03) — the default password `smartlic_local` was removed. But multiple standalone scripts (`datalake-sc-200km.py`, `backfill.py`, etc.) still have the password in their local `DEFAULT_DSN` fallback. These are not imports from `config.settings` — they define their own DSN. Any user running these scripts outside the `config.settings` path is exposed.

**Files affected (partial list):**
- `scripts/datalake-sc-200km.py`
- `scripts/opportunity_intel/backfill.py:27`
- `scripts/opportunity_intel/manifest.py:34`
- `scripts/opportunity_intel/cli.py:43`
- `scripts/consulting_readiness.py:171`
- `scripts/universe_tools.py:49`
- `scripts/crawl/dom_sc_crawler.py`
- `scripts/crawl/contracts_crawler.py`
- `scripts/crawl/pcp_crawler.py`
- `scripts/crawl/sc_compras_crawler.py`
- `scripts/crawl/tce_sc_crawler.py`
- `scripts/crawl/doe_sc_crawler.py`
- `scripts/crawl/ciga_ckan_crawler.py`
- `scripts/crawl/compras_gov_crawler.py`
- `scripts/crawl/mides_bigquery_crawler.py`
- `scripts/crawl/transparencia_crawler.py`
- `scripts/reports/panorama.py:28`

**Severity:** HIGH | **Origin:** LEGACY-PREEXISTING (partially fixed by SEC-03, 17+ hardcoded copies remain)

### H-02: `sys.path.insert(0, ...)` in 50+ files — fragile import chain

**Files:** 50+ scripts use `sys.path.insert(0, ...)` before importing project modules.

**Examples:**
- `scripts/crawl/bids_crawler.py:63-67` — inserts 2 paths
- `scripts/intel_pipeline.py:41` — inserts scripts/
- `scripts/reports/panorama.py:24` — inserts project root
- `scripts/crawl/monitor.py:37` — inserts project root
- `scripts/coverage/run_matching.py:16` — inserts project root

**Problem:** This is the classic Python antipattern for import resolution. It means:
1. These scripts cannot be imported as modules without side effects (the `sys.path` mutation happens at import time)
2. If two different resolutions conflict (e.g., a venv vs project root), silent import shadowing occurs
3. `PYTHONPATH` or package installation with `pip install -e .` would render all of these unnecessary

**TD-001** and **TD-019** are referenced in comments acknowledging this as technical debt that was NOT resolved in this epic — only annotated.

**Severity:** HIGH | **Origin:** LEGACY-PREEXISTING (acknowledged as TD-001, TD-019, not fixed)

### H-03: `_project_entity_evidence` writes rows, then `conn.commit()` — but outer path may skip commit

**File:** `scripts/crawl/monitor.py:894-907`
**Problem:** After `_project_entity_evidence` inserts evidence rows, only `entity_evidence_stats` path calls `conn.commit()`. If `source != "pncp"` or `not entities`, the function is not called. However, the `_record_evidence` function (which also issues INSERT) has no explicit commit following it — it relies on the global `conn.commit()` at line 907. If the PNCP path is skipped, the `_record_evidence` INSERTS are committed only by the `_finish_ingestion_run` commit (line 864), which happens earlier. This creates a window where `_record_evidence` rows may not be flushed if an exception occurs between the two.

**Severity:** HIGH | **Origin:** EXPOSED-BY-STORY (Story 1.1/1.2 schema changes added new INSERT paths without ensuring commit coverage)

### H-04: `consulting_readiness.py` defines `TargetEntity` and `TargetUniverse` as dead wrappers

**File:** `scripts/consulting_readiness.py:60-88`
**Code:**
```python
class TargetEntity(CanonicalEntity):
    """Backward-compatible alias (Story 1.3)."""

class TargetUniverse:
    """Backward-compatible wrapper around CanonicalUniverse (Story 1.3)."""
    def __init__(self, entities=None, radius_km=None):
        ...
    def __getattr__(self, name):
        ...
```
**Problem:** These classes are never referenced anywhere in `consulting_readiness.py` itself. No function or method instantiates `TargetEntity` or `TargetUniverse`. The comment says "Backward-compatible alias (Story 1.3)" and "exposed for tests", but the `compute_readiness()` function directly uses `CanonicalUniverse`, not `TargetUniverse`. This is dead code that was supposed to be removed during refactoring, not left as maintenance burden.

Additionally, line 105-109 defines `load_target_universe()` which returns a `CanonicalUniverse` instance — but line 54-57 also re-imports `CanonicalUniverse` from `scripts.lib.universe`, creating a double import.

**Severity:** HIGH | **Origin:** INTRODUCED-BY-STORY (Story 1.3 — incomplete refactoring left dead wrappers)

### H-05: `run_pncp_open_monitoring` swallows reconciliation errors silently

**File:** `scripts/opportunity_intel/pncp_audit.py:235-241`
**Code:**
```python
except Exception as recon_err:
    _logger.error(
        "Snapshot reconciliation failed for run %d: %s",
        db_run_id, recon_err, exc_info=True,
    )
```
**Problem:** If reconciliation fails (which it does, see C-01 — the function doesn't exist), the error is logged but the parent function `run_pncp_open_monitoring` continues normally and returns a `PncpRunOutcome` as if nothing went wrong. The caller (`radar.py:218`) checks `source_outcome is None` and `source_outcome.scope_complete`, but does not check whether reconciliation succeeded. This means the entire snapshot reconciliation pipeline (Story 1.4) is silently non-functional.

**Severity:** HIGH | **Origin:** INTRODUCED-BY-STORY (Story 1.4)

### H-06: Password in DEFAULT_DSN fallback for `_get_dsn` in `consulting_readiness.py`

**File:** `scripts/consulting_readiness.py:171-173`
**Code:**
```python
def _get_dsn() -> str:
    return os.getenv(
        "LOCAL_DATALAKE_DSN",
        "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres",
    )
```
**Problem:** Despite `config/settings.py` being fixed to remove the password from the default (SEC-03), `consulting_readiness.py` has its OWN copy of the DSN fallback that still contains `smartlic_local`. This function is called by `_get_conn()` at line 176, which is the main connection path for the readiness gate.

**Severity:** HIGH | **Origin:** LEGACY-PREEXISTING (missed by SEC-03 fix)

---

## MEDIUM

### M-01: `intel-validate.py` and `intel_validate.py` deleted — other files may still reference them

**Files:** Both deleted in this commit. Check if any pipeline or cronjob references them.
**Problem:** The diff shows these files (18 lines each) were deleted entirely. If anything imports from them or references them in a pipeline configuration, the pipeline will break.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY

### M-02: `consulting_readiness.py` duplicate `import math` / `EARTH_RADIUS_KM`

**File:** `scripts/consulting_readiness.py:90-92`
**Code:**
```python
import math

EARTH_RADIUS_KM = 6371.0  # noqa: N816
```
**Problem:** `import math` is done at module level at line 90, but line 97 defines `R = 6371.0` inside `haversine_km()` — this shadows the module-level `EARTH_RADIUS_KM` which is itself never used. Two constants for the same value.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY (Story 1.3)

### M-03: `_build_pncp_opportunities` returns ALL records even when not selected

**File:** `scripts/crawl/monitor.py:470-502`
**Problem:** The loop at line 398 builds an `opportunities` list that appends for EVERY record unconditionally (line 471). The `selected` boolean is computed at lines 450-468 and the stat `stats["selected_count"]` is incremented only when selected, but the record is ALWAYS appended to `opportunities`. This means `_persist_engineering_opportunities` writes records that were supposed to be filtered out. The `engineering_only` and `within_200km_only` filters only affect the `selected_count` stat, not the persisted data.

**Severity:** MEDIUM | **Origin:** EXPOSED-BY-STORY (Story 1.5 — coverage model)

### M-04: `consulta/v1` vs `consulta/v3` — PNCP base URL mismatch

**File:** `scripts/opportunity_intel/pncp_crawler.py:29`
```python
PNCP_CONSULTA_BASE = "https://pncp.gov.br/api/consulta/v1"
```
**File:** `config/settings.py:55`
```python
PNCP_BASE = os.getenv("PNCP_BASE", "https://pncp.gov.br/api/consulta/v3")
```
**Problem:** The Opportunity Intelligence crawler uses v1 of the PNCP consulta API while the main system uses v3. This is intentional per comments ("API reference: swagger-ui v1"), but if v1 is ever deprecated, the entire radar/opportunity pipeline breaks silently. No version compatibility check exists.

**Severity:** MEDIUM | **Origin:** LEGACY-PREEXISTING (documented but not addressed)

### M-05: `coverage/blockers.py` — `entity` field can shadow Python built-in

**File:** `scripts/coverage/blockers.py:38`
**Code:**
```python
entity: str = "ALL"
```
**Problem:** The `CoverageBlocker` dataclass has a field named `entity`, which shadows the built-in `entity` concept in the module. While Python allows this, it's confusing and can cause subtle bugs if someone uses `from scripts.coverage.blockers import entity` or uses `entity` as a local variable name inside the module.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY (Story 1.5)

### M-06: `audit_sql_references.py` — `KNOWN_COLUMNS` for `sc_public_entities` is incomplete

**File:** `scripts/schema/audit_sql_references.py:524`
**Problem:** The `KNOWN_COLUMNS` set for `sc_public_entities` does NOT include `raio_200km` (missing), but `raio_200km` is referenced in dozens of SQL queries across the codebase. When the audit tool runs, `raio_200km` will appear as an "unknown column" for every query that references it. This means the audit produces false positives for a column that is clearly present in the schema.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY (Story 1.2 — incomplete schema audit tooling)

### M-07: `freshness_gate.py` — `_status_from_snapshot` ignores timezone

**File:** `scripts/freshness_gate.py:128-145`
**Problem:** `_status_from_snapshot` computes `age_hours = (now - last_success_at).total_seconds() / 3600`. If `last_success_at` is timezone-aware (which it should be, coming from PostgreSQL `timestamptz`), but `now` is `datetime.now(UTC)` (also aware), the comparison works. However, `now` is passed as `now or datetime.now(UTC)`, and if the caller passes a naive datetime, the subtraction produces incorrect results. No guard exists.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY (Story 1.5 — freshness gate)

### M-08: `radar.py` — `_load_presence_ids` filters `crawl_batch_id <> 'test_batch'` in SQL but cannot handle NULLs

**File:** `scripts/opportunity_intel/radar.py:436`
**Code:**
```sql
AND COALESCE(crawl_batch_id, '') <> 'test_batch'
```
**Problem:** The `COALESCE` handles NULLs correctly, so this is technically fine. But the same pattern appears in `manifest.py:112` using `oi.source != 'test_batch'`, which would NOT exclude NULL `crawl_batch_id` rows because NULL comparison with `!=` returns NULL (not TRUE) in SQL. The `manifest.py` query includes `WHERE is_active = TRUE AND source != 'test_batch'` — this would fail to exclude records where `source` is NULL, but `source` is likely `NOT NULL` in the schema.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY (Story 1.4)

### M-09: `crawler_base.py` — `_save_checkpoint` uses `records_fetched` = page_records not cumulative

**File:** `scripts/opportunity_intel/crawler_base.py:446`
**Code:**
```python
records_fetched = opportunity_checkpoints.records_fetched + EXCLUDED.records_fetched,
```
**Problem:** The ON CONFLICT DO UPDATE adds `EXCLUDED.records_fetched` to the existing `records_fetched` — but `EXCLUDED.records_fetched` at line 455 is `page_records`, which is the count for just this page. The INSERT statement also sets `records_fetched = page_records` for the initial insert. This means the first insert has `records_fetched = page_records`, and subsequent updates accumulate: `old + page_records`. This is correct for cumulative tracking — BUT only if the checkpoint is updated after every page. If a crawl restarts from a checkpoint, it will double-count pages that were previously processed.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY (Story 1.4)

### M-10: `reconciliation.py` — `DEFAULT_DSN` import path used vs own DSN

**File:** `scripts/opportunity_intel/reconciliation.py:82`
**Code:**
```python
def __init__(self, dsn: str):
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise ValueError("Reconciliation requires a PostgreSQL DSN")
```
**Problem:** Unlike most other files, `reconciliation.py` correctly requires the DSN as a parameter. However, the callers (`pncp_audit.py:220`) call it as `SourceSnapshotReconciler(dsn)`, and the `dsn` passed comes from the `run_pncp_open_monitoring` parameter. There is no validation that the DSN is valid before calling `_get_conn()`. The ValueError is only raised if DSN doesn't start with `postgresql://`, but it doesn't test connectivity.

**Severity:** MEDIUM | **Origin:** INTRODUCED-BY-STORY (Story 1.4)

---

## LOW

### L-01: Monitor.py comment references removed function `match_entity` — no import present

**File:** `scripts/crawl/monitor.py:86-87`
**Code:**
```python
# NOTE: match_entity is imported from matching/entity_matcher (TD-027 unified)
```
**Problem:** This is just a comment; the actual `_match_entities_cascade` import is on line 174-176:
```python
from scripts.matching.entity_matcher import (
    match_entities_cascade as _match_entities_cascade,
)
```
But there's no import of `match_entity` (singular). The comment on line 86 references a function that is neither imported nor used in this file. The inline `_match_entity()` was removed in this commit; the comment should have been removed too.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.3 — incomplete cleanup)

### L-02: `radar.py` — `presence_ids` resolved only for first match, ambiguity dropped

**File:** `scripts/opportunity_intel/radar.py:441-444`
**Problem:** `_load_presence_ids` calls `universe.resolve_opportunity()` and discards the `method` return value (uses `_`). If the resolution is ambiguous, the entity is silently not counted. Since `resolve_opportunity` returns `(None, "ambiguous_duplicate_cnpj_root")` for ambiguous cases, this is correct behavior, but it means the data_presence metric systematically undercounts for entities sharing CNPJ roots.

**Severity:** LOW | **Origin:** LEGACY-PREEXISTING

### L-03: `radar.py` — `_load_and_score_candidates` dedup by `numero_controle_pncp` may lose records

**File:** `scripts/opportunity_intel/radar.py:469-474`
**Problem:** Deduplication uses `key = str(row.get("numero_controle_pncp") or row.get("source_id") or "")`. If both are empty, `key` is `""`, which means ALL records without keys would map to the same `""` key, keeping only the last one seen. For sources that don't have `numero_controle_pncp`, this is a silent data loss.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.4/1.5)

### L-04: `intel_pipeline.py` — `CONTROL_VARIABLE` not imported but used

**File:** `scripts/intel_pipeline.py:165`
**Code:**
```python
version = __import__("lib.constants", fromlist=["INTEL_VERSION"]).INTEL_VERSION
```
**Problem:** This uses `__import__()` instead of a normal import. While functional, it's fragile — if the import order changes or `lib.constants` has side effects at import time, this breaks. A normal `from lib.constants import INTEL_VERSION` would be cleaner and type-safe.

**Severity:** LOW | **Origin:** LEGACY-PREEXISTING

### L-05: `freshness_gate.py` — unclosed cursor in `evaluate_source`

**File:** `scripts/freshness_gate.py:196-228`
**Problem:** `_run_snapshot` (line 159) opens a cursor via `_query_one_dict`, and `_data_snapshot` (line 189) does the same. The `with conn.cursor()` context manager ensures closure for those. However, `_table_columns` at line 102 uses a raw `conn.cursor()` (not context manager), and the cursor is never explicitly closed — only garbage collected.

**Severity:** LOW | **Origin:** LEGACY-PREEXISTING

### L-06: `bids_crawler.py` — `_has_more` uses `getattr` on possibly unset attribute

**File:** `scripts/crawl/bids_crawler.py:161-162`
**Code:**
```python
def _has_more(self) -> bool:
    resp = getattr(self, "_last_response", {})
    return bool(resp.get("temProximaPagina") or int(resp.get("paginasRestantes", 0)) > 0)
```
**Problem:** `_has_more()` is called in `run()` at line 243, AFTER `fetch_page()` which always sets `self._last_response`. But if `run()` had an early return (e.g., empty first page), the code structure prevents calling `_has_more()` before a `fetch_page()`. However, someone subclassing `BidsCrawler` or calling `_has_more()` out of order would hit this fragility. The `getattr` masks this instead of failing loudly.

**Severity:** LOW | **Origin:** LEGACY-PREEXISTING

### L-07: `pncp_crawler.py` — `PncpPublicationCrawler.build_url` uses manual string concat instead of `urlencode`

**File:** `scripts/opportunity_intel/pncp_crawler.py:138`
**Code:**
```python
qs = "&".join(f"{k}={v}" for k, v in params.items())
```
**Problem:** `PncpOpportunityCrawler.build_url()` uses `urllib.parse.urlencode(params)` which properly encodes special characters. `PncpPublicationCrawler.build_url()` uses manual string concatenation which does NOT URL-encode values. If `date_from` or `date_to` contain characters needing encoding (they shouldn't for ISO dates, but inconsistently), the URL would be malformed.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.4)

### L-08: `radar.py` — `_spreadsheet_cell` only neutralizes formula prefixes on strings

**File:** `scripts/opportunity_intel/radar.py:838-845`
**Code:**
```python
def _spreadsheet_cell(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    clean = ILLEGAL_SPREADSHEET_CHARS.sub("", value)
    if clean.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return "'" + clean
    return clean
```
**Problem:** What if `clean` becomes empty after illegal chars are removed (e.g., a cell with only null bytes)? Then `clean.startswith(...)` returns False (empty string doesn't start with `=`, `+`, `-`, `@`), and an empty string is written to the CSV, which is semantically different from "no value". Edge case, but worth noting.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.4/1.5)

### L-09: `coverage/manifest.py` — `not_applicable` counter never populated

**File:** `scripts/coverage/manifest.py:42`
**Problem:** In `CoverageManifestEntry`, the field `not_applicable: int = 0` is declared but in the `build_manifest_from_db` method (lines 238-253), the mapping from DB columns only sets 9 of the 10 breakdown fields — `not_applicable` is never read from the DB row. The DB column might not exist in the view, but the dataclass field is never populated from the query results.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.5)

### L-10: `audit_sql_references.py` — `KNOWN_COLUMNS` for `entity_coverage` missing `within_200km`, `entity_id`

**File:** `scripts/schema/audit_sql_references.py:545-556`
**Problem:** `entity_coverage` has columns `entity_id`, `within_200km`, `matched_bids` but MANY queries use `within_200km` and `entity_id` — they'll be flagged as unknown.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.2)

### L-11: `reconciliation.py` — `records` parameter is `list[dict]` but items lack `numero_controle_pncp`

**File:** `scripts/opportunity_intel/reconciliation.py:287-289`
**Code:**
```python
source_record_id = rec.get("numero_controle_pncp") or rec.get("source_id") or rec.get("id") or ""
canonical_key = rec.get("content_hash") or rec.get("numero_controle_pncp") or ""
```
**Problem:** If `records` are passed from `pncp_audit.py:224` as `list(deduplicated)`, each record comes from the PNCP API raw format with field names like `numeroControlePNCP` (camelCase), NOT `numero_controle_pncp` (snake_case). The lookup for `numero_controle_pncp` will fail, falling through to `source_id` → `id` → empty string. The `content_hash` lookup will also fail for raw API records. This means membership recording is broken in the primary reconcile path.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.4 — field name mismatch between raw and normalized record formats)

### L-12: `suspicious_duplicate` in universe.py — counter increment on each occurrence

**File:** `scripts/lib/universe.py:209`
**Code:**
```python
identity_occurrences[identity_key] += 1
```
**Problem:** `identity_occurrences` is a `Counter`, but `identity_counts` is also a `Counter` (line 201). Both are incremented by `_parse_seed_row`'s returned `identity_key`. `identity_counts` counts how many rows produce a given identity key (duplicate detection). `identity_occurrences` is used to disambiguate entity IDs: `entity_id = f"extra-{hashlib.sha256(stable_input.encode('utf-8')).hexdigest()[:20]}"`. The `entity_id` generation uses `stable_input = f"{identity_key}|occurrence={identity_occurrences[identity_key]}"`, but the occurrence counter increments per-iteration of the `parsed_rows` loop at `identity_occurrences[identity_key] += 1` (line 209), which happens BEFORE the entity_id generation at line 216. So the first occurrence gets occurrence=1, the second gets occurrence=2. This is correct, but fragile — if the ordering of `parsed_rows` changes between runs, entity IDs change.

**Severity:** LOW | **Origin:** INTRODUCED-BY-STORY (Story 1.3)

---

## INFO

### I-01: `config/settings.py` — SMTP password stored as env var, no encryption

**File:** `config/settings.py:148`
```python
NOTIFY_SMTP_PASSWORD = os.getenv("NOTIFY_SMTP_PASSWORD", "")
```
**Finding:** The SMTP password is loaded from an environment variable but never encrypted at rest. If someone gains access to the environment (e.g., via a leaked `.env` file), they have the SMTP password. This is standard practice for SMTP credentials, but worth documenting.

**Severity:** INFO | **Origin:** LEGACY-PREEXISTING

### I-02: `consulting_readiness.py` — `load_target_universe` returns wrong type

**File:** `scripts/consulting_readiness.py:105-109`
**Code:**
```python
def load_target_universe(path=None, radius_km=None):
    from scripts.lib.universe import CanonicalUniverse
    return CanonicalUniverse(path or DEFAULT_SEED, radius_km or DEFAULT_RADIUS_KM)
```
**Finding:** This function claims to be a "Backward-compatible wrapper around CanonicalUniverse (Story 1.3)", but `CanonicalUniverse(path, radius_km)` — `CanonicalUniverse` is a dataclass, NOT a loader function. Its constructor doesn't load a seed file; it just creates an empty `CanonicalUniverse` object. The comment indicates this was supposed to call `load_canonical_universe()` but actually calls the dataclass constructor, producing an empty universe. This function is never called anywhere in the codebase (dead code).

**Severity:** INFO | **Origin:** INTRODUCED-BY-STORY (Story 1.3)

### I-03: `pncp_audit.py` — `_finish_run` uses `metadata || %s::jsonb` which preserves old scopes

**File:** `scripts/opportunity_intel/pncp_audit.py:392`
**Code:**
```python
metadata = metadata || %s::jsonb
```
**Finding:** `_finish_run` appends scopes metadata via `metadata || %s::jsonb`, which means every re-run with the same `db_run_id` accumulates scopes. For the initial insert (line 363), metadata only has `{"mode": mode, "modalidades": list(...)}`. After `_finish_run`, scopes are appended. If `_finish_run` is called twice, scopes are duplicated in the metadata JSONB. This is unlikely in practice but violates idempotency.

**Severity:** INFO | **Origin:** INTRODUCED-BY-STORY (Story 1.4)

### I-04: `universe_tools.py` — `"generated_at"` missing from `None` check in `list_snapshots`

**File:** `scripts/universe_tools.py:293`
**Problem:** The `list_snapshots` function displays snapshots with the `generated_at` column. But the `get_latest_snapshot` function returns `"created_at"`, and `list_snapshots` also queries `"created_at"`. The column name in the output (line 478) headers says `"Created"`. These are the same column semantically, but the inconsistent naming between `created_at` (DB/snapshot) and `generated_at` (dashboard/radar) could cause confusion.

**Severity:** INFO | **Origin:** INTRODUCED-BY-STORY (Story 1.3)

### I-05: `coverage/states.py` — CoverageState `RUNNING` never used in monitor.py

**File:** `scripts/coverage/states.py:37-44`
**Finding:** The `RUNNING` state is defined in the CoverageState enum but the actual `crawl_source` function in `monitor.py` never transitions evidence to `running`. It goes directly from `pending` to `success_with_data`/`success_zero`/`partial`/`error`/`blocked`. The `RUNNING` state exists for theoretical completeness but is dead logic.

**Severity:** INFO | **Origin:** INTRODUCED-BY-STORY (Story 1.5)

### I-06: `scripts/crawl/bids_crawler.py` — Entire file is DEPRECATED

**File:** `scripts/crawl/bids_crawler.py:1-25`
**Finding:** The deprecation notice says "DEPRECATED since 2026-07-11" and provides a rollback plan. The file was modified in this commit to add `sys.path.insert` patterns (TD-001), even though it's deprecated. This adds maintenance burden to code that should be removed, not enhanced.

**Severity:** INFO | **Origin:** LEGACY-PREEXISTING

### I-07: `scripts/lib/terminal.py` — No `__all__` defined

**File:** `scripts/lib/terminal.py`
**Finding:** This module exports 12 public functions but has no `__all__` list. Tools like `from terminal import *` would import all names, including `_IS_TTY` and `_tty_wrap` which are internal.

**Severity:** INFO | **Origin:** INTRODUCED-BY-STORY (Story 1.1)

### I-08: `scripts/crawl/monitor.py` — 1510 lines, monolithic orchestration

**File:** `scripts/crawl/monitor.py:1510` lines
**Finding:** The `crawl_source` function at line 612 is 341 lines long, handling credential validation, crawling, transforming, upserting, entity matching, opportunity building, evidence projection, and error handling in a single function. This makes testing individual paths difficult. Multiple commit messages reference this, but it wasn't restructured in this epic.

**Severity:** INFO | **Origin:** LEGACY-PREEXISTING

### I-09: `audit_sql_references.py` — `KNOWN_FUNCTIONS` missing 15+ DB functions

**File:** `scripts/schema/audit_sql_references.py:75-87`
**Finding:** Only 11 functions are listed as known. Migration files reference many more: `fn_record_snapshot_membership`, `upsert_opportunity_intel`, `upsert_qw01_pncp_opportunities`, `fn_capture_coverage_snapshot`, etc. This means the SQL audit tool produces many false positives for function references. The audit's own usefulness is undermined by incomplete schema knowledge.

**Severity:** INFO | **Origin:** INTRODUCED-BY-STORY (Story 1.2)

---

## Quantitative Summary

### By Origin

| Origin | Count |
|--------|-------|
| LEGACY-PREEXISTING | 14 |
| INTRODUCED-BY-STORY | 16 |
| EXPOSED-BY-STORY | 2 |
| UNRELATED | 0 |
| UNKNOWN | 0 |

### By File

| File | Issues |
|------|--------|
| `scripts/opportunity_intel/reconciliation.py` | C-01, M-10, L-11 |
| `scripts/opportunity_intel/pncp_audit.py` | H-05, I-03 |
| `scripts/opportunity_intel/radar.py` | L-02, L-03, L-08 |
| `scripts/opportunity_intel/pncp_crawler.py` | M-04, L-07 |
| `scripts/crawl/monitor.py` | H-03, M-03, L-01, I-08 |
| `scripts/crawl/bids_crawler.py` | L-06, I-06 |
| `scripts/consulting_readiness.py` | H-04, H-06, M-02, I-02 |
| `scripts/lib/universe.py` | L-12 |
| `scripts/lib/terminal.py` | I-07 |
| `scripts/coverage/blockers.py` | M-05 |
| `scripts/coverage/manifest.py` | L-09 |
| `scripts/coverage/states.py` | I-05 |
| `scripts/schema/audit_sql_references.py` | M-06, L-10, I-09 |
| `scripts/opportunity_intel/crawler_base.py` | M-09 |
| `scripts/freshness_gate.py` | M-07, L-05 |
| `scripts/opportunity_intel/manifest.py` | M-08 |
| `scripts/reports/panorama.py` | L-04 (via H-02 pattern) |
| `config/settings.py` | H-01 (partial fix), I-01 |
| `scripts/universe_tools.py` | H-01, I-04 |
| _50+ scripts_ | H-02 (systemic) |

### Key Security Gaps

1. **CRITICAL: Reconciliation is a no-op** (C-01) — the `fn_record_snapshot_membership` database function called by `reconciliation.py` doesn't exist in any migration. The entire Story 1.4 feature (snapshot reconciliation with 7 rules) produces no effect at runtime. Errors are caught and logged silently.

2. **Password in 17+ default DSNs** (H-01, H-06) — `config/settings.py` was fixed (SEC-03), but 17+ standalone scripts retain `smartlic_local` in their own `DEFAULT_DSN` fallback, typically when `LOCAL_DATALAKE_DSN` is unset.

3. **50+ `sys.path.insert(0, ...)` patterns** (H-02) — acknowledged as TD-001 and TD-019 but none were fixed in this epic. This isn't a vulnerability in itself, but prevents module import safety and can cause silent import shadowing.

4. **Field name mismatch in reconciliation** (L-11) — `records` from `pncp_audit.py` use camelCase API field names like `numeroControlePNCP`, but `reconciliation.py` looks for snake_case `numero_controle_pncp`. All membership lookups fail silently.

---

## Cross-Story Findings

### Story 1.1 (Fix Critical Security)
- SEC-01: SQL f-string fix in `monitor.py`: **CONFIRMED FIXED**. The old `_match_entities_cascade` (which used f-strings for SQL identifiers) was removed entirely and replaced with `psycopg2.sql.SQL` + `Identifier()`. The `_upsert_raw_records` function now uses `SQL("SELECT * FROM {} (%s)").format(Identifier(upsert_fn))`. No remaining SQL f-string patterns were found in the monitored code paths.
- SEC-03: **PARTIALLY FIXED**. `config/settings.py` no longer has the password in the default, but 17+ scripts still do (see H-01, H-06).
- ANSI codes: **FIXED**. `intel_pipeline.py` now uses `scripts.lib.terminal` instead of raw ANSI codes. Verified in diff.

### Story 1.2 (Canonical Views / Unify Schema)
- SQL audit tool created (`audit_sql_references.py`) — useful but incomplete (M-06, L-10, I-09).
- `KNOWN_SCHEMA_OBJECTS` has 30 tables/views/functions but the migration set has 40+ distinct objects.

### Story 1.3 (Universe Authority)
- `CanonicalUniverse` dataclass implemented with proper immutable entities and resolution logic.
- ~11 files still reference `raio_200km` DB column directly (notably `consulting_readiness.py` has 10+ SQL queries using it, `contract_intel/cli.py` has 12+)
- Dead backward-compatible wrappers left in `consulting_readiness.py` (H-04, I-02)
- `load_target_universe()` function is named misleadingly (returns empty dataclass, not loaded universe)

### Story 1.4 (Reconcile Open Tenders)
- **CRITICAL FLAW**: The entire reconciliation algorithm is non-functional (C-01, L-11).
- Reconciliation errors are silently caught and logged as warnings (H-05).
- Field name mismatch between raw API records and expected field names breaks membership recording (L-11).

### Story 1.5 (Coverage Model)
- State machine is well-designed but `RUNNING` state is dead code (I-05).
- `CoverageManifestEntry` has `not_applicable` field that's never populated from DB (L-09).
- Source registry expanded with proper capability tracking — no structural issues found.
- Blocker management module is clean, no issues.

---

## Recommendations (Priority Order)

1. **[P0]** Deploy `fn_record_snapshot_membership` function matching the call signature in `reconciliation.py`, or fix the call to use existing DB functions. (C-01)

2. **[P0]** Fix field name lookup in `reconciliation.py:_record_memberships` — look up snake_case normalized field names when records come from normalized pipeline, and camelCase raw API field names when records come from `pncp_audit.py`. (L-11 + C-01 cascade)

3. **[P1]** Remove hardcoded passwords from ALL 17+ remaining standalone default DSNs. Centralize DSN resolution through `config/settings.py` or enforce `DATABASE_URL` everywhere. (H-01, H-06)

4. **[P1]** Add `conn.commit()` after `_record_evidence` calls in `crawl_source()` to ensure the evidence INSERTs are flushed regardless of execution path. (H-03)

5. **[P2]** Fix `_build_pncp_opportunities` so the `selected` filter actually excludes non-selected records from the `opportunities` list, not just from the stat counter. (M-03)

6. **[P2]** Add URL encoding to `PncpPublicationCrawler.build_url()` for consistency with `PncpOpportunityCrawler`. (L-07)

7. **[P3]** Remove dead `TargetEntity`, `TargetUniverse`, and `load_target_universe` from `consulting_readiness.py`. (H-04, I-02)

8. **[P3]** Add `__all__` to `scripts/lib/terminal.py`. (I-07)
