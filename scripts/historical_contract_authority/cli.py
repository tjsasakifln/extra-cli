"""CLI: fixture corpus or bounded official-live SELECT. Never writes the lake."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from scripts.contract_publication.official_snapshot import fetch_official_sc_snapshot, resolve_dsn
from scripts.historical_contract_authority.adapters import rank_via_414
from scripts.historical_contract_authority.cases import CASE_BUILDERS, fixture_corpus
from scripts.historical_contract_authority.engine import build_dossier, dossier_dict, process_cases
from scripts.historical_contract_authority.handoff import write_handoff
from scripts.historical_contract_authority.schema import HANDOFF_DIR, canonical_dumps, content_hash, producer_sha


def _stamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def record_to_case(record: dict[str, Any]) -> dict[str, Any]:
    contract_id = str(record.get("canonical_contract_id") or record.get("contrato_id") or "unknown")
    return {
        "case_id": contract_id,
        "catalog_mode": "official_projection",
        "identity": {
            "contract_id": contract_id,
            "process_id": record.get("source_id"),
            "orgao_cnpj": record.get("orgao_cnpj"),
            "orgao_nome": record.get("orgao_nome"),
            "fornecedor_cnpj": record.get("fornecedor_cnpj"),
            "fornecedor_nome": record.get("fornecedor_nome"),
            "municipio": record.get("municipio"),
            "uf": record.get("uf") or "SC",
            "objeto": record.get("objeto_contrato"),
        },
        "values": {
            "valor_original": record.get("valor_total"),
            "valor_atual": record.get("valor_total"),
            "moeda": "BRL",
            "valor_semantic": record.get("valor_semantic") or "unknown",
            "unidade": record.get("unidade"),
            "regime": record.get("regime"),
            "modalidade": record.get("modalidade"),
        },
        "dates": {
            "reference": record.get("data_assinatura") or record.get("data_inicio") or record.get("observed_at"),
            "assinatura": record.get("data_assinatura"),
            "inicio": record.get("data_inicio"),
            "fim": record.get("data_fim"),
            "observed_at": record.get("observed_at"),
        },
        "documents": list(record.get("documents") or []),
        "claims": [],
        "events": [],
        "contradictions": [],
        "editorial": {
            "central_question": "",
            "theses": [],
            "why_singular": "",
            "transferable_utility": "",
            "cannot_assert": ["ficha official sem documentos materiais"],
        },
        "technical_question": "",
        "limitations": ["HOLD_FOR_DATA until official documents and semantics exist"],
        "comparable_peers": [],
        "maintenance": {"invalidation_keys": [contract_id], "expires_at": "2026-11-15T00:00:00Z"},
    }


def run_fixture(*, output: Path, as_of: str | None = None) -> dict[str, Any]:
    stamp = as_of or "2026-08-17T12:00:00Z"
    cases = fixture_corpus()
    snap = content_hash({"mode": "fixture", "case_ids": [item["case_id"] for item in cases]})
    dossiers = process_cases(cases, as_of=stamp, snapshot_hash=snap)
    replay = "python3 -m scripts.historical_contract_authority --mode fixture --as-of 2026-08-17T12:00:00Z"
    written = write_handoff(
        dossiers,
        output_dir=output,
        as_of=stamp,
        snapshot_hash=snap,
        replay_command=replay,
        catalog_mode="fixture",
    )
    return {"dossiers": dossiers, "handoff": written, "snapshot_hash": snap, "as_of": stamp}


def run_live(*, output: Path, dsn: str | None, limit: int, as_of: str | None = None) -> dict[str, Any]:
    stamp = as_of or _stamp()
    started = time.perf_counter()
    snapshot = fetch_official_sc_snapshot(resolve_dsn(dsn), limit=limit, as_of=stamp)
    live_meta = {
        "source_kind": snapshot.get("source_kind"),
        "reason_codes": snapshot.get("reason_codes") or [],
        "row_count": snapshot.get("row_count") or len(snapshot.get("records") or []),
        "query_hash": snapshot.get("query_hash"),
        "geography": snapshot.get("geography"),
        "live_select_executed": snapshot.get("live_select_executed"),
        "official_live": False,
    }
    records = list(snapshot.get("records") or [])
    cases = [record_to_case(record) for record in records]
    if cases:
        rank_via_414(cases, as_of=stamp)
    snap = str(snapshot.get("content_hash") or content_hash(snapshot))
    dossiers = process_cases(cases, as_of=stamp, snapshot_hash=snap) if cases else []
    elapsed = time.perf_counter() - started
    live_meta["elapsed_s"] = round(elapsed, 3)
    live_meta["cost"] = {"requests": 0, "bytes": 0, "note": "select_only_no_document_download"}
    replay = "python3 -m scripts.historical_contract_authority --mode live --limit 40"
    written = write_handoff(
        dossiers,
        output_dir=output,
        as_of=stamp,
        snapshot_hash=snap,
        replay_command=replay,
        catalog_mode="official_projection",
        live_meta=live_meta,
    )
    return {
        "dossiers": dossiers,
        "handoff": written,
        "snapshot": snapshot,
        "snapshot_hash": snap,
        "as_of": stamp,
        "live": live_meta,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="historical-contract-authority")
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--output", type=Path, default=HANDOFF_DIR)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--as-of", dest="as_of", default=None)
    parser.add_argument("--case", choices=sorted(CASE_BUILDERS), default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "fixture" and args.case:
        stamp = args.as_of or "2026-08-17T12:00:00Z"
        case = CASE_BUILDERS[args.case]()
        dossier = dossier_dict(build_dossier(case, as_of=stamp))
        sys.stdout.write(canonical_dumps(dossier) + "\n")
        return 0
    if args.mode == "live":
        result = run_live(output=args.output, dsn=args.dsn, limit=args.limit, as_of=args.as_of)
    else:
        result = run_fixture(output=args.output, as_of=args.as_of)
    summary = {
        "as_of": result["as_of"],
        "snapshot_hash": result["snapshot_hash"],
        "producer_sha": producer_sha(),
        "states": {
            "HANDOFF_READY": sum(1 for item in result["dossiers"] if item.get("state") == "HANDOFF_READY"),
            "HOLD_FOR_DATA": sum(1 for item in result["dossiers"] if item.get("state") == "HOLD_FOR_DATA"),
            "REJECT": sum(1 for item in result["dossiers"] if item.get("state") == "REJECT"),
        },
        "output": str(args.output),
        "live": result.get("live"),
    }
    sys.stdout.write(canonical_dumps(summary) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
