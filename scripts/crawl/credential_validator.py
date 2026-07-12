"""Credential validation for data sources.

Each source declares its required environment variables.  Before a crawl
starts, :func:`validate_source_credentials` checks that every required
variable is set and non-empty.

Usage::

    from scripts.crawl.credential_validator import validate_source_credentials

    ok, missing = validate_source_credentials("dom_sc")
    if not ok:
        print(f"Missing: {missing}")  # → ["DOM_SC_CPF", "DOM_SC_API_KEY"]
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CredentialRequirement:
    """A single credential that a source needs to operate."""

    env_var: str
    """Environment variable name (e.g. ``"DOM_SC_CPF"``)."""

    description: str
    """Human-readable description for error messages."""

    optional: bool = False
    """If True, absence is a warning, not a hard failure."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


SOURCE_CREDENTIALS: dict[str, list[CredentialRequirement]] = {
    "dom_sc": [
        CredentialRequirement("DOM_SC_CPF", "CPF para autenticacao Basic Auth no DOM-SC"),
        CredentialRequirement("DOM_SC_CNPJ", "CNPJ para autenticacao Basic Auth no DOM-SC"),
        CredentialRequirement("DOM_SC_API_KEY", "X-API-Key para DOM-SC"),
    ],
    "doe_sc": [
        CredentialRequirement("DOE_SC_LOGIN", "Login/CPF para autenticacao no DOE-SC"),
        CredentialRequirement("DOE_SC_PASSWORD", "Senha para autenticacao no DOE-SC"),
    ],
    "mides_bigquery": [
        CredentialRequirement(
            "GOOGLE_APPLICATION_CREDENTIALS",
            "Caminho para o JSON de service account do BigQuery",
        ),
    ],
    # -----------------------------------------------------------------------
    # Sources below are public — no credentials required.
    # They are listed explicitly so callers can distinguish "no creds needed"
    # from "unknown source".
    # -----------------------------------------------------------------------
    "pncp": [],
    "pcp": [],
    "compras_gov": [],
    "sc_compras": [],
    "contracts": [],
    "transparencia": [],
    "tce_sc": [],
    "ciga_ckan": [],
    "selenium": [],
}

# Sources that are exclusively public (for fast-path skipping)
_PUBLIC_SOURCES: set[str] = {
    k for k, v in SOURCE_CREDENTIALS.items() if not v
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_source_credentials(
    source: str,
    *,
    strict: bool = True,
) -> tuple[bool, list[str]]:
    """Check that all required env vars for *source* are set and non-empty.

    Args:
        source: Normalised source key (e.g. ``"dom_sc"``).
        strict: If False, missing optional credentials are logged but do not
                cause a failure.

    Returns:
        ``(ok, missing)`` where *ok* is ``True`` when every **required**
        credential is available, and *missing* is a list of human-readable
        descriptions of what is absent.
    """
    requirements = SOURCE_CREDENTIALS.get(source)

    if requirements is None:
        # Unknown source — assume no credentials needed (fail open).
        _logger.debug("Unknown source %r — skipping credential check", source)
        return True, []

    missing: list[str] = []

    for req in requirements:
        value = os.getenv(req.env_var, "").strip()
        if value:
            continue

        if req.optional:
            if strict:
                _logger.warning(
                    "Source %r: optional credential %s is not set",
                    source,
                    req.env_var,
                )
        else:
            msg = f"{req.env_var} ({req.description})"
            missing.append(msg)
            _logger.error(
                "Source %r: required credential %s is missing or empty",
                source,
                req.env_var,
            )

    return len(missing) == 0, missing


def is_public_source(source: str) -> bool:
    """Return True if *source* requires no credentials at all."""
    return source in _PUBLIC_SOURCES


def get_credential_report() -> dict[str, dict[str, bool]]:
    """Return a dict of ``{source: {env_var: is_set}}`` for all known sources."""
    report: dict[str, dict[str, bool]] = {}
    for src, reqs in SOURCE_CREDENTIALS.items():
        report[src] = {}
        for req in reqs:
            report[src][req.env_var] = bool(os.getenv(req.env_var, "").strip())
        if not reqs:
            report[src]["_public"] = True
    return report


__all__ = [
    "CredentialRequirement",
    "SOURCE_CREDENTIALS",
    "get_credential_report",
    "is_public_source",
    "validate_source_credentials",
]
