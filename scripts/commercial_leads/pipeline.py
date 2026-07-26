"""End-to-end commercial leads pipeline."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.commercial_leads import (
    CAMPAIGN_ID,
    CANDIDATE_DISCOVERY_RULE_VERSION,
    DISCOVERY_FULL_SNAPSHOT,
    DISCOVERY_PREFILTERED,
    HISTORY_FULL_CANDIDATE,
    MODULE_VERSION,
    POPULATION_FULL,
    POPULATION_SAMPLE,
    RANKING_BOUNDED,
    RANKING_FULL_ELIGIBLE,
    SOURCE_STATE_RESTORED,
)
from scripts.commercial_leads.baseline import compare_to_baselines
from scripts.commercial_leads.commercial_validity import evaluate_supplier_validity
from scripts.commercial_leads.contract_relevance import (
    filter_relevant_contracts,
)
from scripts.commercial_leads.dbutil import connect, fetch_all
from scripts.commercial_leads.exports import export_all, reconcile_exports
from scripts.commercial_leads.identity import ExclusionRecord, resolve_supplier
from scripts.commercial_leads.isolation import (
    assert_source_state_isolation,
    mask_dsn,
    open_source_connection,
)
from scripts.commercial_leads.profile import CommercialProfile, load_profile
from scripts.commercial_leads.review import load_state_map
from scripts.commercial_leads.scoring import rank_leads, score_supplier
from scripts.commercial_leads.sector_fit import PUBLISHABLE, sector_fit_histogram
from scripts.commercial_leads.signals import compute_signals_for_supplier, rows_from_dicts
from scripts.commercial_leads.snapshot import (
    bind_snapshot_to_database,
    compute_canonical_table_hash,
    validate_snapshot_manifest,
)
from scripts.commercial_leads.supplier_registry import (
    coverage_report,
    ensure_registry_table,
    load_registry_map,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha(root: Path | None = None) -> str:
    r = root or _PROJECT_ROOT
    try:
        out = subprocess.check_output(  # noqa: S603,S607
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(r),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def apply_migrations(dsn: str) -> dict[str, Any]:
    cmd = [
        "python3",
        "-m",
        "scripts.ops.apply_migrations",
        "--dsn",
        dsn,
    ]
    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "ok": proc.returncode == 0,
    }


def verify_migration_idempotence(dsn: str) -> dict[str, Any]:
    first = apply_migrations(dsn)
    second = apply_migrations(dsn)
    return {
        "first_ok": first["ok"],
        "second_ok": second["ok"],
        "idempotent": first["ok"] and second["ok"],
        "first": first,
        "second": second,
    }


def _segment_sql_prefilter(profile: CommercialProfile) -> tuple[str, list[Any]]:
    """Broad SQL prefilter (recall). Final relevance is hierarchical in Python.

    Uses only strong-ish profile keywords plus layer-A tokens so we do not
    scan the entire 4M table blindly, but weak tokens alone never qualify
    after Python classification.
    """
    from scripts.commercial_leads.contract_relevance import STRONG_PHRASES, STRONG_TOKENS

    kws: list[str] = []
    for seg in profile.data.get("segments") or []:
        if isinstance(seg, dict):
            kws.extend(str(x) for x in (seg.get("object_keywords") or []))
    # Prefer strong engineering terms for SQL prefilter
    strongish = [
        k for k in kws
        if k.strip() and k.lower() not in {
            "projeto", "consultoria", "servico", "serviço", "manutencao", "manutenção",
        }
    ]
    strongish.extend(STRONG_PHRASES[:12])
    strongish.extend(STRONG_TOKENS[:10])
    # de-dupe
    seen: set[str] = set()
    ordered: list[str] = []
    for k in strongish:
        kl = k.lower().strip()
        if kl and kl not in seen:
            seen.add(kl)
            ordered.append(k.strip())
    ordered = ordered[:30]
    if not ordered:
        return "TRUE", []
    clauses = []
    params: list[Any] = []
    for kw in ordered:
        clauses.append("objeto_contrato ILIKE %s")
        params.append(f"%{kw}%")
    return "(" + " OR ".join(clauses) + ")", params


_CONTRACT_SELECT = (
    "contrato_id, orgao_cnpj, orgao_nome, "
    "fornecedor_cnpj, fornecedor_nome, objeto_contrato, valor_total, "
    "data_inicio, data_fim, data_publicacao, uf, source, source_id"
)


def _normalize_cnpj_digits(raw: Any) -> str | None:
    import re

    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) >= 14:
        return digits[-14:]
    if len(digits) == 14:
        return digits
    return None


def discover_candidate_suppliers(
    conn: Any,
    profile: CommercialProfile,
    *,
    max_contracts: int | None = None,
    population_mode: str = POPULATION_SAMPLE,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Stage 1 — discovery only.

    Find CNPJs with at least one potentially relevant contract via SQL prefilter
    + hierarchical relevance. Does NOT declare sector fit.
    Returns (discovery_evidence_by_cnpj, meta).
    """
    filt, params = _segment_sql_prefilter(profile)
    uf_list = list((profile.data.get("region") or {}).get("primary_ufs") or [])
    uf_list += list((profile.data.get("region") or {}).get("secondary_ufs") or [])
    uf_list = [u.upper() for u in uf_list if u]

    sql = (
        f"SELECT {_CONTRACT_SELECT} "
        "FROM public.pncp_supplier_contracts "
        "WHERE is_active = TRUE "
        "AND fornecedor_cnpj IS NOT NULL "
        "AND btrim(fornecedor_cnpj) <> '' "
        "AND (" + filt + ")"  # nosec B608
    )
    if uf_list:
        sql += " AND uf IS NOT NULL AND upper(btrim(uf)) = ANY(%s)"
        params.append(uf_list)

    sql += " ORDER BY data_publicacao DESC NULLS LAST, valor_total DESC NULLS LAST"

    limit_applied = None
    if population_mode == POPULATION_FULL:
        pass
    elif max_contracts is not None:
        sql += " LIMIT %s"
        params.append(int(max_contracts))
        limit_applied = int(max_contracts)
    else:
        limit_applied = 250_000
        sql += " LIMIT %s"
        params.append(limit_applied)

    raw = fetch_all(conn, sql, tuple(params))
    kept, excluded = filter_relevant_contracts(raw)

    evidence_by_cnpj: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in kept:
        cnpj = _normalize_cnpj_digits(row.get("fornecedor_cnpj"))
        if not cnpj:
            continue
        evidence_by_cnpj[cnpj].append(row)

    discovery_mode = (
        DISCOVERY_PREFILTERED
        if population_mode == POPULATION_FULL
        else DISCOVERY_PREFILTERED
    )
    if population_mode == POPULATION_FULL and limit_applied is None and not uf_list:
        # Still prefilter-based unless no keyword filter — never claim full snapshot
        # unless SQL had no keyword prefilter.
        discovery_mode = DISCOVERY_PREFILTERED

    meta = {
        "stage": "discovery",
        "discovery_mode": discovery_mode,
        "candidate_discovery_rule_version": CANDIDATE_DISCOVERY_RULE_VERSION,
        "population_mode": population_mode,
        "limit_applied": limit_applied,
        "sql_prefilter_rows": len(raw),
        "relevance_pass_rows": len(kept),
        "relevance_fail_rows": len(excluded),
        "candidate_supplier_count": len(evidence_by_cnpj),
        "candidate_supplier_cnpjs": sorted(evidence_by_cnpj.keys()),
        "ufs_filter": uf_list,
        "uf_null_excluded_when_geo_filter": bool(uf_list),
        "sector_fit_declared_in_discovery": False,
        "note": (
            "Prefilter used only for candidate discovery. "
            "Sector classification requires Stage 2 full history expansion."
        ),
    }
    return dict(evidence_by_cnpj), meta


def load_full_supplier_histories(
    conn: Any,
    candidate_cnpjs: list[str],
    *,
    per_supplier_limit: int | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Stage 2 — expand FULL contract history for each candidate CNPJ.

    Loads ALL active contracts for candidates regardless of keyword/prefilter.
    per_supplier_limit must be None in production; if set, marks history incomplete.
    """
    cleaned = sorted({c for c in (_normalize_cnpj_digits(x) for x in candidate_cnpjs) if c})
    if not cleaned:
        return {}, {
            "stage": "full_history",
            "history_expansion_mode": HISTORY_FULL_CANDIDATE,
            "candidate_count": 0,
            "full_history_contract_count": 0,
            "per_supplier_limit": per_supplier_limit,
            "history_complete": True,
        }

    # Normalize fornecedor_cnpj digits in SQL for join
    sql = (
        f"SELECT {_CONTRACT_SELECT}, "
        "regexp_replace(fornecedor_cnpj, '\\D', '', 'g') AS fornecedor_cnpj_digits "
        "FROM public.pncp_supplier_contracts "
        "WHERE is_active = TRUE "
        "AND fornecedor_cnpj IS NOT NULL "
        "AND btrim(fornecedor_cnpj) <> '' "
        "AND right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) = ANY(%s) "
        "ORDER BY data_publicacao DESC NULLS LAST, valor_total DESC NULLS LAST"
    )
    raw = fetch_all(conn, sql, (cleaned,))

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    truncated: list[str] = []
    for row in raw:
        digits = row.get("fornecedor_cnpj_digits") or _normalize_cnpj_digits(row.get("fornecedor_cnpj"))
        cnpj = _normalize_cnpj_digits(digits)
        if not cnpj or cnpj not in set(cleaned):
            # right(...,14) already applied; re-normalize
            cnpj = _normalize_cnpj_digits(row.get("fornecedor_cnpj"))
        if not cnpj:
            continue
        if per_supplier_limit is not None and len(groups[cnpj]) >= int(per_supplier_limit):
            if cnpj not in truncated:
                truncated.append(cnpj)
            continue
        # drop helper column from contract dict used downstream
        clean = {k: v for k, v in row.items() if k != "fornecedor_cnpj_digits"}
        groups[cnpj].append(clean)

    # Reconcile counts vs direct snapshot query for integrity
    count_rows = fetch_all(
        conn,
        """
        SELECT right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) AS cnpj14,
               COUNT(*)::int AS n
        FROM public.pncp_supplier_contracts
        WHERE is_active = TRUE
          AND fornecedor_cnpj IS NOT NULL
          AND btrim(fornecedor_cnpj) <> ''
          AND right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) = ANY(%s)
        GROUP BY 1
        """,
        (cleaned,),
    )
    snapshot_counts = {str(r["cnpj14"]): int(r["n"]) for r in count_rows}
    mismatches: list[dict[str, Any]] = []
    for cnpj in cleaned:
        loaded = len(groups.get(cnpj, []))
        expected = snapshot_counts.get(cnpj, 0)
        if per_supplier_limit is None and loaded != expected:
            mismatches.append({"cnpj14": cnpj, "loaded": loaded, "snapshot_count": expected})

    history_complete = per_supplier_limit is None and not mismatches
    meta = {
        "stage": "full_history",
        "history_expansion_mode": (
            HISTORY_FULL_CANDIDATE if per_supplier_limit is None else "BOUNDED_PER_SUPPLIER"
        ),
        "candidate_count": len(cleaned),
        "suppliers_with_history": len(groups),
        "full_history_contract_count": sum(len(v) for v in groups.values()),
        "mean_contracts_per_candidate": (
            round(sum(len(v) for v in groups.values()) / len(groups), 4) if groups else 0.0
        ),
        "median_contracts_per_candidate": _median([len(v) for v in groups.values()]),
        "single_contract_candidate_rate": (
            round(sum(1 for v in groups.values() if len(v) == 1) / len(groups), 4)
            if groups
            else 0.0
        ),
        "per_supplier_limit": per_supplier_limit,
        "truncated_suppliers": truncated[:50],
        "history_complete": history_complete,
        "snapshot_count_mismatches": mismatches[:50],
        "snapshot_count_mismatch_n": len(mismatches),
    }
    return dict(groups), meta


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def load_contract_universe(
    conn: Any,
    profile: CommercialProfile,
    *,
    max_contracts: int | None = None,
    as_of: date | None = None,
    population_mode: str = POPULATION_SAMPLE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deprecated path: discovery prefilter only (does NOT return full history).

    Prefer discover_candidate_suppliers + load_full_supplier_histories.
    Kept for backward-compatible tests; marks history incomplete.
    """
    evidence, meta = discover_candidate_suppliers(
        conn, profile, max_contracts=max_contracts, population_mode=population_mode
    )
    # Flatten discovery evidence (relevant-only) — NOT full history
    rows: list[dict[str, Any]] = []
    for lst in evidence.values():
        rows.extend(lst)
    meta["deprecated"] = True
    meta["history_is_full"] = False
    meta["warning"] = (
        "load_contract_universe returns discovery-relevant rows only; "
        "do not use for sector concentration"
    )
    return rows, meta


def group_by_supplier(
    rows: list[dict[str, Any]],
    profile: CommercialProfile,
) -> tuple[dict[str, list[dict[str, Any]]], list[ExclusionRecord], dict[str, str]]:
    """Resolve identity and group contracts by canonical CNPJ14."""
    excl = profile.data.get("exclusions") or {}
    markers = list(excl.get("organ_name_markers") or [])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names: dict[str, str] = {}
    exclusions: list[ExclusionRecord] = []
    seen_excluded: set[str] = set()

    for row in rows:
        resolved = resolve_supplier(
            row.get("fornecedor_cnpj"),
            row.get("fornecedor_nome"),
            organ_markers=markers,
            drop_organs=bool(excl.get("drop_public_organs", True)),
            drop_persons=bool(excl.get("drop_natural_persons", True)),
            drop_invalid=bool(excl.get("drop_invalid_cnpj", True)),
        )
        if not resolved.eligible or not resolved.cnpj14:
            key = f"{resolved.exclusion_reason}:{resolved.raw_tax_id}:{resolved.razao_social}"
            if key not in seen_excluded:
                seen_excluded.add(key)
                exclusions.append(
                    ExclusionRecord(
                        raw_tax_id=resolved.raw_tax_id,
                        raw_name=resolved.razao_social,
                        reason_code=resolved.exclusion_reason or "ineligible",
                    )
                )
            continue
        groups[resolved.cnpj14].append(row)
        names[resolved.cnpj14] = resolved.razao_social
    return groups, exclusions, names


def persist_run(
    conn: Any,
    *,
    run_id: str,
    profile: CommercialProfile,
    snapshot_hash: str,
    snapshot_manifest: dict[str, Any],
    status: str,
    leads: list[dict[str, Any]],
    exclusions: list[ExclusionRecord],
    metrics: dict[str, Any],
    git: str,
) -> None:
    from psycopg2.extras import Json

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO commercial_lead_runs (
                run_id, profile_id, profile_version, profile_hash,
                snapshot_hash, snapshot_manifest, git_sha, status,
                queue_limit, eligible_companies, ranked_companies,
                metrics, non_claims, finished_at
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now()
            )
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                metrics = EXCLUDED.metrics,
                ranked_companies = EXCLUDED.ranked_companies,
                finished_at = now()
            """,
            (
                run_id,
                profile.profile_id,
                profile.version,
                profile.profile_hash,
                snapshot_hash,
                Json(snapshot_manifest),
                git,
                status,
                profile.queue_limit,
                int(metrics.get("eligible_companies") or 0),
                len(leads),
                Json(metrics),
                Json(profile.data.get("non_claims") or []),
            ),
        )
        for i, lead in enumerate(leads, start=1):
            cur.execute(
                """
                INSERT INTO commercial_leads (
                    run_id, cnpj14, cnpj8, razao_social, score_total, priority,
                    score_decomposition, signals_fired, signals_not_computable,
                    evidence, suggested_offer, next_human_step, limitations,
                    commercial_state, rank_position
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (run_id, cnpj14) DO UPDATE SET
                    score_total = EXCLUDED.score_total,
                    priority = EXCLUDED.priority,
                    score_decomposition = EXCLUDED.score_decomposition,
                    signals_fired = EXCLUDED.signals_fired,
                    commercial_state = EXCLUDED.commercial_state,
                    rank_position = EXCLUDED.rank_position
                """,
                (
                    run_id,
                    lead["cnpj14"],
                    lead["cnpj14"][:8],
                    lead["razao_social"],
                    lead["score_total"],
                    lead["priority"],
                    Json(lead.get("score_decomposition") or {}),
                    Json(lead.get("signals_fired") or []),
                    Json(lead.get("signals_not_computable") or []),
                    Json(lead.get("evidence") or []),
                    lead.get("suggested_offer"),
                    lead.get("next_human_step"),
                    Json(lead.get("limitations") or []),
                    lead.get("commercial_state") or "NEW",
                    lead.get("rank_position") or i,
                ),
            )
            cur.execute(
                """
                INSERT INTO commercial_feedback_ledger (run_id, cnpj14, event_type, payload, author)
                VALUES (%s,%s,'EXPORT',%s,'system')
                """,
                (run_id, lead["cnpj14"], Json({"rank": i, "score": lead["score_total"]})),
            )
        for ex in exclusions[:5000]:
            cur.execute(
                """
                INSERT INTO commercial_exclusions (run_id, raw_tax_id, raw_name, reason_code, detail)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (run_id, ex.raw_tax_id, ex.raw_name, ex.reason_code, ex.detail),
            )
    conn.commit()


def run_pipeline(
    *,
    dsn: str,
    profile_path: str | Path,
    snapshot_manifest: str | Path,
    out_dir: str | Path,
    max_contracts: int | None = None,
    as_of: date | None = None,
    skip_migrations: bool = False,
    skip_persist: bool = False,
    verify_snapshot_hash: bool = True,
    source_dsn: str | None = None,
    state_dsn: str | None = None,
    population_mode: str | None = None,
    source_state_mode: str | None = None,
    persistence_required: bool | None = None,
    run_mode: str = "RC",
) -> dict[str, Any]:
    """Run commercial queue with sector validity gates.

    population_mode: FULL_POPULATION | BOUNDED_SAMPLE
    run_mode: RC | TEST | DRY_RUN | EXPERIMENTAL_SAMPLE
    """
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = f"cl-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    as_of_d = as_of or date.today()
    git = git_sha()

    state = state_dsn or dsn
    source = source_dsn or dsn
    # Honest dual-DSN mode
    if source_state_mode is None:
        source_state_mode = SOURCE_STATE_RESTORED if source == state else None
    isolation = assert_source_state_isolation(
        source_dsn=source,
        state_dsn=state,
        out_dir=out,
        force_mode=source_state_mode or SOURCE_STATE_RESTORED,
        enforce_source_readonly=False,  # probe optional; session set readonly on open
    )
    if not isolation.ok or isolation.production_touched or isolation.soak_touched:
        result = {
            "run_id": run_id,
            "status": "FAIL",
            "reason": "isolation_violation",
            "isolation": isolation.as_dict(),
            "campaign_id": CAMPAIGN_ID,
            "production_touched": isolation.production_touched,
            "soak_touched": isolation.soak_touched,
            "artifact_git_sha": git,
            "run_git_sha": git,
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result

    # Population mode defaults: sample unless explicitly FULL
    pop_mode = (population_mode or POPULATION_SAMPLE).upper()
    if pop_mode not in (POPULATION_FULL, POPULATION_SAMPLE):
        pop_mode = POPULATION_SAMPLE
    if run_mode == "RC" and pop_mode != POPULATION_FULL:
        # RC may still run sample but cannot claim final ranking
        run_mode_effective = "EXPERIMENTAL_SAMPLE"
    else:
        run_mode_effective = run_mode

    persist_required = persistence_required
    if persist_required is None:
        persist_required = run_mode_effective == "RC" and pop_mode == POPULATION_FULL
    if skip_persist and run_mode_effective == "RC" and pop_mode == POPULATION_FULL:
        result = {
            "run_id": run_id,
            "status": "FAIL",
            "reason": "skip_persist_not_allowed_for_rc",
            "campaign_id": CAMPAIGN_ID,
            "artifact_git_sha": git,
            "run_git_sha": git,
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result
    if skip_persist and run_mode_effective not in ("TEST", "DRY_RUN", "EXPERIMENTAL_SAMPLE"):
        result = {
            "run_id": run_id,
            "status": "FAIL",
            "reason": "skip_persist_only_for_test_dry_run_sample",
            "campaign_id": CAMPAIGN_ID,
            "artifact_git_sha": git,
            "run_git_sha": git,
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result

    snap = validate_snapshot_manifest(
        snapshot_manifest,
        verify_file_hash=verify_snapshot_hash,
        allow_missing_dump=True,  # content binding uses canonical_table_hash
    )
    # Mint canonical_table_hash into manifest when missing (first bind) — never
    # treat marker dumps as authenticated by themselves.
    if (
        not snap.ok
        and "no_canonical_table_hash" in " ".join(snap.reasons or [])
    ) or (
        snap.ok and not (snap.canonical_table_hash or (snap.details or {}).get("canonical_table_hash"))
    ):
        # Will mint after source connection opens
        pass
    if not snap.ok and snap.status.startswith("BLOCKED"):
        # Allow proceed only when we can mint canonical hash from live DB
        reasons = " ".join(snap.reasons or [])
        if "marker" not in reasons and "canonical" not in reasons and "dump_file_missing" not in reasons and "dump_file_absent" not in reasons:
            result = {
                "run_id": run_id,
                "status": snap.status if snap.status.startswith("BLOCKED") else "FAIL",
                "reason": "snapshot_validation_failed",
                "snapshot": snap.as_dict(),
                "isolation": isolation.as_dict(),
                "campaign_id": CAMPAIGN_ID,
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
            return result

    profile = load_profile(profile_path)
    mig: dict[str, Any]
    if skip_migrations:
        mig = {"idempotent": False, "skipped": True, "first_ok": False, "second_ok": False}
        if run_mode_effective == "RC" and pop_mode == POPULATION_FULL:
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "migrations_skipped_not_allowed_for_rc",
                "migrations": mig,
                "isolation": isolation.as_dict(),
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result
    else:
        mig = verify_migration_idempotence(state)
        mig["skipped"] = False
        if not mig.get("idempotent"):
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "migration_not_idempotent",
                "migrations": mig,
                "isolation": isolation.as_dict(),
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

    source_conn = open_source_connection(source)
    state_conn = connect(state)
    try:
        # Mint / refresh canonical_table_hash on manifest (content fingerprint)
        man_path = Path(snapshot_manifest)
        try:
            man_data = json.loads(man_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            man_data = {}
        if not man_data.get("canonical_table_hash"):
            minted = compute_canonical_table_hash(source_conn)
            man_data["canonical_table_hash"] = minted["canonical_table_hash"]
            man_data["canonical_hash_algorithm"] = minted["canonical_hash_algorithm"]
            man_data["row_count"] = minted["row_count"]
            man_data["contracts_count"] = minted["row_count"]
            man_data["min_date"] = None
            man_data["max_date"] = None
            man_path.write_text(
                json.dumps(man_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            snap = validate_snapshot_manifest(
                man_path, verify_file_hash=False, allow_missing_dump=True
            )

        # Snapshot ↔ DB binding on source (full-table canonical hash required)
        binding = bind_snapshot_to_database(source_conn, snap, require_canonical_match=True)
        # Persist live dates into manifest for audit
        if binding.get("ok") and man_data is not None:
            man_data["canonical_table_hash"] = binding.get("canonical_table_hash")
            man_data["canonical_hash_algorithm"] = binding.get("canonical_hash_algorithm")
            man_data["min_date"] = binding.get("min_date")
            man_data["max_date"] = binding.get("max_date")
            man_data["row_count"] = binding.get("database_row_count")
            man_data["contracts_count"] = binding.get("database_row_count")
            man_path.write_text(
                json.dumps(man_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        if not binding.get("ok"):
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "snapshot_database_binding_failed",
                "snapshot_binding": binding,
                "snapshot": snap.as_dict(),
                "isolation": isolation.as_dict(),
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

        db_count = int(binding["database_row_count"])
        if db_count == 0:
            result = {
                "run_id": run_id,
                "status": "BLOCKED",
                "reason": "BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
                "snapshot": snap.as_dict(),
                "snapshot_binding": binding,
                "isolation": isolation.as_dict(),
                "db_contract_count": 0,
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

        # --- Stage 1: candidate discovery (prefilter only) ---
        discovery_evidence, discovery_meta = discover_candidate_suppliers(
            source_conn,
            profile,
            max_contracts=max_contracts,
            population_mode=pop_mode,
        )
        candidate_cnpjs = list(discovery_meta.get("candidate_supplier_cnpjs") or discovery_evidence.keys())

        # Identity / organ exclusions applied on discovery rows then full history
        discovery_flat: list[dict[str, Any]] = []
        for rows in discovery_evidence.values():
            discovery_flat.extend(rows)
        _disc_groups, exclusions, names_discovery = group_by_supplier(discovery_flat, profile)
        # Keep only eligible discovery CNPJs
        candidate_cnpjs = sorted(set(_disc_groups.keys()) | set(discovery_evidence.keys()))
        # Re-filter candidates through identity on a synthetic row if needed
        eligible_candidates: list[str] = []
        for cnpj in candidate_cnpjs:
            sample = (discovery_evidence.get(cnpj) or _disc_groups.get(cnpj) or [{}])[0]
            resolved = resolve_supplier(
                sample.get("fornecedor_cnpj") or cnpj,
                sample.get("fornecedor_nome") or names_discovery.get(cnpj),
                organ_markers=list((profile.data.get("exclusions") or {}).get("organ_name_markers") or []),
                drop_organs=bool((profile.data.get("exclusions") or {}).get("drop_public_organs", True)),
                drop_persons=bool((profile.data.get("exclusions") or {}).get("drop_natural_persons", True)),
                drop_invalid=bool((profile.data.get("exclusions") or {}).get("drop_invalid_cnpj", True)),
            )
            if resolved.eligible and resolved.cnpj14:
                eligible_candidates.append(resolved.cnpj14)
                if resolved.razao_social:
                    names_discovery[resolved.cnpj14] = resolved.razao_social
        candidate_cnpjs = sorted(set(eligible_candidates))

        # --- Stage 2: full history expansion (denominator integrity) ---
        groups, history_meta = load_full_supplier_histories(
            source_conn,
            candidate_cnpjs,
            per_supplier_limit=None,  # never silent LIMIT per supplier
        )
        # Refresh names from full history
        names: dict[str, str] = dict(names_discovery)
        for cnpj14, crow in groups.items():
            if crow and crow[0].get("fornecedor_nome"):
                names.setdefault(cnpj14, str(crow[0]["fornecedor_nome"]))

        load_meta = {
            **discovery_meta,
            **history_meta,
            "discovery_mode": discovery_meta.get("discovery_mode"),
            "history_expansion_mode": history_meta.get("history_expansion_mode"),
            "ranking_population_mode": (
                RANKING_FULL_ELIGIBLE if pop_mode == POPULATION_FULL else RANKING_BOUNDED
            ),
            "history_is_full": bool(history_meta.get("history_complete")),
            "sql_prefilter_rows": discovery_meta.get("sql_prefilter_rows"),
            "relevance_pass_rows": discovery_meta.get("relevance_pass_rows"),
        }
        if not history_meta.get("history_complete"):
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "FAIL_denominator_history_incomplete",
                "load_meta": load_meta,
                "snapshot_binding": binding,
                "isolation": isolation.as_dict(),
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

        uf_list = list((profile.data.get("region") or {}).get("primary_ufs") or [])
        uf_list += list((profile.data.get("region") or {}).get("secondary_ufs") or [])
        uf_list = [u.upper() for u in uf_list if u]

        # Supplier registry (CNAE) — never invent
        try:
            ensure_registry_table(state_conn)
        except Exception:  # noqa: BLE001
            pass
        try:
            registry_map = load_registry_map(source_conn, list(groups.keys()))
        except Exception:  # noqa: BLE001
            try:
                registry_map = load_registry_map(state_conn, list(groups.keys()))
            except Exception:  # noqa: BLE001
                registry_map = {}

        candidates_meta: list[dict[str, Any]] = []
        scored = []
        sector_decisions = []
        review_queue: list[dict[str, Any]] = []
        validity_excluded = 0
        denominator_failures = 0

        state_map: dict[str, str] = {}
        try:
            state_map = load_state_map(state_conn)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "commercial_lead_state_overrides" in msg or "does not exist" in msg:
                state_map = {}
            else:
                raise
        dnc_set = {c for c, st in state_map.items() if str(st).upper() == "DO_NOT_CONTACT"}

        for cnpj14, crow in groups.items():
            contracts = rows_from_dicts(crow)
            # FULL history dicts for sector/geo — never prefilter-only
            crow_dicts = list(crow)
            reg = registry_map.get(cnpj14)
            cnae_principal = reg.cnae_principal if reg else None
            cnaes_sec = list(reg.cnaes_secundarios) if reg else []
            sigs = compute_signals_for_supplier(contracts, profile, as_of=as_of_d, official_acts=None)
            total_value = sum(float(c.valor_total or 0) for c in contracts if c.valor_total is not None)
            last_pub = None
            pubs = [c.data_publicacao for c in contracts if c.data_publicacao]
            if pubs:
                last_pub = max(pubs).isoformat()
            razao = names.get(cnpj14, crow[0].get("fornecedor_nome") or cnpj14)
            lead = score_supplier(
                cnpj14=cnpj14,
                razao_social=razao,
                signal_results=sigs,
                profile=profile,
                total_value=total_value,
                contract_count=len(contracts),
                last_publication=last_pub,
            )
            # provisional signal dict for validity
            lead_d = lead.as_dict()
            validity, sector, geo = evaluate_supplier_validity(
                razao_social=razao,
                contracts=crow_dicts,
                signals_fired=lead_d.get("signals_fired") or [],
                score_total=lead.score_total,
                allowed_ufs=uf_list,
                cnae_principal=cnae_principal,
                cnaes_secundarios=cnaes_sec,
                min_signals=int((profile.data.get("queue") or {}).get("min_signals_fired") or 1),
                min_score=float((profile.data.get("queue") or {}).get("min_score") or 1.0),
                exclusion_flags={
                    "do_not_contact": cnpj14 in dnc_set,
                },
                run_id=run_id,
            )
            if not sector.denominator_invariant_ok:
                denominator_failures += 1
            sector_decisions.append(sector)
            limitations: list[str] = []
            if reg is None:
                limitations.append("supplier_registry_missing")
                limitations.append("cnae_NOT_COMPUTABLE")
            elif reg.is_inactive:
                limitations.append(f"situacao_cadastral:{reg.situacao_cadastral}")
            if sector.history_source != "full_history":
                limitations.append("history_incomplete")
            meta_row = {
                "cnpj14": cnpj14,
                "razao_social": razao,
                "total_value": total_value,
                "contract_count": len(contracts),
                "total_contract_count_full_history": sector.total_contract_count_full_history,
                "relevant_contract_count": sector.relevant_contract_count,
                "relevant_contract_ratio_full_history": sector.relevant_contract_ratio_full_history,
                "last_publication": last_pub,
                "supplier_sector_fit": sector.classification,
                "activity_class": sector.activity_class,
                "contract_relevance": validity.contract_relevance,
                "commercial_signal_fit": validity.commercial_signal_fit,
                "geography_fit": validity.geography_fit,
                "publishable": validity.publishable,
                "cnae_principal": cnae_principal,
                "discovery_status": "CANDIDATE",
            }
            candidates_meta.append(meta_row)
            lead_d_extra = {
                "supplier_sector_fit": sector.classification,
                "supplier_sector_confidence": sector.confidence,
                "supplier_sector_evidence": sector.as_dict(),
                "activity_class": sector.activity_class,
                "contract_relevance": validity.contract_relevance,
                "contract_relevance_evidence": (validity.evidence or {}).get("contract_relevance_sample"),
                "commercial_signal_fit": validity.commercial_signal_fit,
                "geography_fit": validity.geography_fit,
                "exclusion_checks": validity.exclusion_checks,
                "commercial_validity": validity.as_dict(),
                "data_quality": {
                    "relevant_contract_ratio": sector.relevant_contract_ratio_full_history,
                    "relevant_contract_ratio_full_history": sector.relevant_contract_ratio_full_history,
                    "relevant_contract_count": sector.relevant_contract_count,
                    "irrelevant_contract_count": sector.irrelevant_contract_count,
                    "review_contract_count": sector.review_contract_count,
                    "total_contract_count": sector.total_contract_count_full_history,
                    "total_contract_count_full_history": sector.total_contract_count_full_history,
                    "agency_count_relevant": sector.agency_count_relevant,
                    "object_diversity": sector.object_diversity,
                    "time_span_days": sector.time_span_days,
                    "denominator_invariant_ok": sector.denominator_invariant_ok,
                    "history_source": sector.history_source,
                    "cnae_principal": cnae_principal,
                    "cnae_status": "OK" if cnae_principal else "NOT_COMPUTABLE",
                },
                "limitations": limitations + list(lead_d.get("limitations") or []),
                "manual_review_status": "PENDING",
                "human_review_status": "PENDING",
                "precision_at_10": None,
                "precision_at_20": None,
            }
            # Sector gate: only CONFIRMED/STRONG enter published queue (never POSSIBLE/OUT/UNKNOWN/CONFLICTING)
            if validity.publishable and cnpj14 not in dnc_set:
                scored.append((lead, lead_d_extra))
            else:
                validity_excluded += 1
                if validity.review_queue:
                    review_queue.append({**meta_row, **lead_d_extra})

        if denominator_failures:
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "FAIL_denominator_invariant",
                "denominator_failures": denominator_failures,
                "load_meta": load_meta,
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

        pure_scored = [s[0] for s in scored]
        extras_by_cnpj = {s[0].cnpj14: s[1] for s in scored}
        suppressed_from_score = [s for s in pure_scored if s.cnpj14 in dnc_set]
        ranked = rank_leads(
            pure_scored,
            profile,
            suppressed_cnpjs=dnc_set,
            state_by_cnpj=state_map,
        )
        lead_dicts: list[dict[str, Any]] = []
        for i, lead in enumerate(ranked, start=1):
            d = lead.as_dict()
            d["rank_position"] = i
            d["commercial_state"] = state_map.get(lead.cnpj14, "NEW")
            d.update(extras_by_cnpj.get(lead.cnpj14, {}))
            lead_dicts.append(d)

        # Human-label-aware baseline comparison (labels optional)
        baseline_cmp = compare_to_baselines(ranked, candidates_meta, limit=profile.queue_limit)
        sector_dist = sector_fit_histogram(sector_decisions)

        ledger = [
            {
                "cnpj14": lead["cnpj14"],
                "event_type": "EXPORT",
                "author": "system",
                "payload": {
                    "rank": lead["rank_position"],
                    "score": lead["score_total"],
                    "commercial_state": lead.get("commercial_state"),
                    "supplier_sector_fit": lead.get("supplier_sector_fit"),
                    "profile_version": profile.version,
                    "catalog_version": profile.catalog_hash,
                    "dataset_snapshot_id": snap.snapshot_hash,
                    "source_run_id": run_id,
                    "rule_version": "commercial-validity-v1",
                },
                "created_at": utc_now(),
            }
            for lead in lead_dicts
        ]

        # Registry coverage (human metrics null until labeled)
        top20_cnpjs = [L["cnpj14"] for L in lead_dicts[:20]]
        top100_cnpjs = [m["cnpj14"] for m in sorted(
            candidates_meta, key=lambda x: float(x.get("total_value") or 0), reverse=True
        )[:100]]
        reg_cov = coverage_report(
            registry_map,
            all_candidates=list(groups.keys()),
            top100=top100_cnpjs,
            top20=top20_cnpjs,
        )

        n_sector = max(sum(sector_dist.values()), 1)
        publishable_rate = round(len(pure_scored) / n_sector, 4)
        strong_rate = round(sector_dist.get("STRONG_ENGINEERING_FIT", 0) / n_sector, 4)
        anomaly_flags: list[str] = []
        if strong_rate > 0.25:
            anomaly_flags.append(f"high_strong_rate:{strong_rate}")
        if publishable_rate > 0.40:
            anomaly_flags.append(f"high_publishable_rate:{publishable_rate}")

        metrics = {
            "eligible_companies": len(groups),
            "candidate_count": len(groups),
            "raw_contracts_loaded": load_meta.get("sql_prefilter_rows"),
            "relevance_pass_contracts": load_meta.get("relevance_pass_rows"),
            "full_history_contract_count": load_meta.get("full_history_contract_count"),
            "mean_contracts_per_candidate": load_meta.get("mean_contracts_per_candidate"),
            "median_contracts_per_candidate": load_meta.get("median_contracts_per_candidate"),
            "single_contract_candidate_rate": load_meta.get("single_contract_candidate_rate"),
            "db_contract_count": db_count,
            "exclusions": len(exclusions),
            "scored_companies": len(pure_scored),
            "validity_excluded": validity_excluded,
            "review_queue_size": len(review_queue),
            "ranked_leads": len(lead_dicts),
            "do_not_contact_suppressed": len(suppressed_from_score),
            "human_state_overrides": len(state_map),
            "queue_limit": profile.queue_limit,
            "insufficient_queue": len(lead_dicts) < profile.queue_limit,
            "elapsed_seconds": round(time.time() - t0, 3),
            "module_version": MODULE_VERSION,
            "population_mode": pop_mode,
            "discovery_mode": load_meta.get("discovery_mode"),
            "history_expansion_mode": load_meta.get("history_expansion_mode"),
            "ranking_population_mode": load_meta.get("ranking_population_mode"),
            "limit_applied": load_meta.get("limit_applied"),
            "sector_fit_distribution": sector_dist,
            "publishable_rate": publishable_rate,
            "out_of_scope_rate": round(sector_dist.get("OUT_OF_SCOPE", 0) / n_sector, 4),
            "unknown_rate": round(sector_dist.get("UNKNOWN", 0) / n_sector, 4),
            "conflicting_rate": round(sector_dist.get("CONFLICTING", 0) / n_sector, 4),
            "review_queue_rate": round(len(review_queue) / n_sector, 4),
            "cnae_coverage": reg_cov.get("cnae_primary_coverage"),
            "registry_coverage": reg_cov,
            "anomaly_flags": anomaly_flags,
            # Human metrics: null until real dual human labels exist
            "precision_at_10": None,
            "precision_at_20": None,
            "false_positives": None,
            "false_negatives": None,
            "human_review_status": "PENDING",
        }

        # Commercial top-10 gate
        top10: list[dict[str, Any]] = lead_dicts[:10]
        top10_ok = True
        top10_issues: list[str] = []
        out_of_scope_top10 = 0
        for item in top10:
            if not item.get("cnpj14") or len(str(item["cnpj14"])) != 14:
                top10_ok = False
                top10_issues.append("invalid_cnpj_in_top10")
            if str(item.get("commercial_state") or "").upper() == "DO_NOT_CONTACT":
                top10_ok = False
                top10_issues.append("do_not_contact_in_top10")
            if not (item.get("signals_fired") or []):
                top10_ok = False
                top10_issues.append("top10_without_fired_signal")
            if not (item.get("evidence") or []):
                top10_ok = False
                top10_issues.append("top10_without_evidence")
            sfit = str(item.get("supplier_sector_fit") or "")
            if sfit not in PUBLISHABLE:
                top10_ok = False
                top10_issues.append(f"top10_sector_not_strong:{sfit}")
                if sfit == "OUT_OF_SCOPE":
                    out_of_scope_top10 += 1
            if item.get("contract_relevance") != "PASS":
                top10_ok = False
                top10_issues.append("top10_contract_relevance_fail")
            if item.get("commercial_signal_fit") != "PASS":
                top10_ok = False
                top10_issues.append("top10_commercial_signal_fail")
            if item.get("geography_fit") != "PASS":
                top10_ok = False
                top10_issues.append("top10_geography_fail")
        if out_of_scope_top10:
            top10_ok = False
            top10_issues.append("out_of_scope_in_top10")
        if any(str(L.get("commercial_state") or "").upper() == "DO_NOT_CONTACT" for L in lead_dicts):
            top10_ok = False
            top10_issues.append("do_not_contact_in_published_queue")

        # Terminal status — never RC_TECHNICAL_PASS; never claim PASS without human labels
        if not history_meta.get("history_complete"):
            status = "FAIL"
            reason = "FAIL_denominator_history_incomplete"
        elif denominator_failures:
            status = "FAIL"
            reason = "FAIL_denominator_invariant"
        elif anomaly_flags and strong_rate > 0.5:
            status = "FAIL"
            reason = "FAIL_sector_distribution_anomaly"
            top10_issues.extend(anomaly_flags)
        elif not lead_dicts:
            status = "BLOCKED"
            reason = "BLOCKED_COMMERCIAL_RELEVANCE_NOT_PROVEN"
            top10_issues.append("empty_queue")
        elif pop_mode != POPULATION_FULL:
            status = "BLOCKED"
            reason = "BLOCKED_FULL_POPULATION_NOT_AVAILABLE"
        elif not top10_ok:
            status = "FAIL"
            reason = "FAIL_COMMERCIAL_QUALITY_GATE"
        elif not reg_cov.get("top20_coverage_100pct"):
            status = "BLOCKED"
            reason = "BLOCKED_MISSING_SUPPLIER_SECTOR_DATA"
        else:
            # Technical machine ranking may be OK but commercial PASS requires human labels
            status = "BLOCKED"
            reason = "BLOCKED_INSUFFICIENT_HUMAN_LABELS"

        # Sample mode cannot claim final ranking
        claims = [
            "explainable_signals",
            "reproducible_ranking_inputs",
            "sector_fit_layer_v2_gold",
            "hierarchical_contract_relevance_v1",
            "two_stage_discovery_full_history",
            "denominator_full_history",
        ]
        if pop_mode == POPULATION_FULL and load_meta.get("history_expansion_mode") == HISTORY_FULL_CANDIDATE:
            claims.append("full_candidate_history_ranking")
            claims.append("prefiltered_candidate_discovery")
            # Never claim FULL_SNAPSHOT_SCAN unless discovery was unfiltered
            if load_meta.get("discovery_mode") == DISCOVERY_FULL_SNAPSHOT:
                claims.append("full_snapshot_discovery")
        else:
            claims.append("EXPERIMENTAL_SAMPLE" if pop_mode == POPULATION_SAMPLE else "partial_queue")

        run_payload: dict[str, Any] = {
            "run_id": run_id,
            "campaign_id": CAMPAIGN_ID,
            "status": status,
            "reason": reason,
            "as_of": as_of_d.isoformat(),
            "git_sha": git,
            "artifact_git_sha": git,
            "run_git_sha": git,
            "profile_id": profile.profile_id,
            "profile_version": profile.version,
            "profile_hash": profile.profile_hash,
            "catalog_hash": profile.catalog_hash,
            "snapshot_hash": snap.snapshot_hash,
            "snapshot": snap.as_dict(),
            "snapshot_binding": binding,
            "isolation": isolation.as_dict(),
            "source_state_mode": isolation.source_state_mode,
            # population_mode is a legacy CLI flag only — never a completeness claim
            "population_mode": pop_mode,
            "population_mode_semantics": (
                "legacy_cli_flag_only_not_completeness_claim;"
                "see discovery_mode/history_expansion_mode/ranking_population_mode"
            ),
            "discovery_mode": load_meta.get("discovery_mode"),
            "history_expansion_mode": load_meta.get("history_expansion_mode"),
            "ranking_population_mode": load_meta.get("ranking_population_mode"),
            "claims_full_snapshot_scan": False,
            "run_mode": run_mode_effective,
            "load_meta": load_meta,
            "registry_coverage": reg_cov,
            "human_metrics": {
                "precision_at_10": None,
                "precision_at_20": None,
                "false_positives": None,
                "false_negatives": None,
                "human_review_status": "PENDING",
            },
            "migrations": {
                "idempotent": mig.get("idempotent"),
                "skipped": mig.get("skipped", False),
                "first_ok": mig.get("first_ok", mig.get("idempotent")),
                "second_ok": mig.get("second_ok", mig.get("idempotent")),
            },
            "persistence_required": persist_required,
            "dsn_masked": mask_dsn(state),
            "production_touched": False,
            "soak_touched": False,
            "eligible_companies": len(groups),
            "queue_limit": profile.queue_limit,
            "leads": lead_dicts,
            "review_queue_sample": review_queue[:50],
            "exclusions_sample": [e.as_dict() for e in exclusions[:200]],
            "exclusion_counts": _count_reasons(exclusions),
            "baseline_comparison": baseline_cmp,
            "signal_catalog": profile.catalog,
            "profile_public": profile.as_public_dict(),
            "ledger": ledger,
            "metrics": metrics,
            "sector_fit_distribution": sector_dist,
            "top10_validation": {
                "ok": top10_ok,
                "issues": sorted(set(top10_issues)),
                "out_of_scope_in_top10": out_of_scope_top10,
            },
            "non_claims": profile.data.get("non_claims")
            or [
                "CONFENGE_COMMERCIAL_READY",
                "purchase_propensity",
                "conversion_probability",
                "tiago_acceptance",
                "contact_authorization",
                "PROJECT_DONE",
                "VPS_OPERATIONAL",
                "RC_TECHNICAL_PASS",
            ],
            "claims": claims,
            "language_note": (
                "Fila de priorização por aderência setorial + sinais observados; "
                "não afirma claim estatístico de conversão comercial."
            ),
            "suppressed_do_not_contact": sorted(dnc_set)[:100],
        }

        if not skip_persist:
            try:
                persist_run(
                    state_conn,
                    run_id=run_id,
                    profile=profile,
                    snapshot_hash=str(snap.snapshot_hash),
                    snapshot_manifest=snap.as_dict(),
                    status=status,
                    leads=lead_dicts,
                    exclusions=exclusions,
                    metrics=metrics,
                    git=git,
                )
                run_payload["persist_ok"] = True
            except Exception as exc:  # noqa: BLE001
                run_payload["persist_error"] = str(exc)
                run_payload["persist_ok"] = False
                if persist_required:
                    run_payload["status"] = "FAIL"
                    run_payload["reason"] = "persistence_failed"
                    run_payload["artifact_invalid"] = True
                    try:
                        state_conn.rollback()
                    except Exception as rb_exc:  # noqa: BLE001
                        run_payload["rollback_error"] = str(rb_exc)
        else:
            run_payload["persist_ok"] = None
            run_payload["persist_skipped"] = True

        paths = export_all(out, run_payload)
        recon = reconcile_exports(out, run_payload)
        run_payload["export_paths"] = paths
        run_payload["export_reconciliation"] = recon
        if not recon.get("ok") and run_payload["status"] == "PASS":
            run_payload["status"] = "FAIL"
            run_payload["reason"] = "export_reconciliation_failed"

        rank_blob = json.dumps(
            [
                (
                    lead["cnpj14"],
                    lead["score_total"],
                    lead["priority"],
                    lead.get("supplier_sector_fit"),
                )
                for lead in lead_dicts
            ],
            sort_keys=True,
        )
        run_payload["ranking_hash"] = hashlib.sha256(rank_blob.encode()).hexdigest()

        (out / "run-result.json").write_text(
            json.dumps(run_payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        # review queue separate
        (out / "review-queue.json").write_text(
            json.dumps(review_queue[:200], indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return run_payload
    finally:
        source_conn.close()
        state_conn.close()



def _count_reasons(exclusions: list[ExclusionRecord]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for e in exclusions:
        counts[e.reason_code] += 1
    return dict(counts)
