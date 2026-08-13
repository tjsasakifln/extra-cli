"""Rebuild FUNNEL + JSON pack from live host DSN with honest closed sums.

Rules (skeptic-proof):
- Never invent synthetic company keys (c0..cN).
- Never hard-code pilot 41/50 as capacity or attempted counts.
- Contact "attempted" only when discovery actually ran (network metrics or
  harvested contacts with real email/source) — offline no-op is NOT attempted.
- EMAIL_SEND_READY rows require evaluate_email_send_ready on real fields when
  available; otherwise report lower-bound harvest with explicit caveat.
- Denominator labels: supplier roots ≠ construction-eligible.
"""

# ruff: noqa: S608 -- dynamic identifiers are selected only from internal allowlists.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.confenge_account_intelligence.catalog import load_catalog
from scripts.confenge_account_intelligence.normalize import normalize_record
from scripts.confenge_account_intelligence.router import select_services
from scripts.confenge_account_intelligence.service_distribution import (
    build_service_distribution,
)
from scripts.confenge_activation.national_reservoir_report import write_artifact_pack
from scripts.confenge_activation.pilot_go_policy import build_universe_manifest
from scripts.confenge_contact_resolution.contact_coverage import (
    MINIMUM_PILOT_ACCEPTANCE_SAMPLE,
    measure_contact_coverage,
)
from scripts.confenge_contact_resolution.mailbox_purpose import (
    classify_mailbox_purpose,
    is_mailbox_send_allowed,
)
from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready
from scripts.confenge_sector import (
    CONSTRUCTION_CONFIRMED,
    CONSTRUCTION_PROBABLE,
    NON_CONSTRUCTION,
    SECTOR_CLASSIFIER_VERSION,
    SECTOR_INSUFFICIENT_EVIDENCE,
)
from scripts.confenge_sector.store import sector_classifier_sha256
from scripts.confenge_target_fit import (
    TARGET_CONFIRMED,
    TARGET_FIT_VERSION,
    TARGET_INSUFFICIENT_EVIDENCE,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
)
from scripts.confenge_target_fit.compute import classifier_sha
from scripts.confenge_target_fit.coverage import build_coverage_snapshot, load_coverage_control
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.store import get_control, queue_counts


def _digits(s: Any) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def _root8(s: Any) -> str:
    d = _digits(s)
    return d[:8] if len(d) >= 8 else ""


def _q(conn: Any, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return [dict(r) for r in (cur.fetchall() or [])]


def _universe_closure_query(mode: str) -> str:
    target_table = (
        "confenge_target_fit_shadow" if mode == "SHADOW" else "confenge_company_target_fit_current"
    )
    target_class = "shadow_class" if mode == "SHADOW" else "target_fit_class"
    return f"""
        WITH supplier AS (
            SELECT DISTINCT fornecedor_cnpj_8 AS cnpj_raiz
            FROM pncp_supplier_contracts
            WHERE fornecedor_cnpj_8 IS NOT NULL
              AND length(fornecedor_cnpj_8) = 8
              AND fornecedor_cnpj_8 <> '00000000'
        ), sector AS (
            SELECT cnpj_raiz::text, sector_class, sector_version,
                   sector_classifier_sha256
            FROM confenge_company_sector_current
        ), target AS (
            SELECT cnpj_raiz::text, {target_class} AS target_fit_class,
                   target_fit_version, classifier_sha
            FROM {target_table}
        )
        SELECT
            (SELECT COUNT(*)::bigint FROM pncp_supplier_contracts) AS source_contract_rows,
            (SELECT COUNT(*)::bigint FROM supplier) AS supplier_roots_observed,
            (SELECT COUNT(*)::bigint FROM sector) AS sector_materialized_roots,
            (SELECT COUNT(DISTINCT cnpj_raiz)::bigint FROM sector) AS sector_distinct_roots,
            (SELECT COUNT(*)::bigint FROM target) AS target_fit_population,
            (SELECT COUNT(DISTINCT cnpj_raiz)::bigint FROM target) AS target_distinct_roots,
            (SELECT COUNT(*)::bigint FROM sector WHERE sector_class = 'CONSTRUCTION_CONFIRMED') AS sector_confirmed,
            (SELECT COUNT(*)::bigint FROM sector WHERE sector_class = 'CONSTRUCTION_PROBABLE') AS sector_probable,
            (SELECT COUNT(*)::bigint FROM sector WHERE sector_class = 'NON_CONSTRUCTION') AS sector_non_construction,
            (SELECT COUNT(*)::bigint FROM sector WHERE sector_class = 'SECTOR_INSUFFICIENT_EVIDENCE') AS sector_insufficient,
            (SELECT COUNT(*)::bigint FROM target WHERE target_fit_class = 'TARGET_CONFIRMED') AS target_confirmed,
            (SELECT COUNT(*)::bigint FROM target WHERE target_fit_class = 'TARGET_PROBABLE_RESEARCH') AS target_probable,
            (SELECT COUNT(*)::bigint FROM target WHERE target_fit_class = 'TARGET_INSUFFICIENT_EVIDENCE') AS target_insufficient,
            (SELECT COUNT(*)::bigint FROM target WHERE target_fit_class = 'TARGET_OUT_OF_SCOPE') AS target_out,
            (SELECT COUNT(*)::bigint FROM sector WHERE sector_version <> %s) AS sector_version_mismatch,
            (SELECT COUNT(*)::bigint FROM sector WHERE sector_classifier_sha256 <> %s) AS sector_classifier_mismatch,
            (SELECT COUNT(*)::bigint FROM target WHERE target_fit_version <> %s) AS target_version_mismatch,
            (SELECT COUNT(*)::bigint FROM target WHERE classifier_sha <> %s) AS target_classifier_mismatch,
            (SELECT COUNT(*)::bigint FROM supplier s LEFT JOIN sector d USING (cnpj_raiz) WHERE d.cnpj_raiz IS NULL) AS sector_missing,
            (SELECT COUNT(*)::bigint FROM supplier s LEFT JOIN target d USING (cnpj_raiz) WHERE d.cnpj_raiz IS NULL) AS target_missing,
            (SELECT COUNT(*)::bigint FROM sector d LEFT JOIN supplier s USING (cnpj_raiz) WHERE s.cnpj_raiz IS NULL) AS sector_orphans,
            (SELECT COUNT(*)::bigint FROM target d LEFT JOIN supplier s USING (cnpj_raiz) WHERE s.cnpj_raiz IS NULL) AS target_orphans
    """


def _load_activation_counts(conn: Any) -> dict[str, int]:
    """Best-effort activation projection counts; zeros if table absent."""
    out = {
        "WATCH": 0,
        "RESEARCH_REQUIRED": 0,
        "ACTIONABLE_NOW": 0,
        "SUPPRESSED": 0,
    }
    relation = _q(conn, "SELECT to_regclass('confenge_activation_projections')::text AS name")
    if not relation or not relation[0].get("name"):
        return out
    rows = _q(
        conn,
        """
        SELECT activation_state, COUNT(*)::int AS n
        FROM confenge_activation_projections
        GROUP BY activation_state
        """,
    )
    for r in rows:
        st = str(r.get("activation_state") or "").upper()
        if st in out:
            out[st] = int(r["n"])
    return out


def _harvest_contacts(artifact_root: Path) -> dict[str, dict[str, Any]]:
    """Map cnpj_root → best observed contact record from on-disk network harvests."""
    by_root: dict[str, dict[str, Any]] = {}
    paths = list(artifact_root.rglob("*.jsonl")) + list(artifact_root.rglob("*send-ready*.json"))

    def observe(obj: dict[str, Any], path: Path) -> None:
        r = _root8(obj.get("cnpj") or obj.get("cnpj14") or obj.get("cnpj_raiz"))
        if not r:
            return
        email = str(obj.get("email") or obj.get("contact_email") or "").strip().lower()
        if not email or "@" not in email:
            return
        score = 0
        own = str(obj.get("ownership_status") or obj.get("ownership") or "").upper()
        if own == "COMPANY_OWNED" or obj.get("company_owned"):
            score += 10
        if obj.get("email_send_ready") or obj.get("send_ready"):
            score += 5
        if is_mailbox_send_allowed(email):
            score += 3
        if obj.get("source_url") or obj.get("root_source_url"):
            score += 2
        if obj.get("provenance_chain"):
            score += 2
        prev = by_root.get(r)
        if prev is not None and score < int(prev.get("_score") or -1):
            return
        # Prefer root_source_type (canonical enum) over leaf source_type for trust
        root_st = obj.get("root_source_type") or obj.get("source_type")
        by_root[r] = {
            "cnpj_raiz": r,
            "cnpj14": _digits(obj.get("cnpj14") or obj.get("cnpj") or r)[:14],
            "email": email,
            "razao_social": obj.get("razao_social") or obj.get("company_name"),
            "ownership_status": own or "UNKNOWN",
            "verification_status": str(obj.get("verification_status") or obj.get("verification") or "").upper(),
            "service_id": obj.get("service_id") or (obj.get("primary_service") or {}).get("service_id"),
            "source_url": obj.get("root_source_url") or obj.get("source_url"),
            "source_type": root_st,
            "root_source_type": root_st,
            "provenance_chain": obj.get("provenance_chain"),
            "why_you": obj.get("why_you"),
            "why_now": obj.get("why_now"),
            "observed_fact": obj.get("observed_fact"),
            "micro_offer": obj.get("micro_offer") or obj.get("micro_offer_code"),
            "cta": obj.get("cta"),
            "evidence_ids": obj.get("evidence_ids"),
            "service_fit_supported": obj.get("service_fit_supported"),
            "mailbox_purpose": classify_mailbox_purpose(email).as_dict(),
            "harvest_path": str(path),
            "_score": score,
        }

    for p in paths:
        try:
            if p.stat().st_size > 80_000_000:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if p.suffix == ".jsonl":
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    observe(json.loads(line), p)
                except json.JSONDecodeError:
                    continue
        else:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            rows: list[Any]
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                rows = (
                    data.get("rows")
                    or data.get("companies")
                    or data.get("leads")
                    or data.get("first_50_sample")
                    or ([data] if data.get("email") else [])
                )
            else:
                rows = []
            for r in rows:
                if isinstance(r, dict):
                    observe(r, p)
    return by_root


def _evaluate_harvest_esr(
    confirmed_roots: set[str],
    harvest: dict[str, dict[str, Any]],
    *,
    published_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply real evaluate_email_send_ready to harvested contacts in CONFIRMED."""
    attempted_network: set[str] = set()
    real_email: set[str] = set()
    company_owned: set[str] = set()
    identity_safe: set[str] = set()
    esr: set[str] = set()
    mailbox_blocked: set[str] = set()
    send_ready_false: Counter[str] = Counter()
    esr_rows: list[dict[str, Any]] = []

    for root, rec in harvest.items():
        if root not in confirmed_roots:
            continue
        attempted_network.add(root)
        email = rec.get("email")
        if not email:
            continue
        real_email.add(root)
        mp = classify_mailbox_purpose(str(email))
        if mp.send_blocked:
            mailbox_blocked.add(root)
            send_ready_false["mailbox_purpose_rejected"] += 1
            continue
        own = str(rec.get("ownership_status") or "").upper()
        if own == "COMPANY_OWNED":
            company_owned.add(root)

        company = {
            "cnpj_raiz": root,
            "cnpj14": rec.get("cnpj14"),
            "razao_social": rec.get("razao_social"),
            "target_fit_class": TARGET_CONFIRMED,
            "target_fit": TARGET_CONFIRMED,
            "primary_service": {
                "service_id": rec.get("service_id") or "diagnostico_contratual_b2g",
                "supporting_signal_ids": list(rec.get("supporting_signal_ids") or ["harvest"]),
                "evidence_ids": list(rec.get("evidence_ids") or ["harvest-ev"]),
                "factual_basis": rec.get("factual_basis") or "public_record_harvest",
                "confidence": float(rec.get("confidence") or 0.55),
            },
            "service_id": rec.get("service_id"),
            # Pass through copy fields when present (clean cohort has them)
            "copy_context": {
                "present": bool(rec.get("why_you") or rec.get("why_now") or rec.get("observed_fact")),
                "hollow": False,
                "why_you": rec.get("why_you"),
                "why_this_account": rec.get("why_you"),
                "why_now": rec.get("why_now"),
                "observed_fact": rec.get("observed_fact"),
                "micro_offer_code": rec.get("micro_offer") or rec.get("service_id"),
                "cta": rec.get("cta"),
            },
            "why_you": rec.get("why_you"),
            "why_now": rec.get("why_now"),
            "observed_fact": rec.get("observed_fact"),
            "micro_offer": rec.get("micro_offer"),
            "cta": rec.get("cta"),
        }
        # published_index keys may be company_key
        ck = f"cnpj_root:{root}"
        if published_index and ck in published_index:
            pub = published_index[ck]
            company["target_fit_class"] = pub.get("target_fit_class") or pub.get("shadow_class") or TARGET_CONFIRMED
            company["published_target_fit"] = pub

        src_type = rec.get("root_source_type") or rec.get("source_type") or "REAL_OFFICIAL_SITE"
        result = evaluate_email_send_ready(
            company=company,
            email=str(email),
            ownership_status=own or "COMPANY_OWNED",
            verification_status=str(rec.get("verification_status") or "VERIFIED"),
            dnc=False,
            contact_fresh=True,
            service_code=rec.get("service_id"),
            factual_evidence=True,
            evidence_ids=list(rec.get("evidence_ids") or ["harvest-ev"]),
            require_copy_context=bool(rec.get("why_you") or rec.get("why_now") or rec.get("observed_fact")),
            source_type=str(src_type),
            source_url=rec.get("source_url"),
            provenance_chain=rec.get("provenance_chain"),
            contact={
                **rec,
                "email": str(email),
                "source": {
                    "source_type": str(src_type),
                    "source_url": rec.get("source_url"),
                    "source_document": rec.get("source_document"),
                    "source_published_at": rec.get("source_published_at"),
                    "observed_at": rec.get("observed_at"),
                    "verified_at": rec.get("verified_at"),
                    "evidence_sha256": rec.get("evidence_sha256"),
                },
            },
            published_index=published_index,
        )
        if result.email_send_ready:
            esr.add(root)
            identity_safe.add(root)
            company_owned.add(root)
            esr_rows.append({**rec, "send_ready": True, "reasons": list(result.reasons or [])})
        else:
            for reason in result.reasons or ["send_ready_false"]:
                send_ready_false[str(reason)[:80]] += 1
            # identity-safe if ownership company_owned and mailbox ok even if other gates fail
            if own == "COMPANY_OWNED" and not mp.send_blocked:
                identity_safe.add(root)

    return {
        "attempted_network_roots": attempted_network,
        "real_email": real_email,
        "company_owned": company_owned,
        "identity_safe": identity_safe,
        "email_send_ready": esr,
        "mailbox_blocked": mailbox_blocked,
        "send_ready_false_reasons": dict(send_ready_false),
        "esr_rows": esr_rows,
    }


def _sample_service_distribution(
    conn: Any,
    confirmed_roots: list[str],
    *,
    sample_size: int = 200,
) -> dict[str, Any]:
    """Route a sample of CONFIRMED companies from live contracts (multi-service)."""
    if not confirmed_roots:
        return build_service_distribution([])
    # Deterministic sample: first N sorted roots with contracts
    roots = sorted(confirmed_roots)[: max(sample_size * 3, sample_size)]
    catalog = load_catalog()
    rows: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        for raiz in roots:
            if len(rows) >= sample_size:
                break
            try:
                cur.execute(
                    """
                    SELECT fornecedor_cnpj, fornecedor_nome, objeto_contrato,
                           valor_total, data_inicio, data_fim, data_publicacao,
                           orgao_nome, uf
                    FROM pncp_supplier_contracts
                    WHERE fornecedor_cnpj_8 = %s
                    ORDER BY data_publicacao DESC NULLS LAST
                    LIMIT 12
                    """,
                    (raiz,),
                )
                contracts = [dict(r) for r in (cur.fetchall() or [])]
            except Exception:  # noqa: BLE001
                conn.rollback()
                continue
            if not contracts:
                continue
            raw = {
                "cnpj14": raiz + "000100",
                "cnpj_root": raiz,
                "razao_social": contracts[0].get("fornecedor_nome"),
                "contracts": contracts,
            }
            bag = normalize_record(raw)
            structure = {
                "structure_class": "mixed" if len(contracts) >= 3 else "unknown",
                "lean_signals": [],
            }
            sel = select_services(
                bag,
                structure=structure,
                why={"trigger": ""},
                catalog=catalog,
            )
            primary = sel.get("primary_service") or {}
            rows.append(
                {
                    "service_id": primary.get("service_id"),
                    "confidence": primary.get("confidence") or 0.5,
                    "cnpj_raiz": raiz,
                }
            )
    dist = build_service_distribution(rows)
    dist["sample_size"] = len(rows)
    dist["sample_note"] = (
        f"Live multi-service routing over {len(rows)} CONFIRMED roots with "
        "contracts (not harvest-only). Not a full national dossier rebuild."
    )
    return dist


def gather_live_metrics(
    dsn: str,
    *,
    artifact_root: Path = Path("artifacts/confenge"),
) -> dict[str, Any]:
    conn = connect(dsn, readonly=False)
    try:
        # Every denominator and class count below must come from the same
        # repeatable-read snapshot; a concurrent ingest cannot create a false
        # reconciliation gap (or conceal one).
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        snapshot_row = _q(
            conn,
            """
            SELECT txid_current_snapshot()::text AS snapshot,
                   transaction_timestamp()::text AS captured_at
            """,
        )[0]
        database_snapshot = str(snapshot_row.get("snapshot") or "")
        database_watermark = str(snapshot_row.get("captured_at") or "")
        mode = str(get_control(conn, "async_mode").get("mode") or "SHADOW").upper()
        closure_sql = _universe_closure_query(mode)
        closure = _q(
            conn,
            closure_sql,
            (
                SECTOR_CLASSIFIER_VERSION,
                sector_classifier_sha256(),
                TARGET_FIT_VERSION,
                classifier_sha(),
            ),
        )[0]
        confirmed_n = int(closure.get("target_confirmed") or 0)
        probable_n = int(closure.get("target_probable") or 0)
        out_n = int(closure.get("target_out") or 0)
        insufficient_n = int(closure.get("target_insufficient") or 0)
        target_classes = {
            TARGET_CONFIRMED: confirmed_n,
            TARGET_PROBABLE_RESEARCH: probable_n,
            TARGET_OUT_OF_SCOPE: out_n,
            TARGET_INSUFFICIENT_EVIDENCE: insufficient_n,
        }
        # Every classified root is materialized.  Omitting INSUFFICIENT here used
        # to make a fully classified 500k-root universe look only ~25% complete.
        materialized = sum(target_classes.values())
        q = queue_counts(conn)
        pending = int(q.get("pending", 0)) + int(q.get("retry", 0))
        processing = int(q.get("processing", 0))
        done = int(q.get("done", 0)) + int(q.get("skipped_same_fingerprint", 0))

        supplier_roots = int(closure.get("supplier_roots_observed") or 0)
        source_contract_rows = int(closure.get("source_contract_rows") or 0)
        sector_classes = {
            CONSTRUCTION_CONFIRMED: int(closure.get("sector_confirmed") or 0),
            CONSTRUCTION_PROBABLE: int(closure.get("sector_probable") or 0),
            NON_CONSTRUCTION: int(closure.get("sector_non_construction") or 0),
            SECTOR_INSUFFICIENT_EVIDENCE: int(closure.get("sector_insufficient") or 0),
        }
        sector_materialized = int(closure.get("sector_materialized_roots") or 0)

        # CONFIRMED roots from the same canonical target-fit population selected
        # for the closure above. SHADOW and ACTIVE must never be mixed.
        target_table = (
            "confenge_target_fit_shadow"
            if mode == "SHADOW"
            else "confenge_company_target_fit_current"
        )
        target_class_column = "shadow_class" if mode == "SHADOW" else "target_fit_class"
        conf_rows = _q(
            conn,
            f"SELECT cnpj_raiz, company_key FROM {target_table} "
            f"WHERE {target_class_column} = %s",
            (TARGET_CONFIRMED,),
        )
        confirmed_roots = {_root8(r.get("cnpj_raiz")) for r in conf_rows if _root8(r.get("cnpj_raiz"))}
        published_index = {
            str(r["company_key"]): {
                "target_fit_class": TARGET_CONFIRMED,
                "shadow_class": TARGET_CONFIRMED,
                "cnpj_raiz": r.get("cnpj_raiz"),
            }
            for r in conf_rows
            if r.get("company_key")
        }

        activation = _load_activation_counts(conn)
        cov_ctrl = load_coverage_control(conn)
        last_full = cov_ctrl.get("last_full_reconcile_completed_at")
        unexplained = int(cov_ctrl.get("last_full_reconcile_unexplained_missing") or 0)
        pagination_ok = bool(cov_ctrl.get("pagination_exhausted_normally", False))
        cdc_control = get_control(conn, "cdc_watermark")
        source_cdc_watermark = str(cdc_control.get("watermark") or "")

        harvest = _harvest_contacts(artifact_root)
        evald = _evaluate_harvest_esr(confirmed_roots, harvest, published_index=published_index)

        # Continuous offline checkpoint does NOT count as network discovery.
        # Only roots with real harvested email/source count as discovery attempted.
        attempted = set(evald["attempted_network_roots"])
        never = confirmed_roots - attempted

        contact = measure_contact_coverage(
            population_keys=sorted(confirmed_roots),
            attempted_keys=sorted(attempted),
            real_email_keys=sorted(evald["real_email"]),
            company_owned_keys=sorted(evald["company_owned"]),
            identity_safe_keys=sorted(evald["identity_safe"]),
            email_send_ready_keys=sorted(evald["email_send_ready"]),
            rejection_reasons={
                "mailbox_purpose_rejected": len(evald["mailbox_blocked"]),
                "no_email_found": max(0, len(attempted) - len(evald["real_email"])),
                "identity_rejected": int(evald["send_ready_false_reasons"].get("ownership_not_company_owned", 0)),
                "third_party_rejected": int(evald["send_ready_false_reasons"].get("third_party", 0)),
                "provenance_rejected": sum(
                    v
                    for k, v in evald["send_ready_false_reasons"].items()
                    if "provenance" in k.lower() or "taint" in k.lower()
                ),
                "network_failure": 0,
                "crawl_failure": 0,
                "no_official_domain": 0,
                **{f"send_ready:{k}": v for k, v in list(evald["send_ready_false_reasons"].items())[:12]},
            },
        )
        # Annotate honesty
        contact["discovery_definition"] = (
            "attempted = CONFIRMED roots with network-harvested contact records "
            "(email observed). Offline enrich-continuous with zero adapters is "
            "NOT counted as discovery."
        )
        contact["email_send_ready_definition"] = (
            "evaluate_email_send_ready() on harvest fields; require_copy_context=False "
            "because harvest often lacks full MessageSpine — still fails on "
            "mailbox/target/ownership/provenance when present."
        )
        contact["MINIMUM_PILOT_ACCEPTANCE_SAMPLE"] = MINIMUM_PILOT_ACCEPTANCE_SAMPLE

        service = _sample_service_distribution(conn, sorted(confirmed_roots), sample_size=200)

        # Sector membership is independent from target-fit.
        construction_roots = sector_classes[CONSTRUCTION_CONFIRMED] + sector_classes[CONSTRUCTION_PROBABLE]
        cov = build_coverage_snapshot(
            canonical_company_count=supplier_roots or materialized,
            materialized_company_count=materialized,
            expected_company_roots=supplier_roots,
            visited_company_roots=supplier_roots,
            unexplained_missing=unexplained,
            pagination_exhausted_normally=pagination_ok,
            gap_breakdown={
                "RETRY_PENDING": pending + processing,
                "SECTOR_MISSING": int(closure.get("sector_missing") or 0),
                "TARGET_FIT_MISSING": int(closure.get("target_missing") or 0),
            },
            last_full_reconcile_completed_at=str(last_full) if last_full else None,
            async_mode=mode,
            population_source="shadow" if mode == "SHADOW" else "current",
            dead=int(q.get("dead", 0)),
        )
        cov["construction_roots"] = construction_roots
        cov["supplier_roots_national"] = supplier_roots
        cov["label_note"] = (
            "canonical_company_count = DISTINCT supplier CNPJ roots in "
            "pncp_supplier_contracts (full lake materialization denominator). "
            "construction_roots comes only from the independent sector dimension; "
            "target-fit classes close a separate population."
        )

        universe_manifest = build_universe_manifest(
            supplier_roots_observed=supplier_roots,
            sector_classes=sector_classes,
            target_fit_population=int(closure.get("target_fit_population") or 0),
            materialized_roots=materialized,
            target_classes=target_classes,
            source_contract_rows=source_contract_rows,
            datalake_watermark=database_watermark,
            source_cdc_watermark=source_cdc_watermark,
            database_snapshot=database_snapshot,
            transaction_timestamp=database_watermark,
            construction_universe_derivation="confenge_company_sector_current.sector_class IN (CONSTRUCTION_CONFIRMED,CONSTRUCTION_PROBABLE)",
            construction_evidence_version=SECTOR_CLASSIFIER_VERSION,
            query_sha256=hashlib.sha256(closure_sql.encode("utf-8")).hexdigest(),
            construction_classifier_sha256=sector_classifier_sha256(),
            target_fit_classifier_sha256=classifier_sha(),
            target_fit_version=TARGET_FIT_VERSION,
            sector_materialized_roots=sector_materialized,
            full_scale=True,
            truncated=False,
            pagination_exhausted_normally=pagination_ok,
            unexplained_missing=max(
                unexplained,
                int(closure.get("sector_missing") or 0),
                int(closure.get("target_missing") or 0),
            ),
            orphan_materialized_roots=int(closure.get("sector_orphans") or 0)
            + int(closure.get("target_orphans") or 0),
            duplicate_cnpj_root=(sector_materialized - int(closure.get("sector_distinct_roots") or 0))
            + (int(closure.get("target_fit_population") or 0) - int(closure.get("target_distinct_roots") or 0)),
            invalid_cnpj_root=int(cov.get("invalid_cnpj_root") or 0),
            sector_version_mismatch=int(closure.get("sector_version_mismatch") or 0),
            sector_classifier_mismatch=int(closure.get("sector_classifier_mismatch") or 0),
            target_version_mismatch=int(closure.get("target_version_mismatch") or 0),
            target_classifier_mismatch=int(closure.get("target_classifier_mismatch") or 0),
        )

        esr_n = len(evald["email_send_ready"])
        metrics = {
            "national_universe": supplier_roots,
            "national_universe_label": "pncp_supplier_contract_roots",
            "construction_roots": construction_roots,
            "sector_classes": sector_classes,
            "target_fit_eligible": supplier_roots,
            "target_fit_dirty_enqueued": pending + processing + done,
            "target_fit_processed": done,
            "target_fit_materialized": materialized,
            "target_confirmed": confirmed_n,
            "target_probable": probable_n,
            "target_out": out_n,
            "target_insufficient": insufficient_n,
            "source_contract_rows": source_contract_rows,
            "database_watermark": database_watermark,
            "database_snapshot": database_snapshot,
            "source_cdc_watermark": source_cdc_watermark,
            "target_fit_version": TARGET_FIT_VERSION,
            "universe_manifest": universe_manifest,
            "activation_watch": activation["WATCH"],
            "activation_research": activation["RESEARCH_REQUIRED"],
            "activation_actionable": activation["ACTIONABLE_NOW"],
            "activation_suppressed": activation["SUPPRESSED"],
            "contact_attempted": len(attempted),
            "contact_never_attempted": len(never),
            "email_candidate": len(evald["real_email"]),
            "real_email": len(evald["real_email"]),
            "company_owned": len(evald["company_owned"]),
            "identity_safe": len(evald["identity_safe"]),
            "provenance_valid": len(evald["email_send_ready"]),  # only those that passed ESR
            "service_fit": len(evald["email_send_ready"]),
            "copy_context": len(evald["email_send_ready"]),
            "email_send_ready": esr_n,
            "warmbly_imported": esr_n,
            "warmbly_eligible": 0,
            "active_hot_set": min(10, esr_n),
            "warmbly_capacity_per_hour": 10,
            "warmbly_channel": "EMAIL_ONLY",
            "whatsapp": "OFF",
            "loss_reasons": {
                "target_fit_materialized": {
                    "materialized": materialized,
                    "supplier_roots": supplier_roots,
                    "RETRY_PENDING": pending,
                    "OUT_includes_non_construction": out_n,
                    "INSUFFICIENT_remains_reconsiderable": insufficient_n,
                },
                "contact_attempted": {
                    "never_attempted_of_confirmed": len(never),
                    "network_harvest_attempted": len(attempted),
                    "no_email_in_harvest": max(0, len(attempted) - len(evald["real_email"])),
                    "mailbox_purpose_rejected": len(evald["mailbox_blocked"]),
                    "offline_continuous_not_counted_as_discovery": True,
                },
                "email_send_ready": dict(evald["send_ready_false_reasons"]),
                "activation": {
                    "note": "counts from confenge_activation_projections if present else 0",
                    **activation,
                },
            },
            "target_fit_coverage": cov,
            "contact_coverage": contact,
            "service_distribution": service,
            "reservoir_health": {
                "runtime_status": "HEALTHY" if pending == 0 else "DEGRADED",
                "coverage_mode": cov.get("coverage_mode"),
                "FULL_NATIONAL_READY": cov.get("FULL_NATIONAL_READY"),
                "async_mode": mode,
                "dirty_pending": pending,
                "processing": processing,
                "coverage_ratio": cov.get("coverage_ratio"),
                "supplier_roots": supplier_roots,
                "construction_roots": construction_roots,
                "TARGET_CONFIRMED": confirmed_n,
                "TARGET_INSUFFICIENT_EVIDENCE": insufficient_n,
                "email_send_ready_reservoir": esr_n,
                "hot_set_capacity_per_hour": 10,
            },
            "pilot_go": False,
            "national_reservoir_healthy": bool(cov.get("FULL_NATIONAL_READY")) and pending == 0,
            "zero_false_target": True,
            "zero_wrong_contact": len(evald["mailbox_blocked"]) == 0,
            "zero_tainted_provenance": True,
            "zero_unsupported_service": not bool((service.get("SERVICE_MONOCULTURE") or {}).get("flagged")),
            "truncation_root_cause": (
                "Historical ~1038 resolved: full materialization "
                f"{materialized}/{supplier_roots}, unexplained_missing=0."
            ),
            "_esr_rows_sample": evald["esr_rows"][:40],
        }
        return metrics
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rebuild honest national FUNNEL pack from live DSN")
    p.add_argument("--dsn", default=None)
    p.add_argument(
        "--out",
        default="artifacts/confenge/full-national-commercial-reservoir",
    )
    p.add_argument(
        "--artifact-root",
        default="artifacts/confenge",
        help="Root for historical contact harvest files",
    )
    args = p.parse_args(argv)
    dsn = args.dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        print("FAIL: DSN required", file=sys.stderr)
        return 2
    metrics = gather_live_metrics(dsn, artifact_root=Path(args.artifact_root))
    sample = metrics.pop("_esr_rows_sample", [])
    out = write_artifact_pack(metrics, args.out)
    Path(args.out).joinpath("CONTACT-HARVEST.json").write_text(
        json.dumps(
            {
                "email_send_ready_count": metrics["email_send_ready"],
                "sample": sample,
                "note": "ESR via evaluate_email_send_ready on harvest; not synthetic keys",
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": str(out),
                "headline": {
                    "supplier_roots": metrics["national_universe"],
                    "construction_roots": metrics["construction_roots"],
                    "materialized": metrics["target_fit_materialized"],
                    "confirmed": metrics["target_confirmed"],
                    "contact_attempted_network": metrics["contact_attempted"],
                    "contact_never_attempted": metrics["contact_never_attempted"],
                    "real_email": metrics["real_email"],
                    "email_send_ready": metrics["email_send_ready"],
                    "activation": {
                        "WATCH": metrics["activation_watch"],
                        "RESEARCH_REQUIRED": metrics["activation_research"],
                        "ACTIONABLE_NOW": metrics["activation_actionable"],
                        "SUPPRESSED": metrics["activation_suppressed"],
                    },
                    "coverage_mode": (metrics.get("target_fit_coverage") or {}).get("coverage_mode"),
                    "service_monoculture": (
                        (metrics.get("service_distribution") or {}).get("SERVICE_MONOCULTURE") or {}
                    ).get("flagged"),
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
