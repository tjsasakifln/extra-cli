#!/usr/bin/env python3
"""Entity resolver: resolve publishing CNPJ for subordinate entities.

Story: CM-13 — Deduplicação Multicanal e Aliases de Compradores

Core function: resolve_publishing_cnpj(cnpj_8) → canonical publishing CNPJ.

Design principles:
  - Deterministic lookup via entity_aliases table
  - Idempotent: prefeitura → self (no alias)
  - Fail-safe: fallback to self on any error
  - Cache with TTL for performance

Usage:
  from scripts.lib.entity_resolver import resolve_publishing_cnpj, EntityResolver

  # Simple usage
  pub_cnpj = resolve_publishing_cnpj("62761279")  # → "82892324"

  # With explicit connection (for batch operations)
  resolver = EntityResolver(conn)
  pub_cnpj = resolver.resolve("62761279")
"""

from __future__ import annotations

import logging
import os
import threading
import time

from psycopg2.extras import RealDictCursor

_logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes — aliases mudam raramente)
_CACHE_TTL = 300


def _get_connection():
    """Create a new database connection from env."""
    import psycopg2

    dsn = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        dsn = "postgresql://test:test@127.0.0.1:5433/pncp_datalake"
    return psycopg2.connect(dsn)


class EntityResolver:
    """Resolve subordinate CNPJs to their publishing parent CNPJ.

    Uses entity_aliases table for deterministic mapping.
    Unknown CNPJs return themselves (idempotent).

    Thread-safe with cache invalidation.
    """

    def __init__(self, conn=None):
        self._conn = conn
        self._own_conn = conn is None
        self._cache: dict[str, str] = {}
        self._cache_ts: float = 0.0
        self._lock = threading.Lock()

    @property
    def conn(self):
        if self._conn is None:
            self._conn = _get_connection()
            self._own_conn = True
        return self._conn

    def _cache_valid(self) -> bool:
        return (time.monotonic() - self._cache_ts) < _CACHE_TTL

    def _load_cache(self) -> None:
        """Carrega todos os aliases ativos no cache local."""
        with self._lock:
            if self._cache_valid():
                return

            try:
                cur = self.conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    "SELECT cnpj_8_sub, cnpj_8_pub FROM entity_aliases WHERE is_active = TRUE"
                )
                self._cache = {row["cnpj_8_sub"]: row["cnpj_8_pub"] for row in cur.fetchall()}
                self._cache_ts = time.monotonic()
                _logger.debug("Cache loaded: %d aliases", len(self._cache))
            except Exception:
                _logger.exception("Failed to load entity alias cache")
                if not self._cache:
                    self._cache = {}

    def resolve(self, cnpj_8: str) -> str:
        """Resolve um CNPJ subordinate para o CNPJ publicante.

        Args:
            cnpj_8: CNPJ raiz (8 dígitos) a resolver.

        Returns:
            CNPJ publicante (8 dígitos). Se o CNPJ não tem alias,
            retorna o próprio CNPJ (idempotente).

        Raises:
            ValueError: se cnpj_8 não parece um CNPJ raiz.
        """
        cnpj_8 = _normalize_cnpj(cnpj_8)

        try:
            self._load_cache()
            return self._cache.get(cnpj_8, cnpj_8)
        except Exception:
            _logger.warning(
                "EntityResolver cache miss, falling back to SQL for %s", cnpj_8
            )
            return self._resolve_sql(cnpj_8)

    def _resolve_sql(self, cnpj_8: str) -> str:
        """Fallback: consulta SQL direta."""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT resolve_publishing_cnpj_sql(%s)", (cnpj_8,))
            row = cur.fetchone()
            return row[0] if row else cnpj_8
        except Exception:
            _logger.exception("SQL fallback failed for %s, returning self", cnpj_8)
            return cnpj_8

    def resolve_batch(self, cnpj_list: list[str]) -> dict[str, str]:
        """Resolve múltiplos CNPJs em lote.

        Returns:
            Dict mapping input CNPJ → resolved CNPJ.
        """
        normalized = [_normalize_cnpj(c) for c in cnpj_list]
        try:
            self._load_cache()
            return {cnpj: self._cache.get(cnpj, cnpj) for cnpj in normalized}
        except Exception:
            _logger.exception("Batch resolve failed, returning self for all")
            return {cnpj: cnpj for cnpj in normalized}

    def close(self) -> None:
        if self._own_conn and self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                _logger.debug("Error closing entity resolver connection", exc_info=True)
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _normalize_cnpj(cnpj_8: str) -> str:
    """Normaliza CNPJ: remove não-dígitos, valida comprimento."""
    cnpj = "".join(c for c in cnpj_8 if c.isdigit())
    if len(cnpj) < 8:
        raise ValueError(f"CNPJ raiz deve ter ao menos 8 dígitos, recebeu: {cnpj_8!r}")
    return cnpj[:8]


# Singleton global para conveniência
_resolver: EntityResolver | None = None
_resolver_lock = threading.Lock()


def resolve_publishing_cnpj(cnpj_8: str) -> str:
    """Função de conveniência: resolve CNPJ subordinate → publicante.

    Idempotente: se não houver alias, retorna o próprio CNPJ.

    Exemplo:
        >>> resolve_publishing_cnpj("62761279")
        '82892324'  # Secretaria → Prefeitura de Santo Amaro da Imperatriz

    Args:
        cnpj_8: CNPJ raiz (8 dígitos).

    Returns:
        CNPJ publicante (8 dígitos).
    """
    global _resolver
    if _resolver is None:
        with _resolver_lock:
            if _resolver is None:
                _resolver = EntityResolver()
    return _resolver.resolve(cnpj_8)


# ── Test helpers ──────────────────────────────────────────────────────────


def _reset_global_resolver() -> None:
    """Reset singleton for testing."""
    global _resolver
    with _resolver_lock:
        if _resolver is not None:
            _resolver.close()
            _resolver = None
