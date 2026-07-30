"""Common adapter protocol for process document collectors."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import DocumentRunStatus


@runtime_checkable
class DocumentAdapter(Protocol):
    portal_family: str
    source_id: str

    def collect(
        self,
        entity: EntityDocumentDiscovery,
        *,
        since: str | None = None,
        until: str | None = None,
        max_processes: int = 20,
        download: bool = True,
    ) -> object:
        """Run live collection and return DocumentRunResult."""
        ...


def classify_http_status(code: int | None) -> DocumentRunStatus:
    if code is None:
        return DocumentRunStatus.CONNECTION_FAILED
    if code == 429:
        return DocumentRunStatus.HTTP_RATE_LIMIT
    if code in (401, 403):
        return DocumentRunStatus.AUTH_REQUIRED
    if 400 <= code < 500:
        return DocumentRunStatus.HTTP_CLIENT_ERROR
    if code >= 500:
        return DocumentRunStatus.HTTP_SERVER_ERROR
    return DocumentRunStatus.CONNECTION_FAILED


def get_adapter(portal_family: str) -> DocumentAdapter:
    from scripts.process_documents.adapters.ciga_ckan import CigaCkanDocumentAdapter
    from scripts.process_documents.adapters.generic_html import GenericHtmlDocumentAdapter
    from scripts.process_documents.adapters.pncp import PncpDocumentAdapter

    family = (portal_family or "pncp").lower()
    if family == "pncp":
        return PncpDocumentAdapter()
    if family in {"ciga_ckan", "ciga_dom", "dom_sc"}:
        return CigaCkanDocumentAdapter()
    if family in {
        "doe_sc",
        "sc_compras",
        "compras_gov",
        "pcp",
        "transparencia",
        "tce_sc",
        "portal_institucional",
        "generic_public_html",
    }:
        return GenericHtmlDocumentAdapter(portal_family=family)
    return PncpDocumentAdapter()
