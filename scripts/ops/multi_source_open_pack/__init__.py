"""Motor canônico multi-fonte EXTRA-MS-OPEN — inteligência decisória B2G.

Substitui o gerador ad hoc `build_multi_source_opportunities_pack.py` e produz
exatamente os 6 entregáveis cliente, com modelo semântico reconciliado.
"""

from __future__ import annotations

from scripts.ops.multi_source_open_pack.pipeline import (
    CLIENT_ARTIFACTS,
    build_pack,
    run_pack_cli,
)

__all__ = ["CLIENT_ARTIFACTS", "build_pack", "run_pack_cli"]

VERSION = "extra-ms-open-pack/2.0.0"
TAXONOMY_VERSION = "aec-hierarchy/1.0.0"
SCORING_VERSION = "extra-decision/1.0.0"
