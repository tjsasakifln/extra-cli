"""Entity linkage pipeline — golden records + auditable links on isolated DSN."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from scripts.linkage import RULE_VERSION
from scripts.linkage.isolation import assert_isolated, mask_dsn
from scripts.linkage.keys import (
    extract_organ_keys,
    extract_person_keys,
    organ_canonical_key,
    supplier_canonical_key,
)
from scripts.linkage.resolve import (
    LinkDecision,
    MatchMetrics,
    decide_contract_to_opportunity,
    decide_opportunity_organ,
    decide_supplier_from_contract,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return None


def connect(dsn: str) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def _json_adapt(value: Any) -> Any:
    from psycopg2.extras import Json

    return Json(value)


@dataclass
class PipelineResult:
    run_id: str
    as_of: str
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    dsn_masked: str = ""
    production_touched: bool = False
    errors: list[str] = field(default_factory=list)
    sample_investigation: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "as_of": self.as_of,
            "status": self.status,
            "metrics": self.metrics,
            "dsn_masked": self.dsn_masked,
            "production_touched": self.production_touched,
            "errors": self.errors,
            "sample_investigation": self.sample_investigation,
            "rule_version": RULE_VERSION,
        }


def _upsert_organ(cur: Any, keys: Any, run_id: str, source: str, source_ids: list[str]) -> str | None:
    ck = organ_canonical_key(keys)
    if not ck:
        return None
    cur.execute(
        """
        INSERT INTO canonical_organs (
            canonical_key, entity_kind, cnpj14, cnpj8, ibge_code,
            raw_name, normalized_name, source, source_record_ids,
            decision_history, first_seen_run_id, last_seen_run_id, updated_at
        ) VALUES (
            %s, 'organ', %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, now()
        )
        ON CONFLICT (canonical_key) DO UPDATE SET
            cnpj14 = COALESCE(EXCLUDED.cnpj14, canonical_organs.cnpj14),
            cnpj8 = COALESCE(EXCLUDED.cnpj8, canonical_organs.cnpj8),
            ibge_code = COALESCE(EXCLUDED.ibge_code, canonical_organs.ibge_code),
            raw_name = CASE
                WHEN canonical_organs.raw_name = '' THEN EXCLUDED.raw_name
                ELSE canonical_organs.raw_name
            END,
            last_seen_run_id = EXCLUDED.last_seen_run_id,
            updated_at = now()
        RETURNING canonical_key
        """,
        (
            ck,
            keys.cnpj14,
            keys.cnpj8,
            keys.ibge7,
            keys.raw_name or ck,
            keys.normalized_name or ck,
            source,
            _json_adapt(source_ids),
            _json_adapt([{"run_id": run_id, "action": "upsert", "rule": RULE_VERSION}]),
            run_id,
            run_id,
        ),
    )
    row = cur.fetchone()
    return row["canonical_key"] if row else ck


def _upsert_supplier(cur: Any, keys: Any, run_id: str, source: str, source_ids: list[str]) -> str | None:
    ck = supplier_canonical_key(keys)
    if not ck:
        return None
    person_kind = "cnpj" if keys.cnpj14 or keys.cnpj8 else ("cpf" if keys.cpf11 else "unknown")
    cur.execute(
        """
        INSERT INTO canonical_suppliers (
            canonical_key, person_kind, cnpj14, cnpj8, cpf11,
            raw_name, normalized_name, source, source_record_ids,
            decision_history, first_seen_run_id, last_seen_run_id, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, now()
        )
        ON CONFLICT (canonical_key) DO UPDATE SET
            cnpj14 = COALESCE(EXCLUDED.cnpj14, canonical_suppliers.cnpj14),
            cnpj8 = COALESCE(EXCLUDED.cnpj8, canonical_suppliers.cnpj8),
            cpf11 = COALESCE(EXCLUDED.cpf11, canonical_suppliers.cpf11),
            last_seen_run_id = EXCLUDED.last_seen_run_id,
            updated_at = now()
        RETURNING canonical_key
        """,
        (
            ck,
            person_kind,
            keys.cnpj14,
            keys.cnpj8,
            keys.cpf11,
            keys.raw_name or ck,
            keys.normalized_name or ck,
            source,
            _json_adapt(source_ids),
            _json_adapt([{"run_id": run_id, "action": "upsert", "rule": RULE_VERSION}]),
            run_id,
            run_id,
        ),
    )
    row = cur.fetchone()
    return row["canonical_key"] if row else ck


def _insert_decision_row(
    cur: Any,
    table: str,
    run_id: str,
    decision: LinkDecision,
    **cols: Any,
) -> None:
    if table == "opportunity_organ_links":
        cur.execute(
            """
            INSERT INTO opportunity_organ_links (
                run_id, opportunity_id, organ_canonical_key, classification,
                score, reason_codes, claim_level, source_record_ids, rule_version
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                run_id,
                cols["opportunity_id"],
                decision.target_key,
                decision.classification,
                decision.score,
                list(decision.reason_codes),
                decision.claim_level,
                json.dumps(list(decision.source_record_ids)),
                decision.rule_version,
            ),
        )
    elif table == "opportunity_contract_links":
        cur.execute(
            """
            INSERT INTO opportunity_contract_links (
                run_id, opportunity_id, contract_id, organ_canonical_key,
                supplier_canonical_key, classification, score, reason_codes,
                claim_level, non_claims, source_record_ids, rule_version
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (run_id, opportunity_id, contract_id) DO NOTHING
            """,
            (
                run_id,
                cols["opportunity_id"],
                cols["contract_id"],
                cols.get("organ_canonical_key") or decision.target_key,
                cols.get("supplier_canonical_key"),
                decision.classification,
                decision.score,
                list(decision.reason_codes),
                decision.claim_level,
                list(decision.non_claims or ()),
                json.dumps(list(decision.source_record_ids)),
                decision.rule_version,
            ),
        )
    elif table == "observed_supplier_relations":
        cur.execute(
            """
            INSERT INTO observed_supplier_relations (
                run_id, opportunity_id, organ_canonical_key, supplier_canonical_key,
                contract_id, relation_kind, classification, score, reason_codes,
                claim_level, non_claims, source_record_ids, rule_version
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT DO NOTHING
            """,
            (
                run_id,
                cols.get("opportunity_id"),
                cols.get("organ_canonical_key"),
                decision.target_key,
                cols.get("contract_id"),
                cols.get("relation_kind", "historical_winner"),
                decision.classification,
                decision.score,
                list(decision.reason_codes),
                decision.claim_level,
                list(decision.non_claims or ()),
                json.dumps(list(decision.source_record_ids)),
                decision.rule_version,
            ),
        )

    if decision.classification in ("heuristic_reviewable", "ambiguous"):
        cur.execute(
            """
            INSERT INTO entity_linkage_review_queue (
                run_id, subject_type, subject_id, classification, score,
                reason_codes, payload, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'open')
            """,
            (
                run_id,
                table,
                str(cols.get("opportunity_id") or cols.get("contract_id") or ""),
                decision.classification,
                decision.score,
                list(decision.reason_codes),
                json.dumps(decision.as_dict()),
            ),
        )


def run_linkage(
    dsn: str,
    *,
    run_id: str | None = None,
    snapshot_id: str | None = None,
    snapshot_hash: str | None = None,
    contract_limit_per_opp: int = 50,
    max_opportunities: int | None = None,
) -> PipelineResult:
    """Execute one identified linkage run on an isolated DSN."""
    iso = assert_isolated(dsn)
    rid = run_id or f"link-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    as_of = _utc_now()
    result = PipelineResult(
        run_id=rid,
        as_of=as_of.isoformat().replace("+00:00", "Z"),
        status="running",
        dsn_masked=iso.dsn_masked,
        production_touched=False,
    )

    organ_m = MatchMetrics()
    contract_m = MatchMetrics()
    supplier_m = MatchMetrics()

    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO entity_linkage_runs (
                    run_id, as_of, git_sha, schema_version, rule_version,
                    snapshot_id, snapshot_hash, status, production_touched
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'running',false)
                ON CONFLICT (run_id) DO UPDATE SET status = 'running', started_at = now()
                """,
                (
                    rid,
                    as_of,
                    _git_sha(),
                    "061",
                    RULE_VERSION,
                    snapshot_id,
                    snapshot_hash,
                ),
            )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, orgao_cnpj, orgao_nome, objeto, uf, municipio,
                       numero_controle_pncp, status_canonico AS status, codigo_ibge
                FROM opportunity_intel
                WHERE COALESCE(is_active, TRUE) IS TRUE
                ORDER BY id
                """
                + (f" LIMIT {int(max_opportunities)}" if max_opportunities else "")
            )
            opportunities = list(cur.fetchall())

        if not opportunities:
            # Fail closed when no universe of open opportunities
            result.status = "failed"
            result.errors.append("no_eligible_open_opportunities")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE entity_linkage_runs
                    SET status='failed', finished_at=now(),
                        metrics=%s::jsonb
                    WHERE run_id=%s
                    """,
                    (
                        json.dumps(
                            {
                                "error": "no_eligible_open_opportunities",
                                "fail_closed": True,
                            }
                        ),
                        rid,
                    ),
                )
            conn.commit()
            result.metrics = {"fail_closed": True, "error": "no_eligible_open_opportunities"}
            return result

        for opp in opportunities:
            oid = int(opp["id"])
            src_id = f"opportunity_intel:{oid}"
            okeys = extract_organ_keys(
                opp.get("orgao_cnpj"),
                opp.get("orgao_nome"),
                opp.get("codigo_ibge"),
                opp.get("numero_controle_pncp"),
            )
            d_org = decide_opportunity_organ(
                opp.get("orgao_cnpj"),
                opp.get("orgao_nome"),
                opp_ibge=opp.get("codigo_ibge"),
                pncp_control=opp.get("numero_controle_pncp"),
                source_record_id=src_id,
            )
            organ_m.observe(d_org)

            with conn.cursor() as cur:
                if d_org.target_key and d_org.auto_accept:
                    _upsert_organ(cur, okeys, rid, "opportunity_intel", [src_id])
                _insert_decision_row(
                    cur,
                    "opportunity_organ_links",
                    rid,
                    d_org,
                    opportunity_id=oid,
                )

                # Related historical contracts by same organ CNPJ root
                organ_digits = "".join(ch for ch in str(opp.get("orgao_cnpj") or "") if ch.isdigit())
                if len(organ_digits) >= 8:
                    cur.execute(
                        """
                        SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj,
                               fornecedor_nome, objeto_contrato, uf, valor_total,
                               data_publicacao, data_assinatura
                        FROM pncp_supplier_contracts
                        WHERE orgao_cnpj_8 = %s
                          AND COALESCE(is_active, TRUE) IS TRUE
                        ORDER BY COALESCE(data_publicacao, data_assinatura) DESC NULLS LAST
                        LIMIT %s
                        """,
                        (organ_digits[:8], contract_limit_per_opp),
                    )
                    contracts = list(cur.fetchall())
                else:
                    contracts = []

                if not contracts and not d_org.auto_accept:
                    # explicit unresolved path already recorded
                    pass

                for ctr in contracts:
                    d_ctr = decide_contract_to_opportunity(
                        opp_organ_cnpj=opp.get("orgao_cnpj"),
                        opp_organ_name=opp.get("orgao_nome"),
                        opp_objeto=opp.get("objeto"),
                        opp_uf=opp.get("uf"),
                        contract_organ_cnpj=ctr.get("orgao_cnpj"),
                        contract_organ_name=ctr.get("orgao_nome"),
                        contract_objeto=ctr.get("objeto_contrato"),
                        contract_uf=ctr.get("uf"),
                        contract_id=ctr.get("contrato_id"),
                        supplier_cnpj=ctr.get("fornecedor_cnpj"),
                    )
                    contract_m.observe(d_ctr)

                    skeys = extract_person_keys(ctr.get("fornecedor_cnpj"), ctr.get("fornecedor_nome"))
                    d_sup = decide_supplier_from_contract(
                        ctr.get("fornecedor_cnpj"),
                        ctr.get("fornecedor_nome"),
                        contract_id=ctr.get("contrato_id"),
                    )
                    supplier_m.observe(d_sup)
                    sup_key = None
                    if d_sup.target_key and d_sup.auto_accept:
                        sup_key = _upsert_supplier(
                            cur,
                            skeys,
                            rid,
                            "pncp_supplier_contracts",
                            [f"contract:{ctr.get('contrato_id')}"],
                        )

                    if d_ctr.classification != "unresolved" or d_ctr.score > 0:
                        _insert_decision_row(
                            cur,
                            "opportunity_contract_links",
                            rid,
                            d_ctr,
                            opportunity_id=oid,
                            contract_id=ctr.get("contrato_id"),
                            organ_canonical_key=d_org.target_key,
                            supplier_canonical_key=sup_key or d_sup.target_key,
                        )
                    if d_sup.auto_accept and d_sup.target_key:
                        _insert_decision_row(
                            cur,
                            "observed_supplier_relations",
                            rid,
                            d_sup,
                            opportunity_id=oid,
                            organ_canonical_key=d_org.target_key,
                            contract_id=ctr.get("contrato_id"),
                            relation_kind="historical_winner",
                        )

            conn.commit()

        metrics = {
            "opportunities": len(opportunities),
            "organ_links": organ_m.as_dict(),
            "contract_links": contract_m.as_dict(),
            "supplier_links": supplier_m.as_dict(),
            "rule_version": RULE_VERSION,
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot_hash,
            "dsn_masked": mask_dsn(dsn),
            "production_touched": False,
        }

        # Build sample investigation for first opportunity with any contract link
        sample = investigate_opportunity(conn, rid, int(opportunities[0]["id"]))
        result.sample_investigation = sample

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE entity_linkage_runs
                SET status='completed', finished_at=now(), metrics=%s::jsonb
                WHERE run_id=%s
                """,
                (json.dumps(metrics), rid),
            )
        conn.commit()
        result.status = "completed"
        result.metrics = metrics
        return result
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        result.status = "failed"
        result.errors.append(str(exc))
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE entity_linkage_runs
                    SET status='failed', finished_at=now(),
                        metrics=%s::jsonb
                    WHERE run_id=%s
                    """,
                    (json.dumps({"error": str(exc)}), rid),
                )
            conn.commit()
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        conn.close()


def investigate_opportunity(conn: Any, run_id: str, opportunity_id: int) -> dict[str, Any]:
    """Direct investigation: opportunity → organ → contracts → observed suppliers."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, orgao_cnpj, orgao_nome, objeto, uf, municipio,
                   numero_controle_pncp, status_canonico, valor_estimado
            FROM opportunity_intel WHERE id = %s
            """,
            (opportunity_id,),
        )
        opp = cur.fetchone()
        cur.execute(
            """
            SELECT classification, score, reason_codes, claim_level,
                   organ_canonical_key, source_record_ids, rule_version
            FROM opportunity_organ_links
            WHERE run_id = %s AND opportunity_id = %s
            ORDER BY score DESC
            """,
            (run_id, opportunity_id),
        )
        organs = list(cur.fetchall())
        cur.execute(
            """
            SELECT contract_id, classification, score, reason_codes, claim_level,
                   non_claims, organ_canonical_key, supplier_canonical_key, rule_version
            FROM opportunity_contract_links
            WHERE run_id = %s AND opportunity_id = %s
            ORDER BY score DESC, contract_id
            LIMIT 100
            """,
            (run_id, opportunity_id),
        )
        contracts = list(cur.fetchall())
        cur.execute(
            """
            SELECT supplier_canonical_key, relation_kind, classification, score,
                   reason_codes, claim_level, non_claims, contract_id
            FROM observed_supplier_relations
            WHERE run_id = %s AND opportunity_id = %s
            ORDER BY score DESC
            LIMIT 100
            """,
            (run_id, opportunity_id),
        )
        suppliers = list(cur.fetchall())

    def _ser(rows: list[Any]) -> list[dict[str, Any]]:
        out = []
        for r in rows:
            d = dict(r)
            for k, v in list(d.items()):
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            out.append(d)
        return out

    has_data = bool(organs or contracts or suppliers)
    return {
        "run_id": run_id,
        "opportunity_id": opportunity_id,
        "opportunity": dict(opp) if opp else None,
        "organs": _ser(organs),
        "contracts": _ser(contracts),
        "observed_suppliers": _ser(suppliers),
        "status": "OK" if has_data else "INSUFFICIENT",
        "claims": [
            "organ_identity_from_official_keys" if organs else None,
            "historical_contracts_same_organ" if contracts else None,
            "observed_contract_winners_only" if suppliers else None,
        ],
        "non_claims": [
            "not_observed_participant_of_open_tender",
            "not_inferred_consortium",
            "not_win_rate",
            "similarity_is_not_participation",
        ],
        "fail_closed_if_empty": not has_data,
    }


def investigate_inverse_supplier(conn: Any, run_id: str, supplier_key_or_cnpj: str) -> dict[str, Any]:
    """Inverse: supplier → contracts/organs/opportunities linked in this run."""
    key = supplier_key_or_cnpj.strip()
    digits = "".join(ch for ch in key if ch.isdigit())
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM observed_supplier_relations
            WHERE run_id = %s
              AND (
                supplier_canonical_key = %s
                OR supplier_canonical_key LIKE %s
                OR supplier_canonical_key LIKE %s
              )
            ORDER BY opportunity_id NULLS LAST
            LIMIT 200
            """,
            (
                run_id,
                key if key.startswith("sup:") else f"sup:cnpj14:{digits}",
                f"%{digits}%",
                f"%{digits[:8]}%" if len(digits) >= 8 else f"%{digits}%",
            ),
        )
        rows = list(cur.fetchall())
    return {
        "run_id": run_id,
        "query": key,
        "count": len(rows),
        "relations": [dict(r) for r in rows],
        "claim_level_note": "Rows are observed historical winners; not open-tender participants unless independently observed.",
    }


def snapshot_hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
