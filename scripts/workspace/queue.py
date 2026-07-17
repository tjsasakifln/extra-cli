"""Daily queue assembly for ``workspace today``.

Graceful degradation: each section is OK / EMPTY / UNAVAILABLE independently.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.workspace.common import (
    CLIENT_PROFILE,
    SESSION_DIR,
    SESSION_OUTPUT,
    SectionResult,
    load_json,
    load_jsonl,
    load_yaml,
    parse_date_safe,
    pg_query,
    try_pg_conn,
)

# Profile keys that must be elicited (null/empty → pending)
PENDING_PROFILE_KEYS = [
    "capital_giro",
    "capacidade_simultanea",
    "cats_atestados",
    "equipe",
    "equipamentos",
    "certidoes",
    "margem_minima",
    "risco_aceitavel",
    "contratos_atuais",
    "apetite_consorcios",
    "capacidade_garantia",
]


def build_today(dsn: str | None = None, hours_new: int = 48) -> dict[str, Any]:
    """Build full daily queue payload."""
    conn, pg_err = try_pg_conn(dsn)
    sections: list[SectionResult] = []

    sections.append(_section_new_open(conn, pg_err, hours_new))
    sections.append(_section_near_deadline(conn, pg_err, days=7))
    sections.append(_section_review(conn, pg_err))
    sections.append(_section_source_health(conn, pg_err))
    sections.append(_section_expiring(conn, pg_err))
    sections.append(_section_pending_profile())
    sections.append(_section_suggested_actions(sections))

    pg_ok = conn is not None
    if conn is not None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001, S110 — close is best-effort on degrade path
            pass

    return {
        "command": "today",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": date.today().isoformat(),
        "pg_available": pg_ok,
        "pg_error": pg_err,
        "sections": [s.to_dict() for s in sections],
    }


def _section_new_open(
    conn: Any | None,
    pg_err: str | None,
    hours_new: int,
) -> SectionResult:
    name = "Novas oportunidades abertas (24-48h)"
    if conn is not None:
        try:
            rows = pg_query(
                conn,
                """
                SELECT id, orgao_nome, municipio, objeto, valor_estimado,
                       ranking, status_canonico, source, data_publicacao,
                       data_abertura, ranking_score
                FROM opportunity_intel
                WHERE is_active = TRUE
                  AND COALESCE(source, '') <> 'test_batch'
                  AND status_canonico IN ('open', 'upcoming')
                  AND (
                    ingested_at >= NOW() - (%s || ' hours')::interval
                    OR data_publicacao >= CURRENT_DATE - 2
                  )
                ORDER BY ranking_score DESC NULLS LAST, data_publicacao DESC NULLS LAST
                LIMIT 30
                """,
                (hours_new,),
            )
            if rows:
                return SectionResult(name=name, status="OK", items=rows, meta={"source": "opportunity_intel"})
            return SectionResult(
                name=name,
                status="EMPTY",
                reason="Nenhuma oportunidade nova no horizonte solicitado (PG).",
                meta={"source": "opportunity_intel"},
            )
        except Exception as exc:  # noqa: BLE001
            pg_err = f"query failed: {exc}"

    # File fallback — session radar / commercial sample
    items = _load_session_opportunities(status_open=True, recent_days=2)
    if items:
        return SectionResult(
            name=name,
            status="OK",
            reason="Fallback: artefatos de sessão (PG indisponível)." if pg_err else "Fallback de sessão.",
            items=items[:30],
            meta={"source": "session_files", "pg_error": pg_err},
        )
    return SectionResult(
        name=name,
        status="UNAVAILABLE",
        reason=pg_err or "Sem PG e sem artefatos de sessão com oportunidades abertas.",
    )


def _section_near_deadline(
    conn: Any | None,
    pg_err: str | None,
    days: int,
) -> SectionResult:
    name = f"Prazos próximos ({days} dias)"
    if conn is not None:
        try:
            rows = pg_query(
                conn,
                """
                SELECT id, orgao_nome, municipio, objeto, valor_estimado,
                       ranking, status_canonico, source,
                       data_abertura, data_encerramento,
                       COALESCE(data_encerramento, data_abertura) AS prazo
                FROM opportunity_intel
                WHERE is_active = TRUE
                  AND COALESCE(source, '') <> 'test_batch'
                  AND status_canonico IN ('open', 'upcoming')
                  AND COALESCE(data_encerramento, data_abertura) IS NOT NULL
                  AND COALESCE(data_encerramento, data_abertura)::date
                      BETWEEN CURRENT_DATE AND CURRENT_DATE + %s
                ORDER BY COALESCE(data_encerramento, data_abertura) ASC
                LIMIT 30
                """,
                (days,),
            )
            if rows:
                return SectionResult(name=name, status="OK", items=rows, meta={"source": "opportunity_intel"})
            return SectionResult(
                name=name,
                status="EMPTY",
                reason="Nenhum prazo nos próximos dias (PG).",
                meta={"source": "opportunity_intel"},
            )
        except Exception as exc:  # noqa: BLE001
            pg_err = f"query failed: {exc}"

    items = _load_session_opportunities(status_open=True, near_deadline_days=days)
    if items:
        return SectionResult(
            name=name,
            status="OK",
            reason="Fallback: artefatos de sessão." if pg_err else "Fallback de sessão.",
            items=items[:30],
            meta={"source": "session_files", "pg_error": pg_err},
        )
    return SectionResult(
        name=name,
        status="UNAVAILABLE",
        reason=pg_err or "Sem dados de prazo (PG e sessão).",
    )


def _section_review(conn: Any | None, pg_err: str | None) -> SectionResult:
    name = "Aguardando revisão humana (REVIEW)"
    if conn is not None:
        try:
            rows = pg_query(
                conn,
                """
                SELECT id, orgao_nome, municipio, objeto, valor_estimado,
                       ranking, ranking_score, status_canonico, source
                FROM opportunity_intel
                WHERE is_active = TRUE
                  AND COALESCE(source, '') <> 'test_batch'
                  AND ranking = 'REVIEW'
                ORDER BY ranking_score DESC NULLS LAST
                LIMIT 30
                """,
            )
            if rows:
                return SectionResult(name=name, status="OK", items=rows, meta={"source": "opportunity_intel"})
            return SectionResult(
                name=name,
                status="EMPTY",
                reason="Nenhum item com ranking REVIEW no momento.",
                meta={"source": "opportunity_intel"},
            )
        except Exception as exc:  # noqa: BLE001
            pg_err = f"query failed: {exc}"

    items = _load_session_opportunities(needs_review=True)
    if items:
        return SectionResult(
            name=name,
            status="OK",
            reason="Fallback: needs_human_review nos artefatos de sessão.",
            items=items[:30],
            meta={"source": "session_files", "pg_error": pg_err},
        )
    return SectionResult(
        name=name,
        status="UNAVAILABLE" if pg_err else "EMPTY",
        reason=pg_err or "Sem itens REVIEW e sem fallback de sessão.",
    )


def _section_source_health(conn: Any | None, pg_err: str | None) -> SectionResult:
    name = "Fontes falhas / stale"
    if conn is not None:
        try:
            rows = pg_query(
                conn,
                """
                SELECT source,
                       COUNT(*) AS total_records,
                       COUNT(*) FILTER (WHERE status_canonico = 'open') AS open_count,
                       MAX(ingested_at) AS last_ingested
                FROM opportunity_intel
                WHERE is_active = TRUE
                GROUP BY source
                ORDER BY source
                """,
            )
            stale: list[dict[str, Any]] = []
            now = datetime.now()
            for r in rows:
                last = r.get("last_ingested")
                last_dt = None
                if isinstance(last, str):
                    try:
                        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00")).replace(tzinfo=None)
                    except ValueError:
                        last_dt = None
                elif isinstance(last, datetime):
                    last_dt = last.replace(tzinfo=None) if last.tzinfo else last
                hours = (now - last_dt).total_seconds() / 3600 if last_dt else 9999
                if hours > 36 or (r.get("open_count") or 0) == 0:
                    stale.append(
                        {
                            "source": r.get("source"),
                            "open_count": r.get("open_count"),
                            "total_records": r.get("total_records"),
                            "last_ingested": last,
                            "hours_since": round(hours, 1),
                            "status": "STALE" if hours > 36 else "NO_OPEN",
                        }
                    )
            # Also try opportunity_runs failures
            try:
                failed = pg_query(
                    conn,
                    """
                    SELECT id, source, status, started_at, error_message
                    FROM opportunity_runs
                    WHERE status ILIKE '%%fail%%' OR status ILIKE '%%error%%'
                    ORDER BY started_at DESC
                    LIMIT 10
                    """,
                )
                for f in failed:
                    stale.append(
                        {
                            "source": f.get("source"),
                            "status": f.get("status"),
                            "started_at": f.get("started_at"),
                            "error_message": (f.get("error_message") or "")[:120],
                        }
                    )
            except Exception:  # noqa: BLE001, S110 — runs table optional
                pass

            if stale:
                return SectionResult(name=name, status="OK", items=stale, meta={"source": "opportunity_intel"})
            return SectionResult(
                name=name,
                status="EMPTY",
                reason="Nenhuma fonte stale/falha detectada nas métricas disponíveis.",
                meta={"source": "opportunity_intel"},
            )
        except Exception as exc:  # noqa: BLE001
            pg_err = f"query failed: {exc}"

    # File fallback
    for path in (
        SESSION_DIR / "freshness_manifest.json",
        Path("output/readiness/freshness-gate.json"),
        SESSION_DIR / "multi_source-latest.json",
    ):
        data = load_json(path)
        if not data:
            continue
        items: list[dict[str, Any]] = []
        if isinstance(data, dict):
            failing = data.get("failing_sources") or []
            if failing:
                items.extend({"source": s, "status": "FAILING"} for s in failing)
            for src in data.get("critical_sources") or []:
                if isinstance(src, dict) and (
                    src.get("recent_records") == 0 or src.get("last_success_at") is None
                ):
                    items.append(
                        {
                            "source": src.get("source"),
                            "status": "STALE",
                            "last_success_at": src.get("last_success_at"),
                            "recent_records": src.get("recent_records"),
                        }
                    )
            freshness = data.get("freshness") or {}
            for s in freshness.get("failing_sources") or []:
                items.append({"source": s, "status": "FAILING", "from": str(path)})
        if items:
            return SectionResult(
                name=name,
                status="OK",
                reason=f"Fallback: {path}",
                items=items,
                meta={"source": "session_files", "pg_error": pg_err},
            )

    return SectionResult(
        name=name,
        status="UNAVAILABLE",
        reason=pg_err or "source-health indisponível (sem PG e sem freshness artifacts).",
    )


def _section_expiring(conn: Any | None, pg_err: str | None) -> SectionResult:
    name = "Contratos expirando (30/60/90d)"
    if conn is not None:
        try:
            rows = pg_query(
                conn,
                """
                SELECT contrato_id, orgao_nome, fornecedor_nome, objeto_contrato,
                       valor_contrato, data_fim_contrato, dias_ate_fim, municipio
                FROM v_expiring_contracts
                WHERE dias_ate_fim BETWEEN 0 AND 90
                ORDER BY dias_ate_fim ASC
                LIMIT 30
                """,
            )
            if rows:
                for r in rows:
                    d = r.get("dias_ate_fim")
                    if d is None:
                        r["bucket"] = "?"
                    elif d <= 30:
                        r["bucket"] = "30d"
                    elif d <= 60:
                        r["bucket"] = "60d"
                    else:
                        r["bucket"] = "90d"
                return SectionResult(name=name, status="OK", items=rows, meta={"source": "contract_intel"})
            return SectionResult(
                name=name,
                status="EMPTY",
                reason="Nenhum contrato com fim de vigência em 90 dias (view).",
                meta={"source": "contract_intel"},
            )
        except Exception as exc:  # noqa: BLE001
            # Try raw table
            try:
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
                          AND CURRENT_DATE + INTERVAL '90 days'
                    ORDER BY data_fim_vigencia ASC
                    LIMIT 30
                    """,
                )
                if rows:
                    for r in rows:
                        d = r.get("dias_ate_fim")
                        try:
                            di = int(d) if d is not None else None
                        except (TypeError, ValueError):
                            di = None
                        if di is None:
                            r["bucket"] = "?"
                        elif di <= 30:
                            r["bucket"] = "30d"
                        elif di <= 60:
                            r["bucket"] = "60d"
                        else:
                            r["bucket"] = "90d"
                    return SectionResult(
                        name=name,
                        status="OK",
                        items=rows,
                        meta={"source": "pncp_supplier_contracts"},
                    )
            except Exception as exc2:  # noqa: BLE001
                pg_err = f"query failed: {exc}; fallback: {exc2}"

    summary = load_json(SESSION_DIR / "session_summary.json") or load_json(
        SESSION_OUTPUT / "session_summary.json"
    )
    if summary:
        return SectionResult(
            name=name,
            status="UNAVAILABLE",
            reason=(
                "contract_intel indisponível offline. "
                f"Sessão: open_opportunities={summary.get('open_opportunities')}. "
                f"PG: {pg_err or 'n/a'}"
            ),
            meta={"source": "session_summary_note"},
        )
    return SectionResult(
        name=name,
        status="UNAVAILABLE",
        reason=pg_err or "Contratos expirando: PG e views indisponíveis.",
    )


def _section_pending_profile() -> SectionResult:
    name = "Campos de perfil pendentes (elicitation)"
    profile = load_yaml(CLIENT_PROFILE)
    if profile is None:
        return SectionResult(
            name=name,
            status="UNAVAILABLE",
            reason=f"Perfil não legível: {CLIENT_PROFILE}",
        )

    pending: list[dict[str, Any]] = []
    # Nested elicitation block preferred
    elicitation = profile.get("elicitation") or profile.get("pending_fields") or {}
    operational = profile.get("operational_capacity") or profile.get("capacity") or {}

    for key in PENDING_PROFILE_KEYS:
        val = None
        if key in profile:
            val = profile[key]
        elif key in operational:
            val = operational[key]
        elif key in elicitation:
            val = elicitation[key]
        # Nested dict with value/status
        if isinstance(val, dict):
            status = str(val.get("status") or val.get("state") or "").upper()
            inner = val.get("value")
            if status in {"PENDING", "ELICIT", "TODO", "NULL"} or _is_empty(inner):
                pending.append(
                    {
                        "field": key,
                        "status": status or "PENDING",
                        "note": val.get("note") or val.get("description") or "Aguardando elicitation",
                    }
                )
            continue
        if _is_empty(val):
            pending.append(
                {
                    "field": key,
                    "status": "PENDING",
                    "note": "null/empty no extra.yaml — não inventar valor",
                }
            )

    # Also flag empty lists that are commercially meaningful
    for key in ("priority_organs", "known_competitors", "priority_municipalities"):
        if _is_empty(profile.get(key)):
            pending.append(
                {
                    "field": key,
                    "status": "PENDING",
                    "note": "lista vazia — calibrar com Tiago",
                }
            )

    if pending:
        return SectionResult(
            name=name,
            status="OK",
            items=pending,
            meta={"profile": str(CLIENT_PROFILE), "count": len(pending)},
        )
    return SectionResult(name=name, status="EMPTY", reason="Nenhum campo pendente detectado.")


def _section_suggested_actions(prior: list[SectionResult]) -> SectionResult:
    name = "Ações sugeridas / relatórios devidos"
    actions: list[dict[str, Any]] = []

    for sec in prior:
        if sec.status == "UNAVAILABLE":
            actions.append(
                {
                    "action": f"Restaurar dados: {sec.name}",
                    "priority": "high",
                    "detail": sec.reason,
                }
            )
        elif sec.status == "OK" and sec.items and "REVIEW" in sec.name:
            actions.append(
                {
                    "action": "Revisar fila REVIEW",
                    "priority": "high",
                    "detail": f"{len(sec.items)} itens aguardando decisão humana",
                }
            )
        elif sec.status == "OK" and sec.items and "Prazos" in sec.name:
            actions.append(
                {
                    "action": "Triagem de prazos",
                    "priority": "high",
                    "detail": f"{len(sec.items)} oportunidades com prazo ≤7d",
                }
            )
        elif sec.status == "OK" and sec.items and "perfil" in sec.name.lower():
            actions.append(
                {
                    "action": "Elicitar perfil Extra",
                    "priority": "medium",
                    "detail": f"{len(sec.items)} campos PENDING em extra.yaml",
                }
            )
        elif sec.status == "OK" and sec.items and "Fontes" in sec.name:
            actions.append(
                {
                    "action": "Checar source-health / crawlers",
                    "priority": "medium",
                    "detail": f"{len(sec.items)} fontes com alerta",
                }
            )

    # Standing operational suggestions
    actions.append(
        {
            "action": "Briefing diário",
            "priority": "medium",
            "detail": "python -m scripts.workspace briefing",
        }
    )
    actions.append(
        {
            "action": "Coverage check",
            "priority": "low",
            "detail": "python -m scripts.workspace coverage",
        }
    )
    weekday = date.today().weekday()
    if weekday == 0:  # Monday
        actions.append(
            {
                "action": "Relatório semanal de cobertura",
                "priority": "medium",
                "detail": "python -m scripts.workspace report weekly",
            }
        )

    return SectionResult(name=name, status="OK", items=actions, meta={"count": len(actions)})


def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() in {"", "null", "None", "PENDING", "TODO"}:
        return True
    if isinstance(val, (list, dict, tuple, set)) and len(val) == 0:
        return True
    return False


def _load_session_opportunities(
    *,
    status_open: bool = False,
    recent_days: int | None = None,
    near_deadline_days: int | None = None,
    needs_review: bool = False,
) -> list[dict[str, Any]]:
    """Load opportunities from session radar / commercial sample files."""
    candidates = [
        SESSION_OUTPUT / "radar_opportunities_sample.jsonl",
        SESSION_OUTPUT / "radar_opportunities.jsonl",
        SESSION_DIR / "commercial-sample-sc.json",
        SESSION_OUTPUT / "commercial-sample-sc.json",
        SESSION_DIR / "commercial-b2g-session-sc.json",
    ]
    items: list[dict[str, Any]] = []
    today = date.today()

    for path in candidates:
        if path.suffix == ".jsonl":
            raw = load_jsonl(path, limit=200)
            for r in raw:
                mapped = _map_session_row(r)
                if _filter_session_item(
                    mapped,
                    r,
                    status_open=status_open,
                    recent_days=recent_days,
                    near_deadline_days=near_deadline_days,
                    needs_review=needs_review,
                    today=today,
                ):
                    items.append(mapped)
        else:
            data = load_json(path)
            if not isinstance(data, dict):
                continue
            sample = (data.get("opportunities") or {}).get("open_sample") or data.get("open_sample") or []
            for r in sample:
                mapped = _map_session_row(r)
                if _filter_session_item(
                    mapped,
                    r,
                    status_open=True,  # open_sample is already open
                    recent_days=recent_days,
                    near_deadline_days=near_deadline_days,
                    needs_review=needs_review,
                    today=today,
                ):
                    items.append(mapped)
        if items:
            break
    return items


def _map_session_row(r: dict[str, Any]) -> dict[str, Any]:
    commercial = r.get("commercial") if isinstance(r.get("commercial"), dict) else {}
    return {
        "id": r.get("source_id") or r.get("id") or r.get("source_id"),
        "orgao_nome": r.get("orgao_nome") or r.get("orgao") or r.get("title"),
        "municipio": r.get("municipio"),
        "objeto": r.get("objeto") or r.get("title") or "",
        "valor_estimado": r.get("valor_total_estimado") or r.get("valor_estimado"),
        "status_canonico": r.get("status_bucket")
        or commercial.get("status")
        or r.get("status"),
        "source": r.get("source") or "session",
        "data_publicacao": r.get("data_publicacao") or r.get("publication_date"),
        "data_abertura": r.get("data_abertura"),
        "data_encerramento": r.get("data_encerramento"),
        "ranking": "REVIEW" if commercial.get("needs_human_review") else None,
        "link": r.get("link_oficial") or r.get("url"),
    }


def _filter_session_item(
    mapped: dict[str, Any],
    raw: dict[str, Any],
    *,
    status_open: bool,
    recent_days: int | None,
    near_deadline_days: int | None,
    needs_review: bool,
    today: date,
) -> bool:
    commercial = raw.get("commercial") if isinstance(raw.get("commercial"), dict) else {}

    if needs_review:
        return bool(commercial.get("needs_human_review")) or mapped.get("ranking") == "REVIEW"

    if status_open:
        bucket = str(mapped.get("status_canonico") or "").lower()
        if bucket and bucket not in {
            "open",
            "upcoming",
            "open_opportunity",
            "upcoming_opportunity",
            "recent_notice",
            "em recebimento de proposta",
            "aguardando abertura da sessão",
        }:
            # commercial-sample open_sample is trusted open
            if raw.get("status_bucket") not in {None, "open", "upcoming"}:
                if "open" not in bucket and "upcoming" not in bucket and "recent" not in bucket:
                    return False

    if recent_days is not None:
        pub = parse_date_safe(mapped.get("data_publicacao"))
        if pub is None:
            return True  # keep if unknown date in fallback sample
        if pub < today - timedelta(days=recent_days):
            return False

    if near_deadline_days is not None:
        prazo = parse_date_safe(mapped.get("data_encerramento")) or parse_date_safe(
            mapped.get("data_abertura")
        )
        if prazo is None:
            return False
        if not (today <= prazo <= today + timedelta(days=near_deadline_days)):
            return False

    return True
