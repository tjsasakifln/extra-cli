"""Base types for multi-source consolidation.

STUB: Minimal definitions to enable imports without ImportError.
Full implementation deferred to future epic.
"""

from scripts.crawl.clients.base.base import (
    SourceCapability,
    SourceMetadata,
    SourceStatus,
    UnifiedProcurement,
)

__all__ = [
    "SourceCapability",
    "SourceMetadata",
    "SourceStatus",
    "UnifiedProcurement",
]
