"""QW-01 auditable, PostgreSQL-only opportunity radar orchestration."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg2.extras

from scripts.crawl.registry import iter_sources
from scripts.lib.universe import CanonicalEntity, CanonicalUniverse, load_canonical_universe
from scripts.opportunity_intel.pncp_audit import PncpRunOutcome, run_pncp_open_monitoring
from scripts.opportunity_intel.profile import ClientProfile, load_client_profile
from scripts.opportunity_intel.schema import (
    connect_postgres,
    git_identity,
    schema_fingerprint,
    validate_qw01_schema,
)
from scripts.opportunity_intel.scoring import RadarScores, score_opportunity

MONITORING_THRESHOLD = 95.0
ILLEGAL_SPREADSHEET_CHARS = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")
RADAR_COLUMNS = (
    "opportunity_key",
    "source",
    "source_ids",
    "official_url",
    "entity_id",
    "orgao_cnpj",
    "orgao_nome",
    "municipio",
    "distancia_km",
    "objeto",
    "categoria",
    "modalidade",
    "valor_estimado",
    "valor_semantica",
    "data_publicacao",
    "data_abertura",
    "data_encerramento",
    "dias_restantes",
    "status_canonico",
    "status_evidence",
    "data_confidence_score",
    "client_fit_score",
    "triage_recommendation",
    "positive_factors",
    "negative_factors",
    "blockers",
    "missing_fields",
    "first_seen_at",
    "last_seen_at",
    "run_id",
    "generated_at",
    "git_sha",
    "seed_sha256",
    "schema_fingerprint",
)


@dataclass(frozen=True)
class RadarExecution:
    run_id: str
    output_dir: str
    exit_code: int
    readiness: str
    universe_resolution_percent: float
    monitoring_coverage_percent: float
    data_presence_percent: float
    triage_counts: dict[str, int]


def bounded_percent(numerator: int, denominator: int) -> float:
    """Return a percentage that can never escape [0, 100]."""
    if denominator <= 0:
        return 0.0
    return round(min(100.0, max(0.0, numerator / denominator * 100.0)), 2)


def build_monitoring_metrics(
    universe: CanonicalUniverse,
    latest_evidence: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compute coverage and gaps from one identical conservative population."""
    population = universe.conservative_monitoring_population
    covered = 0
    state_counts: Counter[str] = Counter()
    gaps: list[dict[str, Any]] = []
    for entity in population:
        evidence = latest_evidence.get(entity.entity_id, {})
        state = str(evidence.get("state") or "never")
        state_counts[state] += 1
        complete = evidence_is_monitoring_success(evidence)
        if complete:
            covered += 1
            continue
        gaps.append(
            {
                "entity_id": entity.entity_id,
                "razao_social": entity.razao_social,
                "municipio": entity.municipio,
                "distancia_km": entity.distancia_km,
                "source": "pncp",
                "status": state,
                "blocker": evidence.get("error_message")
                or evidence.get("error_code")
                or "Nenhuma investigação auditável dentro da janela",
                "ultima_tentativa": evidence.get("checked_at"),
                "acao_recomendada": _gap_action(state),
            }
        )
    denominator = len(population)
    return (
        {
            "denominator": denominator,
            "numerator": covered,
            "percent": bounded_percent(covered, denominator),
            "threshold_percent": MONITORING_THRESHOLD,
            "formula": (
                "entes com success/success_zero fresco e escopo/paginação completos "
                "/ (entes incluídos + unresolved) * 100"
            ),
            "states": dict(sorted(state_counts.items())),
        },
        gaps,
    )


def evidence_is_monitoring_success(evidence: dict[str, Any]) -> bool:
    """Accept success_zero only with explicit full-scope evidence."""
    if evidence.get("state") not in {"success", "success_zero"}:
        return False
    if evidence.get("freshness_status") != "fresh":
        return False
    pages_processed = int(evidence.get("pages_processed") or 0)
    pages_expected = evidence.get("pages_expected")
    metadata = evidence.get("evidence_metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    explicit_complete = bool(metadata.get("scope_complete"))
    if pages_expected is not None:
        pagination_complete = pages_processed >= int(pages_expected)
    else:
        pagination_complete = metadata.get("completion_rule") in {
            "short_page_without_total",
            "empty_page_after_valid_scope",
            "http_204_complete",
        }
    return pages_processed > 0 and explicit_complete and pagination_complete


def run_radar(
    *,
    dsn: str,
    profile_path: str | Path,
    seed_path: str | Path,
    window_days: int,
    output_root: str | Path,
    update_mode: str = "auto",
    timeout: int = 10,
    max_retries: int = 0,
    max_pages: int | None = None,
    max_records: int | None = None,
) -> RadarExecution:
    """Execute the complete radar vertical and emit one immutable artifact set."""
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    if update_mode not in {"auto", "always", "never"}:
        raise ValueError("update_mode must be auto, always, or never")

    generated = datetime.now(UTC)
    run_id = f"qw01-{generated.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    output_dir = Path(output_root).resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    conn = connect_postgres(dsn)
    warnings: list[str] = []
    try:
        schema_info = validate_qw01_schema(conn)
        fingerprint = schema_fingerprint(conn)
        git = git_identity()
        profile = load_client_profile(profile_path)
        universe = load_canonical_universe(seed_path=seed_path, conn=conn)
        metadata = {
            "run_id": run_id,
            "generated_at": generated.isoformat(),
            "git_sha": git.sha,
            "branch": git.branch,
            "seed_path": universe.seed_path,
            "seed_sha256": universe.seed_sha256,
            "schema_fingerprint": fingerprint,
        }
        _write_json(output_dir / "universe_snapshot.json", metadata, universe.to_snapshot())

        source_outcome = _update_or_reuse_source(
            conn=conn,
            dsn=dsn,
            run_id=run_id,
            universe=universe,
            generated=generated,
            window_days=window_days,
            update_mode=update_mode,
            timeout=timeout,
            max_retries=max_retries,
            max_pages=max_pages,
            max_records=max_records,
        )
        if source_outcome is None:
            warnings.append("Nenhuma execução PNCP auditável foi executada ou reutilizada")
        elif not source_outcome.scope_complete:
            warnings.append("Coleta PNCP incompleta; success_zero não foi reconhecido")

        evidence = _load_latest_evidence(conn, universe, generated, window_days)
        monitoring, gaps = build_monitoring_metrics(universe, evidence)
        presence_ids = _load_presence_ids(conn, universe)
        presence_denominator = len(universe.conservative_monitoring_population)
        data_presence = {
            "denominator": presence_denominator,
            "numerator": len(presence_ids),
            "percent": bounded_percent(len(presence_ids), presence_denominator),
            "formula": "entes canônicos com ao menos um registro / denominador conservador * 100",
            "operational_coverage": False,
        }

        candidates, candidate_warnings = _load_and_score_candidates(
            conn, universe, profile, generated, window_days, metadata
        )
        warnings.extend(candidate_warnings)
        field_readiness = _field_readiness(candidates)
        source_health = _source_health(source_outcome, generated, window_days)
        applicability = _source_applicability(universe)
        source_channel = {
            "pncp": source_health,
            "overall_channel_readiness": "NOT_READY",
            "reason": "Somente o canal PNCP foi selecionado e executado no QW-01",
        }

        universe_resolution = {
            "denominator": len(universe.entities),
            "numerator": len(universe.entities) - len(universe.unresolved),
            "percent": universe.resolution_coverage,
            "formula": "linhas-seed com identidade e decisão de raio / linhas-seed * 100",
        }
        readiness = _readiness(universe_resolution, monitoring, source_health)
        coverage_manifest = {
            "metadata": metadata,
            "universe_resolution": universe_resolution,
            "monitoring_coverage": monitoring,
            "pncp_monitoring_coverage": monitoring,
            "data_presence": data_presence,
            "opportunity_field_readiness": field_readiness,
            "source_channel_readiness": source_channel,
            "unresolved": [entity.entity_id for entity in universe.unresolved],
            "duplicates": {
                "cnpj_roots": universe.duplicate_roots,
                "suspicious_identity_keys": universe.suspicious_duplicate_keys,
            },
            "stale": monitoring["states"].get("stale", 0),
            "partial": monitoring["states"].get("partial", 0),
            "failed": monitoring["states"].get("error", 0),
            "success_zero": monitoring["states"].get("success_zero", 0),
            "threshold_percent": MONITORING_THRESHOLD,
            "status": readiness,
        }

        _write_radar_csv(output_dir / "radar_editais.csv", candidates)
        _write_optional_xlsx(output_dir / "radar_editais.xlsx", candidates, metadata, warnings)
        _write_json(output_dir / "coverage_manifest.json", metadata, coverage_manifest)
        _write_gaps_csv(output_dir / "coverage_gaps.csv", gaps, metadata)
        _write_json(output_dir / "source_health.json", metadata, source_health)
        _write_source_applicability(output_dir / "source-applicability.csv", applicability, metadata)

        triage_counts = dict(Counter(row["triage_recommendation"] for row in candidates))
        claims_blocked = [
            "cobertura multicanal de 95%",
            "recomendação definitiva de participação",
            "preço efetivamente pago ou deságio real",
            "conjunto completo de licitantes",
        ]
        run_manifest = {
            "metadata": metadata,
            "schema": schema_info,
            "profile": {"path": str(Path(profile_path).resolve()), "id": profile.profile_id},
            "commands": [
                "python3 -m scripts.opportunity_intel.cli radar "
                f"--profile {profile_path} --window-days {window_days} --output-dir {output_root}"
            ],
            "source_runs": [source_outcome.manifest()] if source_outcome else [],
            "record_counts": {
                "radar": len(candidates),
                "coverage_gaps": len(gaps),
                "monitoring_denominator": monitoring["denominator"],
                "triage": triage_counts,
            },
            "test_results": _load_gate_results(Path(output_root)),
            "warnings": warnings,
            "claims_explicitly_blocked": claims_blocked,
            "readiness": readiness,
            "exit_code": 0 if readiness == "PASS" else 2,
        }
        _write_json(output_dir / "run_manifest.json", metadata, run_manifest)
        _write_summary(
            output_dir / "summary.md",
            metadata,
            readiness,
            coverage_manifest,
            triage_counts,
            candidates,
            warnings,
        )
        _publish_current_applicability(Path(output_root), output_dir)
        return RadarExecution(
            run_id=run_id,
            output_dir=str(output_dir),
            exit_code=0 if readiness == "PASS" else 2,
            readiness=readiness,
            universe_resolution_percent=universe.resolution_coverage,
            monitoring_coverage_percent=monitoring["percent"],
            data_presence_percent=data_presence["percent"],
            triage_counts=triage_counts,
        )
    finally:
        conn.close()


def _update_or_reuse_source(
    *,
    conn: Any,
    dsn: str,
    run_id: str,
    universe: CanonicalUniverse,
    generated: datetime,
    window_days: int,
    update_mode: str,
    timeout: int,
    max_retries: int,
    max_pages: int | None,
    max_records: int | None,
) -> PncpRunOutcome | None:
    if update_mode in {"auto", "never"}:
        recent = _load_recent_complete_run(conn, generated, window_days)
        if recent is not None:
            return recent
        if update_mode == "never":
            return None
    return run_pncp_open_monitoring(
        dsn=dsn,
        external_run_id=run_id,
        universe=universe,
        period_start=(generated - timedelta(days=window_days)).date(),
        period_end=generated.date(),
        mode="full",
        max_pages=max_pages,
        max_records=max_records,
        persist=True,
        timeout=timeout,
        max_retries=max_retries,
        request_delay=None,
    )


def _load_recent_complete_run(conn: Any, generated: datetime, window_days: int) -> PncpRunOutcome | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT * FROM opportunity_runs
            WHERE source = 'pncp' AND source_strategy = 'pncp_open_proposals'
              AND scope_complete IS TRUE AND status IN ('completed', 'completed_zero')
              AND finished_at >= %s
            ORDER BY finished_at DESC LIMIT 1
            """,
            (generated - timedelta(days=window_days),),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return PncpRunOutcome(
        external_run_id=str(row["external_run_id"]),
        db_run_id=int(row["id"]),
        status=str(row["status"]),
        scope_complete=True,
        pages_expected=row["pages_expected"],
        pages_processed=int(row["pages_processed"] or 0),
        records_expected=row["records_expected"],
        records_fetched=int(row["records_fetched"] or 0),
        records_inserted=int(row["records_new"] or 0),
        records_updated=int(row["records_updated"] or 0),
        error_code=row["error_code"],
        error_message=row["error_message"],
        scopes=(),
        records=(),
    )


def _load_latest_evidence(
    conn: Any, universe: CanonicalUniverse, generated: datetime, window_days: int
) -> dict[str, dict[str, Any]]:
    keys = [entity.entity_id for entity in universe.conservative_monitoring_population]
    if not keys:
        return {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (canonical_entity_key)
                canonical_entity_key, state::text, checked_at, pages_expected,
                pages_processed, freshness_status, error_code, error_message,
                evidence_metadata
            FROM coverage_evidence
            WHERE source = 'pncp' AND data_type = 'bids'
              AND canonical_entity_key = ANY(%s) AND checked_at >= %s
            ORDER BY canonical_entity_key, checked_at DESC, id DESC
            """,
            (keys, generated - timedelta(days=window_days)),
        )
        return {str(row["canonical_entity_key"]): dict(row) for row in cursor.fetchall()}


def _load_presence_ids(conn: Any, universe: CanonicalUniverse) -> set[str]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT DISTINCT orgao_cnpj, orgao_nome, municipio
            FROM opportunity_intel
            WHERE source = 'pncp' AND is_active IS TRUE AND source_active IS TRUE
              AND COALESCE(crawl_batch_id, '') <> 'test_batch'
            """
        )
        rows = cursor.fetchall()
    resolved: set[str] = set()
    for row in rows:
        entity, _ = universe.resolve_opportunity(row["orgao_cnpj"], row["orgao_nome"], row["municipio"])
        if entity is not None:
            resolved.add(entity.entity_id)
    return resolved


def _load_and_score_candidates(
    conn: Any,
    universe: CanonicalUniverse,
    profile: ClientProfile,
    generated: datetime,
    window_days: int,
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT * FROM opportunity_intel
            WHERE source = 'pncp' AND is_active IS TRUE AND source_active IS TRUE
              AND data_encerramento > %s
              AND status_canonico NOT IN ('closed','suspended','revoked','annulled','failed')
              AND COALESCE(crawl_batch_id, '') <> 'test_batch'
            ORDER BY last_seen_at DESC NULLS LAST, id DESC
            """,
            (generated,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
    deduplicated: dict[str, dict[str, Any]] = {}
    outside = 0
    ambiguous = 0
    for row in rows:
        key = str(row.get("numero_controle_pncp") or row.get("source_id") or "")
        if not key or key in deduplicated:
            continue
        entity, method = universe.resolve_opportunity(
            row.get("orgao_cnpj"), row.get("orgao_nome"), row.get("municipio")
        )
        if entity is None:
            if method == "ambiguous_duplicate_cnpj_root":
                ambiguous += 1
            else:
                outside += 1
            continue
        status_evidence = _status_evidence(row)
        scores = score_opportunity(
            row,
            entity,
            profile,
            status_evidence,
            now=generated,
            freshness_window_days=window_days,
        )
        deduplicated[key] = _radar_row(row, entity, scores, status_evidence, generated, metadata)
    warnings = []
    if outside:
        warnings.append(f"{outside} oportunidades futuras foram bloqueadas por estarem fora do universo")
    if ambiguous:
        warnings.append(f"{ambiguous} oportunidades foram bloqueadas por identidade ambígua")
    result = list(deduplicated.values())
    result.sort(
        key=lambda row: (
            {"PRIORITARIA": 0, "REVISAR": 1, "DESCARTAR": 2}[row["triage_recommendation"]],
            -int(row["client_fit_score"]),
            -int(row["data_confidence_score"]),
        )
    )
    return result, warnings


def _status_evidence(row: dict[str, Any]) -> str:
    provenance = row.get("proveniencia") or {}
    if isinstance(provenance, str):
        provenance = json.loads(provenance)
    if provenance.get("status_evidence") == "pncp_open_proposals_endpoint":
        return "pncp_open_proposals_endpoint"
    return "future_deadline"


def _radar_row(
    row: dict[str, Any],
    entity: CanonicalEntity,
    scores: RadarScores,
    status_evidence: str,
    generated: datetime,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    deadline = row["data_encerramento"]
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return {
        "opportunity_key": row.get("numero_controle_pncp") or row.get("source_id"),
        "source": "pncp",
        "source_ids": _json_cell([row.get("numero_controle_pncp") or row.get("source_id")]),
        "official_url": row.get("source_url") or row.get("link_edital"),
        "entity_id": entity.entity_id,
        "orgao_cnpj": row.get("orgao_cnpj"),
        "orgao_nome": row.get("orgao_nome") or entity.razao_social,
        "municipio": entity.municipio,
        "distancia_km": entity.distancia_km,
        "objeto": row.get("objeto"),
        "categoria": scores.category or row.get("categoria"),
        "modalidade": row.get("modalidade"),
        "valor_estimado": row.get("valor_estimado"),
        "valor_semantica": "valor_total_estimado_informado_pelo_pncp",
        "data_publicacao": _iso(row.get("data_publicacao")),
        "data_abertura": _iso(row.get("data_abertura")),
        "data_encerramento": _iso(deadline),
        "dias_restantes": max(0, int((deadline - generated).total_seconds() // 86400)),
        "status_canonico": row.get("status_canonico"),
        "status_evidence": status_evidence,
        "data_confidence_score": scores.data_confidence_score,
        "client_fit_score": scores.client_fit_score,
        "triage_recommendation": scores.triage_recommendation,
        "positive_factors": _json_cell(scores.positive_factors),
        "negative_factors": _json_cell(scores.negative_factors),
        "blockers": _json_cell(scores.blockers),
        "missing_fields": _json_cell(scores.missing_fields),
        "first_seen_at": _iso(row.get("first_seen_at") or row.get("ingested_at")),
        "last_seen_at": _iso(row.get("last_seen_at") or row.get("updated_at")),
        "run_id": metadata["run_id"],
        "generated_at": metadata["generated_at"],
        "git_sha": metadata["git_sha"],
        "seed_sha256": metadata["seed_sha256"],
        "schema_fingerprint": metadata["schema_fingerprint"],
    }


def _field_readiness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {
        "identificacao_ente": lambda row: bool(row["entity_id"] and row["orgao_nome"]),
        "objeto": lambda row: bool(row["objeto"]),
        "status": lambda row: bool(row["status_canonico"] and row["status_evidence"]),
        "data_encerramento": lambda row: bool(row["data_encerramento"]),
        "link_oficial": lambda row: bool(row["official_url"]),
        "modalidade": lambda row: bool(row["modalidade"]),
        "valor_estimado": lambda row: row["valor_estimado"] is not None,
        "municipio": lambda row: bool(row["municipio"]),
        "match_universo": lambda row: bool(row["entity_id"]),
    }
    denominator = len(rows)
    return {
        name: {
            "numerator": sum(check(row) for row in rows),
            "denominator": denominator,
            "percent": bounded_percent(sum(check(row) for row in rows), denominator),
        }
        for name, check in checks.items()
    }


def _source_health(outcome: PncpRunOutcome | None, generated: datetime, window_days: int) -> dict[str, Any]:
    if outcome is None:
        return {
            "source": "pncp",
            "applicability": "applicable",
            "operational_status": "never",
            "scope": "uf=SC;modalidades=1-19",
            "window_days": window_days,
            "freshness": "never",
            "scope_complete": False,
            "success_zero_evidence": False,
            "blocker": "No auditable source run",
        }
    payload = outcome.manifest()
    return {
        "source": "pncp",
        "applicability": "applicable",
        "operational_status": outcome.status,
        "scope": "uf=SC;modalidades=1-19",
        "window_days": window_days,
        "pages_expected": outcome.pages_expected,
        "pages_processed": outcome.pages_processed,
        "records_expected": outcome.records_expected,
        "records_received": outcome.records_fetched,
        "last_successful_run": generated.isoformat() if outcome.scope_complete else None,
        "freshness": "fresh" if outcome.scope_complete else "unknown",
        "scope_complete": outcome.scope_complete,
        "success_zero_evidence": outcome.scope_complete and outcome.records_fetched == 0,
        "error_code": outcome.error_code,
        "blocker": outcome.error_message,
        "run": payload,
    }


def _source_applicability(universe: CanonicalUniverse) -> list[dict[str, Any]]:
    rows = []
    denominator = len(universe.conservative_monitoring_population)
    for source in iter_sources():
        selected = source.name == "pncp"
        credentials_missing = [name for name in source.credentials if not os.getenv(name)]
        if selected:
            operational_status = "selected_for_execution"
            blocker = ""
            applicable = denominator
        else:
            operational_status = "registered_not_proven"
            blocker = (
                "Credenciais ausentes: " + ", ".join(credentials_missing)
                if credentials_missing
                else "Fora da vertical QW-01; operação ponta a ponta não comprovada"
            )
            applicable = "unknown"
        rows.append(
            {
                "source": source.name,
                "target_group": "entes canônicos ativos dentro de 200 km + unresolved",
                "applicable_entities": applicable,
                "operational_status": operational_status,
                "blocker": blocker,
                "expected_gap_reduction": "unknown",
                "selected_for_qw": selected,
                "rationale": (
                    "Fonte primária oficial do QW-01" if selected else "Não expandir a vertical sem prova ponta a ponta"
                ),
            }
        )
    return rows


def _readiness(
    universe_resolution: dict[str, Any],
    monitoring: dict[str, Any],
    source_health: dict[str, Any],
) -> str:
    if (
        universe_resolution["percent"] >= MONITORING_THRESHOLD
        and monitoring["percent"] >= MONITORING_THRESHOLD
        and source_health.get("scope_complete") is True
    ):
        # A single selected channel cannot prove overall multichannel readiness.
        return "PARTIAL"
    return "FAIL"


def _write_json(path: Path, metadata: dict[str, Any], payload: dict[str, Any]) -> None:
    document = dict(payload)
    document.setdefault("metadata", metadata)
    path.write_text(
        json.dumps(document, default=str, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_radar_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RADAR_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({column: _spreadsheet_cell(row.get(column)) for column in RADAR_COLUMNS} for row in rows)


def _write_gaps_csv(path: Path, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    columns = (
        "entity_id",
        "razao_social",
        "municipio",
        "distancia_km",
        "source",
        "status",
        "blocker",
        "ultima_tentativa",
        "acao_recomendada",
        "run_id",
        "generated_at",
        "git_sha",
        "seed_sha256",
        "schema_fingerprint",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            output = {**row, **{name: metadata[name] for name in columns if name in metadata}}
            writer.writerow({column: _spreadsheet_cell(output.get(column)) for column in columns})


def _write_source_applicability(path: Path, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    base = (
        "source",
        "target_group",
        "applicable_entities",
        "operational_status",
        "blocker",
        "expected_gap_reduction",
        "selected_for_qw",
        "rationale",
    )
    columns = base + ("run_id", "generated_at", "git_sha", "seed_sha256", "schema_fingerprint")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            output = {**row, **{name: metadata[name] for name in columns if name in metadata}}
            writer.writerow({column: _spreadsheet_cell(output.get(column)) for column in columns})


def _write_optional_xlsx(
    path: Path,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    warnings: list[str],
) -> None:
    try:
        from openpyxl import Workbook
    except ImportError:
        warnings.append("radar_editais.xlsx não gerado: openpyxl indisponível")
        return
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Radar"
    sheet.append(list(RADAR_COLUMNS))
    for row in rows:
        sheet.append([_spreadsheet_cell(row.get(column)) for column in RADAR_COLUMNS])
    meta_sheet = workbook.create_sheet("Metadata")
    for key, value in metadata.items():
        meta_sheet.append([key, value])
    workbook.save(path)


def _write_summary(
    path: Path,
    metadata: dict[str, Any],
    readiness: str,
    coverage: dict[str, Any],
    triage_counts: dict[str, int],
    candidates: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    priority = [row for row in candidates if row["triage_recommendation"] == "PRIORITARIA"][:10]
    lines = [
        "# QW-01 — Radar auditável de editais",
        "",
        f"- run_id: `{metadata['run_id']}`",
        f"- generated_at: `{metadata['generated_at']}`",
        f"- git_sha: `{metadata['git_sha']}`",
        f"- seed_sha256: `{metadata['seed_sha256']}`",
        f"- schema_fingerprint: `{metadata['schema_fingerprint']}`",
        f"- readiness: **{readiness}**",
        "",
        "## Métricas",
        "",
        f"- Universe resolution: {coverage['universe_resolution']['percent']}%",
        f"- Monitoring coverage PNCP: {coverage['monitoring_coverage']['percent']}%",
        f"- Data presence: {coverage['data_presence']['percent']}% (descritiva)",
        f"- PRIORITARIA: {triage_counts.get('PRIORITARIA', 0)}",
        f"- REVISAR: {triage_counts.get('REVISAR', 0)}",
        f"- DESCARTAR: {triage_counts.get('DESCARTAR', 0)}",
        "",
        "## Oportunidades prioritárias",
        "",
    ]
    if priority:
        lines.extend(f"- [{row['opportunity_key']}]({row['official_url']}): {row['objeto']}" for row in priority)
    else:
        lines.append("Nenhuma oportunidade atingiu os limiares configurados nesta execução.")
    lines.extend(["", "## Limitações e fontes bloqueadas", ""])
    lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(
        [
            "- Readiness multicanal não comprovada: apenas PNCP foi selecionado.",
            "- A triagem prioriza leitura humana; não é parecer definitivo de participação.",
            "- Valores são estimativas informadas pelo PNCP, não preço efetivamente pago.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _publish_current_applicability(output_root: Path, output_dir: Path) -> None:
    destination = output_root.resolve() / "source-applicability.csv"
    shutil.copyfile(output_dir / "source-applicability.csv", destination)


def _load_gate_results(output_root: Path) -> dict[str, Any]:
    path = output_root.resolve() / "quality-gates.json"
    if not path.is_file():
        return {"status": "not_run_for_this_artifact", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def _gap_action(state: str) -> str:
    return {
        "partial": "Retomar a paginação do escopo PNCP",
        "error": "Corrigir blocker e repetir a coleta PNCP",
        "stale": "Executar nova coleta PNCP completa",
        "blocked": "Resolver identidade/raio ou blocker da fonte",
        "pending": "Executar o escopo pendente",
    }.get(state, "Executar investigação PNCP com paginação comprovada")


def _json_cell(values: Iterable[Any]) -> str:
    return json.dumps(list(values), default=str, ensure_ascii=False)


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _spreadsheet_cell(value: Any) -> Any:
    """Remove invalid controls and neutralize formulas in exported strings."""
    if not isinstance(value, str):
        return value
    clean = ILLEGAL_SPREADSHEET_CHARS.sub("", value)
    if clean.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return "'" + clean
    return clean
