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
    orgao_cnpj = raw.get("orgaoCNPJ", "") or raw.get("orgaoCnpj", "")
    orgao_nome = raw.get("orgaoRazaoSocial", "") or raw.get("orgaoNome", "")
    objeto = raw.get("objeto", "") or raw.get("descricaoObjeto", "")
    modalidade = raw.get("modalidadeNome", "")
    modalidade_id = raw.get("codigoModalidade", 0)
    if isinstance(modalidade_id, str) and modalidade_id.isdigit():
        modalidade_id = int(modalidade_id)
    uf = raw.get("uf", "SC") or "SC"
    municipio = raw.get("municipio", "") or raw.get("nomeMunicipio", "")
    codigo_ibge = raw.get("codigoMunicipioIbge", "") or raw.get("codigoIBGE", "")

    valor_estimado = safe_float(raw.get("valorTotalEstimado", raw.get("valorEstimado")))

    data_publicacao = _parse_dt(raw.get("dataPublicacao") or raw.get("dataPublicacaoPncp"))
    data_abertura = _parse_dt(raw.get("dataAbertura") or raw.get("dataAberturaProposta"))
    data_encerramento = _parse_dt(raw.get("dataEncerramento") or raw.get("dataFechamentoProposta"))

    status_fonte = raw.get("situacaoCompra", "") or raw.get("situacao", "")
    link_edital = raw.get("linkSistemaOrigem", "") or raw.get("urlSistemaOrigem", "")
    link_pncp = raw.get("linkPNCP", "") or raw.get("url", "")

    record = OpportunityRecord(
        source="pncp",
        source_id=source_id,
        content_hash="",  # computed below
        source_url=link_pncp or link_edital or None,
        numero_controle_pncp=source_id if source_id else None,
        orgao_cnpj=orgao_cnpj if orgao_cnpj else None,
        orgao_nome=orgao_nome if orgao_nome else None,
        ente_federativo=_infer_esfera(uf, orgao_cnpj),
        uf=uf,
        municipio=municipio if municipio else None,
        codigo_ibge=codigo_ibge if codigo_ibge else None,
        numero_processo=raw.get("numeroProcesso", ""),
        numero_edital=raw.get("numeroEdital", ""),
        modalidade=modalidade if modalidade else None,
        modalidade_id=modalidade_id if modalidade_id else None,
        objeto=objeto,
        valor_estimado=valor_estimado,
        valor_semantica="estimado" if valor_estimado else None,
        data_publicacao=data_publicacao,
        data_abertura=data_abertura,
        data_encerramento=data_encerramento,
        status_fonte=status_fonte if status_fonte else None,
        link_edital=link_edital if link_edital else None,
        proveniencia={"source": "pncp", "all_fields": "pncp_api"},
    )

    # Compute content hash, status, and ranking
    record.content_hash = compute_content_hash(record.to_db_dict())
    record.status_canonico, record.status_motivo = compute_canonical_status(
        status_fonte=status_fonte,
        source="pncp",
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
        link_anexos=record.link_anexos,
        has_match_entity=bool(orgao_cnpj),
        dentro_raio=(uf == "SC"),
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
    uf = raw.get("uf", raw.get("UF", "SC")) or "SC"
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

NORMALIZERS = {
    "pncp": normalize_pncp,
    "dom_sc": normalize_dom_sc,
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
