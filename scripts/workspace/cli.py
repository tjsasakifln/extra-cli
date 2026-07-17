#!/usr/bin/env python3
"""Workspace CLI — unified operational facade for Extra Consultoria.

Usage:
    python -m scripts.workspace today
    python -m scripts.workspace opportunities --status open
    python -m scripts.workspace dossier 42
    python scripts/workspace/cli.py coverage
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from scripts.source_registry.models import EntitySourceRecord, is_strict_operational
from scripts.workspace import actions as workspace_actions
from scripts.workspace.common import (
    CLIENT_PROFILE,
    ENTITY_SOURCE_REGISTRY,
    PROJECT_ROOT,
    SESSION_DIR,
    SESSION_OUTPUT,
    get_dsn,
    load_json,
    load_jsonl,
    load_overrides,
    load_yaml,
    pg_query,
    print_section,
    print_table,
    try_pg_conn,
)
from scripts.workspace.queue import PENDING_PROFILE_KEYS, SectionResult, build_today

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_today(args: argparse.Namespace) -> int:
    payload = build_today(dsn=args.dsn, hours_new=args.hours)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    print("\n=== WORKSPACE TODAY — Extra Construtora / Tiago ===")
    print(f"Gerado: {payload['generated_at']} | as_of: {payload['as_of']}")
    if payload.get("pg_error"):
        print(f"PG: UNAVAILABLE — {payload['pg_error']}")
    else:
        print("PG: OK")

    for sec in payload["sections"]:
        print_section(SectionResult(**sec), as_json=False)
    print()
    return 0


def cmd_opportunities(args: argparse.Namespace) -> int:
    conn, err = try_pg_conn(args.dsn)
    if conn is None:
        items = _offline_opportunities(args)
        payload = {
            "status": "DEGRADED",
            "reason": err,
            "count": len(items),
            "items": items,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"⚠️  PG indisponível — fallback sessão ({err})")
            if items:
                print_table(items)
            else:
                print("Nenhuma oportunidade no fallback.")
        return 0

    try:
        conditions = ["is_active = TRUE", "COALESCE(source, '') <> 'test_batch'"]
        params: list[Any] = []

        if args.status:
            statuses = [s.strip() for s in args.status.split(",")]
            placeholders = ",".join(["%s"] * len(statuses))
            conditions.append(f"status_canonico IN ({placeholders})")
            params.extend(statuses)
        if args.orgao:
            conditions.append("orgao_nome ILIKE %s")
            params.append(f"%{args.orgao}%")
        if args.municipio:
            conditions.append("municipio ILIKE %s")
            params.append(f"%{args.municipio}%")
        if args.modalidade:
            conditions.append("modalidade ILIKE %s")
            params.append(f"%{args.modalidade}%")
        if args.valor is not None:
            conditions.append("valor_estimado >= %s")
            params.append(float(args.valor))
        if args.valor_max is not None:
            conditions.append("valor_estimado <= %s")
            params.append(float(args.valor_max))
        if args.score is not None:
            conditions.append("ranking_score >= %s")
            params.append(float(args.score))
        if args.ranking:
            rankings = [r.strip() for r in args.ranking.split(",")]
            placeholders = ",".join(["%s"] * len(rankings))
            conditions.append(f"ranking IN ({placeholders})")
            params.extend(rankings)
        if args.fonte or args.source:
            conditions.append("source = %s")
            params.append(args.fonte or args.source)
        if args.search:
            conditions.append("objeto ILIKE %s")
            params.append(f"%{args.search}%")
        if args.prazo:
            conditions.append(
                "COALESCE(data_encerramento, data_abertura)::date "
                "BETWEEN CURRENT_DATE AND CURRENT_DATE + %s"
            )
            params.append(int(args.prazo))
        if args.distance is not None:
            # Soft filter via join when entity distance available
            conditions.append(
                """EXISTS (
                    SELECT 1 FROM sc_public_entities e
                    WHERE LEFT(opportunity_intel.orgao_cnpj, 8) = e.cnpj_8
                      AND e.distancia_fk IS NOT NULL
                      AND e.distancia_fk <= %s
                )"""
            )
            params.append(float(args.distance))

        where = " AND ".join(conditions)
        limit = min(500, max(1, args.limit or 50))
        sql = f"""
            SELECT id, orgao_nome, municipio, modalidade, objeto,
                   valor_estimado, ranking, ranking_score, status_canonico,
                   source, data_abertura, data_encerramento, link_edital
            FROM opportunity_intel
            WHERE {where}
            ORDER BY ranking_score DESC NULLS LAST, data_abertura ASC NULLS LAST
            LIMIT %s
        """  # noqa: S608 — conditions built from parameterized fragments only
        params.append(limit)
        rows = pg_query(conn, sql, tuple(params))
    finally:
        conn.close()

    if args.json:
        print(json.dumps({"status": "OK", "count": len(rows), "items": rows}, indent=2, ensure_ascii=False, default=str))
    else:
        if not rows:
            print("Nenhuma oportunidade encontrada.")
        else:
            print(f"\n=== OPORTUNIDADES ({len(rows)}) ===\n")
            print_table(
                rows,
                [
                    "id",
                    "orgao_nome",
                    "municipio",
                    "ranking",
                    "valor_estimado",
                    "status_canonico",
                    "source",
                ],
            )
    return 0


def cmd_dossier(args: argparse.Namespace) -> int:
    opp_id = args.id
    conn, err = try_pg_conn(args.dsn)
    row: dict[str, Any] | None = None
    explain: dict[str, Any] | None = None

    if conn is not None:
        try:
            if str(opp_id).isdigit():
                rows = pg_query(conn, "SELECT * FROM opportunity_intel WHERE id = %s", (int(opp_id),))
            else:
                rows = pg_query(
                    conn,
                    "SELECT * FROM opportunity_intel WHERE numero_controle_pncp = %s",
                    (opp_id,),
                )
            if rows:
                row = rows[0]
                fatores = row.get("ranking_fatores") or row.get("ranking_reasons") or row.get("explain_json")
                regras = row.get("ranking_regras")
                qualidade = row.get("qualidade_fatores")
                # Build explainable surface even when structured columns sparse
                positive: list[str] = []
                negative: list[str] = []
                missing = list(row.get("dados_ausentes") or [])
                if isinstance(fatores, dict):
                    for k, v in fatores.items():
                        try:
                            if float(v) >= 0:
                                positive.append(f"{k}={v}")
                            else:
                                negative.append(f"{k}={v}")
                        except (TypeError, ValueError):
                            positive.append(f"{k}={v}")
                elif isinstance(fatores, list):
                    positive.extend(str(x) for x in fatores)
                # Deterministic fallback explain when ranking_fatores empty
                if not positive and not negative:
                    if row.get("status_canonico") in {"open", "upcoming"}:
                        positive.append("status_canonico_open_or_upcoming")
                    if row.get("source") and row.get("source") != "test_batch":
                        positive.append(f"official_source={row.get('source')}")
                    if row.get("valor_estimado"):
                        positive.append(f"valor_estimado_present={row.get('valor_estimado')}")
                    if row.get("link_edital") or row.get("source_url"):
                        positive.append("official_url_present")
                    obj = (row.get("objeto") or "").lower()
                    eng_terms = ("reforma", "manutenc", "edific", "predial", "constru", "obra")
                    if any(t in obj for t in eng_terms):
                        positive.append("objeto_matches_engineering_terms")
                    else:
                        negative.append("objeto_no_engineering_terms_detected")
                    if row.get("ranking_score") in (None, 0, 0.0):
                        negative.append("ranking_score_zero_or_null_needs_recalibration")
                if row.get("ranking") == "NO_GO":
                    negative.append("ranking=NO_GO")
                if not row.get("orgao_nome"):
                    missing.append("orgao_nome")
                if not row.get("valor_estimado"):
                    missing.append("valor_estimado")
                if not row.get("data_encerramento"):
                    missing.append("data_encerramento")
                if not row.get("numero_processo") and not row.get("numero_edital"):
                    missing.append("processo_or_edital_number")
                if (row.get("source") or "") == "test_batch":
                    negative.append("source=test_batch (synthetic fixture — not production signal)")
                explain = {
                    "ranking": row.get("ranking"),
                    "ranking_score": row.get("ranking_score"),
                    "ranking_confianca": row.get("ranking_confianca") or "LOW",
                    "ranking_fatores": fatores,
                    "ranking_regras": regras,
                    "qualidade_score": row.get("qualidade_score"),
                    "qualidade_fatores": qualidade,
                    "positive_factors": positive,
                    "negative_factors": negative,
                    "missing_fields": missing,
                    "status_canonico": row.get("status_canonico"),
                    "status_motivo": row.get("status_motivo"),
                    "source": row.get("source"),
                    "explain_mode": "structured_columns" if fatores else "deterministic_fallback",
                    "disclaimer": (
                        "Recomendação explicável a partir de colunas ranking_* ou fallback determinístico; "
                        "não substitui julgamento humano. GO exige fit de perfil Extra."
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            err = f"{err or ''}; query: {exc}"
        finally:
            conn.close()

    if row is None:
        # Offline stub from session
        for path in (
            SESSION_OUTPUT / "radar_opportunities_sample.jsonl",
            SESSION_OUTPUT / "radar_opportunities.jsonl",
        ):
            for item in load_jsonl(path, limit=500):
                sid = str(item.get("source_id") or item.get("id") or "")
                if sid == str(opp_id):
                    row = item
                    break
            if row:
                break

    overrides = load_overrides()
    human = [
        o
        for o in overrides.get("overrides", [])
        if str(o.get("opportunity_id")) == str(opp_id)
    ]

    profile = load_yaml(CLIENT_PROFILE) or {}
    missing_fields = []
    for key in PENDING_PROFILE_KEYS:
        val = profile.get(key)
        cap = (profile.get("operational_capacity") or {}).get(key)
        elic = (profile.get("elicitation") or {}).get(key)
        if val is None and cap is None and elic is None:
            missing_fields.append(key)
        elif isinstance(elic, dict) and str(elic.get("status", "")).upper() == "PENDING":
            missing_fields.append(key)

    fit_notes = []
    if profile.get("region"):
        fit_notes.append(f"UF primária: {profile['region'].get('uf_primary')} raio {profile['region'].get('radius_km')}km")
    if profile.get("desired_object_types"):
        fit_notes.append(
            "Objetos desejados: "
            + ", ".join(d.get("id", str(d)) for d in profile["desired_object_types"][:6])
        )
    if missing_fields:
        fit_notes.append(f"Perfil incompleto: {', '.join(missing_fields[:8])}")

    # The persisted legacy ranking is an input, not the operational decision.
    # A GO is impossible while material client-profile fields are still pending.
    persisted_recommendation = (row or {}).get("ranking")
    effective_recommendation = persisted_recommendation
    if persisted_recommendation == "GO" and missing_fields:
        effective_recommendation = "REVIEW"
        if explain is None:
            explain = {
                "positive_factors": [],
                "negative_factors": [],
                "missing_fields": [],
                "ranking_confianca": "LOW",
                "source": (row or {}).get("source"),
            }
        explain.setdefault("negative_factors", []).append(
            "client_profile_incomplete_blocks_go"
        )
        explain.setdefault("missing_fields", []).extend(missing_fields)
        explain["persisted_recommendation"] = persisted_recommendation
        explain["effective_recommendation"] = effective_recommendation
        explain["ranking_confianca"] = "LOW"
        explain["profile_gate"] = "BLOCKED"

    next_steps = [
        "Ler edital oficial e preencher checklist (workspace edital analyze)",
        "Validar ranking com explain / evidências",
        "Registrar decisão: workspace decide --id ... --decision approve|reject --reason '...'",
    ]
    if human:
        next_steps.insert(0, "Há override humano registrado — revisar motivo antes de propor.")

    payload = {
        "id": opp_id,
        "status": "OK" if row else "NOT_FOUND",
        "pg_error": err,
        "opportunity": row,
        "explain": explain,
        "persisted_recommendation": persisted_recommendation,
        "effective_recommendation": effective_recommendation,
        "profile_fit_notes": fit_notes,
        "missing_profile_fields": missing_fields,
        "human_overrides": human,
        "next_steps": next_steps,
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if row else 1

    print(f"\n=== DOSSIÊ — {opp_id} ===")
    if not row:
        print(f"Oportunidade não encontrada. ({err or 'sem dados'})")
        return 1
    # Compact detail
    if isinstance(row, dict):
        keys = [
            "id",
            "orgao_nome",
            "orgao",
            "municipio",
            "objeto",
            "title",
            "valor_estimado",
            "ranking",
            "ranking_score",
            "status_canonico",
            "source",
            "data_abertura",
            "data_encerramento",
            "link_edital",
            "url",
            "link_oficial",
        ]
        for k in keys:
            if k in row and row[k] is not None:
                val = row[k]
                text = str(val)
                if len(text) > 200:
                    text = text[:200] + "…"
                print(f"  {k}: {text}")
    print("\n--- Explain / ranking ---")
    print(json.dumps(explain, indent=2, ensure_ascii=False, default=str) if explain else "  (indisponível offline)")
    print("\n--- Fit de perfil ---")
    for n in fit_notes:
        print(f"  • {n}")
    print("\n--- Campos de perfil faltantes ---")
    print("  " + (", ".join(missing_fields) if missing_fields else "(nenhum marcado)"))
    print("\n--- Override humano ---")
    if human:
        for h in human:
            print(f"  {h.get('ts')} | {h.get('decision')} | {h.get('reason')} | owner={h.get('owner')}")
    else:
        print("  (nenhum em data/workspace_overrides.json)")
    print("\n--- Próximos passos ---")
    for s in next_steps:
        print(f"  → {s}")
    print()
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    metrics: list[dict[str, Any]] = []
    notes: list[str] = []
    gaps: list[dict[str, Any]] = []
    contract_table: str | None = None

    # Prefer multi-dimension coverage contract (ADR-018) when available
    try:
        from scripts.coverage.coverage_contract import (
            build_contract_report,
            format_report_table,
        )

        report = build_contract_report(session_dir=SESSION_DIR if SESSION_DIR.exists() else None)
        if hasattr(report, "to_dict"):
            report_dict = report.to_dict()
        elif isinstance(report, dict):
            report_dict = report
        else:
            report_dict = {"raw": str(report)}
        metrics.append({"name": "coverage_contract", "result": report_dict})
        try:
            contract_table = format_report_table(report)
        except Exception:  # noqa: BLE001
            contract_table = None
        # Flatten metric results for human table
        for m in report_dict.get("metrics") or []:
            if isinstance(m, dict):
                metrics.append(
                    {
                        "name": m.get("name") or m.get("metric_id"),
                        "numerator": m.get("numerator"),
                        "denominator": m.get("denominator"),
                        "pct": m.get("pct") or m.get("result_pct") or m.get("value"),
                        "status": m.get("status"),
                        "kind": m.get("kind"),
                    }
                )
        notes.append("coverage_contract: OK (multi-metric operational contract).")
    except Exception as exc:  # noqa: BLE001
        notes.append(
            f"coverage_contract unavailable ({exc}) — fallback session_summary + coverage_canonical."
        )

    summary = (
        load_json(SESSION_DIR / "session_summary.json")
        or load_json(SESSION_OUTPUT / "session_summary.json")
        or load_json(SESSION_DIR / "coverage_canonical.json")
    )
    canonical = load_json(SESSION_DIR / "coverage_canonical.json") or load_json(
        SESSION_OUTPUT / "coverage_canonical.json"
    )

    if summary:
        metrics.append(
            {
                "name": "commercial_opportunity_any",
                "numerator": summary.get("final_db_covered") or summary.get("covered"),
                "denominator": 1093,
                "pct": summary.get("final_pct"),
                "open_opportunities": summary.get("open_opportunities"),
                "open_engineering": summary.get("open_engineering"),
                "go_recommendations": summary.get("go_recommendations"),
                "note": "SINAL COMERCIAL — NÃO é cobertura operacional 100% DoD.",
            }
        )
        notes.append(
            "Sinal comercial (entities with ≥1 open opportunity) ≠ cobertura operacional multi-fonte."
        )

    if canonical and isinstance(canonical, dict):
        for m in canonical.get("metrics") or []:
            if isinstance(m, dict):
                metrics.append(
                    {
                        "name": m.get("name"),
                        "numerator": m.get("numerator"),
                        "denominator": m.get("denominator"),
                        "pct": m.get("result_pct"),
                        "formula": m.get("formula"),
                    }
                )
        src = canonical.get("source_stats") or {}
        for source, stats in src.items():
            if isinstance(stats, dict):
                metrics.append(
                    {
                        "name": f"source:{source}",
                        "records": stats.get("records"),
                        "matched": stats.get("matched"),
                        "coverage_eligible": stats.get("coverage_eligible"),
                    }
                )

    # Entity/source gaps sample
    if ENTITY_SOURCE_REGISTRY.exists():
        for row in load_jsonl(ENTITY_SOURCE_REGISTRY, limit=50):
            try:
                record = EntitySourceRecord.from_dict(row)
                operational = is_strict_operational(record)
            except (TypeError, ValueError, KeyError):
                operational = False
            if not operational:
                gaps.append(row)
    else:
        uncovered = SESSION_DIR / "entities_uncovered.jsonl"
        if uncovered.exists():
            gaps = load_jsonl(uncovered, limit=20)
            notes.append(f"Gaps sample from {uncovered} (entity_source_registry ausente).")
        else:
            notes.append("data/entity_source_registry.jsonl ausente — sem amostra de gaps por entidade.")

    # Live PG optional enrichment
    conn, err = try_pg_conn(args.dsn)
    if conn is not None:
        try:
            try:
                from scripts.coverage.calculator import report_coverage

                live = report_coverage(conn)
                metrics.append({"name": "live_monitoring_coverage", "result": live})
            except Exception as exc:  # noqa: BLE001
                notes.append(f"live calculator skip: {exc}")
        finally:
            conn.close()
    elif err:
        notes.append(err)

    payload = {
        "command": "coverage",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metrics": metrics,
        "gaps_sample": gaps[:20],
        "notes": notes,
        "disclaimer": (
            "Métrica comercial (open opportunity any) NÃO substitui cobertura operacional "
            "multi-dimensional do contrato de cobertura."
        ),
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    print("\n=== COVERAGE — contrato multi-dimensional ===\n")
    print(payload["disclaimer"])
    print()
    if contract_table:
        print(contract_table)
        print()
    for m in metrics:
        name = m.get("name")
        if name == "coverage_contract":
            continue  # already printed via format_report_table
        if "pct" in m and m["pct"] is not None:
            print(f"  • {name}: {m.get('numerator')}/{m.get('denominator')} = {m['pct']}%")
        elif "result" in m:
            print(f"  • {name}: (ver --json para detalhe)")
        else:
            bits = [f"{k}={v}" for k, v in m.items() if k != "name" and v is not None]
            print(f"  • {name}: {', '.join(bits)}")
    if notes:
        print("\nNotas:")
        for n in notes:
            print(f"  - {n}")
    if gaps:
        # Prefer compact gap columns when registry rows are wide
        compact = []
        for g in gaps[:10]:
            compact.append(
                {
                    "canonical_id": g.get("canonical_id") or g.get("id"),
                    "razao_social": (g.get("razao_social") or g.get("name") or "")[:48],
                    "municipio": g.get("municipio"),
                    "priority": g.get("priority"),
                    "access_status": g.get("access_status"),
                    "next_action": (g.get("next_action") or "")[:48],
                }
            )
        print(f"\nAmostra de gaps ({min(10, len(gaps))}):")
        print_table(compact)
    print()
    return 0


def cmd_competitors(args: argparse.Namespace) -> int:
    conn, err = try_pg_conn(args.dsn)
    items: list[dict[str, Any]] = []

    if conn is not None:
        try:
            if args.cnpj:
                cnpj = "".join(ch for ch in args.cnpj if ch.isdigit())
                items = pg_query(
                    conn,
                    """
                    SELECT numero_controle_pncp, orgao_nome, objeto_contrato,
                           valor_total, data_assinatura, data_fim_vigencia,
                           municipio, uf, ni_fornecedor, nome_fornecedor
                    FROM pncp_supplier_contracts
                    WHERE is_active IS TRUE
                      AND (ni_fornecedor = %s OR LEFT(ni_fornecedor, 8) = %s)
                    ORDER BY data_assinatura DESC NULLS LAST
                    LIMIT %s
                    """,
                    (cnpj, cnpj[:8], args.limit),
                )
            else:
                try:
                    items = pg_query(
                        conn,
                        """
                        SELECT fornecedor_cnpj, fornecedor_nome, qtd_contratos,
                               valor_total_contratos, ticket_medio_contrato,
                               qtd_orgaos_distintos, hhi_concentracao
                        FROM v_supplier_winners
                        ORDER BY valor_total_contratos DESC NULLS LAST
                        LIMIT %s
                        """,
                        (args.limit,),
                    )
                except Exception:
                    items = pg_query(
                        conn,
                        """
                        SELECT ni_fornecedor AS fornecedor_cnpj,
                               MAX(nome_fornecedor) AS fornecedor_nome,
                               COUNT(*) AS qtd_contratos,
                               SUM(valor_total) AS valor_total_contratos,
                               AVG(valor_total) AS ticket_medio_contrato
                        FROM pncp_supplier_contracts
                        WHERE is_active IS TRUE AND ni_fornecedor IS NOT NULL
                        GROUP BY ni_fornecedor
                        ORDER BY SUM(valor_total) DESC NULLS LAST
                        LIMIT %s
                        """,
                        (args.limit,),
                    )
        except Exception as exc:  # noqa: BLE001
            err = f"{err or ''}; {exc}"
        finally:
            conn.close()

    payload = {
        "status": "OK" if items else ("UNAVAILABLE" if err else "EMPTY"),
        "pg_error": err,
        "cnpj": args.cnpj,
        "count": len(items),
        "items": items,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    title = f"DOSSIÊ CONCORRENTE {args.cnpj}" if args.cnpj else "TOP FORNECEDORES"
    print(f"\n=== {title} ===")
    if err and not items:
        print(f"UNAVAILABLE: {err}")
        return 0
    if not items:
        print("Nenhum concorrente encontrado.")
        return 0
    print_table(items)
    print()
    return 0


def cmd_expiring_contracts(args: argparse.Namespace) -> int:
    buckets = [30, 60, 90, 180, 365]
    conn, err = try_pg_conn(args.dsn)
    result: dict[str, Any] = {"buckets": {}, "pg_error": err}

    if conn is not None:
        try:
            for b in buckets:
                try:
                    rows = pg_query(
                        conn,
                        """
                        SELECT contrato_id, orgao_nome, fornecedor_nome,
                               objeto_contrato, valor_contrato, data_fim_contrato,
                               dias_ate_fim, municipio
                        FROM v_expiring_contracts
                        WHERE dias_ate_fim BETWEEN 0 AND %s
                        ORDER BY dias_ate_fim ASC
                        LIMIT %s
                        """,
                        (b, args.limit),
                    )
                except Exception:
                    rows = pg_query(
                        conn,
                        """
                        SELECT numero_controle_pncp AS contrato_id,
                               orgao_nome, nome_fornecedor AS fornecedor_nome,
                               objeto_contrato, valor_total AS valor_contrato,
                               data_fim_vigencia AS data_fim_contrato,
                               (data_fim_vigencia - CURRENT_DATE) AS dias_ate_fim,
                               municipio
                        FROM pncp_supplier_contracts
                        WHERE is_active IS TRUE
                          AND data_fim_vigencia BETWEEN CURRENT_DATE
                              AND CURRENT_DATE + (%s || ' days')::interval
                        ORDER BY data_fim_vigencia ASC
                        LIMIT %s
                        """,
                        (b, args.limit),
                    )
                result["buckets"][f"{b}d"] = {"count": len(rows), "items": rows}
        finally:
            conn.close()
    else:
        result["status"] = "UNAVAILABLE"
        result["reason"] = err or "PG down"

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0

    print("\n=== CONTRATOS EXPIRANDO — buckets 30/60/90/180/365 ===\n")
    if result.get("status") == "UNAVAILABLE":
        print(f"UNAVAILABLE: {result.get('reason')}")
        return 0
    for label, data in result["buckets"].items():
        print(f"--- {label}: {data['count']} ---")
        if data["items"]:
            print_table(data["items"][:10])
        print()
    return 0


def cmd_prices(args: argparse.Namespace) -> int:
    keywords = args.keywords or args.category or ""
    conn, err = try_pg_conn(args.dsn)

    if conn is None:
        payload = {
            "status": "NOT_READY",
            "reason": err or "PostgreSQL required for price panel",
            "keywords": keywords,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("NOT_READY — painel de preços requer PG (local_datalake/contract_intel).")
            print(f"  {payload['reason']}")
        return 0

    try:
        kws = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        if not kws:
            payload = {
                "status": "NOT_READY",
                "reason": "Informe --keywords ou --category",
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print("NOT_READY — use --keywords 'reforma,predial' ou --category")
            return 0

        # Schema real: valor_total (não valor_global) em pncp_supplier_contracts
        wheres = ["is_active IS TRUE", "valor_total IS NOT NULL", "valor_total > 1"]
        params: list[Any] = []
        for kw in kws:
            wheres.append("objeto_contrato ILIKE %s")
            params.append(f"%{kw}%")
        if args.uf:
            wheres.append("uf = %s")
            params.append(args.uf.upper())

        sql = f"""
            SELECT valor_total AS valor_contratado,
                   objeto_contrato,
                   orgao_nome,
                   data_assinatura,
                   'CONTRATADO'::text AS valor_semantica
            FROM pncp_supplier_contracts
            WHERE {" AND ".join(wheres)}
            ORDER BY data_assinatura DESC NULLS LAST
            LIMIT 1000
        """  # noqa: S608
        try:
            rows = pg_query(conn, sql, tuple(params))
        except Exception as exc:  # noqa: BLE001 — try opportunity_intel estimated fallback
            # Fallback: valor_estimado from opportunities (explicit semantics ESTIMADO)
            try:
                oi_wheres = ["is_active IS TRUE", "valor_estimado IS NOT NULL", "valor_estimado > 1", "source <> 'test_batch'"]
                oi_params: list[Any] = []
                for kw in kws:
                    oi_wheres.append("objeto ILIKE %s")
                    oi_params.append(f"%{kw}%")
                oi_sql = f"""
                    SELECT valor_estimado AS valor_contratado, objeto AS objeto_contrato,
                           orgao_nome, data_publicacao AS data_assinatura,
                           'ESTIMADO'::text AS valor_semantica
                    FROM opportunity_intel
                    WHERE {" AND ".join(oi_wheres)}
                    LIMIT 1000
                """  # noqa: S608
                rows = pg_query(conn, oi_sql, tuple(oi_params))
                err = f"contracts query failed ({exc}); using opportunity_intel ESTIMADO"
            except Exception as exc2:  # noqa: BLE001
                payload = {
                    "status": "NOT_READY",
                    "reason": f"price panel query failed: {exc}; fallback: {exc2}",
                    "keywords": kws,
                }
                if args.json:
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                else:
                    print(f"NOT_READY — {payload['reason']}")
                return 0
    finally:
        conn.close()

    if not rows:
        payload = {
            "status": "NOT_READY",
            "reason": "Sem contratos para as keywords informadas",
            "keywords": kws,
            "semantics": "valor_total (CONTRATADO) when available",
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("NOT_READY — sem amostra de preços.")
        return 0

    valores = sorted(
        float(r["valor_contratado"])
        for r in rows
        if r.get("valor_contratado") is not None
    )
    n = len(valores)

    def pct(p: float) -> float:
        if n == 1:
            return valores[0]
        k = (n - 1) * p
        f = int(k)
        c = min(f + 1, n - 1)
        return valores[f] + (valores[c] - valores[f]) * (k - f) if f != c else valores[f]

    payload = {
        "status": "OK",
        "keywords": kws,
        "sample": n,
        "p25": round(pct(0.25), 2),
        "median": round(pct(0.50), 2),
        "p75": round(pct(0.75), 2),
        "p10": round(pct(0.10), 2),
        "p90": round(pct(0.90), 2),
        "mean": round(sum(valores) / n, 2),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"\n=== PAINEL DE PREÇOS — {', '.join(kws)} ===")
        print(f"Amostra: {n}")
        print(f"  P25:    R$ {payload['p25']:,.2f}")
        print(f"  Mediana:R$ {payload['median']:,.2f}")
        print(f"  P75:    R$ {payload['p75']:,.2f}")
        print(f"  Média:  R$ {payload['mean']:,.2f}")
        print()
    return 0


def cmd_edital(args: argparse.Namespace) -> int:
    if args.edital_command != "analyze":
        print("Uso: workspace edital analyze PATH_OR_URL", file=sys.stderr)
        return 2
    result = workspace_actions.scaffold_edital(args.path_or_url)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n=== EDITAL ANALYZE — workspace criado ===")
        print(f"  pasta: {result['folder']}")
        print(f"  recomendação: {result['recommendation']} (sem evidência não há GO)")
        print(f"  checklist: {result['checklist_items']} pontos")
        print(f"  extract: {result['extract_status']} — {result['extract_note']}")
        print(f"  evidências faltantes: {len(result['missing_evidence'])}")
        print()
    return 0


def cmd_proposal(args: argparse.Namespace) -> int:
    if args.proposal_command != "support":
        print("Uso: workspace proposal support OPP_ID", file=sys.stderr)
        return 2
    result = workspace_actions.scaffold_proposal(args.opp_id)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n=== PROPOSAL SUPPORT ===")
        print(f"  pasta: {result['folder']}")
        print(f"  {result['disclaimer']}")
        print("  pendências:")
        for p in result["pending_items"]:
            print(f"    - {p}")
        print()
    return 0


def cmd_contracts(args: argparse.Namespace) -> int:
    """Admin contract monitoring (vigência/prazos/garantias placeholders)."""
    conn, err = try_pg_conn(args.dsn)
    items: list[dict[str, Any]] = []

    if conn is not None:
        try:
            try:
                items = pg_query(
                    conn,
                    """
                    SELECT contrato_id, orgao_nome, fornecedor_nome, objeto_contrato,
                           valor_contrato, data_inicio_contrato, data_fim_contrato,
                           dias_ate_fim, municipio, uf
                    FROM v_contract_historical
                    ORDER BY data_fim_contrato DESC NULLS LAST
                    LIMIT %s
                    """,
                    (args.limit,),
                )
            except Exception:
                items = pg_query(
                    conn,
                    """
                    SELECT numero_controle_pncp AS contrato_id,
                           orgao_nome, nome_fornecedor AS fornecedor_nome,
                           objeto_contrato, valor_total AS valor_contrato,
                           data_assinatura AS data_inicio_contrato,
                           data_fim_vigencia AS data_fim_contrato,
                           municipio, uf
                    FROM pncp_supplier_contracts
                    WHERE is_active IS TRUE
                    ORDER BY data_fim_vigencia DESC NULLS LAST
                    LIMIT %s
                    """,
                    (args.limit,),
                )
            # Placeholders for garantia / prazo admin (not physical obra fields)
            for it in items:
                it.setdefault("garantia_status", "PLACEHOLDER")
                it.setdefault("prazo_admin_status", "PLACEHOLDER")
                it.setdefault("vigencia_status", "OK" if it.get("data_fim_contrato") else "UNKNOWN")
        except Exception as exc:  # noqa: BLE001
            err = f"{err or ''}; {exc}"
        finally:
            conn.close()

    # Merge own contracts from ledger
    ledger = load_json(PROJECT_ROOT / "data" / "extra_ledger.json") or {}
    own = ledger.get("contratos") or []

    payload = {
        "status": "OK" if items or own else ("UNAVAILABLE" if err else "EMPTY"),
        "pg_error": err,
        "market_contracts": items,
        "own_contracts": own,
        "note": "Campos de obra física excluídos por design (acompanhamento físico fora de escopo).",
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    print("\n=== CONTRATOS — monitoramento administrativo ===")
    print(payload["note"])
    if err and not items:
        print(f"Market: UNAVAILABLE ({err})")
    elif items:
        print(f"\nMercado (sample {len(items)}):")
        print_table(items[:20])
    if own:
        print(f"\nPróprios (extra_ledger): {len(own)}")
        print_table(own[:20])
    elif not items:
        print("Nenhum contrato disponível.")
    print()
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    try:
        result = workspace_actions.decide_opportunity(
            opportunity_id=args.id,
            decision=args.decision,
            reason=args.reason,
            tags=tags,
            owner=args.owner,
            orgao=args.orgao or "",
            objeto=args.objeto or "",
            valor=args.valor or 0.0,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"✅ Decisão registrada: {result['decision']} "
            f"opp={result['opportunity_id']} ledger_id={result['ledger_id']}"
        )
    return 0


def cmd_briefing(args: argparse.Namespace) -> int:
    """Delegate to opportunity_intel briefing when PG up; else session summary."""
    conn, err = try_pg_conn(args.dsn)
    if conn is not None:
        conn.close()
        try:
            from scripts.opportunity_intel.cli import build_parser as oi_parser
            from scripts.opportunity_intel.cli import cmd_briefing as oi_briefing

            p = oi_parser()
            ns = p.parse_args(
                [
                    "briefing",
                    "--dias",
                    str(args.dias),
                    "--limit",
                    str(args.limit),
                    "--dsn",
                    get_dsn(args.dsn),
                ]
            )
            oi_briefing(ns)
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️  briefing opportunity_intel falhou: {exc}")

    summary = load_json(SESSION_DIR / "session_summary.json") or {}
    print("\n=== BRIEFING (offline fallback) ===")
    if err:
        print(f"PG: {err}")
    if summary:
        print(f"Cobertura comercial: {summary.get('final_db_covered')}/1093 ({summary.get('final_pct')}%)")
        print(f"Open opportunities: {summary.get('open_opportunities')}")
        print(f"Open engineering: {summary.get('open_engineering')}")
        print(f"GO recommendations: {summary.get('go_recommendations')}")
        print(f"Sources: {summary.get('source_presence')}")
    else:
        print("Sem session_summary — rode crawlers / opportunity_intel.")
    print()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    kind = args.report_kind
    if kind == "daily":
        return cmd_briefing(args)
    if kind == "weekly":
        try:
            from scripts.reports import coverage_weekly

            # Prefer programmatic main if available
            if hasattr(coverage_weekly, "main"):
                sys.argv = ["coverage_weekly"]
                if args.output_dir:
                    sys.argv += ["--output-dir", args.output_dir]
                coverage_weekly.main()
                return 0
        except Exception as exc:  # noqa: BLE001
            print(f"coverage_weekly falhou: {exc}")
        try:
            from scripts.reports import panorama

            if hasattr(panorama, "main"):
                panorama.main()
                return 0
        except Exception as exc:  # noqa: BLE001
            print(f"panorama falhou: {exc}")
        # Last resort: print coverage payload
        return cmd_coverage(args)
    print(f"Report desconhecido: {kind}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Offline helpers
# ---------------------------------------------------------------------------


def _offline_opportunities(args: argparse.Namespace) -> list[dict[str, Any]]:
    from scripts.workspace.queue import _load_session_opportunities

    items = _load_session_opportunities(status_open=True)
    if args.search:
        q = args.search.lower()
        items = [i for i in items if q in (i.get("objeto") or "").lower()]
    if args.municipio:
        m = args.municipio.lower()
        items = [i for i in items if m in (i.get("municipio") or "").lower()]
    if args.orgao:
        o = args.orgao.lower()
        items = [i for i in items if o in (i.get("orgao_nome") or "").lower()]
    return items[: args.limit or 50]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace",
        description="Workspace operacional unificado — Extra Construtora (facade CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.workspace today
  python -m scripts.workspace today --json
  python -m scripts.workspace opportunities --status open --ranking GO,REVIEW
  python -m scripts.workspace dossier 42
  python -m scripts.workspace coverage
  python -m scripts.workspace competitors --limit 20
  python -m scripts.workspace competitors --cnpj 12345678000199
  python -m scripts.workspace expiring-contracts
  python -m scripts.workspace prices --keywords reforma,predial
  python -m scripts.workspace edital analyze ./edital.pdf
  python -m scripts.workspace proposal support 42
  python -m scripts.workspace decide --id 42 --decision approve --reason "fit AEC"
  python -m scripts.workspace briefing
  python -m scripts.workspace report weekly
        """,
    )
    parser.add_argument("--dsn", default=None, help="PostgreSQL DSN (default: LOCAL_DATALAKE_DSN)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    sub = parser.add_subparsers(dest="command", help="Comando")

    # today
    p_today = sub.add_parser("today", help="Fila diária priorizada")
    p_today.add_argument("--hours", type=int, default=48, help="Janela de novidades (default 48h)")
    p_today.add_argument("--json", action="store_true")
    p_today.add_argument("--dsn", default=None)

    # opportunities
    p_opp = sub.add_parser("opportunities", help="Listar oportunidades com filtros")
    p_opp.add_argument("--orgao", default=None)
    p_opp.add_argument("--municipio", default=None)
    p_opp.add_argument("--distance", type=float, default=None, help="Distância máx. km")
    p_opp.add_argument("--modalidade", default=None)
    p_opp.add_argument("--valor", type=float, default=None, help="Valor mínimo")
    p_opp.add_argument("--valor-max", type=float, default=None)
    p_opp.add_argument("--prazo", type=int, default=None, help="Dias até prazo")
    p_opp.add_argument("--status", default=None)
    p_opp.add_argument("--score", type=float, default=None)
    p_opp.add_argument("--ranking", default=None)
    p_opp.add_argument("--fonte", default=None)
    p_opp.add_argument("--source", default=None)
    p_opp.add_argument("--search", default=None)
    p_opp.add_argument("--limit", type=int, default=50)
    p_opp.add_argument("--json", action="store_true")
    p_opp.add_argument("--dsn", default=None)

    # dossier
    p_dos = sub.add_parser("dossier", help="Dossiê completo de oportunidade")
    p_dos.add_argument("id", help="ID numérico ou PNCP/source id")
    p_dos.add_argument("--json", action="store_true")
    p_dos.add_argument("--dsn", default=None)

    # coverage
    p_cov = sub.add_parser("coverage", help="Métricas de cobertura multi-dimensional")
    p_cov.add_argument("--json", action="store_true")
    p_cov.add_argument("--dsn", default=None)

    # competitors
    p_comp = sub.add_parser("competitors", help="Top fornecedores / dossiê CNPJ")
    p_comp.add_argument("--cnpj", default=None)
    p_comp.add_argument("--limit", type=int, default=20)
    p_comp.add_argument("--json", action="store_true")
    p_comp.add_argument("--dsn", default=None)

    # expiring-contracts
    p_exp = sub.add_parser("expiring-contracts", help="Contratos por bucket 30/60/90/180/365")
    p_exp.add_argument("--limit", type=int, default=50)
    p_exp.add_argument("--json", action="store_true")
    p_exp.add_argument("--dsn", default=None)

    # prices
    p_price = sub.add_parser("prices", help="Painel de preços P25/mediana/P75")
    p_price.add_argument("--keywords", default=None)
    p_price.add_argument("--category", default=None)
    p_price.add_argument("--uf", default="SC")
    p_price.add_argument("--json", action="store_true")
    p_price.add_argument("--dsn", default=None)

    # edital analyze
    p_ed = sub.add_parser("edital", help="Análise de edital")
    ed_sub = p_ed.add_subparsers(dest="edital_command")
    p_ed_an = ed_sub.add_parser("analyze", help="Scaffold de análise")
    p_ed_an.add_argument("path_or_url", help="Caminho local ou URL do edital")
    p_ed_an.add_argument("--json", action="store_true")

    # proposal support
    p_prop = sub.add_parser("proposal", help="Apoio à proposta")
    prop_sub = p_prop.add_subparsers(dest="proposal_command")
    p_prop_s = prop_sub.add_parser("support", help="Scaffold de apoio")
    p_prop_s.add_argument("opp_id", help="ID da oportunidade")
    p_prop_s.add_argument("--json", action="store_true")

    # contracts
    p_ct = sub.add_parser("contracts", help="Monitoramento administrativo de contratos")
    p_ct.add_argument("--limit", type=int, default=50)
    p_ct.add_argument("--json", action="store_true")
    p_ct.add_argument("--dsn", default=None)

    # decide
    p_dec = sub.add_parser("decide", help="Registrar decisão (ledger + overrides)")
    p_dec.add_argument("--id", required=True, help="ID da oportunidade")
    p_dec.add_argument(
        "--decision",
        required=True,
        help="approve|reject|override (ou participar|nao_participar|reavaliar)",
    )
    p_dec.add_argument("--reason", required=True)
    p_dec.add_argument("--tags", default="")
    p_dec.add_argument("--owner", default="tiago")
    p_dec.add_argument("--orgao", default="")
    p_dec.add_argument("--objeto", default="")
    p_dec.add_argument("--valor", type=float, default=0.0)
    p_dec.add_argument("--json", action="store_true")

    # briefing
    p_br = sub.add_parser("briefing", help="Briefing diário (delega opportunity_intel)")
    p_br.add_argument("--dias", type=int, default=7)
    p_br.add_argument("--limit", type=int, default=20)
    p_br.add_argument("--dsn", default=None)
    p_br.add_argument("--json", action="store_true")

    # report daily|weekly
    p_rep = sub.add_parser("report", help="Relatórios daily|weekly")
    p_rep.add_argument("report_kind", choices=["daily", "weekly"])
    p_rep.add_argument("--dias", type=int, default=7)
    p_rep.add_argument("--limit", type=int, default=20)
    p_rep.add_argument("--output-dir", default=None)
    p_rep.add_argument("--dsn", default=None)
    p_rep.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Propagate top-level --json if subcommand didn't set it
    if getattr(args, "json", False) is False and "--json" in (argv or sys.argv):
        # handled per-subcommand flags already
        pass

    commands = {
        "today": cmd_today,
        "opportunities": cmd_opportunities,
        "dossier": cmd_dossier,
        "coverage": cmd_coverage,
        "competitors": cmd_competitors,
        "expiring-contracts": cmd_expiring_contracts,
        "prices": cmd_prices,
        "edital": cmd_edital,
        "proposal": cmd_proposal,
        "contracts": cmd_contracts,
        "decide": cmd_decide,
        "briefing": cmd_briefing,
        "report": cmd_report,
    }
    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    code = handler(args)
    sys.exit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    main()
