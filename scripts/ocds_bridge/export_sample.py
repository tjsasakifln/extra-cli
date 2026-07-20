#!/usr/bin/env python3
"""Export a small OCDS-inspired release package from synthetic (or provided) rows.

Spike tool — does not replace operational tables.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.ocds_bridge.mapping import bid_to_ocds_release, contract_to_ocds_release
from scripts.ocds_bridge.validate import validate_release_package


def _demo_bids() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "numero_controle_pncp": "12345678000199-1-000001/2026",
            "objeto_compra": "Pavimentação asfáltica em vias urbanas",
            "valor_total_estimado": 1_500_000.50,
            "moeda": "BRL",
            "data_publicacao_pncp": "2026-07-01T12:00:00Z",
            "situacao_nome": "Divulgada no PNCP",
            "modalidade_nome": "Pregão Eletrônico",
            "orgao_cnpj": "12345678000199",
            "orgao_nome": "Prefeitura Municipal Exemplo",
            "content_hash": "a" * 64,
            "raw_uri": "https://pncp.gov.br/api/pncp/v1/orgaos/12345678000199/compras/2026/1",
        },
        {
            "id": 2,
            "numero_controle_pncp": "11222333000144-1-000010/2026",
            "objeto_compra": "Reforma de escola municipal",
            "valor_total_estimado": 890_000,
            "data_publicacao_pncp": "2026-07-05T09:00:00Z",
            "situacao_nome": "Recebendo proposta",
            "modalidade_nome": "Concorrência",
            "orgao_cnpj": "11.222.333/0001-44",
            "orgao_nome": "Município Beta",
            "content_hash": "b" * 64,
        },
    ]


def _demo_contracts() -> list[dict[str, Any]]:
    return [
        {
            "contrato_id": "C-9001",
            "objeto_contrato": "Pavimentação asfáltica — lote 1",
            "valor_global": 1_420_000,
            "situacao": "Ativo",
            "data_assinatura": "2026-06-01",
            "data_vigencia_inicio": "2026-06-15",
            "data_vigencia_fim": "2027-06-14",
            "orgao_cnpj": "12345678000199",
            "orgao_nome": "Prefeitura Municipal Exemplo",
            "fornecedor_cnpj": "99888777000166",
            "fornecedor_nome": "Construtora Delta LTDA",
            "numero_controle_pncp_compra": "12345678000199-1-000001/2026",
            "content_hash": "c" * 64,
        }
    ]


def build_package(
    *,
    bids: list[dict[str, Any]] | None = None,
    contracts: list[dict[str, Any]] | None = None,
    uri: str = "file://spike/ocds-sample",
) -> dict[str, Any]:
    releases = [bid_to_ocds_release(b) for b in (bids or _demo_bids())]
    releases.extend(contract_to_ocds_release(c) for c in (contracts or _demo_contracts()))
    return {
        "uri": uri,
        "version": "1.1",
        "publishedDate": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publisher": {"name": "Extra Consultoria — OCDS spike (not official publisher)"},
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "publicationPolicy": "Synthetic/sanitized sample for interoperability spike only",
        "releases": releases,
        "extensions": [
            "https://raw.githubusercontent.com/open-contracting-extensions/ocds_bid_extension/master/extension.json"
        ],
        "extra:spike": {
            "campaign": "ARCH-RESET-2026-07-20",
            "decision_hint": "ADOPT_AS_REFERENCE",
            "not_physical_model": True,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/OCDS/sample-release-package.json"),
    )
    p.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Optional path to OCDS release-schema.json for strict validation",
    )
    args = p.parse_args()
    package = build_package()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = validate_release_package(package, schema_path=args.schema)
    report_path = args.out.with_suffix(".validation.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(args.out), "validation": report}, ensure_ascii=False, indent=2))
    # Spike always exits 0 if structural ok; strict schema failures are reported
    return 0 if report.get("structural_ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
