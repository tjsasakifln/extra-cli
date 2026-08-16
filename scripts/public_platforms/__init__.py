"""Public per-entity platform adapters (BBMNET, Licitanet, Compras BR)."""

from scripts.public_platforms.contract import (
    PLATFORMS,
    PageResult,
    RunResult,
    classify_http_block,
    pagination_terminal,
    sha256_bytes,
    sha256_json,
)

__all__ = [
    "PLATFORMS",
    "PageResult",
    "RunResult",
    "classify_http_block",
    "pagination_terminal",
    "sha256_bytes",
    "sha256_json",
]
