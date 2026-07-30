"""Portal-family adapters for process document collection."""

from __future__ import annotations

from scripts.process_documents.adapters.base import DocumentAdapter, get_adapter
from scripts.process_documents.adapters.pncp import PncpDocumentAdapter

__all__ = ["DocumentAdapter", "get_adapter", "PncpDocumentAdapter"]
