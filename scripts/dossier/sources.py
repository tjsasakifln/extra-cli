"""SELECT-only DataLake reads for the dossier engine.

Every method returns a :class:`SourceRead` carrying the view it came from, the
observation timestamp and any reason codes. Nothing here writes, and nothing
here interprets: interpretation lives in ``compose.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from scripts.dossier.constants import (
    BUYER_LIMIT,
    COMPETITOR_LIMIT,
    EXPIRING_WINDOW_DAYS,
    OPPORTUNITY_LIMIT,
    REASON_TABLE_MISSING,
)
from scripts.dossier.models import SourceRead

# Same ladder as v_contract_intel_percentis. Duplicated deliberately so the
# focal contract is classified by the exact rule that built the panel; if the
# view changes, `test_category_ladder_matches_view` fails.
CATEGORY_SQL = """
CASE
  WHEN {col} ILIKE '%%obra%%' OR {col} ILIKE '%%construção%%' OR {col} ILIKE '%%pavimentação%%'
       OR {col} ILIKE '%%edificação%%' OR {col} ILIKE '%%engenharia%%' THEN 'OBRAS'
  WHEN {col} ILIKE '%%limpeza%%' OR {col} ILIKE '%%conservação%%' OR {col} ILIKE '%%manutenção%%'
       OR {col} ILIKE '%%zeladoria%%' THEN 'FACILITIES'
  WHEN {col} ILIKE '%%software%%' OR {col} ILIKE '%%ti%%' OR {col} ILIKE '%%tecnologia%%'
       OR {col} ILIKE '%%sistema%%' OR {col} ILIKE '%%informática%%' THEN 'TI'
  WHEN {col} ILIKE '%%saúde%%' OR {col} ILIKE '%%medicamento%%' OR {col} ILIKE '%%hospitalar%%'
       OR {col} ILIKE '%%medico%%' OR {col} ILIKE '%%farmacêutico%%'
       OR {col} ILIKE '%%laboratório%%' THEN 'SAÚDE'
  WHEN {col} ILIKE '%%alimentação%%' OR {col} ILIKE '%%alimento%%' OR {col} ILIKE '%%merenda%%'
       OR {col} ILIKE '%%gênero alimentício%%' THEN 'ALIMENTAÇÃO'
  WHEN {col} ILIKE '%%transporte%%' OR {col} ILIKE '%%veículo%%' OR {col} ILIKE '%%frota%%'
       OR {col} ILIKE '%%ônibus%%' OR {col} ILIKE '%%locação de veículo%%' THEN 'TRANSPORTE'
  WHEN {col} ILIKE '%%segurança%%' OR {col} ILIKE '%%vigilância%%' OR {col} ILIKE '%%monitoramento%%'
       OR {col} ILIKE '%%porteiro%%' THEN 'SEGURANÇA'
  WHEN {col} ILIKE '%%consultoria%%' OR {col} ILIKE '%%assessoria%%' OR {col} ILIKE '%%advocacia%%'
       OR {col} ILIKE '%%jurídico%%' OR {col} ILIKE '%%contábil%%' THEN 'CONSULTORIA'
  WHEN {col} ILIKE '%%combustível%%' OR {col} ILIKE '%%gasolina%%' OR {col} ILIKE '%%diesel%%'
       OR {col} ILIKE '%%etanol%%' THEN 'COMBUSTÍVEL'
  ELSE 'OUTROS'
END
"""

VIEW_CONTRACTS = "v_contracts_canonical_v2"
VIEW_EXPIRING = "v_expiring_contracts"
VIEW_PERCENTIS = "v_contract_intel_percentis"
VIEW_OPPORTUNITIES = "v_open_opportunities_canonical"
TABLE_REGISTRY = "supplier_registry"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _rows(cursor: Any) -> tuple[dict[str, Any], ...]:
    columns = [c.name for c in cursor.description]
    return tuple({col: _jsonable(val) for col, val in zip(columns, row)} for row in cursor.fetchall())


class Source(Protocol):
    """What ``compose.py`` needs. Implemented by DataLake and fixture backends."""

    catalog_mode: str

    def identity(self, cnpj: str) -> SourceRead: ...
    def contracts(self, cnpj: str) -> SourceRead: ...
    def buyers(self, cnpj: str) -> SourceRead: ...
    def competitors(self, cnpj: str) -> SourceRead: ...
    def price_panel(self, cnpj: str) -> SourceRead: ...
    def expiring(self, cnpj: str, window_days: int) -> SourceRead: ...
    def opportunities(self, cnpj: str) -> SourceRead: ...


class DatalakeSource:
    """Read-only DataLake backend. Opens one read-only transaction per read."""

    catalog_mode = "official_live"

    def __init__(self, dsn: str, *, observed_at: str | None = None, competitor_limit: int = COMPETITOR_LIMIT):
        import psycopg2  # imported lazily so fixture runs need no driver

        self._connect = lambda: psycopg2.connect(dsn)
        self._observed_at = observed_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self._competitor_limit = competitor_limit

    def _query(self, view: str, sql: str, params: tuple[Any, ...]) -> SourceRead:
        conn = self._connect()
        try:
            conn.set_session(readonly=True, autocommit=True)
            with conn.cursor() as cur:
                try:
                    cur.execute(sql, params)
                except Exception as exc:  # undefined_table / undefined_column
                    if getattr(exc, "pgcode", None) in {"42P01", "42703"}:
                        return SourceRead(
                            source=view,
                            observed_at=self._observed_at,
                            reason_codes=(REASON_TABLE_MISSING,),
                            available=False,
                        )
                    raise
                return SourceRead(source=view, observed_at=self._observed_at, rows=_rows(cur))
        finally:
            conn.close()

    def identity(self, cnpj: str) -> SourceRead:
        return self._query(
            TABLE_REGISTRY,
            f"""
            SELECT cnpj14, razao_social, nome_fantasia, cnae_principal, situacao_cadastral,
                   municipio, uf, source, source_date
              FROM {TABLE_REGISTRY}
             WHERE cnpj14 = %s
             LIMIT 1
            """,  # noqa: S608 -- table name is a module constant; the CNPJ is bound via %s
            (cnpj,),
        )

    def contracts(self, cnpj: str) -> SourceRead:
        return self._query(
            VIEW_CONTRACTS,
            f"""
            SELECT contrato_id, buyer_cnpj, buyer_nome, objeto, valor, data_inicio, data_fim,
                   data_publicacao, data_assinatura, uf, municipio, is_active, source,
                   {CATEGORY_SQL.format(col="objeto")} AS categoria
              FROM {VIEW_CONTRACTS}
             WHERE supplier_cnpj = %s
             ORDER BY contrato_id
            """,  # noqa: S608 -- view names are module constants; the CNPJ is bound via %s
            (cnpj,),
        )

    def buyers(self, cnpj: str) -> SourceRead:
        return self._query(
            VIEW_CONTRACTS,
            f"""
            SELECT buyer_cnpj,
                   MIN(buyer_nome) AS buyer_nome,
                   MIN(uf) AS uf,
                   COUNT(*) AS contract_count,
                   COUNT(valor) AS valued_count,
                   SUM(valor) AS valor_sum,
                   MAX(data_fim) AS last_data_fim,
                   MAX(data_publicacao) AS last_publicacao
              FROM {VIEW_CONTRACTS}
             WHERE supplier_cnpj = %s
             GROUP BY buyer_cnpj
             ORDER BY COUNT(*) DESC, SUM(valor) DESC NULLS LAST, buyer_cnpj
             LIMIT %s
            """,  # noqa: S608 -- view names are module constants; every value is bound via %s
            (cnpj, BUYER_LIMIT),
        )

    def competitors(self, cnpj: str) -> SourceRead:
        """Suppliers that dispute the same space as the focal.

        Sharing a buyer is not enough: a municipality buys stationery and asphalt
        from the same list. A competitor must hold contracts with the focal's
        buyers **and** in one of the focal's own contract categories.
        """
        return self._query(
            VIEW_CONTRACTS,
            f"""
            WITH focal AS (
                SELECT buyer_cnpj, {CATEGORY_SQL.format(col="objeto")} AS categoria
                  FROM {VIEW_CONTRACTS}
                 WHERE supplier_cnpj = %s AND buyer_cnpj IS NOT NULL
            ),
            focal_buyers AS (SELECT DISTINCT buyer_cnpj FROM focal),
            -- Primary category only. Sharing a secondary bucket (a road-maintenance
            -- contract lands in FACILITIES alongside cleaning supplies) produces
            -- peers that do not dispute the same work.
            focal_categories AS (
                SELECT categoria FROM focal GROUP BY categoria ORDER BY COUNT(*) DESC, categoria LIMIT 1
            ),
            peers AS (
                SELECT c.supplier_cnpj, c.supplier_nome, c.buyer_cnpj, c.valor,
                       {CATEGORY_SQL.format(col="c.objeto")} AS categoria
                  FROM {VIEW_CONTRACTS} c
                  JOIN focal_buyers b ON b.buyer_cnpj = c.buyer_cnpj
                 WHERE c.supplier_cnpj IS NOT NULL AND c.supplier_cnpj <> %s
            )
            SELECT p.supplier_cnpj,
                   MIN(p.supplier_nome) AS supplier_nome,
                   COUNT(*) AS contract_count,
                   COUNT(p.valor) AS valued_count,
                   SUM(p.valor) AS valor_sum,
                   COUNT(DISTINCT p.buyer_cnpj) AS shared_buyer_count,
                   STRING_AGG(DISTINCT p.categoria, ',' ORDER BY p.categoria) AS shared_categories
              FROM peers p
              JOIN focal_categories fc ON fc.categoria = p.categoria
             GROUP BY p.supplier_cnpj
             ORDER BY COUNT(DISTINCT p.buyer_cnpj) DESC, COUNT(*) DESC, SUM(p.valor) DESC NULLS LAST,
                      p.supplier_cnpj
             LIMIT %s
            """,  # noqa: S608 -- view names are module constants; every value is bound via %s
            (cnpj, cnpj, self._competitor_limit),
        )

    def price_panel(self, cnpj: str) -> SourceRead:
        """Reference percentiles by category, plus the focal position per category."""
        return self._query(
            VIEW_PERCENTIS,
            f"""
            WITH focal AS (
                SELECT {CATEGORY_SQL.format(col="objeto")} AS categoria,
                       COUNT(*) AS focal_count,
                       COUNT(valor) AS focal_valued_count,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY valor) AS focal_median
                  FROM {VIEW_CONTRACTS}
                 WHERE supplier_cnpj = %s
                 GROUP BY 1
            )
            SELECT p.categoria, p.qtd_contratos, p.valor_total, p.ticket_medio,
                   p.p25_valor, p.p50_valor, p.p75_valor,
                   focal.focal_count, focal.focal_valued_count, focal.focal_median
              FROM {VIEW_PERCENTIS} p
              JOIN focal ON focal.categoria = p.categoria
             ORDER BY p.categoria
            """,  # noqa: S608 -- view names are module constants; the CNPJ is bound via %s
            (cnpj,),
        )

    def expiring(self, cnpj: str, window_days: int = EXPIRING_WINDOW_DAYS) -> SourceRead:
        return self._query(
            VIEW_EXPIRING,
            f"""
            SELECT contrato_id, orgao_cnpj, orgao_nome, objeto_contrato, valor_contrato,
                   data_inicio_contrato, data_fim_contrato, dias_ate_fim, uf, municipio
              FROM {VIEW_EXPIRING}
             WHERE fornecedor_cnpj = %s AND dias_ate_fim IS NOT NULL AND dias_ate_fim <= %s
             ORDER BY dias_ate_fim, contrato_id
            """,  # noqa: S608 -- view name is a module constant; every value is bound via %s
            (cnpj, window_days),
        )

    def opportunities(self, cnpj: str) -> SourceRead:
        return self._query(
            VIEW_OPPORTUNITIES,
            f"""
            WITH focal_buyers AS (
                SELECT DISTINCT buyer_cnpj
                  FROM {VIEW_CONTRACTS}
                 WHERE supplier_cnpj = %s AND buyer_cnpj IS NOT NULL
            )
            SELECT o.bid_id, o.pncp_id, o.objeto, o.valor_estimado, o.modalidade,
                   o.orgao_cnpj, o.orgao_nome, o.uf, o.municipio,
                   o.data_publicacao, o.data_abertura, o.data_encerramento, o.link_edital
              FROM {VIEW_OPPORTUNITIES} o
              JOIN focal_buyers f ON f.buyer_cnpj = o.orgao_cnpj
             ORDER BY o.data_encerramento NULLS LAST, o.bid_id
             LIMIT %s
            """,  # noqa: S608 -- view names are module constants; every value is bound via %s
            (cnpj, OPPORTUNITY_LIMIT),
        )


class FixtureSource:
    """Deterministic backend for tests and offline demos. Never claims live."""

    catalog_mode = "fixture"

    def __init__(self, path: str | Path):
        self._data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._observed_at = self._data.get("observed_at", "1970-01-01T00:00:00Z")

    def _read(self, key: str, view: str) -> SourceRead:
        block = self._data.get(key)
        if block is None:
            return SourceRead(
                source=view, observed_at=self._observed_at, reason_codes=(REASON_TABLE_MISSING,), available=False
            )
        return SourceRead(source=view, observed_at=self._observed_at, rows=tuple(block))

    def identity(self, cnpj: str) -> SourceRead:
        return self._read("identity", TABLE_REGISTRY)

    def contracts(self, cnpj: str) -> SourceRead:
        return self._read("contracts", VIEW_CONTRACTS)

    def buyers(self, cnpj: str) -> SourceRead:
        return self._read("buyers", VIEW_CONTRACTS)

    def competitors(self, cnpj: str) -> SourceRead:
        return self._read("competitors", VIEW_CONTRACTS)

    def price_panel(self, cnpj: str) -> SourceRead:
        return self._read("price_panel", VIEW_PERCENTIS)

    def expiring(self, cnpj: str, window_days: int = EXPIRING_WINDOW_DAYS) -> SourceRead:
        return self._read("expiring", VIEW_EXPIRING)

    def opportunities(self, cnpj: str) -> SourceRead:
        return self._read("opportunities", VIEW_OPPORTUNITIES)
