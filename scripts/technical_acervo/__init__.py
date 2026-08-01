"""Technical acervo knowledge base for EXTRA EMPREITEIRA LTDA.

Canonical store: data/extra_technical_acervo.json
CLI: python -m scripts.technical_acervo
"""

from __future__ import annotations

from scripts.technical_acervo.store import AcervoStore, load_store

__all__ = ["AcervoStore", "load_store"]
