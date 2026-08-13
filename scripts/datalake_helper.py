"""DataLake PostgreSQL shared helper — Extra Consultoria.

Centraliza acesso ao DataLake (`pncp_raw_bids`, `pncp_supplier_contracts`,
`enriched_entities`, `ingestion_runs`) para commands B2G.

Usa psycopg2 direto (backend local PostgreSQL). Single-user, sem Supabase.

Uso típico:

    from datalake_helper import DatalakeClient

    dl = DatalakeClient()
    if dl.is_enabled:
        rows, meta = dl.search_bids(ufs=["SC"], dias=30, modalidades=[5, 6])
        if rows is None:
            # falha — usar fluxo live
            ...
        else:
            for row in rows:
                ...

NÃO ARMAZENADO — fluxos que permanecem live:
- PNCP `/pncp/v1/orgaos/.../arquivos` (download de PDFs do edital):
  DataLake não armazena binários.
- SICAF (captcha-gated): script dedicado.
- WebSearch (regulatório, jurisprudência, notícias).
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any

_DEFAULT_LIMIT = 2000
_MAX_LIMIT = 5000  # search_datalake RPC cap


# ------------------------------------------------------------------
# Local PostgreSQL Backend (psycopg2)
# ------------------------------------------------------------------


class _LocalPgResult:
    """Mimics Supabase .execute() result object."""

    def __init__(self, data: list[dict]) -> None:
        self.data = data

    def execute(self) -> _LocalPgResult:
        """No-op for compatibility with Supabase rpc().execute() chain."""
        return self


class _LocalPgQuery:
    """Fluent query builder mimicking Supabase table().select().eq()... chain."""

    def __init__(self, conn, table: str) -> None:
        self._conn = conn
        self._table = table
        self._cols: str = "*"
        self._wheres: list[str] = []
        self._params: list[Any] = []
        self._order_col: str | None = None
        self._order_desc: bool = True
        self._limit_val: int | None = None

    def _param(self, val: Any) -> str:
        self._params.append(val)
        return "%s"

    def select(self, cols: str) -> _LocalPgQuery:
        self._cols = cols
        return self

    def eq(self, col: str, val: Any) -> _LocalPgQuery:
        self._wheres.append(f'"{col}" = {self._param(val)}')
        return self

    def in_(self, col: str, vals: list[Any]) -> _LocalPgQuery:
        placeholders = ", ".join(self._param(v) for v in vals)
        self._wheres.append(f'"{col}" IN ({placeholders})')
        return self

    def gte(self, col: str, val: Any) -> _LocalPgQuery:
        self._wheres.append(f'"{col}" >= {self._param(val)}')
        return self

    def lte(self, col: str, val: Any) -> _LocalPgQuery:
        self._wheres.append(f'"{col}" <= {self._param(val)}')
        return self

    def ilike(self, col: str, pattern: str) -> _LocalPgQuery:
        self._wheres.append(f'"{col}" ILIKE {self._param(pattern)}')
        return self

    def order(self, col: str, *, desc: bool = True) -> _LocalPgQuery:
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> _LocalPgQuery:
        self._limit_val = n
        return self

    def execute(self) -> _LocalPgResult:
        sql = f"SELECT {self._cols} FROM {self._table}"  # noqa: S608 -- internal query builder, values are %s parameterized
        if self._wheres:
            sql += " WHERE " + " AND ".join(self._wheres)
        if self._order_col:
            direction = "DESC" if self._order_desc else "ASC"
            sql += f' ORDER BY "{self._order_col}" {direction}'
        if self._limit_val is not None:
            sql += f" LIMIT {self._limit_val}"
        with self._conn._cursor() as cur:
            cur.execute(sql, self._params)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return _LocalPgResult(rows)


class _LocalPg:
    """Mimics Supabase client with rpc() and table() methods via psycopg2."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    @contextmanager
    def _cursor(self):
        import psycopg2
        import psycopg2.extras

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._dsn)
        try:
            cur = self._conn.cursor()
            yield cur
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def rpc(self, fn_name: str, params: dict[str, Any]) -> _LocalPgResult:
        """Call a PostgreSQL function with named parameters.

        Auto-casts ISO date strings to ::date and numeric literals to ::numeric
        to resolve function overloads unambiguously.
        """
        arg_list = []
        values = []
        _iso_date = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for k, v in params.items():
            if v is None:
                arg_list.append(f'"{k}" := NULL')
            elif isinstance(v, str) and _iso_date.match(v):
                arg_list.append(f'"{k}" := %s::date')
                values.append(v)
            elif isinstance(v, str):
                arg_list.append(f'"{k}" := %s::text')
                values.append(v)
            elif isinstance(v, float):
                arg_list.append(f'"{k}" := %s::numeric')
                values.append(str(v))
            else:
                arg_list.append(f'"{k}" := %s')
                values.append(v)
        sql = f'SELECT * FROM "public"."{fn_name}"({", ".join(arg_list)})'  # noqa: S608 -- function name is internal, values are %s parameterized
        with self._cursor() as cur:
            cur.execute(sql, values)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return _LocalPgResult(rows)

    def table(self, name: str) -> _LocalPgQuery:
        return _LocalPgQuery(self, f'"public"."{name}"')


# Extra Consultoria: always use local PostgreSQL backend.
# Supabase backend removed — single-user, direct psycopg2 access.


# ------------------------------------------------------------------
# DatalakeClient
# ------------------------------------------------------------------


class DatalakeClient:
    """Wrapper sobre Supabase RPCs/tabelas do DataLake PNCP.

    Suporta 2 backends:
    - Supabase (remoto): SUPABASE_URL + key configurados
    - Local (psycopg2 direto): LOCAL_DATALAKE_DSN configurado, sem SUPABASE_URL
    """

    def __init__(self) -> None:
        self._local: _LocalPg | None = None
        self._init_error: str | None = None
        self._enabled: bool | None = None
        self._use_local: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_enabled(self) -> bool:
        """True quando DATALAKE_QUERY_ENABLED=true E backend disponível."""
        if self._enabled is not None:
            return self._enabled
        if os.getenv("DATALAKE_QUERY_ENABLED", "").lower() not in ("true", "1"):
            self._enabled = False
            return False

        # Extra Consultoria: always use local PostgreSQL backend
        self._use_local = True
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            self._init_error = "psycopg2 not installed for local backend"
            self._enabled = False
            return False
        self._enabled = True
        return True

    def _client(self) -> Any:
        """Lazy init local PostgreSQL client."""
        if self._local is not None:
            return self._local
        if not self.is_enabled:
            return None

        dsn = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@127.0.0.1:5433/pncp_datalake")
        try:
            self._local = _LocalPg(dsn)
        except Exception as e:
            self._init_error = f"Local PG init failed: {e}"
            self._local = None
        return self._local

    @property
    def init_error(self) -> str | None:
        return self._init_error

    @property
    def backend(self) -> str:
        """'local' ou 'none'."""
        if self._use_local:
            return "local"
        return "none"

    # ------------------------------------------------------------------
    # search_datalake RPC (pncp_raw_bids)
    # ------------------------------------------------------------------

    def search_bids(
        self,
        ufs: list[str] | None = None,
        dias: int | None = None,
        date_start: date | str | None = None,
        date_end: date | str | None = None,
        tsquery: str | None = None,
        websearch_text: str | None = None,
        modalidades: list[int] | None = None,
        valor_min: float | None = None,
        valor_max: float | None = None,
        esferas: list[str] | None = None,
        modo: str = "publicacao",
        limit: int = _DEFAULT_LIMIT,
        paginate_by_uf_modalidade: bool = True,
        verbose: bool = False,
    ) -> tuple[list[dict] | None, dict]:
        """Wrapper sobre `search_datalake` RPC.

        Args:
            ufs: lista de siglas UF (ou None p/ todas)
            dias: janela [hoje - dias, hoje]; ignorado se date_start/date_end fornecidos
            date_start, date_end: bounds explícitos (ISO YYYY-MM-DD ou date)
            tsquery: tsquery PT-BR (sector keywords OR-joined)
            websearch_text: texto livre user (phrases + exclusions)
            modalidades: lista de modalidade_id (4=Concorrência, 5/6=Pregão, 8=Inexigib...)
            valor_min, valor_max: range de valor_total_estimado
            esferas: ["F","E","M","D"]
            modo: 'publicacao' (filtra por data_publicacao) ou 'abertas' (encerramento futuro)
            limit: cap por chamada (max 5000)
            paginate_by_uf_modalidade: se True, faz N×M chamadas para evitar PostgREST 1000-row cap

        Returns:
            (rows, meta) onde rows é lista de dicts ou None em falha. Meta inclui
            `source='datalake'`, `total_raw`, `pages_fetched`, e `errors`.
        """
        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}

        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}

        ds, de = self._resolve_dates(dias, date_start, date_end)

        # Always pass all 12 params to resolve overload (12-param version includes
        # p_websearch_text + p_embedding; 11-param version does not)
        base_params: dict[str, Any] = {
            "p_ufs": ufs or None,
            "p_date_start": ds,
            "p_date_end": de,
            "p_tsquery": tsquery,
            "p_websearch_text": websearch_text,
            "p_modalidades": modalidades or None,
            "p_valor_min": valor_min,
            "p_valor_max": valor_max,
            "p_esferas": esferas,
            "p_modo": modo,
            "p_limit": min(limit, _MAX_LIMIT),
            "p_embedding": None,
        }

        rows: list[dict] = []
        errors: list[str] = []
        pages = 0

        if paginate_by_uf_modalidade and ufs and modalidades:
            # PostgREST cap = 1000 rows; paginar por (UF, modalidade)
            for uf in ufs:
                uf_total = 0
                for mod_id in modalidades:
                    p = {**base_params, "p_ufs": [uf], "p_modalidades": [mod_id]}
                    try:
                        r = sb.rpc("search_datalake", p).execute()
                        chunk = r.data or []
                        rows.extend(chunk)
                        uf_total += len(chunk)
                        pages += 1
                    except Exception as e:
                        errors.append(f"{uf}/mod{mod_id}: {e}")
                if verbose and uf_total:
                    print(f"      {uf}: {uf_total} editais")
        else:
            try:
                r = sb.rpc("search_datalake", base_params).execute()
                rows = r.data or []
                pages = 1
            except Exception as e:
                errors.append(str(e))

        meta = {
            "source": "datalake",
            "total_raw": len(rows),
            "pages_fetched": pages,
            "errors": errors,
            "date_start": ds,
            "date_end": de,
        }

        if not rows and errors:
            return None, {**meta, "datalake_error": errors[0]}

        return rows, meta

    def search_bids_trigram(
        self,
        query_term: str,
        ufs: list[str] | None = None,
        limit: int = 200,
    ) -> tuple[list[dict] | None, dict]:
        """Fuzzy fallback (`search_datalake_trigram_fallback`). Use quando FTS retorna 0."""
        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}
        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}
        try:
            r = sb.rpc(
                "search_datalake_trigram_fallback",
                {"p_query_term": query_term, "p_ufs": ufs, "p_limit": min(limit, 500)},
            ).execute()
            rows = r.data or []
            return rows, {"source": "datalake_trigram", "total_raw": len(rows)}
        except Exception as e:
            return None, {"datalake_error": f"trigram failed: {e}"}

    # ------------------------------------------------------------------
    # pncp_supplier_contracts (raw SELECT)
    # ------------------------------------------------------------------

    def supplier_contracts(
        self,
        ni_fornecedor: str | None = None,
        supplier_id_type: str | None = None,
        supplier_identifier: str | None = None,
        orgao_cnpj: str | None = None,
        ufs: list[str] | None = None,
        keywords: list[str] | None = None,
        date_start: date | str | None = None,
        date_end: date | str | None = None,
        meses: int | None = None,
        modalidade_keywords: list[str] | None = None,
        value_min: float | None = None,
        limit: int = 1000,
        order_by_data_desc: bool = True,
        cursor: dict[str, Any] | None = None,
        snapshot_at: str | None = None,
    ) -> tuple[list[dict] | None, dict]:
        """SELECT em `pncp_supplier_contracts` com filtros compostos.

        Args:
            ni_fornecedor: identificador BR legado; 14 dígitos=CNPJ, 11=CPF
            supplier_id_type/supplier_identifier: identidade canônica explícita
            orgao_cnpj: CNPJ 14d do órgão comprador
            ufs: lista de UFs
            keywords: lista de termos para ILIKE em objeto_contrato (OR)
            date_start, date_end: bounds em data_assinatura
            meses: alternativa — janela [hoje - meses, hoje]
            modalidade_keywords: NÃO disponível (tabela não tem modalidade — ignored)
            limit: tamanho da página de apresentação (máximo 1000)
            order_by_data_desc: True (default) ordena por data_assinatura DESC

        Returns:
            (rows, meta) ou (None, error_meta).
        """
        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}
        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}

        ds, de = self._resolve_dates(meses_to_dias(meses), date_start, date_end)

        canonical_type = supplier_id_type.upper() if supplier_id_type else None
        canonical_identifier = supplier_identifier
        if ni_fornecedor and not canonical_identifier:
            digits = "".join(ch for ch in ni_fornecedor if ch.isdigit())
            if len(digits) == 14:
                canonical_type, canonical_identifier = "CNPJ", digits
            elif len(digits) == 11:
                canonical_type, canonical_identifier = "CPF", digits
            else:
                return None, {"datalake_error": "supplier identity must be canonical or a valid CNPJ/CPF length"}
        if bool(canonical_type) != bool(canonical_identifier):
            return None, {"datalake_error": "supplier_id_type and supplier_identifier must be provided together"}
        if canonical_type not in (None, "CNPJ", "CPF", "FOREIGN", "UNKNOWN"):
            return None, {"datalake_error": f"unsupported supplier_id_type: {canonical_type}"}

        try:
            if not order_by_data_desc:
                return None, {"datalake_error": "v2 contract pagination requires deterministic descending order"}
            r = sb.rpc(
                "supplier_contracts_page_v2",
                {
                    "p_supplier_id_type": canonical_type,
                    "p_supplier_identifier": canonical_identifier,
                    "p_orgao_cnpj": orgao_cnpj,
                    "p_ufs": [u.upper() for u in ufs] if ufs else None,
                    "p_keywords": [k for k in (keywords or []) if k],
                    "p_date_start": ds,
                    "p_date_end": de,
                    "p_value_min": value_min,
                    "p_page_size": min(max(limit, 1), 1000),
                    "p_cursor_date": (cursor or {}).get("date"),
                    "p_cursor_id": (cursor or {}).get("id"),
                    "p_snapshot_at": snapshot_at,
                },
            ).execute()
            response_rows = r.data
            if (
                not isinstance(response_rows, list)
                or not response_rows
                or not isinstance(response_rows[0], dict)
                or not isinstance(response_rows[0].get("supplier_contracts_page_v2"), dict)
            ):
                return None, {"datalake_error": "supplier_contracts returned an empty or invalid RPC payload"}
            payload = response_rows[0]["supplier_contracts_page_v2"]
            rows = payload.get("items") or []
            meta = payload.get("meta") or {}
            return rows, meta
        except Exception as e:
            return None, {"datalake_error": f"supplier_contracts query failed: {e}"}

    def pricing_stats(
        self,
        keywords: list[str],
        ufs: list[str] | None = None,
        meses: int = 12,
        orgao_cnpj: str | None = None,
        valor_min: float = 1.0,
    ) -> tuple[dict | None, dict]:
        """Estatísticas agregadas de preço sobre `pncp_supplier_contracts`.

        Args:
            keywords: termos (ILIKE OR) para `objeto_contrato`
            ufs: filtro de UF (opcional)
            meses: janela em data_assinatura
            orgao_cnpj: filtro adicional por órgão
            valor_min: piso para descartar registros zerados (default 1.0)

        Returns:
            ({n, p10, p25, mediana, p75, p90, media, dp, cv, sample}, meta)
            onde `sample` são os top-N contratos brutos (ordenados por data desc, max 200).
        """
        rows, meta = self.supplier_contracts(
            keywords=keywords,
            ufs=ufs,
            meses=meses,
            orgao_cnpj=orgao_cnpj,
            value_min=valor_min,
            limit=200,
        )
        if rows is None:
            return None, meta

        if int(meta.get("total_count") or 0) == 0:
            return None, {**meta, "datalake_error": "0 contracts with valid valor_global"}

        # Aggregates come from SQL over the complete filtered set. ``rows`` is
        # only a presentation sample and never changes the denominator.
        n = int(meta["total_count"])
        media = float(meta.get("average_value") or 0)
        dp = float(meta.get("stddev_value") or 0)
        sample = [r for r in rows if float(r.get("valor_global") or 0) >= valor_min]

        stats = {
            "n": n,
            "p10": round(float(meta.get("p10") or 0), 2),
            "p25": round(float(meta.get("p25") or 0), 2),
            "mediana": round(float(meta.get("p50") or 0), 2),
            "p75": round(float(meta.get("p75") or 0), 2),
            "p90": round(float(meta.get("p90") or 0), 2),
            "media": round(media, 2),
            "dp": round(dp, 2),
            "cv": round((dp / media * 100) if media > 0 else 0.0, 2),
            "sample": sample,
        }
        return stats, {**meta, "n_valid": n, "n_filtered_out": int(meta.get("quarantine_count") or 0)}

    # ------------------------------------------------------------------
    # enriched_entities (BrasilAPI cache, TTL lógico 30d)
    # ------------------------------------------------------------------

    def enriched_entity(
        self,
        entity_type: str,
        entity_id: str,
        max_age_days: int = 30,
    ) -> tuple[dict | None, dict]:
        """Lookup em `enriched_entities`.

        Args:
            entity_type: 'fornecedor' | 'municipio' | 'orgao'
            entity_id: CNPJ 14d ou IBGE 7d
            max_age_days: rejeita rows com `enriched_at` mais velhas (default 30d)

        Returns:
            (data_payload | None, meta). data é o JSONB armazenado.
        """
        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}
        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}
        try:
            r = (
                sb.table("enriched_entities")
                .select("data,enriched_at")
                .eq("entity_type", entity_type)
                .eq("entity_id", entity_id)
                .limit(1)
                .execute()
            )
            rows = r.data or []
            if not rows:
                return None, {"source": "enriched_cache_miss"}
            row = rows[0]
            enriched_at = row.get("enriched_at") or ""
            try:
                ts = datetime.fromisoformat(enriched_at.replace("Z", "+00:00"))
                age = datetime.now(ts.tzinfo) - ts
                if age > timedelta(days=max_age_days):
                    return None, {"source": "enriched_cache_stale", "age_days": age.days}
            except (ValueError, TypeError):
                pass
            return row.get("data"), {
                "source": "enriched_cache_hit",
                "enriched_at": enriched_at,
            }
        except Exception as e:
            return None, {"datalake_error": f"enriched_entities query failed: {e}"}

    # ------------------------------------------------------------------
    # ingestion_runs (último ETL — usado pelo radar híbrido)
    # ------------------------------------------------------------------

    def last_etl_at(self, source: str = "pncp") -> tuple[datetime | None, dict]:
        """Último ARQ run completado em `ingestion_runs`.

        Schema real (validado 2026-04-29):
        - tabela NÃO tem coluna `source` (PNCP é implícito; outras fontes têm tabelas
          próprias)
        - `completed_at` é populado raramente (quase sempre NULL); usamos `started_at`
          como melhor aproximação
        - status válidos: 'completed' (sucesso), 'running', 'partial'

        Usado pelo `/radar-b2g` modo híbrido: se `last_etl_at < NOW() - 30min`, o caller
        complementa o resultado do DataLake com 1 curl PNCP cobrindo `[last_etl_at, NOW()]`.

        Arg `source` é mantido por compat com callers antigos mas é ignorado.
        """
        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}
        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}
        try:
            r = (
                sb.table("ingestion_runs")
                .select("started_at,completed_at,status,run_type")
                .eq("status", "completed")
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = r.data or []
            if not rows:
                return None, {"source": "ingestion_runs_empty"}
            ts_raw = rows[0].get("completed_at") or rows[0].get("started_at")
            if not ts_raw:
                return None, {"source": "ingestion_runs_no_timestamp"}
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            return ts, {
                "source": "ingestion_runs",
                "started_at": rows[0].get("started_at"),
                "run_type": rows[0].get("run_type"),
            }
        except Exception as e:
            return None, {"datalake_error": f"ingestion_runs query failed: {e}"}

    # ------------------------------------------------------------------
    # bid_detail (single edital lookup)
    # ------------------------------------------------------------------

    def bid_detail(self, pncp_id: str) -> tuple[dict | None, dict]:
        """SELECT por PK em `pncp_raw_bids`.

        Args:
            pncp_id: `numeroControlePNCP` raw, formato Lei 14.133:
                `{cnpj14}-1-{seq:06d}/{ano}` (ex: `13714142000162-1-000014/2026`).
                Outras modalidades podem usar `-2-` ou `-3-`.

        Returns:
            (bid_dict | None, meta). bid_dict contém todas as colunas da tabela
            (objeto_compra, valor_total_estimado, modalidade_id/nome, datas, orgao,
            link_pncp, link_sistema_origem, situacao_compra, etc.).
        """
        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}
        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}
        try:
            r = (
                sb.table("pncp_raw_bids")
                .select(
                    "pncp_id,objeto_compra,valor_total_estimado,modalidade_id,modalidade_nome,"
                    "uf,municipio,codigo_municipio_ibge,esfera_id,situacao_compra,"
                    "orgao_cnpj,orgao_razao_social,unidade_nome,"
                    "data_publicacao,data_abertura,data_encerramento,"
                    "link_pncp,link_sistema_origem,source,is_active,ingested_at,updated_at"
                )
                .eq("pncp_id", pncp_id)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            rows = r.data or []
            if not rows:
                return None, {"datalake_error": "not_found", "pncp_id": pncp_id}
            return rows[0], {"source": "datalake_bid_detail", "pncp_id": pncp_id}
        except Exception as e:
            return None, {"datalake_error": f"bid_detail query failed: {e}"}

    # ------------------------------------------------------------------
    # top_competitors (groupby ni_fornecedor sobre supplier_contracts)
    # ------------------------------------------------------------------

    def top_competitors(
        self,
        orgao_cnpj: str | None = None,
        setor_keywords: list[str] | None = None,
        ufs: list[str] | None = None,
        meses: int = 24,
        limit: int = 10,
    ) -> tuple[list[dict] | None, dict]:
        """Top fornecedores, agregado no PostgreSQL sobre o recorte completo.

        Args:
            orgao_cnpj: filtra por órgão comprador (opcional)
            setor_keywords: lista de tokens ILIKE AND no objeto_contrato (opcional)
            ufs: filtro de UF (opcional)
            meses: janela em data_assinatura (default 24)
            limit: top-N a retornar (default 10)

        Returns:
            (rows, meta) onde rows é
            `[{ni_fornecedor, nome_fornecedor, n_contratos, valor_total, ultimo_contrato_data, ufs}]`
            ou (None, error_meta).
        """
        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}
        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}
        ds, de = self._resolve_dates(meses_to_dias(meses), None, None)
        try:
            result = sb.rpc(
                "supplier_contracts_grouped_v2",
                {
                    "p_group_by": "supplier",
                    "p_orgao_cnpj": orgao_cnpj,
                    "p_ufs": [u.upper() for u in ufs] if ufs else None,
                    "p_keywords": [k for k in (setor_keywords or []) if k],
                    "p_date_start": ds,
                    "p_date_end": de,
                    "p_limit": limit,
                    "p_snapshot_at": None,
                },
            ).execute()
            payload = (result.data or [{}])[0].get("supplier_contracts_grouped_v2") or {}
            ranked = [
                {
                    "ni_fornecedor": row.get("group_identifier"),
                    "supplier_id_type": row.get("group_type"),
                    "nome_fornecedor": row.get("group_name"),
                    "n_contratos": int(row.get("matched_contracts") or 0),
                    "valor_total": round(float(row.get("sum_value") or 0), 2),
                    "ultimo_contrato_data": row.get("latest_event_date"),
                    "ufs": row.get("ufs") or [],
                }
                for row in payload.get("items") or []
            ]
            meta = payload.get("meta") or {}
            return ranked, {**meta, "n_input": meta.get("total_count"), "n_unique_suppliers": meta.get("total_groups")}
        except Exception as e:
            return None, {"datalake_error": f"top_competitors query failed: {e}"}

    # ------------------------------------------------------------------
    # agg_by_orgao (groupby orgao_cnpj sobre supplier_contracts)
    # ------------------------------------------------------------------

    def agg_by_orgao(
        self,
        setor_keywords: list[str],
        ufs: list[str] | None = None,
        meses: int = 12,
        limit: int = 20,
    ) -> tuple[list[dict] | None, dict]:
        """Top órgãos contratantes para um setor (sinal de demanda real).

        Args:
            setor_keywords: tokens ILIKE AND no objeto_contrato (obrigatório)
            ufs: filtro UF (opcional)
            meses: janela em data_assinatura (default 12)
            limit: top-N (default 20)

        Returns:
            (rows, meta) onde rows é
            `[{orgao_cnpj, orgao_nome, uf, n_contratos, valor_total, ticket_medio}]`
            ordenado por `valor_total DESC`.
        """
        if not setor_keywords:
            return None, {"datalake_error": "setor_keywords required"}

        if not self.is_enabled:
            return None, {"datalake_error": self._init_error or "disabled"}
        sb = self._client()
        if sb is None:
            return None, {"datalake_error": self._init_error or "client unavailable"}
        ds, de = self._resolve_dates(meses_to_dias(meses), None, None)
        try:
            result = sb.rpc(
                "supplier_contracts_grouped_v2",
                {
                    "p_group_by": "orgao",
                    "p_orgao_cnpj": None,
                    "p_ufs": [u.upper() for u in ufs] if ufs else None,
                    "p_keywords": setor_keywords,
                    "p_date_start": ds,
                    "p_date_end": de,
                    "p_limit": limit,
                    "p_snapshot_at": None,
                },
            ).execute()
            payload = (result.data or [{}])[0].get("supplier_contracts_grouped_v2") or {}
            ranked = []
            for row in payload.get("items") or []:
                n = int(row.get("matched_contracts") or 0)
                value = round(float(row.get("sum_value") or 0), 2)
                ufs_for_org = row.get("ufs") or []
                ranked.append(
                    {
                        "orgao_cnpj": row.get("group_identifier"),
                        "orgao_nome": row.get("group_name"),
                        "uf": ufs_for_org[0] if len(ufs_for_org) == 1 else None,
                        "ufs": ufs_for_org,
                        "n_contratos": n,
                        "valor_total": value,
                        "ticket_medio": round(value / n, 2) if n else 0.0,
                    }
                )
            meta = payload.get("meta") or {}
            return ranked, {**meta, "n_input": meta.get("total_count"), "n_unique_orgaos": meta.get("total_groups")}
        except Exception as e:
            return None, {"datalake_error": f"agg_by_orgao query failed: {e}"}

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_dates(
        dias: int | None,
        date_start: date | str | None,
        date_end: date | str | None,
    ) -> tuple[str | None, str | None]:
        """Normaliza inputs de data para ISO YYYY-MM-DD."""

        def to_iso(d: date | str | None) -> str | None:
            if d is None:
                return None
            if isinstance(d, str):
                return d[:10]
            return d.strftime("%Y-%m-%d")

        ds = to_iso(date_start)
        de = to_iso(date_end)
        if ds is None and de is None and dias is not None:
            today = date.today()
            ds = (today - timedelta(days=dias)).strftime("%Y-%m-%d")
            de = today.strftime("%Y-%m-%d")
        return ds, de


def meses_to_dias(meses: int | None) -> int | None:
    """Converte janela em meses para dias (~30.4 dias/mês)."""
    if meses is None:
        return None
    return int(meses * 30.4)
