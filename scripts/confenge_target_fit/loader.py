"""Load company inputs from the datalake for recompute.

Maps contract → CNPJ14 → CNPJ root → company target-fit.
Treats consórcios conservatively (CONSORTIUM_EVIDENCE provenance).
"""

# ruff: noqa: S608  # dynamic SQL over allowlisted table/column identifiers
from __future__ import annotations

from datetime import datetime
from typing import Any

from scripts.confenge_target_fit.company_key import (
    company_key_from_raiz,
    digits_only,
    is_consortium_contract,
)
from scripts.confenge_target_fit.models import CompanyInput
from scripts.confenge_universe.construction import assess_construction


def load_company_input(
    conn: Any,
    *,
    cnpj_raiz: str,
    source_watermark: str = "",
    contract_limit: int = 200,
) -> CompanyInput:
    raiz = digits_only(cnpj_raiz)[:8]
    if len(raiz) != 8:
        raise ValueError(f"invalid cnpj_raiz: {cnpj_raiz}")

    contracts, branch_cnpjs, max_ts, razao, consortium = _load_contracts(
        conn, raiz=raiz, limit=contract_limit
    )
    cnae_principal, cnaes_sec, fantasia = _load_registry(conn, raiz=raiz)

    # Construction evidence from existing commercial classifiers (shared with universe)
    ce = assess_construction(
        razao_social=razao,
        nome_fantasia=fantasia,
        contracts=contracts,
        cnae_principal=cnae_principal,
        cnaes_secundarios=cnaes_sec,
    )
    ce_dict = ce.as_dict()
    if consortium:
        ce_dict.setdefault("reason_codes", []).append("CONSORTIUM_EVIDENCE")
        # Conservative: do not auto-boost sector on consortium-only portfolios
        notes = ["consortium_contracts_present_conservative"]
    else:
        notes = []

    return CompanyInput(
        company_key=company_key_from_raiz(raiz),
        cnpj_raiz=raiz,
        razao_social=razao,
        nome_fantasia=fantasia,
        cnae_principal=cnae_principal,
        cnaes_secundarios=cnaes_sec,
        contracts=contracts,
        sector_fit=ce.sector_fit,
        activity_class=ce.activity_class,
        construction_evidence=ce_dict,
        is_consortium_member=consortium,
        consortium_notes=notes,
        source_max_updated_at=max_ts,
        source_watermark=source_watermark,
        branch_cnpjs=sorted(branch_cnpjs),
    )


def _load_contracts(
    conn: Any,
    *,
    raiz: str,
    limit: int,
) -> tuple[list[dict[str, Any]], set[str], datetime | None, str | None, bool]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='pncp_supplier_contracts'
            """
        )
        cols = {r["column_name"] for r in (cur.fetchall() or [])}
        cnpj_col = (
            "fornecedor_cnpj"
            if "fornecedor_cnpj" in cols
            else ("ni_fornecedor" if "ni_fornecedor" in cols else None)
        )
        if not cnpj_col:
            return [], set(), None, None, False

        select_cols = [cnpj_col]
        for c in (
            "contrato_id",
            "id",
            "orgao_cnpj",
            "orgao_nome",
            "fornecedor_nome",
            "nome_fornecedor",
            "objeto_contrato",
            "valor_total",
            "valor_global",
            "data_inicio",
            "data_fim",
            "data_fim_vigencia",
            "data_publicacao",
            "data_assinatura",
            "uf",
            "municipio",
            "ingested_at",
            "updated_at",
            "source",
        ):
            if c in cols and c not in select_cols:
                select_cols.append(c)

        order = "data_publicacao" if "data_publicacao" in cols else (
            "ingested_at" if "ingested_at" in cols else select_cols[0]
        )
        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM pncp_supplier_contracts
            WHERE left(regexp_replace({cnpj_col}, '\\D', '', 'g'), 8) = %s
            ORDER BY {order} DESC NULLS LAST
            LIMIT %s
        """
        cur.execute(sql, (raiz, limit))
        rows = [dict(r) for r in (cur.fetchall() or [])]

    contracts: list[dict[str, Any]] = []
    branches: set[str] = set()
    max_ts: datetime | None = None
    razao: str | None = None
    consortium = False

    for r in rows:
        c14 = digits_only(r.get(cnpj_col))[:14]
        if c14:
            branches.add(c14)
        nome = r.get("fornecedor_nome") or r.get("nome_fornecedor")
        if nome and not razao:
            razao = str(nome)
        if is_consortium_contract(r):
            consortium = True
            r = {**r, "is_consortium": True, "consortium_evidence": True}
        # Normalize logical fields
        contracts.append(
            {
                "contrato_id": r.get("contrato_id") or r.get("id"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "orgao_nome": r.get("orgao_nome"),
                "fornecedor_cnpj": c14 or r.get(cnpj_col),
                "fornecedor_nome": nome,
                "objeto_contrato": r.get("objeto_contrato"),
                "valor_total": r.get("valor_total")
                if r.get("valor_total") is not None
                else r.get("valor_global"),
                "data_inicio": r.get("data_inicio") or r.get("data_assinatura"),
                "data_fim": r.get("data_fim") or r.get("data_fim_vigencia"),
                "data_publicacao": r.get("data_publicacao"),
                "uf": r.get("uf"),
                "municipio": r.get("municipio"),
                "is_consortium": r.get("is_consortium", False),
                "source": r.get("source") or "pncp",
            }
        )
        for tkey in ("ingested_at", "updated_at"):
            ts = r.get(tkey)
            if isinstance(ts, datetime):
                if max_ts is None or ts > max_ts:
                    max_ts = ts

    return contracts, branches, max_ts, razao, consortium


def _load_registry(
    conn: Any, *, raiz: str
) -> tuple[str | None, list[str], str | None]:
    """Optional registry enrichment (CNAE). Fail-soft if tables absent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name = ANY(%s)
            """,
            (["supplier_registry", "enriched_entities", "company_registry"],),
        )
        tables = {r["table_name"] for r in (cur.fetchall() or [])}

    if "enriched_entities" in tables:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='enriched_entities'
                """
            )
            cols = {r["column_name"] for r in (cur.fetchall() or [])}
            cnpj_col = "cnpj" if "cnpj" in cols else None
            if cnpj_col:
                fields = [c for c in ("cnae_principal", "cnae", "nome_fantasia", "razao_social") if c in cols]
                if fields:
                    cur.execute(
                        f"""
                        SELECT {", ".join(fields)}
                        FROM enriched_entities
                        WHERE left(regexp_replace({cnpj_col}, '\\D', '', 'g'), 8) = %s
                        LIMIT 1
                        """,
                        (raiz,),
                    )
                    row = cur.fetchone()
                    if row:
                        cnae = row.get("cnae_principal") or row.get("cnae")
                        fantasia = row.get("nome_fantasia")
                        return (
                            str(cnae) if cnae else None,
                            [],
                            str(fantasia) if fantasia else None,
                        )
    return None, [], None


def company_input_from_dict(data: dict[str, Any]) -> CompanyInput:
    """Build CompanyInput from a synthetic/test dict (no DB)."""
    raiz = digits_only(data.get("cnpj_raiz") or data.get("cnpj14") or "")[:8]
    contracts = data.get("contracts") or []
    if not isinstance(contracts, list):
        contracts = []
    consortium = any(is_consortium_contract(c) for c in contracts if isinstance(c, dict))
    ce = data.get("construction_evidence")
    if not isinstance(ce, dict):
        assessed = assess_construction(
            razao_social=data.get("razao_social"),
            nome_fantasia=data.get("nome_fantasia"),
            contracts=contracts,
            cnae_principal=data.get("cnae_principal"),
            cnaes_secundarios=list(data.get("cnaes_secundarios") or []),
        )
        ce = assessed.as_dict()
        sector = assessed.sector_fit
        activity = assessed.activity_class
    else:
        sector = ce.get("sector_fit") or data.get("sector_fit")
        activity = ce.get("activity_class") or data.get("activity_class")
    return CompanyInput(
        company_key=data.get("company_key") or company_key_from_raiz(raiz),
        cnpj_raiz=raiz,
        razao_social=data.get("razao_social"),
        nome_fantasia=data.get("nome_fantasia"),
        cnae_principal=data.get("cnae_principal"),
        cnaes_secundarios=list(data.get("cnaes_secundarios") or []),
        contracts=contracts,
        sector_fit=sector,
        activity_class=activity,
        construction_evidence=ce,
        is_consortium_member=consortium,
        source_watermark=str(data.get("source_watermark") or ""),
    )
