#!/usr/bin/env python3
"""
Stub para coleta SICAF — retorna NOT_IMPLEMENTED.

A implementacao completa do coletor SICAF requer Playwright + captcha manual
e esta em desenvolvimento separado. Este stub permite que o pipeline intel
continue sem SICAF sem abortar.

Para implementacao completa:
  1. Instale playwright: pip install playwright && playwright install chromium
  2. Substitua este stub pelo script completo de automacao SICAF

Status retornado: SICAF_NAO_DISPONIVEL
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime


def collect_sicaf_stub(cnpj14: str) -> dict:
    """Return stub result indicating SICAF collection is not available.

    This stub is used when the real collect-sicaf.py is not yet implemented.
    The pipeline receives SICAF_NAO_DISPONIVEL and continues gracefully.

    Args:
        cnpj14: Clean 14-digit CNPJ string.

    Returns:
        Dict with status = "SICAF_NAO_DISPONIVEL" and instructions.
    """
    now = datetime.now(UTC).strftime("%d/%m/%Y %H:%M")
    return {
        "status": "SICAF_NAO_DISPONIVEL",
        "crc_status": "N/D",
        "restricao": {"possui_restricao": None},
        "attempted_at": now,
        "error_type": "NOT_IMPLEMENTED",
        "error_detail": (
            "O script collect-sicaf.py completo ainda nao foi implementado. "
            "Instale o modulo SICAF completo para verificar CRC e restricoes. "
            "Contate o suporte para obter o script completo."
        ),
        "instrucao": (
            "Para habilitar SICAF: (1) Instale playwright: pip install playwright && "
            "playwright install chromium. "
            "(2) Substitua este stub pelo script completo em scripts/collect-sicaf.py. "
            "(3) Execute o pipeline com --skip-sicaf ate la."
        ),
        "_source": {
            "status": "UNAVAILABLE",
            "detail": "collect-sicaf.py stub — SICAF nao disponivel",
        },
    }


def main() -> int:
    """Entry point for the SICAF stub."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Stub SICAF — retorna NOT_IMPLEMENTED (placeholder)",
    )
    parser.add_argument("--cnpj", required=True, help="CNPJ (14 digitos, sem formatacao)")
    parser.add_argument("--output", required=True, help="Caminho do JSON de saida")
    parser.add_argument("--skip-linhas", action="store_true", help="Ignorado (stub)")
    args = parser.parse_args()

    result = collect_sicaf_stub(args.cnpj)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  [SICAF STUB] SICAF_NAO_DISPONIVEL — salvo em {args.output}")
    print("  [SICAF STUB] Substitua por implementacao real para coleta completa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
