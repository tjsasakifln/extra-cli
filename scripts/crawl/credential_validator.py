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


# Credential requirements are sourced from the central registry.
# Each SourceInfo.credentials is a list of env var names.
# Descriptions are maintained here for human-readable error messages.

_CREDENTIAL_DESCRIPTIONS: dict[str, str] = {
    "DOM_SC_CPF": "CPF para autenticacao Basic Auth no DOM-SC",
    "DOM_SC_CNPJ": "CNPJ para autenticacao Basic Auth no DOM-SC",
    "DOM_SC_API_KEY": "X-API-Key para DOM-SC",
    "DOE_SC_LOGIN": "Login/CPF para autenticacao no DOE-SC",
    "DOE_SC_PASSWORD": "Senha para autenticacao no DOE-SC",
    "GOOGLE_APPLICATION_CREDENTIALS": "Caminho para o JSON de service account do BigQuery",
}


def _build_source_credentials() -> dict[str, list[CredentialRequirement]]:
    """Build SOURCE_CREDENTIALS from the central registry."""
    from scripts.crawl.registry import iter_sources  # local import to avoid circular

    result: dict[str, list[CredentialRequirement]] = {}
    for info in iter_sources(active_only=True):
        reqs: list[CredentialRequirement] = []
        for env_var in info.credentials:
            desc = _CREDENTIAL_DESCRIPTIONS.get(env_var, env_var)
            reqs.append(CredentialRequirement(env_var, desc))
        result[info.name] = reqs
    return result


# Lazily built from registry
_SOURCE_CREDENTIALS_CACHE: dict[str, list[CredentialRequirement]] | None = None


def _get_source_credentials() -> dict[str, list[CredentialRequirement]]:
    global _SOURCE_CREDENTIALS_CACHE
    if _SOURCE_CREDENTIALS_CACHE is None:
        _SOURCE_CREDENTIALS_CACHE = _build_source_credentials()
    return _SOURCE_CREDENTIALS_CACHE


# Backward-compatible alias
SOURCE_CREDENTIALS = _get_source_credentials()

# Sources that are exclusively public (for fast-path skipping)
_PUBLIC_SOURCES: set[str] = set()


def _get_public_sources() -> set[str]:
    global _PUBLIC_SOURCES
    if not _PUBLIC_SOURCES:
        from scripts.crawl.registry import get_public_sources

        _PUBLIC_SOURCES = get_public_sources()
    return _PUBLIC_SOURCES


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
    # Refresh from registry each call (lazy cache rebuilds once)
    creds = _get_source_credentials()
    requirements = creds.get(source)

    if requirements is None:
        # Unknown source — check registry for existence
        from scripts.crawl.registry import lookup

        info = lookup(source)
        if info is None:
            _logger.debug("Unknown source %r — skipping credential check", source)
            return True, []
        # Known source with no credential requirements → public
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
    return source in _get_public_sources()


def get_credential_report() -> dict[str, dict[str, bool]]:
    """Return a dict of ``{source: {env_var: is_set}}`` for all known sources."""
    report: dict[str, dict[str, bool]] = {}
    creds = _get_source_credentials()
    for src, reqs in creds.items():
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
