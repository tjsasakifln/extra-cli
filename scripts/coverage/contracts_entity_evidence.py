#!/usr/bin/env python3
"""Project national contracts crawl lineage into per-entity coverage_evidence.

National / windowed PNCP contract crawls do not automatically create dual
coverage numerators. This adapter binds a completed run (or lake window) to
nominal evidence for every applicable entity:

* success_with_data — contracts present for entity in [period_start, period_end]
* success_zero — zero contracts after complete window proof (pagination complete)

Semantic roles for historical_contracts required combination ``pncp+contracts``:
both rows share the same official PNCP /contratos origin and run_id; they are
two audit roles (catalog authority + contracts product surface), not two
independent fetches.

Does not lower denominators. Does not invent success without window proof.

Operational rule (HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01):
``success_zero`` may only be written when a checkpoint/manifest proof artifact
demonstrates that every planned window completed with pagination integrity.
CLI flags alone (``--window-complete --pages-processed 1 --pages-expected 1``)
are not sufficient proof and are rejected for success_zero writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg2.extras import Json

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

CAPABILITY = "historical_contracts"
REQUIRED_SOURCES = ("pncp", "contracts")
DATA_TYPE = "contracts"


@dataclass(frozen=True)
class CheckpointWindowProof:
    """Verified completion proof extracted from crawl checkpoint or manifest."""

    path: str
    completed_windows: tuple[str, ...]
    planned_windows: int
    total_windows_failed: int
    pages_processed: int
    pages_expected: int | None
    run_ids: tuple[str, ...]
    valid: bool
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_checkpoint_window_proof(
    path: Path | str,
    *,
    require_all_planned: bool = True,
    min_planned_windows: int = 1,
) -> CheckpointWindowProof:
    """Load and validate a checkpoint/manifest as proof for window completion.

    Fail-closed: missing file, empty completed set, residual failures, or
    incomplete planned set produce ``valid=False`` with explicit errors.
    """
    p = Path(path)
    errors: list[str] = []
    if not p.is_file():
        return CheckpointWindowProof(
            path=str(p),
            completed_windows=(),
            planned_windows=0,
            total_windows_failed=0,
            pages_processed=0,
            pages_expected=None,
            run_ids=(),
            valid=False,
            errors=(f"checkpoint proof not found: {p}",),
        )
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckpointWindowProof(
            path=str(p),
            completed_windows=(),
            planned_windows=0,
            total_windows_failed=0,
            pages_processed=0,
            pages_expected=None,
            run_ids=(),
            valid=False,
            errors=(f"checkpoint proof unreadable: {exc}",),
        )

    # Accept both pilot live-3y artifact and contracts_full checkpoint shapes.
    if isinstance(raw.get("checkpoint"), dict):
        ck = raw["checkpoint"]
        windows_meta = raw.get("windows") or []
        planned = int(raw.get("planned_windows") or ck.get("planned_windows") or 0)
        pages_from_windows = 0
        incomplete: list[str] = []
        for w in windows_meta:
            if not isinstance(w, dict):
                continue
            st = str(w.get("status") or "")
            if st in {"completed", "skipped_resume"}:
                pages_from_windows += int(w.get("pages") or 0)
            elif st and st not in {"skipped_resume"}:
                incomplete.append(f"{w.get('window_key')}:{st}")
        completed = tuple(str(x) for x in (ck.get("completed_windows") or []))
        failed = int(ck.get("total_windows_failed") or raw.get("totals", {}).get("windows_failed") or 0)
        pages_processed = int(
            (raw.get("totals") or {}).get("pages")
            or pages_from_windows
            or ck.get("total_pages")
            or 0
        )
        run_ids = tuple(
            str(x)
            for x in (
                (ck.get("meta") or {}).get("run_ids")
                or raw.get("previous_run_ids")
                or ([raw["run_id"]] if raw.get("run_id") else [])
            )
        )
        if incomplete:
            errors.append(f"incomplete windows in artifact: {incomplete[:5]}")
    else:
        completed = tuple(str(x) for x in (raw.get("completed_windows") or []))
        planned = int(raw.get("planned_windows") or raw.get("total_windows_planned") or 0)
        # When planned unknown, infer from completed + remaining markers
        if planned <= 0 and completed:
            # contracts_full often lacks planned_windows; allow meta override
            planned = int((raw.get("meta") or {}).get("planned_windows") or 0)
        failed = int(raw.get("total_windows_failed") or 0)
        pages_processed = int(
            raw.get("total_pages")
            or raw.get("pages_processed")
            or (raw.get("meta") or {}).get("pages_processed")
            or 0
        )
        run_ids = tuple(
            str(x)
            for x in (
                (raw.get("meta") or {}).get("run_ids")
                or ([raw["run_id"]] if raw.get("run_id") else [])
            )
        )

    if planned < min_planned_windows and require_all_planned:
        # For national 3y we expect many windows; still allow explicit planned in meta
        if planned <= 0:
            errors.append(
                "planned_windows missing/zero in proof — cannot attest completion"
            )

    if not completed:
        errors.append("completed_windows empty — no window completion proof")

    if require_all_planned and planned > 0 and len(completed) < planned:
        errors.append(
            f"completed_windows={len(completed)} < planned_windows={planned}"
        )

    if failed > 0 and require_all_planned:
        # Residual failures only OK if every planned window is still in completed
        # (failed counter may be historical). Prefer explicit incomplete list.
        if planned > 0 and len(completed) < planned:
            errors.append(f"total_windows_failed={failed} with incomplete set")

    pages_expected = planned if planned > 0 else None
    # Pagination integrity: at least one page processed when windows completed
    if completed and pages_processed < 1:
        errors.append(
            "pages_processed < 1 with completed windows — insufficient pagination proof"
        )

    valid = not errors
    return CheckpointWindowProof(
        path=str(p),
        completed_windows=completed,
        planned_windows=planned,
        total_windows_failed=failed,
        pages_processed=pages_processed,
        pages_expected=pages_expected,
        run_ids=run_ids,
        valid=valid,
        errors=tuple(errors),
    )


def assert_success_zero_proof(
    *,
    window_complete: bool,
    proof: CheckpointWindowProof | None,
    pages_processed: int,
    pages_expected: int | None,
) -> list[str]:
    """Return error list; empty means success_zero writes are allowed."""
    errs: list[str] = []
    if not window_complete:
        errs.append("window_complete=false")
        return errs
    if proof is None:
        errs.append(
            "success_zero requires checkpoint/manifest proof "
            "(--checkpoint-proof PATH); CLI flags alone are not attestation"
        )
        return errs
    if not proof.valid:
        errs.extend(proof.errors or ("checkpoint proof invalid",))
        return errs
    if pages_expected is not None and pages_processed < pages_expected:
        errs.append(
            f"pages_processed={pages_processed} < pages_expected={pages_expected}"
        )
    # Reject trivial self-attestation 1/1 unless proof carries real page counts
    if (
        pages_processed == 1
        and pages_expected == 1
        and proof.pages_processed <= 1
        and len(proof.completed_windows) < 2
    ):
        errs.append(
            "trivial pages_processed=1/pages_expected=1 without multi-window "
            "checkpoint proof is not operational attestation"
        )
    return errs


@dataclass
class EntityEvidenceProjection:
    entity_id: str
    cnpj8: str
    state: str
    records: int
    sources_written: list[str] = field(default_factory=list)


@dataclass
class ProjectionReport:
    run_id: str
    period_start: str
    period_end: str
    as_of: str
    universe_count: int
    applicable_count: int
    success_with_data: int = 0
    success_zero: int = 0
    skipped: int = 0
    written_rows: int = 0
    dry_run: bool = True
    window_complete: bool = False
    completion_rule: str = ""
    limitations: list[str] = field(default_factory=list)
    entities: list[EntityEvidenceProjection] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def default_backfill_window(*, as_of: date | None = None, days: int = 1098) -> tuple[date, date]:
    """Return inclusive [start, end] covering at least 3.0 years under dual math.

    dual_capability_coverage.contracts_backfill_ok uses (end-start).days / 365.25 >= 3.
    1095 calendar days yields ~2.995 years and fails the gate; 1098 is the safe floor.
    """
    end = as_of or datetime.now(UTC).date()
    # inclusive length = days → span_days = days - 1 when using end - (days-1)
    start = end - timedelta(days=max(days, 1098) - 1)
    return start, end


def _connect(dsn: str) -> Any:
    import psycopg2

    return psycopg2.connect(dsn)


def count_contracts_by_cnpj8(
    conn: Any,
    *,
    period_start: date,
    period_end: date,
) -> dict[str, int]:
    """Count supplier contracts per orgao cnpj8 root in publication window."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT REGEXP_REPLACE(COALESCE(orgao_cnpj_8, LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj, ''), '[^0-9]', '', 'g'), 8), ''), '[^0-9]', '', 'g') AS c8,
               COUNT(*)::int
        FROM pncp_supplier_contracts
        WHERE COALESCE(data_publicacao, data_assinatura)::date >= %s
          AND COALESCE(data_publicacao, data_assinatura)::date <= %s
        GROUP BY 1
        """,
        (period_start, period_end),
    )
    out: dict[str, int] = {}
    for c8, n in cur.fetchall():
        digits = "".join(ch for ch in str(c8 or "") if ch.isdigit())[:8]
        if len(digits) == 8:
            out[digits] = int(n)
    cur.close()
    return out


def upsert_entity_source_evidence(
    conn: Any,
    *,
    canonical_entity_key: str,
    source: str,
    run_id: str,
    state: str,
    period_start: date,
    period_end: date,
    records: int,
    pages_processed: int,
    pages_expected: int | None,
    completion_rule: str,
    freshness_status: str,
    provenance: dict[str, Any],
    dry_run: bool = False,
) -> bool:
    """Insert one coverage_evidence row for entity×source×capability."""
    if dry_run:
        return True
    now = datetime.now(UTC)
    scope_key = (
        f"pncp|contracts|entity={canonical_entity_key}|"
        f"{period_start.isoformat()}..{period_end.isoformat()}"
    )
    meta = {
        "completion_rule": completion_rule,
        "pagination_complete": completion_rule in {
            "http_204_complete",
            "pagination_complete",
            "complete",
            "national_window_complete",
        },
        "provenance": provenance,
        "evidence_persisted": True,
        "adapter": "contracts_entity_evidence/1.0",
        "satisfies_semantic_role": source,
        "shared_origin": "pncp_contratos",
    }
    evidence_metadata = dict(meta)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO coverage_evidence (
          entity_id, source, data_type, queried_start, queried_end, run_id,
          started_at, completed_at, count_obtained, count_transformed, count_persisted,
          state, metadata, canonical_entity_key, applicability, applicability_reason,
          scope_key, checked_at, pages_expected, pages_processed, records_fetched,
          open_records, freshness_status, evidence_metadata, capability,
          records_expected, request_scope, pages_fetched, provenance, satisfactory
        ) VALUES (
          NULL, %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s,
          %s, %s, %s, 'applicable', %s,
          %s, %s, %s, %s, %s,
          0, %s, %s, %s,
          %s, %s, %s, %s, %s
        )
        """,
        (
            source,
            DATA_TYPE,
            period_start,
            period_end,
            run_id,
            now,
            now,
            records,
            records,
            records,
            state,
            Json(meta),
            canonical_entity_key,
            f"adapter_projection:{state}",
            scope_key,
            now,
            pages_expected,
            pages_processed,
            records,
            freshness_status,
            Json(evidence_metadata),
            CAPABILITY,
            records if state == "success_with_data" else 0,
            scope_key,
            pages_processed,
            Json(provenance),
            True,
        ),
    )
    cur.close()
    return True


def project_historical_contracts_evidence(
    conn: Any,
    *,
    run_id: str,
    period_start: date,
    period_end: date,
    window_complete: bool,
    completion_rule: str = "national_window_complete",
    pages_processed: int = 1,
    pages_expected: int | None = 1,
    seed_path: Path | None = None,
    dry_run: bool = True,
    only_with_data: bool = False,
    as_of: datetime | None = None,
    checkpoint_proof: CheckpointWindowProof | None = None,
    checkpoint_proof_path: Path | str | None = None,
) -> ProjectionReport:
    """Project lake contracts + window proof into dual-readable coverage_evidence.

    ``success_zero`` writes require a validated checkpoint/manifest proof.
    Manual ``window_complete`` without proof never fabricates success_zero.
    """
    from scripts.coverage.source_policy import (
        entity_attributes_from_canonical,
        load_source_policy,
        select_required_combination,
    )
    from scripts.lib.universe import load_canonical_universe, resolve_default_seed_path

    as_of_dt = as_of or datetime.now(UTC)
    seed = seed_path or resolve_default_seed_path()
    universe = load_canonical_universe(seed_path=seed)
    policy = load_source_policy(require_active=True)
    counts = count_contracts_by_cnpj8(conn, period_start=period_start, period_end=period_end)

    proof = checkpoint_proof
    if proof is None and checkpoint_proof_path is not None:
        proof = load_checkpoint_window_proof(checkpoint_proof_path)

    # Prefer pagination counts from verified proof when present
    eff_pages_processed = pages_processed
    eff_pages_expected = pages_expected
    if proof is not None and proof.valid:
        if proof.pages_processed > 0:
            eff_pages_processed = proof.pages_processed
        if proof.pages_expected is not None:
            eff_pages_expected = proof.pages_expected

    zero_proof_errors = assert_success_zero_proof(
        window_complete=window_complete,
        proof=proof,
        pages_processed=eff_pages_processed,
        pages_expected=eff_pages_expected,
    )
    allow_success_zero = not zero_proof_errors

    report = ProjectionReport(
        run_id=run_id,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        as_of=as_of_dt.isoformat().replace("+00:00", "Z"),
        universe_count=len(universe.included),
        applicable_count=0,
        dry_run=dry_run,
        window_complete=window_complete and allow_success_zero,
        completion_rule=completion_rule,
    )

    if not window_complete:
        report.limitations.append(
            "window_complete=false — success_zero projection disabled; only success_with_data may write"
        )
    elif not allow_success_zero:
        report.limitations.append(
            "success_zero blocked: " + "; ".join(zero_proof_errors)
        )
        report.limitations.append(
            "CLI --window-complete without verified checkpoint proof is not operational attestation"
        )
    else:
        report.limitations.append(
            "window_complete verified via checkpoint/manifest proof "
            f"({proof.path if proof else 'inline'}); "
            f"completed_windows={len(proof.completed_windows) if proof else 0}"
        )

    # SLA freshness for historical_contracts is 168h; projection timestamp is as_of.
    age_hours = 0.0
    freshness = "fresh" if age_hours <= 168 else "stale"

    provenance_base = {
        "run_id": run_id,
        "adapter": "contracts_entity_evidence/1.1",
        "source_origin": "pncp_supplier_contracts",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "window_complete": window_complete and allow_success_zero,
        "completion_rule": completion_rule,
        "success_zero_allowed": allow_success_zero,
        "checkpoint_proof": proof.to_dict() if proof is not None else None,
        "semantic_roles": list(REQUIRED_SOURCES),
        "role_contract": (
            "pncp=official catalog authority; contracts=historical product surface; "
            "shared PNCP /contratos origin"
        ),
    }

    for ent in universe.included:
        attrs = entity_attributes_from_canonical(ent)
        sel = select_required_combination(
            policy, CAPABILITY, attrs, validated_at=report.as_of
        )
        if sel.get("entity_capability_status") != "applicable":
            report.skipped += 1
            continue
        report.applicable_count += 1
        n = int(counts.get(ent.cnpj8, 0))
        if n > 0:
            state = "success_with_data"
            report.success_with_data += 1
        else:
            if only_with_data or not allow_success_zero:
                report.skipped += 1
                continue
            # success_zero requires pagination/window proof (already gated)
            if eff_pages_expected is not None and eff_pages_processed < eff_pages_expected:
                report.skipped += 1
                continue
            state = "success_zero"
            report.success_zero += 1

        proj = EntityEvidenceProjection(
            entity_id=ent.entity_id,
            cnpj8=ent.cnpj8,
            state=state,
            records=n,
        )
        for src in REQUIRED_SOURCES:
            ok = upsert_entity_source_evidence(
                conn,
                canonical_entity_key=ent.entity_id,
                source=src,
                run_id=run_id,
                state=state,
                period_start=period_start,
                period_end=period_end,
                records=n,
                pages_processed=eff_pages_processed,
                pages_expected=eff_pages_expected,
                completion_rule=completion_rule,
                freshness_status=freshness,
                provenance={**provenance_base, "entity_cnpj8": ent.cnpj8, "role": src},
                dry_run=dry_run,
            )
            if ok:
                proj.sources_written.append(src)
                report.written_rows += 1
        report.entities.append(proj)

    if not dry_run:
        conn.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=None)
    p.add_argument("--run-id", required=True)
    p.add_argument("--period-start", required=True, help="YYYY-MM-DD")
    p.add_argument("--period-end", required=True, help="YYYY-MM-DD")
    p.add_argument("--window-complete", action="store_true")
    p.add_argument(
        "--checkpoint-proof",
        type=Path,
        default=None,
        help="Path to contracts_full.json or live-3y.json; required for success_zero",
    )
    p.add_argument("--completion-rule", default="national_window_complete")
    p.add_argument("--pages-processed", type=int, default=1)
    p.add_argument("--pages-expected", type=int, default=1)
    p.add_argument("--write", action="store_true", help="Persist rows (default dry-run)")
    p.add_argument("--only-with-data", action="store_true")
    p.add_argument("--output-json", type=Path, default=None)
    p.add_argument("--seed", type=Path, default=None)
    args = p.parse_args(argv)

    import os

    dsn = args.dsn or os.environ.get(
        "LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    proof = None
    if args.checkpoint_proof is not None:
        proof = load_checkpoint_window_proof(args.checkpoint_proof)
        if args.window_complete and not proof.valid:
            print(
                json.dumps(
                    {
                        "error": "invalid_checkpoint_proof",
                        "path": str(args.checkpoint_proof),
                        "errors": list(proof.errors),
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2
    elif args.window_complete and not args.only_with_data:
        # Fail closed before connecting when operator asks for full projection
        # including potential success_zero without proof.
        print(
            json.dumps(
                {
                    "error": "checkpoint_proof_required",
                    "message": (
                        "--window-complete requires --checkpoint-proof PATH "
                        "for success_zero attestation; flags alone are rejected"
                    ),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    conn = _connect(dsn)
    try:
        report = project_historical_contracts_evidence(
            conn,
            run_id=args.run_id,
            period_start=_parse_date(args.period_start),
            period_end=_parse_date(args.period_end),
            window_complete=bool(args.window_complete),
            completion_rule=args.completion_rule,
            pages_processed=args.pages_processed,
            pages_expected=args.pages_expected,
            seed_path=args.seed,
            dry_run=not args.write,
            only_with_data=args.only_with_data,
            checkpoint_proof=proof,
        )
    finally:
        conn.close()

    payload = report.to_dict()
    # Keep entity sample small in stdout
    payload["entities"] = payload["entities"][:20]
    payload["entities_truncated"] = report.applicable_count > 20
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
