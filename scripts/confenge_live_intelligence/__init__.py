"""CONFENGE_LIVE_INTELLIGENCE/1.0 — motor INBOUND, estritamente aditivo.

Este pacote observa oportunidades publicas abertas e as relaciona ao portfolio
publico observado de empresas. Ele NAO participa de nenhum caminho do pipeline
outbound: nao e importado por ``scripts/confenge_target_fit/``,
``scripts/confenge_outreach_pipeline/``, ``scripts/warmbly_bridge/`` nem
``scripts/confenge_contact_resolution/``.

Invariante de isolamento (AC11): nenhum modulo deste pacote executa
INSERT/UPDATE/DELETE sobre tabela outbound. Toda leitura de objeto outbound e
SELECT. As unicas tabelas escritas sao ``confenge_live_intelligence_*``,
criadas por ``db/migrations/104_confenge_live_intelligence_v1.sql``.

Story: docs/stories/story-confenge-live-intelligence-01.md
Normativo: docs/architecture/confenge-live-intelligence-impact-analysis.md
"""

from __future__ import annotations

from scripts.confenge_live_intelligence.schema import (
    ALLOWED_WRITE_TARGETS,
    ENGINE_ID,
    ENGINE_VERSION,
    SCHEMA_VERSION,
    WRITE_TARGET_ORDER,
    OutboundWriteAttemptError,
    assert_write_target,
    live_hash,
)

__all__ = [
    "ALLOWED_WRITE_TARGETS",
    "ENGINE_ID",
    "ENGINE_VERSION",
    "SCHEMA_VERSION",
    "WRITE_TARGET_ORDER",
    "OutboundWriteAttemptError",
    "assert_write_target",
    "live_hash",
]
