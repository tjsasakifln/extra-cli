"""STUB: PNCP retry/types module.

Minimal definitions to enable imports from clients.pncp.retry.
Full implementation lives in scripts/crawl/retry.py and scripts/crawl/pncp_crawler.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class DateFormat:
    """Date format constants."""

    YYYYMMDD = "YYYYMMDD"
    YYYY_MM_DD = "YYYY-MM-DD"
    DDMMYYYY = "DDMMYYYY"
    DD_MM_YYYY = "DD-MM-YYYY"


@dataclass
class ModalityFetchState:
    """Mutable state for partial accumulation during modality fetch."""

    items: list[dict[str, Any]] = field(default_factory=list)
    seen_ids: set[str] = field(default_factory=set)
    pages_fetched: int = 0
    was_truncated: bool = False
    timed_out: bool = False


@dataclass
class ParallelFetchResult:
    """Result of parallel UF fetch."""

    items: list[dict[str, Any]] = field(default_factory=list)
    succeeded_ufs: list[str] = field(default_factory=list)
    failed_ufs: list[str] = field(default_factory=list)
    truncated_ufs: list[str] = field(default_factory=list)


# UFs ordered by population (largest first)
UFS_BY_POPULATION: list[str] = [
    "SP",
    "MG",
    "RJ",
    "BA",
    "RS",
    "PR",
    "PE",
    "CE",
    "PA",
    "MA",
    "SC",
    "GO",
    "DF",
    "ES",
    "AL",
    "PB",
    "RN",
    "MT",
    "PI",
    "RO",
    "SE",
    "TO",
    "AM",
    "AC",
    "AP",
    "RR",
    "MS",
]


def _get_format_rotation() -> list[str]:
    return [DateFormat.YYYYMMDD, DateFormat.YYYY_MM_DD, DateFormat.DDMMYYYY, DateFormat.DD_MM_YYYY]


def _handle_422_response(
    response_text: str,
    params: dict[str, Any],
    data_inicial: str,
    data_final: str,
    attempt: int = 0,
    max_retries: int = 1,
) -> str | dict[str, Any]:
    return "retry_format"


def _set_cached_date_format(fmt: str) -> None:
    pass


def _validate_date_params(
    data_inicial: str,
    data_inicial_fmt: str,
    data_final: str,
    data_final_fmt: str,
) -> None:
    pass


def calculate_delay(attempt: int, config: Any) -> float:
    return min(config.base_delay * (config.exponential_base**attempt), config.max_delay)


def format_date(date_str: str, fmt: str) -> str:
    return date_str.replace("-", "")


__all__ = [
    "DateFormat",
    "ModalityFetchState",
    "ParallelFetchResult",
    "UFS_BY_POPULATION",
    "_get_format_rotation",
    "_handle_422_response",
    "_set_cached_date_format",
    "_validate_date_params",
    "calculate_delay",
    "format_date",
]
