"""Record normalization from raw source data to OpportunityRecord.

Transforms raw JSON/dict from each source into the canonical
OpportunityRecord format. Each source has its own normalize_* function.

Design:
- Source-specific normalize functions handle field mapping
- Common normalize_record applies shared logic (dedup hash, status, ranking)
- All functions return OpportunityRecord — never partial dicts
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from scripts.crawl.common import parse_date, safe_float
from scripts.opportunity_intel.dedup import compute_content_hash
from scripts.opportunity_intel.models import OpportunityRecord
from scripts.opportunity_intel.ranking import compute_ranking
from scripts.opportunity_intel.status import compute_canonical_status

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source-specific: PNCP API
# ---------------------------------------------------------------------------


def normalize_pncp(raw: dict[str, Any]) -> OpportunityRecord:
    """Transform PNCP API contratacao → OpportunityRecord.

    PNCP API returns fields like:
    - numeroControlePNCP, orgaoCNPJ, orgaoRazaoSocial
    - objeto, valorTotalEstimado, modalidadeNome, modalidadeId
    - dataPublicacao, dataAbertura, dataEncerramento
    - situacaoCompra, linkSistemaOrigem
    - uf, municipio, codigoMunicipioIbge
    """
    source_id = raw.get("numeroControlePNCP", "") or str(raw.get("id", ""))
    orgao_raw = raw.get("orgaoEntidade")
    orgao: dict[str, Any] = orgao_raw if isinstance(orgao_raw, dict) else {}
    unidade_raw = raw.get("unidadeOrgao")
    unidade: dict[str, Any] = unidade_raw if isinstance(unidade_raw, dict) else {}
    orgao_cnpj = raw.get("orgaoCNPJ", "") or raw.get("orgaoCnpj", "") or orgao.get("cnpj", "")
    orgao_nome = raw.get("orgaoRazaoSocial", "") or raw.get("orgaoNome", "") or orgao.get("razaoSocial", "")
    objeto = raw.get("objeto", "") or raw.get("objetoCompra", "") or raw.get("descricaoObjeto", "")
    modalidade = raw.get("modalidadeNome", "")
    modalidade_id = raw.get("codigoModalidade", 0) or raw.get("modalidadeId", 0)
    if isinstance(modalidade_id, str) and modalidade_id.isdigit():
        modalidade_id = int(modalidade_id)
    # Never impute UF=SC: missing/blank stays unknown. Prefer nested unidadeOrgao
    # (PNCP API common shape: ufSigla / siglaUf) over invented territorial defaults.
    uf_raw = (
        raw.get("uf") or raw.get("UF") or unidade.get("ufSigla") or unidade.get("siglaUf") or unidade.get("uf") or ""
    )
    uf = str(uf_raw).strip().upper() if uf_raw else ""
    municipio = raw.get("municipio", "") or raw.get("nomeMunicipio", "") or unidade.get("municipioNome", "")
    codigo_ibge = raw.get("codigoMunicipioIbge", "") or raw.get("codigoIBGE", "") or unidade.get("codigoIbge", "")

    valor_estimado = safe_float(raw.get("valorTotalEstimado", raw.get("valorEstimado")))

    data_publicacao = _parse_dt(raw.get("dataPublicacao") or raw.get("dataPublicacaoPncp"))
    data_abertura = _parse_dt(raw.get("dataAbertura") or raw.get("dataAberturaProposta"))
    data_encerramento = _parse_dt(
        raw.get("dataEncerramento") or raw.get("dataEncerramentoProposta") or raw.get("dataFechamentoProposta")
    )

    status_fonte = raw.get("situacaoCompra", "") or raw.get("situacaoCompraNome", "") or raw.get("situacao", "")
    link_edital = raw.get("linkSistemaOrigem", "") or raw.get("urlSistemaOrigem", "")
    link_pncp = raw.get("linkPNCP", "") or raw.get("url", "")
    if not link_pncp and orgao_cnpj and raw.get("anoCompra") and raw.get("sequencialCompra"):
        link_pncp = (
            f"https://pncp.gov.br/app/editais/{orgao_cnpj}/{int(raw['anoCompra'])}/{int(raw['sequencialCompra'])}"
        )

    record = OpportunityRecord(
        source="pncp",
        source_id=source_id,
        content_hash="",  # computed below
        source_url=link_pncp or link_edital or None,
        numero_controle_pncp=source_id if source_id else None,
        orgao_cnpj=orgao_cnpj if orgao_cnpj else None,
        orgao_nome=orgao_nome if orgao_nome else None,
        ente_federativo=_infer_esfera(uf, orgao_cnpj),
        uf=uf,  # "" when unknown — never default SC for PNCP
        municipio=municipio if municipio else None,
        codigo_ibge=codigo_ibge if codigo_ibge else None,
        # Empty string is NOT NULL in Postgres and trips partial unique index
        # uq_oi_orgao_processo_edital (orgao, processo, edital) for multiple PNCP
        # controls that omit process number. Prefer NULL when absent.
        numero_processo=(
            (str(raw.get("numeroProcesso")).strip() or None) if raw.get("numeroProcesso") not in (None, "") else None
        ),
        numero_edital=(str(raw.get("numeroEdital") or raw.get("numeroCompra") or "").strip() or None),
        modalidade=modalidade if modalidade else None,
        modalidade_id=modalidade_id if modalidade_id else None,
        objeto=objeto,
        valor_estimado=valor_estimado,
        valor_semantica="valor_total_estimado_informado_pelo_pncp" if valor_estimado is not None else None,
        data_publicacao=data_publicacao,
        data_abertura=data_abertura,
        data_encerramento=data_encerramento,
        status_fonte=status_fonte if status_fonte else None,
        link_edital=link_edital if link_edital else None,
        proveniencia={
            "source": "pncp",
            "all_fields": "pncp_api",
            "status_evidence": str(raw.get("_qw01_status_evidence") or "source_and_dates"),
        },
    )

    # Compute content hash, status, and ranking
    record.content_hash = compute_content_hash(record.to_db_dict())
    record.status_canonico, record.status_motivo = compute_canonical_status(
        status_fonte=status_fonte,
        source="pncp",
        data_abertura=data_abertura,
        data_encerramento=data_encerramento,
        data_publicacao=data_publicacao,
        modalidade=modalidade,
    )
    if raw.get("_qw01_status_evidence") == "pncp_open_proposals_endpoint":
        record.status_canonico = "open"
        record.status_motivo = "Retornado pelo endpoint PNCP de propostas abertas"
    record.status_data = datetime.now(UTC)

    ranking = compute_ranking(
        status_canonico=record.status_canonico,
        orgao_cnpj=record.orgao_cnpj,
        objeto=record.objeto,
        valor_estimado=record.valor_estimado,
        modalidade=record.modalidade,
        data_abertura=record.data_abertura,
        data_encerramento=record.data_encerramento,
        data_publicacao=record.data_publicacao,
        uf=record.uf,
        municipio=record.municipio,
        link_edital=record.link_edital,
        link_anexos=record.link_anexos,
        has_match_entity=bool(orgao_cnpj),
        dentro_raio=(uf == "SC") if uf else False,
        fonte_confiavel=True,
    )
    record.ranking = ranking["ranking"]
    record.ranking_score = ranking["ranking_score"]
    record.ranking_fatores = ranking["ranking_fatores"]
    record.ranking_regras = ranking["ranking_regras"]
    record.ranking_confianca = ranking["ranking_confianca"]

    return record


# ---------------------------------------------------------------------------
# Source-specific: DOM-SC
# ---------------------------------------------------------------------------


def normalize_dom_sc(raw: dict[str, Any]) -> OpportunityRecord:
    """Transform DOM-SC publicacao → OpportunityRecord.

    DOM-SC list endpoint returns:
    - id (ato number), titulo, cod_categoria (1-28)
    - status, data_publicacao, url (PDF), url_web
    - entidade (municipio/orgao name)
    """
    ato_id = str(raw.get("id", ""))
    titulo = raw.get("titulo", "") or raw.get("Ato[titulo]", "")
    # DOM-SC category codes: 6=Contratos, 7=Convênios, 28=Empenhos
    # Licitações use specific category (via search filter, not stored here)
    status_fonte = raw.get("status", "")
    data_publicacao = _parse_dom_date(raw.get("data_publicacao", ""))
    url = raw.get("url", "") or raw.get("url_web", "")
    entidade = raw.get("entidade", "") or raw.get("nome_entidade", "")

    # Extract municipality from entidade name
    municipio = _extract_municipio_from_entidade(entidade)

    # Try to extract process/edital numbers from titulo
    numero_edital = _extract_edital_from_title(titulo)
    numero_processo = _extract_processo_from_title(titulo)

    record = OpportunityRecord(
        source="dom_sc",
        source_id=ato_id,
        content_hash="",
        source_url=url if url else None,
        orgao_nome=entidade if entidade else None,
        uf="SC",
        municipio=municipio,
        numero_edital=numero_edital,
        numero_processo=numero_processo,
        objeto=titulo if titulo else "Publicação DOM-SC",
        data_publicacao=data_publicacao,
        status_fonte=status_fonte if status_fonte else None,
        link_edital=url if url else None,
        proveniencia={"source": "dom_sc", "all_fields": "dom_sc_api"},
    )

    record.content_hash = compute_content_hash(record.to_db_dict())
    record.status_canonico, record.status_motivo = compute_canonical_status(
        status_fonte=status_fonte,
        source="dom_sc",
        data_publicacao=data_publicacao,
    )
    record.status_data = datetime.now(UTC)

    ranking = compute_ranking(
        status_canonico=record.status_canonico,
        orgao_cnpj=record.orgao_cnpj,
        objeto=record.objeto,
        valor_estimado=record.valor_estimado,
        modalidade=record.modalidade,
        data_abertura=record.data_abertura,
        data_encerramento=record.data_encerramento,
        data_publicacao=record.data_publicacao,
        uf=record.uf,
        municipio=record.municipio,
        link_edital=record.link_edital,
        link_anexos=record.link_anexos,
        fonte_confiavel=True,
    )
    record.ranking = ranking["ranking"]
    record.ranking_score = ranking["ranking_score"]
    record.ranking_fatores = ranking["ranking_fatores"]
    record.ranking_regras = ranking["ranking_regras"]
    record.ranking_confianca = ranking["ranking_confianca"]

    return record


# ---------------------------------------------------------------------------
# Generic: catch-all for unknown sources
# ---------------------------------------------------------------------------


def normalize_generic(raw: dict[str, Any], source: str = "unknown") -> OpportunityRecord:
    """Best-effort normalization from unknown source format.

    Uses heuristics to map common field names.
    """
    source_id = str(raw.get("id", raw.get("source_id", raw.get("identificador", ""))))
    objeto = raw.get("objeto", "") or raw.get("descricao", "") or raw.get("titulo", "") or raw.get("nome", "") or ""
    orgao_cnpj = raw.get("orgao_cnpj", "") or raw.get("cnpj", "") or raw.get("orgaoCNPJ", "")
    orgao_nome = raw.get("orgao_nome", "") or raw.get("nome_orgao", "") or raw.get("orgaoRazaoSocial", "")
    # Generic path: never invent SC. DOM-SC keeps SC only via normalize_dom_sc.
    uf_raw = raw.get("uf") or raw.get("UF") or ""
    uf = str(uf_raw).strip().upper() if uf_raw else ""
    municipio = raw.get("municipio", "") or raw.get("cidade", "") or raw.get("nomeMunicipio", "")
    valor_estimado = safe_float(raw.get("valor", raw.get("valor_estimado", raw.get("valorTotal"))))

    data_publicacao = _parse_dt(raw.get("data_publicacao", raw.get("dataPublicacao")))
    data_abertura = _parse_dt(raw.get("data_abertura", raw.get("dataAbertura")))
    data_encerramento = _parse_dt(raw.get("data_encerramento", raw.get("dataEncerramento")))

    status_fonte = raw.get("status", "") or raw.get("situacao", "")

    record = OpportunityRecord(
        source=source,
        source_id=source_id if source_id else "",
        content_hash="",
        source_url=raw.get("url", raw.get("link", "")),
        orgao_cnpj=orgao_cnpj if orgao_cnpj else None,
        orgao_nome=orgao_nome if orgao_nome else None,
        uf=uf,
        municipio=municipio if municipio else None,
        codigo_ibge=raw.get("codigo_ibge", raw.get("codigoIBGE", "")),
        numero_processo=raw.get("numero_processo", raw.get("processo", "")),
        numero_edital=raw.get("numero_edital", raw.get("edital", "")),
        modalidade=raw.get("modalidade", ""),
        objeto=objeto,
        valor_estimado=valor_estimado,
        valor_semantica="estimado" if valor_estimado else None,
        data_publicacao=data_publicacao,
        data_abertura=data_abertura,
        data_encerramento=data_encerramento,
        status_fonte=status_fonte if status_fonte else None,
        link_edital=raw.get("link_edital", raw.get("url", "")),
        proveniencia={"source": source, "all_fields": f"{source}_heuristic"},
    )

    record.content_hash = compute_content_hash(record.to_db_dict())
    record.status_canonico, record.status_motivo = compute_canonical_status(
        status_fonte=status_fonte,
        source=source,
        data_abertura=data_abertura,
        data_encerramento=data_encerramento,
        data_publicacao=data_publicacao,
    )
    record.status_data = datetime.now(UTC)

    ranking = compute_ranking(
        status_canonico=record.status_canonico,
        orgao_cnpj=record.orgao_cnpj,
        objeto=record.objeto,
        valor_estimado=record.valor_estimado,
        modalidade=record.modalidade,
        data_abertura=record.data_abertura,
        data_encerramento=record.data_encerramento,
        data_publicacao=record.data_publicacao,
        uf=record.uf,
        municipio=record.municipio,
        link_edital=record.link_edital,
        fonte_confiavel=False,
    )
    record.ranking = ranking["ranking"]
    record.ranking_score = ranking["ranking_score"]
    record.ranking_fatores = ranking["ranking_fatores"]
    record.ranking_regras = ranking["ranking_regras"]
    record.ranking_confianca = ranking["ranking_confianca"]

    return record


# ---------------------------------------------------------------------------
# Normalizer dispatch
# ---------------------------------------------------------------------------


def _normalize_named(raw: dict[str, Any], source: str) -> OpportunityRecord:
    """Keep the declared source name; never coerce non-PNCP rows to pncp."""
    record = normalize_generic(raw, source=source)
    if source != "pncp" and record.source == "pncp":
        raise ValueError(f"normalizer must not relabel {source} as pncp")
    return record


def normalize_sc_compras(raw: dict[str, Any]) -> OpportunityRecord:
    return _normalize_named(raw, "sc_compras")


def normalize_compras_gov(raw: dict[str, Any]) -> OpportunityRecord:
    return _normalize_named(raw, "compras_gov")


def normalize_pcp(raw: dict[str, Any]) -> OpportunityRecord:
    return _normalize_named(raw, "pcp")


def normalize_tce_sc(raw: dict[str, Any]) -> OpportunityRecord:
    return _normalize_named(raw, "tce_sc")


def normalize_doe_sc(raw: dict[str, Any]) -> OpportunityRecord:
    return _normalize_named(raw, "doe_sc")


def normalize_transparencia(raw: dict[str, Any]) -> OpportunityRecord:
    return _normalize_named(raw, "transparencia")


NORMALIZERS = {
    "pncp": normalize_pncp,
    "dom_sc": normalize_dom_sc,
    "sc_compras": normalize_sc_compras,
    "compras_gov": normalize_compras_gov,
    "pcp": normalize_pcp,
    "tce_sc": normalize_tce_sc,
    "doe_sc": normalize_doe_sc,
    "transparencia": normalize_transparencia,
}


def normalize_record(raw: dict[str, Any], source: str) -> OpportunityRecord:
    """Dispatch to source-specific normalizer or fall back to generic.

    Args:
        raw: Raw record dict from source.
        source: Source name (must match registry canonical name).

    Returns:
        Normalized OpportunityRecord.
    """
    normalizer = NORMALIZERS.get(source)
    if normalizer:
        try:
            return normalizer(raw)
        except Exception:
            _logger.warning(
                "Source-specific normalizer failed for %s, falling back to generic",
                source,
                exc_info=True,
            )
    return normalize_generic(raw, source)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_dt(val: Any) -> datetime | None:
    """Parse datetime from various formats. Returns timezone-aware datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val
    dt_str = parse_date(str(val))
    if dt_str:
        try:
            dt = datetime.fromisoformat(dt_str)
            return dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None
    return None


def _parse_dom_date(val: Any) -> datetime | None:
    """Parse DOM-SC date format (dd/mm/yyyy). Returns timezone-aware datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val
    from datetime import datetime as dt

    try:
        return dt.strptime(str(val).strip()[:10], "%d/%m/%Y").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return _parse_dt(val)


def _infer_esfera(uf: str, cnpj: str | None) -> str:
    """Infer governmental sphere from UF and CNPJ."""
    if not uf:
        return "desconhecida"
    if uf.upper() == "DF":
        return "distrital"
    if cnpj and len(cnpj) >= 8:
        # Federal CNPJs start with specific prefixes
        federal_prefixes = ("00", "01", "02", "03", "04")
        if cnpj[:2] in federal_prefixes:
            return "federal"
    # Municipal by default for SC within 200km target
    return "municipal"


def _extract_municipio_from_entidade(entidade: str) -> str | None:
    """Extract municipality name from DOM-SC entidade string.

    Examples:
        "Prefeitura Municipal de Santo Amaro da Imperatriz" → "Santo Amaro da Imperatriz"
        "Câmara de Vereadores de Itá" → "Itá"
        "CISAMA - Consórcio Intermunicipal Serra Catarinense" → None
    """
    import re

    if not entidade:
        return None

    patterns = [
        r"(?:Prefeitura|Câmara|Camara)\s+(?:Municipal\s+)?(?:de\s+)?(.+?)(?:\s*[-–]\s*.+)?$",
        r"Município\s+de\s+(.+)",
        r"Governo\s+(?:do\s+)?(?:Município|Municipio)\s+de\s+(.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, entidade, re.IGNORECASE)
        if match:
            municipio = match.group(1).strip()
            if municipio and len(municipio) > 2:
                return municipio

    return None


def _extract_edital_from_title(titulo: str) -> str | None:
    """Extract edital number from DOM-SC publication title."""
    import re

    patterns = [
        r"(?:edital|EDITAL)\s*(?:de\s*)?(?:licitação|licitacao)?\s*(?:n[º°]?\s*)?(\d+[\d/]*\d+)",
        r"(?:pregão|PREGAO|PREGÃO)\s*(?:eletrônico|eletronico|ELETRÔNICO|ELETRONICO)?\s*(?:n[º°]?\s*)?(\d+[\d/]*\d+)",
        r"(?:concorrência|concorrencia|CONCORRÊNCIA|CONCORRENCIA)\s*(?:n[º°]?\s*)?(\d+[\d/]*\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, titulo, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_processo_from_title(titulo: str) -> str | None:
    """Extract processo number from DOM-SC publication title."""
    import re

    patterns = [
        r"(?:processo|PROCESSO)\s*(?:administrativo|ADMINISTRATIVO)?\s*(?:n[º°]?\s*)?(\d+[\d/]*\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, titulo)
        if match:
            return match.group(1).strip()

    return None
