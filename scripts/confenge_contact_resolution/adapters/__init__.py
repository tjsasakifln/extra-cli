"""Source adapters for public business contact observations."""

from scripts.confenge_contact_resolution.adapters.base import AdapterContext, ContactAdapter
from scripts.confenge_contact_resolution.adapters.contact_pages import ContactPageAdapter
from scripts.confenge_contact_resolution.adapters.public_docs import PublicDocsAdapter
from scripts.confenge_contact_resolution.adapters.registry import RegistryAdapter
from scripts.confenge_contact_resolution.adapters.site import SiteAdapter
from scripts.confenge_contact_resolution.adapters.web_search import (
    NoOpWebSearchProvider,
    WebSearchAdapter,
    WebSearchProvider,
)

__all__ = [
    "AdapterContext",
    "ContactAdapter",
    "RegistryAdapter",
    "SiteAdapter",
    "PublicDocsAdapter",
    "ContactPageAdapter",
    "WebSearchAdapter",
    "WebSearchProvider",
    "NoOpWebSearchProvider",
]
