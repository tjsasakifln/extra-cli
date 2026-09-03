"""LI-3 — leitores as-of estritamente read-only (Decisao 6, §8.4).

Regras invariantes desta camada:

* Todo acesso a objeto outbound e SELECT. Nenhum INSERT/UPDATE/DELETE aqui.
* A leitura de oportunidades vai a ``live_open_opportunities_as_of(DATE)``, que
  por sua vez le a TABELA BASE ``pncp_raw_bids``. NAO usamos
  ``v_open_opportunities_canonical``: a view ja filtrou
  ``data_encerramento >= CURRENT_DATE`` e as linhas que ela descartou sao
  irrecuperaveis por qualquer consulta descendente (R2 / AC4).
* O ``TimeZone`` da sessao e fixado explicitamente antes de qualquer leitura.
  As colunas de data sao ``TIMESTAMPTZ`` e a comparacao com o parametro ``DATE``
  promove o dia civil no fuso da sessao — sem esta fixacao o mesmo
  ``snapshot_id`` produziria ``universe_hash`` diferente sob fusos distintos
  (R13 / AC5).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from scripts.confenge_live_intelligence.schema import CUTOFF_TIMEZONE

AS_OF_FUNCTION = "public.live_open_opportunities_as_of"
CONTRACTS_VIEW = "public.v_contracts_canonical_v2"


class LiveIntelligenceSourceError(RuntimeError):
    """Falha de leitura de fonte. Sempre fail-closed, nunca degradacao silenciosa."""


def pin_session_timezone(conn: Any, timezone: str = CUTOFF_TIMEZONE) -> None:
    """Fixa o ``TimeZone`` da sessao. Pre-condicao de todo replay determinístico."""
    with conn.cursor() as cur:
        cur.execute("SET TimeZone TO %s", (timezone,))


def session_timezone(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute("SHOW TimeZone")
        row = cur.fetchone()
    if row is None:
        raise LiveIntelligenceSourceError("nao foi possivel ler o TimeZone da sessao")
    return str(row["TimeZone"] if isinstance(row, dict) else row[0])


def _rows_as_dicts(cur: Any) -> list[dict[str, Any]]:
    if cur.description is None:
        return []
    columns = [d[0] for d in cur.description]
    fetched = cur.fetchall() or []
    out: list[dict[str, Any]] = []
    for row in fetched:
        out.append(dict(row) if isinstance(row, dict) else dict(zip(columns, row, strict=True)))
    return out


def fetch_open_opportunities_as_of(conn: Any, as_of: date) -> list[dict[str, Any]]:
    """Oportunidades abertas na data civil ``as_of`` (SELECT puro).

    Ordenacao deterministica por ``bid_id`` para que o ``universe_hash`` nao
    dependa da ordem fisica das linhas.
    """
    if as_of is None:
        raise LiveIntelligenceSourceError("as_of_date ausente: leitura as-of e indefinida")
    pin_session_timezone(conn)
    with conn.cursor() as cur:
        # noqa justificado: AS_OF_FUNCTION e constante do modulo, nao entrada externa.
        cur.execute(f"SELECT * FROM {AS_OF_FUNCTION}(%s) ORDER BY bid_id", (as_of,))  # noqa: S608
        rows = _rows_as_dicts(cur)
    return rows


def fetch_canonical_open_opportunities(conn: Any) -> list[dict[str, Any]]:
    """Leitura da view outbound, apenas para o teste de equivalencia de AC4."""
    pin_session_timezone(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM public.v_open_opportunities_canonical ORDER BY bid_id")
        return _rows_as_dicts(cur)


def fetch_observed_portfolio(conn: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Contratos publicos observados por fornecedor (SELECT puro sobre a view v2).

    Nenhuma coluna de ``confenge_company_target_fit_current`` /
    ``confenge_company_sector_current`` e lida aqui: a COMPANY do motor inbound e
    projecao independente (Decisao 3, §3.2).
    """
    pin_session_timezone(conn)
    # noqa justificado: CONTRACTS_VIEW e constante do modulo, nao entrada externa.
    sql = f"""
        SELECT contrato_id,
               supplier_cnpj,
               supplier_nome,
               objeto,
               valor,
               uf,
               municipio,
               buyer_cnpj,
               data_assinatura,
               data_inicio,
               data_publicacao,
               data_publicacao_fonte
        FROM {CONTRACTS_VIEW}
        WHERE supplier_cnpj IS NOT NULL AND supplier_cnpj <> ''
        ORDER BY supplier_cnpj, contrato_id
    """  # noqa: S608
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return _rows_as_dicts(cur)


def fetch_source_watermark(conn: Any, source: str) -> dict[str, Any] | None:
    """Watermark observado da fonte. ``None`` = watermark ausente ⇒ blocker.

    O ``TimeZone`` da sessao e fixado ANTES da leitura, como em todo leitor
    deste modulo. Sem isso, ``MAX(updated_at)`` (``TIMESTAMPTZ``) voltava com o
    ``tzinfo`` da sessao corrente — o MESMO instante com offset diferente entre
    duas chamadas (a primeira antes de qualquer pin, a segunda depois). Como o
    watermark passou a ser a proveniencia de ``source_as_of`` e este entra nos
    hashes de linha, a representacao instavel reproduzia a divergencia de
    ``snapshot_id`` de REL-001 por outra via. O produtor ainda normaliza o valor
    para UTC — cinto e suspensorio, por serem defeitos independentes.
    """
    pin_session_timezone(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT MAX(updated_at) AS watermark_at, COUNT(*)::bigint AS observed_rows
            FROM public.pncp_raw_bids
            WHERE source = %s
            """,
            (source,),
        )
        rows = _rows_as_dicts(cur)
    if not rows:
        return None
    row = rows[0]
    if row.get("watermark_at") is None:
        return None
    return row
