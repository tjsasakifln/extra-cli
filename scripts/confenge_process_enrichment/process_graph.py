"""Build confenge.public_process_graph.v1 from datalake / PNCP contract rows."""

from __future__ import annotations

import os
from typing import Any

from scripts.confenge_process_enrichment.identifiers import (
    digits_only,
    normalize_cnpj,
    normalize_pncp_control,
    normalize_process_number,
)
from scripts.confenge_process_enrichment.models import (
    ContractNode,
    ProvenanceEdge,
    PublicProcessGraph,
    _now_iso,
)


def contract_node_from_row(row: dict[str, Any], *, supplier_cnpj: str | None = None) -> ContractNode:
    """Map heterogeneous contract dicts into a ContractNode."""
    supplier = normalize_cnpj(
        supplier_cnpj
        or row.get("supplier_cnpj")
        or row.get("fornecedor_cnpj")
        or row.get("ni_fornecedor")
        or row.get("niFornecedor")
    )
    orgao = normalize_cnpj(
        row.get("orgao_cnpj")
        or row.get("contracting_authority_cnpj")
        or (row.get("orgaoEntidade") or {}).get("cnpj")
    )
    orgao_name = (
        row.get("orgao_nome")
        or row.get("orgao_razao_social")
        or row.get("contracting_authority_name")
        or (row.get("orgaoEntidade") or {}).get("razaoSocial")
    )
    # Prefer compra control (richer document packs) over contract control number.
    pncp = normalize_pncp_control(
        row.get("numero_controle_pncp_compra")
        or row.get("numeroControlePncpCompra")
        or row.get("numero_controle_pncp")
        or row.get("numeroControlePNCP")
        or row.get("pncp_control_number")
    )
    # Keep raw compra key even when also storing contract control elsewhere
    if not row.get("numeroControlePncpCompra") and row.get("numero_controle_pncp_compra"):
        row = {**row, "numeroControlePncpCompra": row.get("numero_controle_pncp_compra")}
    year = row.get("ano_contrato") or row.get("ano") or row.get("anoCompra") or row.get("year")
    seq = (
        row.get("sequencial_contrato")
        or row.get("sequencial")
        or row.get("sequencialCompra")
        or row.get("sequential")
    )
    try:
        year_i = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_i = None
    try:
        seq_i = int(seq) if seq is not None else None
    except (TypeError, ValueError):
        seq_i = None

    process = normalize_process_number(
        row.get("processo")
        or row.get("administrative_process_number")
        or row.get("numero_processo")
        or row.get("process_number")
    )
    # Keep original process string if normalization only reformats
    process_raw = row.get("processo") or row.get("numero_processo") or process

    contract_number = (
        row.get("numero_contrato_empenho")
        or row.get("contract_number")
        or row.get("numeroContratoEmpenho")
        or row.get("numero_contrato")
    )
    contract_id = (
        row.get("contrato_id")
        or row.get("contract_id")
        or (f"{orgao}|{year_i}|{seq_i}" if orgao and year_i is not None and seq_i is not None else None)
        or pncp
        or f"{supplier}|{contract_number or 'unknown'}"
    )

    edges: list[ProvenanceEdge] = []
    if pncp:
        edges.append(
            ProvenanceEdge(
                source="pncp",
                source_identifier=pncp,
                source_url=row.get("source_url"),
                confidence=1.0,
                join_method="numeroControlePNCP",
                notes="Deterministic PNCP control identifier",
            )
        )
    if process:
        edges.append(
            ProvenanceEdge(
                source=str(row.get("source") or "contract_record"),
                source_identifier=str(process_raw),
                confidence=0.9 if process else 0.5,
                join_method="process_number",
                notes="Administrative process number from contract metadata",
            )
        )

    uf = row.get("uf") or row.get("unidade_uf") or (row.get("unidadeOrgao") or {}).get("ufSigla")
    municipio = (
        row.get("municipio")
        or row.get("unidade_municipio")
        or (row.get("unidadeOrgao") or {}).get("municipioNome")
    )
    valor = row.get("valor_global") or row.get("valorGlobal") or row.get("value_global")
    try:
        valor_f = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        valor_f = None

    return ContractNode(
        contract_id=str(contract_id),
        supplier_cnpj=supplier,
        contracting_authority_cnpj=orgao or None,
        contracting_authority_name=str(orgao_name) if orgao_name else None,
        pncp_control_number=pncp,
        contract_number=str(contract_number) if contract_number else None,
        administrative_process_number=str(process_raw) if process_raw else process,
        year=year_i,
        sequential=seq_i,
        uf=str(uf) if uf else None,
        municipality=str(municipio) if municipio else None,
        object_summary=(row.get("objeto_contrato") or row.get("objeto") or row.get("informacao_complementar") or None),
        signed_at=str(row.get("data_assinatura") or row.get("dataAssinatura") or "")[:10] or None,
        vigency_end=str(row.get("data_vigencia_fim") or row.get("dataVigenciaFim") or "")[:10] or None,
        value_global=valor_f,
        originating_procurement_id=pncp or row.get("originating_procurement_id"),
        edges=edges,
        raw_keys={
            k: row.get(k)
            for k in (
                "numeroControlePNCP",
                "numeroControlePncpCompra",
                "numero_controle_pncp_compra",
                "numero_controle_pncp",
                "processo",
                "niFornecedor",
                "anoContrato",
                "sequencialContrato",
            )
            if row.get(k) is not None
        },
    )


def build_process_graph(
    *,
    account_cnpj: str,
    contracts: list[dict[str, Any]],
    razao_social: str | None = None,
) -> PublicProcessGraph:
    cnpj = normalize_cnpj(account_cnpj)
    nodes: list[ContractNode] = []
    seen: set[str] = set()
    limitations: list[str] = []
    for row in contracts:
        node = contract_node_from_row(row, supplier_cnpj=cnpj)
        if node.contract_id in seen:
            continue
        seen.add(node.contract_id)
        nodes.append(node)
    if not nodes:
        limitations.append("no_contracts_for_account")
    if nodes and not any(n.administrative_process_number for n in nodes):
        limitations.append("no_process_number_on_contracts")
    if nodes and not any(n.pncp_control_number for n in nodes):
        limitations.append("no_pncp_control_on_contracts")
    return PublicProcessGraph(
        account_cnpj=cnpj,
        razao_social=razao_social,
        contracts=nodes,
        built_at=_now_iso(),
        limitations=limitations,
    )


def load_contracts_for_supplier(
    cnpj14: str,
    *,
    dsn: str | None = None,
    limit: int = 50,
    inline_contracts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Load supplier contracts from inline list or pncp_supplier_contracts table."""
    if inline_contracts is not None:
        cnpj = normalize_cnpj(cnpj14)
        out = []
        for row in inline_contracts:
            rc = normalize_cnpj(
                row.get("supplier_cnpj")
                or row.get("fornecedor_cnpj")
                or row.get("ni_fornecedor")
                or row.get("niFornecedor")
            )
            if not rc or rc == cnpj or rc[:8] == cnpj[:8]:
                out.append(row)
        return out[:limit]

    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        return []
    cnpj = normalize_cnpj(cnpj14)
    if len(cnpj) < 8:
        return []

    try:
        import psycopg
    except ImportError:
        try:
            import psycopg2 as psycopg  # type: ignore
        except ImportError:
            return []

    sql_candidates = [
        """
        SELECT ni_fornecedor AS fornecedor_cnpj, nome_fornecedor,
               orgao_cnpj, orgao_nome, uf, municipio,
               valor_global, data_assinatura, objeto_contrato,
               numero_controle_pncp, processo, numero_processo,
               ano_contrato, sequencial_contrato, numero_contrato_empenho,
               data_vigencia_fim
        FROM pncp_supplier_contracts
        WHERE regexp_replace(ni_fornecedor, '\\D', '', 'g') = %s
          AND COALESCE(is_active, true) = true
        ORDER BY data_assinatura DESC NULLS LAST
        LIMIT %s
        """,
        """
        SELECT fornecedor_cnpj, orgao_cnpj, orgao_razao_social AS orgao_nome,
               unidade_uf AS uf, unidade_municipio AS municipio,
               valor_global, data_assinatura, informacao_complementar AS objeto_contrato,
               numero_controle_pncp_compra AS numero_controle_pncp, processo,
               ano_contrato, sequencial_contrato, numero_contrato_empenho,
               data_vigencia_fim
        FROM supplier_contracts
        WHERE regexp_replace(fornecedor_cnpj, '\\D', '', 'g') = %s
        ORDER BY data_assinatura DESC NULLS LAST
        LIMIT %s
        """,
    ]
    try:
        conn = psycopg.connect(dsn)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return []
    try:
        with conn.cursor() as cur:
            for sql in sql_candidates:
                try:
                    cur.execute(sql, (cnpj, limit))
                    cols = [d[0] for d in cur.description] if cur.description else []
                    rows = [dict(zip(cols, r, strict=False)) for r in (cur.fetchall() or [])]
                    if rows:
                        return rows
                except Exception:  # noqa: BLE001
                    try:
                        conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    continue
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return []


def graph_has_traceable_process(graph: PublicProcessGraph) -> bool:
    return any(
        c.administrative_process_number or (c.contracting_authority_cnpj and c.year and c.sequential)
        for c in graph.contracts
    )
