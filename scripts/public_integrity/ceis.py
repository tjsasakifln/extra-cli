"""CEIS adapter. Separate from CNEP; shares only retry/pagination/normalize."""

from __future__ import annotations

from collections.abc import Callable

from scripts.public_integrity.cadastro import run_cadastro
from scripts.public_integrity.models import MAX_PAGES, MAX_RETRIES, SourceRun
from scripts.public_integrity.transport import Transport

CEIS_TYPE_PATH = ("tipo", "descricaoResumida")


def run_ceis(
    queried_cnpj: str,
    transport: Transport,
    *,
    captured_at: str,
    max_retries: int = MAX_RETRIES,
    max_pages: int = MAX_PAGES,
    sleeper: Callable[[float], None] | None = None,
) -> SourceRun:
    return run_cadastro(
        "CEIS",
        queried_cnpj,
        transport,
        captured_at=captured_at,
        type_path=CEIS_TYPE_PATH,
        max_retries=max_retries,
        max_pages=max_pages,
        sleeper=sleeper,
    )
