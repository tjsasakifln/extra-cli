"""Canonical public export for web-cfg pSEO.

Usage:
  python -m scripts.pseo.export_web_cfg --out /path/to/webcfg/data/pseo
  python -m scripts.pseo.export_web_cfg --fixture tests/pseo/fixtures/sample_contracts.json --out /tmp/pseo

Read-only. Never writes to the database. Fails closed if forbidden fields
would be emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.pseo import SCHEMA_VERSION
from scripts.pseo.aggregate import assemble_public_payload, classify_bids, classify_rows
from scripts.pseo.archetypes import load_icp_signature_from_top20_artifact
from scripts.pseo.sanitize import assert_public, deep_strip_forbidden

DEFAULT_TOP20 = (
    "artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/"
    "post-merge/evidence-slim/top20-slim.json"
)

TABLES = [
    "pncp_supplier_contracts",
    "pncp_raw_bids",
    "sc_public_entities",
]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_sha() -> str:
    try:
        import shutil

        git = shutil.which("git")
        if not git:
            return "unknown"
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).resolve().parents[2],
        )
        return out.decode().strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_text(s: str) -> str:
    return _sha256_bytes(s.encode("utf-8"))


def load_from_db(dsn: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:
        raise SystemExit(f"psycopg2 required for DB export: {e}") from e

    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    counts: dict[str, int] = {}

    cur.execute(
        """
        SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
               objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
               uf, municipio, source
        FROM pncp_supplier_contracts
        WHERE valor_total IS NOT NULL AND valor_total > 0
        """
    )
    contracts = [dict(r) for r in cur.fetchall()]
    counts["pncp_supplier_contracts"] = len(contracts)

    cur.execute(
        """
        SELECT pncp_id, objeto_compra, valor_total_estimado, modalidade_nome, uf, municipio,
               orgao_razao_social AS orgao_nome, orgao_cnpj,
               data_publicacao, data_abertura, data_encerramento, link_pncp, source
        FROM pncp_raw_bids
        WHERE is_active IS DISTINCT FROM false
        """
    )
    bids = [dict(r) for r in cur.fetchall()]
    counts["pncp_raw_bids"] = len(bids)

    cur.execute("SELECT COUNT(*) AS n FROM sc_public_entities")
    counts["sc_public_entities"] = int(cur.fetchone()["n"])
    conn.close()
    return contracts, bids, counts


def load_from_fixture(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    contracts = raw.get("contracts") or []
    bids = raw.get("bids") or []
    counts = {
        "pncp_supplier_contracts": len(contracts),
        "pncp_raw_bids": len(bids),
        "sc_public_entities": int(raw.get("entity_count") or 0),
        "fixture": 1,
    }
    return contracts, bids, counts


def build_export(
    contracts: list[dict[str, Any]],
    bids: list[dict[str, Any]],
    counts: dict[str, int],
    *,
    top20_path: str | None,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    classified = classify_rows(contracts)
    open_bids = classify_bids(bids)
    # keep only still-open-ish for radar (encerramento null or >= today-7 handled upstream optionally)
    payload = assemble_public_payload(classified, open_bids)
    payload = deep_strip_forbidden(payload)
    assert_public(payload, "export_payload")

    # ICP signature methodology note (no proprietary rows)
    icp = load_icp_signature_from_top20_artifact(top20_path)
    # Strip any accidental identifiers
    icp = {
        "available": icp.get("available"),
        "n_accounts_internal": icp.get("n_accounts_internal"),
        "activity_class_histogram": icp.get("activity_class_histogram"),
        "sector_fit_histogram": icp.get("sector_fit_histogram"),
        "public_signal_frequency": icp.get("public_signal_frequency"),
        "note": icp.get("note"),
    }

    files_body = {
        "archetypes": payload["archetypes"],
        "markets": payload["markets"],
        "agencies": payload["agencies"],
        "prices": payload["prices"],
        "competition": payload["competition"],
        "opportunities": payload["opportunities"],
        "problem_service": payload["problem_service"],
        "icp_methodology": {
            "schema_version": SCHEMA_VERSION,
            "methodology": (
                "Top 20 comercial usado apenas para calibrar classes de atividade "
                "e sinais públicos de portfólio. Nenhuma conta, score, rank ou "
                "estado de pipeline é exportado."
            ),
            "internal_signature_aggregates": icp,
        },
    }
    assert_public(files_body, "files_body")

    dataset_hash = _sha256_text(_canonical_json(files_body))
    generated_at = _now()
    run_id = source_run_id or f"pseo-{generated_at.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"

    # Freshness: max publication date in classified set
    dates = [c.data_publicacao for c in classified if c.data_publicacao]
    bid_dates = [b.get("data_publicacao") for b in open_bids if b.get("data_publicacao")]
    all_dates = [str(d)[:10] for d in dates + bid_dates if d]
    max_data = max(all_dates) if all_dates else None
    min_data = min(all_dates) if all_dates else None

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_run_id": run_id,
        "source_commit_sha": _git_sha(),
        "dataset_hash": dataset_hash,
        "sources": [
            {"table": t, "role": "read_only_aggregate"} for t in TABLES
        ],
        "counts": {
            **counts,
            "classified_aec_contracts": len(classified),
            "classified_aec_bids": len(open_bids),
            "markets": len(payload["markets"]),
            "agencies": len(payload["agencies"]),
            "prices": len(payload["prices"]),
            "competition": len(payload["competition"]),
            "opportunities": len(payload["opportunities"]),
            "archetypes": len(payload["archetypes"]),
            "problem_service": len(payload["problem_service"]),
        },
        "denominators": {
            "contracts_total_loaded": counts.get("pncp_supplier_contracts", 0),
            "bids_total_loaded": counts.get("pncp_raw_bids", 0),
            "classified_share_note": (
                "Classified AEC share is pattern-matched objects only; "
                "not all public works are captured by keyword archetypes."
            ),
        },
        "freshness": {
            "data_period_start": min_data,
            "data_period_end": max_data,
            "max_age_days_policy": 180,
            "generated_at": generated_at,
            "note": "Not real-time. Snapshot at generated_at.",
        },
        "horizon": {
            "period_start": min_data,
            "period_end": max_data,
        },
        "limitations": [
            "Export is aggregated and sanitized; no commercial pipeline fields.",
            "Datalake coverage is incomplete relative to the national universe.",
            "Do not interpret medians as unit prices.",
            "Open opportunities are not guaranteed current after as_of.",
        ],
        "methodology_notes": [
            "ICP-Derived Evidence pSEO: archetypes from public objects + internal activity-class signature.",
            "Allowlist sanitization applied; forbidden commercial fields stripped and asserted absent.",
        ],
        "checksums": {},  # filled after write
    }
    return {"manifest": manifest, "files": files_body, "dataset_hash": dataset_hash}


def write_export(out_dir: Path, bundle: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, Any] = bundle["files"]
    checksums: dict[str, str] = {}
    written: dict[str, str] = {}

    mapping = {
        "archetypes.json": files["archetypes"],
        "markets.json": files["markets"],
        "agencies.json": files["agencies"],
        "prices.json": files["prices"],
        "competition.json": files["competition"],
        "opportunities.json": files["opportunities"],
        "problem_service.json": files["problem_service"],
        "icp_methodology.json": files["icp_methodology"],
    }
    for name, data in mapping.items():
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
        path = out_dir / name
        path.write_text(text, encoding="utf-8")
        checksums[name] = _sha256_text(text)
        written[name] = str(path)

    # schema pointer
    schema = {
        "schema_version": SCHEMA_VERSION,
        "description": "CONFENGE public pSEO evidence snapshot",
        "files": list(mapping.keys()) + ["manifest.json"],
        "forbidden_fields_policy": "scripts/pseo/allowlist.py FORBIDDEN_KEYS",
    }
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (out_dir / "schema.json").write_text(schema_text, encoding="utf-8")
    checksums["schema.json"] = _sha256_text(schema_text)
    written["schema.json"] = str(out_dir / "schema.json")

    manifest = dict(bundle["manifest"])
    manifest["checksums"] = checksums
    m_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    (out_dir / "manifest.json").write_text(m_text, encoding="utf-8")
    written["manifest.json"] = str(out_dir / "manifest.json")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export sanitized pSEO data for web-cfg")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/pseo/web_cfg_export"),
        help="Output directory for JSON snapshot",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Offline fixture JSON (skips database)",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN (default: DATABASE_URL or LOCAL_DATALAKE_DSN)",
    )
    parser.add_argument(
        "--top20",
        default=None,
        help="Path to Top-20 slim artifact (internal signature only)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional source_run_id override",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    top20 = args.top20
    if top20 is None:
        candidate = root / DEFAULT_TOP20
        top20 = str(candidate) if candidate.exists() else None

    if args.fixture:
        contracts, bids, counts = load_from_fixture(args.fixture)
    else:
        dsn = args.dsn or os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_DATALAKE_DSN")
        if not dsn:
            print("ERROR: no DSN and no --fixture", file=sys.stderr)
            return 2
        contracts, bids, counts = load_from_db(dsn)

    bundle = build_export(contracts, bids, counts, top20_path=top20, source_run_id=args.run_id)
    paths = write_export(args.out, bundle)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "dataset_hash": bundle["dataset_hash"],
                "files": list(paths.keys()),
                "counts": bundle["manifest"]["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
