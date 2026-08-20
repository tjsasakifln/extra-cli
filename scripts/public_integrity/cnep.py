"""CNEP adapter. Separate from CEIS; shares only retry/pagination/normalize."""

from __future__ import annotations

from collections.abc import Callable

from scripts.public_integrity.cadastro import run_cadastro
from scripts.public_integrity.models import MAX_PAGES, MAX_RETRIES, SourceRun
from scripts.public_integrity.transport import Transport

CNEP_TYPE_PATH = ("tipoSancao", "descricaoResumida")


def run_cnep(
    queried_cnpj: str,
    transport: Transport,
    *,
    captured_at: str,
    max_retries: int = MAX_RETRIES,
    max_pages: int = MAX_PAGES,
    sleeper: Callable[[float], None] | None = None,
) -> SourceRun:
    return run_cadastro(
        "CNEP",
        queried_cnpj,
        transport,
        captured_at=captured_at,
        type_path=CNEP_TYPE_PATH,
        max_retries=max_retries,
        max_pages=max_pages,
        sleeper=sleeper,
    )
