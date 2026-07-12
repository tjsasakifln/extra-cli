"""Cross-source deduplication for bidding opportunities.

Conservative 4-level strategy:
1. Official ID match (numero_controle_pncp)
2. Same source + same source_id
3. orgão CNPJ + processo number + edital number
4. Content hash collision (primary dedup — handled at DB level)

NEVER merges on textual similarity alone.
Preserves source attribution and field-level provenance.
"""

from __future__ import annotations

import hashlib
from typing import Any

from scripts.opportunity_intel.models import OpportunityRecord

# ---------------------------------------------------------------------------
# Dedup key generation
# ---------------------------------------------------------------------------


def compute_content_hash(record: dict[str, Any]) -> str:
    """Deterministic MD5 hash for dedup across fields.

    Uses fields that uniquely identify a bidding opportunity
    regardless of source.

    Args:
        record: Normalized record dict with at least:
            source, source_id, objeto, orgao_cnpj, modalidade.

    Returns:
        32-character MD5 hex digest.
    """
    key_fields = [
        str(record.get("source", "")),
        str(record.get("source_id", "")),
        str(record.get("orgao_cnpj", "")),
        str(record.get("numero_edital", "")),
        str(record.get("numero_processo", "")),
        str(record.get("objeto", "")),
        str(record.get("modalidade", "")),
    ]
    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8"), usedforsecurity=False).hexdigest()


def compute_dedup_keys(record: OpportunityRecord) -> dict[str, str | None]:
    """Generate all dedup keys for a normalized record.

    Args:
        record: Normalized OpportunityRecord.

    Returns:
        Dict with keys: content_hash, pncp_id, source_compound, org_processo_edital.
    """
    content_hash = compute_content_hash(record.to_db_dict())

    # Level 1: PNCP official ID
    pncp_id = record.numero_controle_pncp

    # Level 2: Source + source_id
    source_compound = f"{record.source}:{record.source_id}" if record.source_id else None

    # Level 3: órgão CNPJ + processo + edital
    org_processo_edital = None
    if record.orgao_cnpj and record.numero_processo and record.numero_edital:
        org_processo_edital = f"{record.orgao_cnpj}|{record.numero_processo}|{record.numero_edital}"

    return {
        "content_hash": content_hash,
        "pncp_id": pncp_id,
        "source_compound": source_compound,
        "org_processo_edital": org_processo_edital,
    }


def find_duplicate(
    record: OpportunityRecord,
    existing_records: list[OpportunityRecord],
) -> OpportunityRecord | None:
    """Check if record duplicates any existing record.

    Conservative: only returns match on exact key collision.
    Does NOT use fuzzy/text similarity.

    Args:
        record: Candidate record to check.
        existing_records: Already-persisted records to check against.

    Returns:
        Matching record if duplicate found, None otherwise.
    """
    keys = compute_dedup_keys(record)

    for existing in existing_records:
        existing_keys = compute_dedup_keys(existing)

        # Level 1: PNCP ID match
        if keys["pncp_id"] and existing_keys["pncp_id"]:
            if keys["pncp_id"] == existing_keys["pncp_id"]:
                return existing

        # Level 2: Same source + source_id
        if keys["source_compound"] and existing_keys["source_compound"]:
            if keys["source_compound"] == existing_keys["source_compound"]:
                return existing

        # Level 3: órgão + processo + edital
        if keys["org_processo_edital"] and existing_keys["org_processo_edital"]:
            if keys["org_processo_edital"] == existing_keys["org_processo_edital"]:
                return existing

        # Level 4: Content hash
        if keys["content_hash"] == existing_keys["content_hash"]:
            return existing

    return None


def merge_sources(
    primary: OpportunityRecord,
    secondary: OpportunityRecord,
) -> OpportunityRecord:
    """Merge two records representing the same opportunity from different sources.

    Primary source data takes precedence. Secondary data fills gaps.
    Provenance is updated to show which source provided each field.

    Args:
        primary: Already-persisted record (keeps its content_hash).
        secondary: New record from another source.

    Returns:
        Merged record with combined data and updated provenance.
    """
    merged = OpportunityRecord(
        source=f"{primary.source}+{secondary.source}",
        source_id=primary.source_id,
        content_hash=primary.content_hash,
        numero_controle_pncp=primary.numero_controle_pncp or secondary.numero_controle_pncp,
        source_url=primary.source_url or secondary.source_url,
        orgao_cnpj=primary.orgao_cnpj or secondary.orgao_cnpj,
        orgao_nome=primary.orgao_nome or secondary.orgao_nome,
        ente_federativo=primary.ente_federativo or secondary.ente_federativo,
        uf=primary.uf or secondary.uf,
        municipio=primary.municipio or secondary.municipio,
        codigo_ibge=primary.codigo_ibge or secondary.codigo_ibge,
        numero_processo=primary.numero_processo or secondary.numero_processo,
        numero_edital=primary.numero_edital or secondary.numero_edital,
        modalidade=primary.modalidade or secondary.modalidade,
        modalidade_id=primary.modalidade_id or secondary.modalidade_id,
        objeto=primary.objeto or secondary.objeto,
        categoria=primary.categoria or secondary.categoria,
        valor_estimado=primary.valor_estimado or secondary.valor_estimado,
        valor_homologado=primary.valor_homologado or secondary.valor_homologado,
        valor_semantica=primary.valor_semantica or secondary.valor_semantica,
        data_publicacao=primary.data_publicacao or secondary.data_publicacao,
        data_abertura=primary.data_abertura or secondary.data_abertura,
        data_encerramento=primary.data_encerramento or secondary.data_encerramento,
        data_homologacao=primary.data_homologacao or secondary.data_homologacao,
        status_fonte=primary.status_fonte,
        status_canonico=primary.status_canonico,
        status_motivo=primary.status_motivo,
        status_data=primary.status_data,
        link_edital=primary.link_edital or secondary.link_edital,
        link_anexos=list(set((primary.link_anexos or []) + (secondary.link_anexos or []))),
        qualidade_score=max(primary.qualidade_score, secondary.qualidade_score),
        qualidade_fatores={**secondary.qualidade_fatores, **primary.qualidade_fatores},
        dados_ausentes=primary.dados_ausentes,
        ranking=primary.ranking,
        ranking_score=primary.ranking_score,
        ranking_fatores=primary.ranking_fatores,
        ranking_regras=primary.ranking_regras,
        ranking_confianca=primary.ranking_confianca,
        first_seen_at=primary.first_seen_at,
        last_seen_at=secondary.last_seen_at or primary.last_seen_at,
        proveniencia=_merge_proveniencia(primary.proveniencia, secondary.proveniencia),
    )
    return merged


def _merge_proveniencia(
    primary_prov: dict[str, str],
    secondary_prov: dict[str, str],
) -> dict[str, str]:
    """Merge provenance maps — primary wins on conflict."""
    merged = dict(secondary_prov)
    merged.update(primary_prov)
    return merged
