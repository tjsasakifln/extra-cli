"""Tier 0/1: optional live datalake. Isolated failure → BLOCKED attempt, not R0."""

from __future__ import annotations

import os
from typing import Any

from scripts.decision_unit_intelligence.models import SearchAttempt, normalize_cnpj, now_iso, stable_id
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult

_QUERY = """
SELECT fornecedor_cnpj, max(fornecedor_nome) AS nome,
       count(*) AS n_contratos,
       max(objeto_contrato) AS objeto,
       max(orgao_nome) AS orgao
FROM pncp_supplier_contracts
WHERE regexp_replace(fornecedor_cnpj, '[^0-9]', '', 'g') = %s
GROUP BY fornecedor_cnpj
LIMIT 1
"""


class ExistingDatalakeProvider:
    provider_id = "existing_datalake"
    tier = 0

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        if not self.dsn:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj, "nodsn"),
                        company_entity_id=cnpj,
                        tier=0,
                        provider_id=self.provider_id,
                        source="postgres",
                        status="skipped",
                        reason="dsn_unavailable",
                    )
                ],
                terminal="skipped",
            )
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj, "nopsycopg"),
                        company_entity_id=cnpj,
                        tier=0,
                        provider_id=self.provider_id,
                        source="postgres",
                        status="skipped",
                        reason="psycopg2_missing",
                    )
                ],
                terminal="skipped",
            )
        try:
            conn = psycopg2.connect(self.dsn, connect_timeout=4)
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(_QUERY, (cnpj,))
                    row: dict[str, Any] | None = cur.fetchone()
            finally:
                conn.close()
        except Exception as exc:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj, "err"),
                        company_entity_id=cnpj,
                        tier=0,
                        provider_id=self.provider_id,
                        source="postgres",
                        status="blocked",
                        reason=str(exc)[:200],
                        blocked=True,
                        stop_reason="SOURCE_BLOCKED",
                    )
                ],
                terminal="blocked",
            )
        if not row:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj, "miss"),
                        company_entity_id=cnpj,
                        tier=0,
                        provider_id=self.provider_id,
                        source="pncp_supplier_contracts",
                        status="miss",
                    )
                ],
                terminal="miss",
            )
        why = f"Lake: {row.get('n_contratos')} contrato(s). Órgão: {row.get('orgao')}. Objeto: {str(row.get('objeto') or '')[:180]}"
        return ProviderResult(
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("att", self.provider_id, cnpj, "hit"),
                    company_entity_id=cnpj,
                    tier=0,
                    provider_id=self.provider_id,
                    source="pncp_supplier_contracts",
                    status="hit",
                    extra={"checked_at": now_iso()},
                )
            ],
            terminal="ok",
            why_now=why,
            legal_name=row.get("nome"),
            extra={"lake_row": dict(row)},
        )
