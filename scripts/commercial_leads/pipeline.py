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

from scripts.commercial_leads import CAMPAIGN_ID, MODULE_VERSION
from scripts.commercial_leads.baseline import compare_to_baselines
from scripts.commercial_leads.dbutil import connect, fetch_all
from scripts.commercial_leads.exports import export_all, reconcile_exports
from scripts.commercial_leads.identity import ExclusionRecord, resolve_supplier
from scripts.commercial_leads.isolation import assert_isolation, mask_dsn
from scripts.commercial_leads.profile import CommercialProfile, load_profile
from scripts.commercial_leads.review import load_state_map
from scripts.commercial_leads.scoring import rank_leads, score_supplier
from scripts.commercial_leads.signals import compute_signals_for_supplier, rows_from_dicts
from scripts.commercial_leads.snapshot import validate_snapshot_manifest

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


def _segment_sql_filter(profile: CommercialProfile) -> tuple[str, list[Any]]:
    """Build ILIKE filter for engineering-ish objects from profile keywords."""
    kws: list[str] = []
    for seg in profile.data.get("segments") or []:
        if isinstance(seg, dict):
            kws.extend(str(x) for x in (seg.get("object_keywords") or []))
    kws = [k for k in kws if k.strip()]
    if not kws:
        return "TRUE", []
    # Limit to top keywords for performance
    kws = kws[:24]
    clauses = []
    params: list[Any] = []
    for kw in kws:
        clauses.append("objeto_contrato ILIKE %s")
        params.append(f"%{kw}%")
    return "(" + " OR ".join(clauses) + ")", params


def load_contract_universe(
    conn: Any,
    profile: CommercialProfile,
    *,
    max_contracts: int | None = None,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Load active contracts relevant to profile (keyword filter + optional UFs)."""
    filt, params = _segment_sql_filter(profile)
    uf_list = list((profile.data.get("region") or {}).get("primary_ufs") or [])
    uf_list += list((profile.data.get("region") or {}).get("secondary_ufs") or [])
    uf_list = [u.upper() for u in uf_list if u]

    # filt is built only from bound ILIKE params (no raw user SQL)
    # filt is only composed of static "col ILIKE %s" clauses with bound params
    sql = (
        "SELECT contrato_id, orgao_cnpj, orgao_nome, "
        "fornecedor_cnpj, fornecedor_nome, objeto_contrato, valor_total, "
        "data_inicio, data_fim, data_publicacao, uf, source, source_id "
        "FROM public.pncp_supplier_contracts "
        "WHERE is_active = TRUE "
        "AND fornecedor_cnpj IS NOT NULL "
        "AND btrim(fornecedor_cnpj) <> '' "
        "AND (" + filt + ")"  # nosec B608
    )
    if uf_list:
        sql += " AND (uf IS NULL OR upper(btrim(uf)) = ANY(%s))"
        params.append(uf_list)

    # Prefer recent + high value for scoring pool
    sql += " ORDER BY data_publicacao DESC NULLS LAST, valor_total DESC NULLS LAST"
    if max_contracts:
        sql += " LIMIT %s"
        params.append(max_contracts)

    return fetch_all(conn, sql, tuple(params))


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
    max_contracts: int | None = 250_000,
    as_of: date | None = None,
    skip_migrations: bool = False,
    skip_persist: bool = False,
    verify_snapshot_hash: bool = True,
) -> dict[str, Any]:
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = f"cl-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    as_of_d = as_of or date.today()
    git = git_sha()

    isolation = assert_isolation(dsn, out_dir=out)
    if not isolation.ok or isolation.production_touched or isolation.soak_touched:
        result = {
            "run_id": run_id,
            "status": "FAIL",
            "reason": "isolation_violation",
            "isolation": isolation.as_dict(),
            "campaign_id": CAMPAIGN_ID,
            "production_touched": isolation.production_touched,
            "soak_touched": isolation.soak_touched,
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result

    snap = validate_snapshot_manifest(
        snapshot_manifest,
        verify_file_hash=verify_snapshot_hash,
    )
    if not snap.ok:
        status = snap.status if snap.status.startswith("BLOCKED") else "FAIL"
        result = {
            "run_id": run_id,
            "status": status,
            "reason": "snapshot_validation_failed",
            "snapshot": snap.as_dict(),
            "isolation": isolation.as_dict(),
            "campaign_id": CAMPAIGN_ID,
            "production_touched": False,
            "soak_touched": False,
            "non_claims": [
                "CONFENGE_COMMERCIAL_READY",
                "purchase_propensity",
                "tiago_acceptance",
            ],
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return result

    profile = load_profile(profile_path)
    mig: dict[str, Any]
    if skip_migrations:
        mig = {"idempotent": True, "skipped": True}
    else:
        mig = verify_migration_idempotence(dsn)
        if not mig.get("idempotent"):
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "migration_not_idempotent",
                "migrations": mig,
                "isolation": isolation.as_dict(),
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

    conn = connect(dsn)
    try:
        count_row = fetch_all(conn, "SELECT COUNT(*)::bigint AS n FROM pncp_supplier_contracts")
        db_count = int(count_row[0]["n"]) if count_row else 0
        if db_count == 0:
            result = {
                "run_id": run_id,
                "status": "BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
                "reason": "database_has_zero_contracts",
                "snapshot": snap.as_dict(),
                "isolation": isolation.as_dict(),
                "db_contract_count": 0,
                "hint": "Restore authenticated dump into isolated DB before run.",
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

        raw_rows = load_contract_universe(conn, profile, max_contracts=max_contracts, as_of=as_of_d)
        groups, exclusions, names = group_by_supplier(raw_rows, profile)

        candidates_meta: list[dict[str, Any]] = []
        scored = []
        for cnpj14, crow in groups.items():
            contracts = rows_from_dicts(crow)
            sigs = compute_signals_for_supplier(contracts, profile, as_of=as_of_d, official_acts=None)
            total_value = sum(float(c.valor_total or 0) for c in contracts if c.valor_total is not None)
            last_pub = None
            pubs = [c.data_publicacao for c in contracts if c.data_publicacao]
            if pubs:
                last_pub = max(pubs).isoformat()
            lead = score_supplier(
                cnpj14=cnpj14,
                razao_social=names.get(cnpj14, crow[0].get("fornecedor_nome") or cnpj14),
                signal_results=sigs,
                profile=profile,
                total_value=total_value,
                contract_count=len(contracts),
                last_publication=last_pub,
            )
            candidates_meta.append(
                {
                    "cnpj14": cnpj14,
                    "razao_social": lead.razao_social,
                    "total_value": total_value,
                    "contract_count": len(contracts),
                    "last_publication": last_pub,
                }
            )
            scored.append(lead)

        # Human overrides / DO_NOT_CONTACT must suppress from published queue
        state_map: dict[str, str] = {}
        try:
            state_map = load_state_map(conn)
        except Exception as exc:  # noqa: BLE001
            # Fail closed for missing relation only (fresh DB before 062); otherwise abort.
            msg = str(exc).lower()
            if "commercial_lead_state_overrides" in msg or "does not exist" in msg:
                state_map = {}
            else:
                raise
        dnc_set = {c for c, st in state_map.items() if str(st).upper() == "DO_NOT_CONTACT"}
        suppressed_from_score = [s for s in scored if s.cnpj14 in dnc_set]
        ranked = rank_leads(
            scored,
            profile,
            suppressed_cnpjs=dnc_set,
            state_by_cnpj=state_map,
        )
        lead_dicts: list[dict[str, Any]] = []
        for i, lead in enumerate(ranked, start=1):
            d = lead.as_dict()
            d["rank_position"] = i
            # Preserve prior human state when present; default NEW for first sighting
            d["commercial_state"] = state_map.get(lead.cnpj14, "NEW")
            lead_dicts.append(d)

        baseline_cmp = compare_to_baselines(ranked, candidates_meta, limit=profile.queue_limit)
        ledger = [
            {
                "cnpj14": lead["cnpj14"],
                "event_type": "EXPORT",
                "author": "system",
                "payload": {
                    "rank": lead["rank_position"],
                    "score": lead["score_total"],
                    "commercial_state": lead.get("commercial_state"),
                },
                "created_at": utc_now(),
            }
            for lead in lead_dicts
        ]

        metrics = {
            "eligible_companies": len(groups),
            "raw_contracts_loaded": len(raw_rows),
            "db_contract_count": db_count,
            "exclusions": len(exclusions),
            "scored_companies": len(scored),
            "ranked_leads": len(lead_dicts),
            "do_not_contact_suppressed": len(suppressed_from_score),
            "human_state_overrides": len(state_map),
            "queue_limit": profile.queue_limit,
            "insufficient_queue": len(lead_dicts) < profile.queue_limit,
            "elapsed_seconds": round(time.time() - t0, 3),
            "module_version": MODULE_VERSION,
        }

        # Top-10 quality gates for status
        top10: list[dict[str, Any]] = lead_dicts[:10]
        top10_ok = True
        top10_issues: list[str] = []
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
        # Package must never publish DO_NOT_CONTACT
        if any(str(L.get("commercial_state") or "").upper() == "DO_NOT_CONTACT" for L in lead_dicts):
            top10_ok = False
            top10_issues.append("do_not_contact_in_published_queue")

        status = "PASS" if top10_ok and lead_dicts else ("BLOCKED" if not lead_dicts else "FAIL")
        if not lead_dicts:
            status = "BLOCKED"
            top10_issues.append("empty_queue")
        if not top10_ok and lead_dicts:
            status = "FAIL"

        run_payload: dict[str, Any] = {
            "run_id": run_id,
            "campaign_id": CAMPAIGN_ID,
            "status": status,
            "as_of": as_of_d.isoformat(),
            "git_sha": git,
            "profile_id": profile.profile_id,
            "profile_version": profile.version,
            "profile_hash": profile.profile_hash,
            "catalog_hash": profile.catalog_hash,
            "snapshot_hash": snap.snapshot_hash,
            "snapshot": snap.as_dict(),
            "isolation": isolation.as_dict(),
            "migrations": {"idempotent": mig.get("idempotent"), "skipped": mig.get("skipped", False)},
            "dsn_masked": mask_dsn(dsn),
            "production_touched": False,
            "soak_touched": False,
            "eligible_companies": len(groups),
            "queue_limit": profile.queue_limit,
            "leads": lead_dicts,
            "exclusions_sample": [e.as_dict() for e in exclusions[:200]],
            "exclusion_counts": _count_reasons(exclusions),
            "baseline_comparison": baseline_cmp,
            "signal_catalog": profile.catalog,
            "profile_public": profile.as_public_dict(),
            "ledger": ledger,
            "metrics": metrics,
            "top10_validation": {"ok": top10_ok, "issues": sorted(set(top10_issues))},
            "non_claims": profile.data.get("non_claims")
            or [
                "CONFENGE_COMMERCIAL_READY",
                "purchase_propensity",
                "conversion_probability",
                "tiago_acceptance",
                "contact_authorization",
                "PROJECT_DONE",
                "VPS_OPERATIONAL",
            ],
            "claims": [
                "technical_commercial_queue_generated",
                "explainable_signals",
                "reproducible_ranking_inputs",
                "package_ready_for_human_review",
            ],
            "language_note": (
                "Fila de priorização por sinais observados; "
                "não afirma claim estatístico de conversão comercial."
            ),
            "suppressed_do_not_contact": sorted(dnc_set)[:100],
        }

        if not skip_persist:
            try:
                persist_run(
                    conn,
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
            except Exception as exc:  # noqa: BLE001
                run_payload["persist_error"] = str(exc)

        paths = export_all(out, run_payload)
        recon = reconcile_exports(out, run_payload)
        run_payload["export_paths"] = paths
        run_payload["export_reconciliation"] = recon
        if not recon.get("ok") and run_payload["status"] == "PASS":
            run_payload["status"] = "FAIL"
            run_payload["reason"] = "export_reconciliation_failed"

        # ranking hash for reproducibility
        rank_blob = json.dumps(
            [(lead["cnpj14"], lead["score_total"], lead["priority"]) for lead in lead_dicts],
            sort_keys=True,
        )
        run_payload["ranking_hash"] = hashlib.sha256(rank_blob.encode()).hexdigest()

        (out / "run-result.json").write_text(
            json.dumps(run_payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return run_payload
    finally:
        conn.close()


def _count_reasons(exclusions: list[ExclusionRecord]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for e in exclusions:
        counts[e.reason_code] += 1
    return dict(counts)
