"""Deterministic recortes: typology, regime, geography, period, value semantic."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from scripts.contract_comparables.constants import (
    AMBIGUOUS_TYPOLOGY_KEYWORDS,
    NON_PAVING_KEYWORDS,
    PAVING_KEYWORDS,
    REGIME_GLOBAL,
    REGIME_UNITARIO,
    REGION_BY_UF,
    UNIT_CANONICAL,
    UNIT_KM_ALIASES,
    UNIT_M2_ALIASES,
    UNIT_TOTAL_ALIASES,
    VALUE_SEMANTIC_ALIASES,
)
from scripts.contract_comparables.models import ContractRecord, Recorte, RectificationEvent


def fold_text(value: str | None) -> str:
    if value is None:
        return ""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(character for character in nfkd if not unicodedata.combining(character))


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "" or value == "UNKNOWN":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_year(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        if 1990 <= year <= 2100:
            return year
    return None


def classify_typology(objeto: str) -> tuple[str, float, str]:
    folded = fold_text(objeto)
    paving = any(token in folded for token in PAVING_KEYWORDS)
    non_paving = any(token in folded for token in NON_PAVING_KEYWORDS)
    ambiguous = any(token in folded for token in AMBIGUOUS_TYPOLOGY_KEYWORDS)
    if paving and non_paving:
        return "mixed", 0.40, "mixed_paving_and_building"
    if paving:
        return "pavimentacao", 0.95, "paving_works"
    if non_paving:
        return "nao_pavimentacao", 0.90, "non_paving"
    if ambiguous:
        return "ambiguo", 0.45, "ambiguous_roadworks"
    return "desconhecido", 0.10, "unclassified"


def classify_regime(raw: str | None) -> str:
    folded = fold_text(raw)
    if not folded or folded == "unknown":
        return "unknown"
    if folded in REGIME_GLOBAL:
        return "empreitada_global"
    if folded in REGIME_UNITARIO:
        return "empreitada_unitaria"
    return folded.replace(" ", "_")


def classify_unit(raw: str | None, *, quantity: Decimal | None) -> str:
    folded = fold_text(raw)
    if not folded or folded == "unknown":
        return UNIT_CANONICAL if quantity is None else "unknown"
    if folded in UNIT_TOTAL_ALIASES:
        return UNIT_CANONICAL
    if folded in UNIT_KM_ALIASES:
        return "km"
    if folded in UNIT_M2_ALIASES:
        return "m2"
    return folded.replace(" ", "_")


def classify_value_semantic(raw: str | None) -> str:
    folded = fold_text(raw)
    if not folded:
        return "unknown"
    return VALUE_SEMANTIC_ALIASES.get(folded, folded.replace(" ", "_"))


def classify_value_basis(raw: str | None) -> str:
    folded = fold_text(raw)
    if folded in {"original", "instrumento", "assinado"}:
        return "original"
    if folded in {"atualizado", "reajustado", "aditado"}:
        return "atualizado"
    if not folded:
        return "unknown"
    return folded


def classify_porte(raw: str | None, valor: Decimal | None) -> str:
    folded = fold_text(raw)
    if folded in {"pequeno", "medio", "grande"}:
        return folded
    if valor is None:
        return "unknown"
    if valor < Decimal("500000"):
        return "pequeno"
    if valor <= Decimal("5000000"):
        return "medio"
    return "grande"


def record_from_mapping(raw: dict[str, Any]) -> ContractRecord:
    valor_raw = raw.get("valor")
    unknown = bool(raw.get("valor_is_unknown")) or valor_raw in {"UNKNOWN", "unknown"}
    valor = None if unknown else parse_decimal(valor_raw)
    if valor_raw is None and raw.get("valor_is_unknown") is not False:
        unknown = True
    year = raw.get("year")
    if year is None:
        year = parse_year(raw.get("data_referencia") or raw.get("data_inicio") or raw.get("data_publicacao"))
    return ContractRecord(
        contract_id=str(raw["contract_id"]),
        objeto=str(raw.get("objeto") or ""),
        valor=valor,
        valor_is_unknown=unknown or valor is None,
        valor_semantic=str(raw.get("valor_semantic") or "unknown"),
        value_basis=str(raw.get("value_basis") or "unknown"),
        unidade=raw.get("unidade"),
        quantidade=parse_decimal(raw.get("quantidade")),
        uf=(str(raw["uf"]).upper() if raw.get("uf") else None),
        municipio=raw.get("municipio"),
        regime=raw.get("regime"),
        modalidade=raw.get("modalidade"),
        porte=raw.get("porte"),
        data_referencia=raw.get("data_referencia") or raw.get("data_publicacao"),
        year=int(year) if year is not None else None,
        revision=int(raw.get("revision") or 1),
        superseded_by=raw.get("superseded_by"),
        evidence_ref=raw.get("evidence_ref"),
        source=str(raw.get("source") or "fixture"),
        orgao_id=raw.get("orgao_id") or raw.get("orgao_cnpj"),
        orgao_nome=raw.get("orgao_nome"),
        fornecedor_id=raw.get("fornecedor_id") or raw.get("fornecedor_cnpj"),
        fornecedor_nome=raw.get("fornecedor_nome"),
        extra={key: value for key, value in raw.items() if key.startswith("extra_")},
    )


def recorte_from_record(record: ContractRecord) -> Recorte:
    typology, confidence, scope = classify_typology(record.objeto)
    unknown: list[str] = []
    regime = classify_regime(record.regime)
    if regime == "unknown":
        unknown.append("regime")
    unit = classify_unit(record.unidade, quantity=record.quantidade)
    if unit == "unknown":
        unknown.append("unidade")
    semantic = classify_value_semantic(record.valor_semantic)
    if semantic == "unknown":
        unknown.append("valor_semantic")
    basis = classify_value_basis(record.value_basis)
    if basis == "unknown":
        unknown.append("value_basis")
    if record.valor_is_unknown or record.valor is None:
        unknown.append("valor")
    uf = record.uf.upper() if record.uf else None
    if uf is None:
        unknown.append("uf")
    year = record.year
    if year is None:
        unknown.append("year")
    return Recorte(
        contract=record,
        typology=typology,
        typology_confidence=confidence,
        scope=scope,
        regime=regime,
        unit=unit,
        value_semantic=semantic,
        value_basis=basis,
        uf=uf,
        region=REGION_BY_UF.get(uf) if uf else None,
        year=year,
        porte=classify_porte(record.porte, record.valor),
        modalidade=fold_text(record.modalidade).replace(" ", "_") if record.modalidade else "unknown",
        unknown_fields=tuple(unknown),
    )


def collapse_revisions(records: tuple[ContractRecord, ...]) -> tuple[ContractRecord, tuple[str, ...]]:
    """Keep the highest revision per contract_id. Flag unresolved duplicates."""
    grouped: dict[str, list[ContractRecord]] = {}
    for record in records:
        grouped.setdefault(record.contract_id, []).append(record)
    kept: list[ContractRecord] = []
    flags: list[str] = []
    for contract_id, versions in grouped.items():
        ordered = tuple(sorted(versions, key=lambda item: (item.revision, item.data_referencia or "")))
        revisions = {item.revision for item in ordered}
        if len(ordered) > 1 and len(revisions) == 1:
            values = {item.valor for item in ordered}
            if len(values) > 1:
                flags.append(contract_id)
                continue
        latest = ordered[-1]
        if latest.superseded_by:
            flags.append(contract_id)
            continue
        kept.append(latest)
    kept_sorted = tuple(sorted(kept, key=lambda item: item.contract_id))
    return kept_sorted, tuple(sorted(set(flags)))


def apply_rectification(
    records: tuple[ContractRecord, ...],
    event: RectificationEvent,
) -> tuple[ContractRecord, ...]:
    updated: list[ContractRecord] = []
    for record in records:
        if record.contract_id != event.contract_id:
            updated.append(record)
            continue
        payload = {
            "contract_id": record.contract_id,
            "objeto": event.fields.get("objeto", record.objeto),
            "valor": event.fields.get("valor", record.valor),
            "valor_is_unknown": event.fields.get("valor_is_unknown", record.valor_is_unknown),
            "valor_semantic": event.fields.get("valor_semantic", record.valor_semantic),
            "value_basis": event.fields.get("value_basis", record.value_basis),
            "unidade": event.fields.get("unidade", record.unidade),
            "quantidade": event.fields.get("quantidade", record.quantidade),
            "uf": event.fields.get("uf", record.uf),
            "municipio": event.fields.get("municipio", record.municipio),
            "regime": event.fields.get("regime", record.regime),
            "modalidade": event.fields.get("modalidade", record.modalidade),
            "porte": event.fields.get("porte", record.porte),
            "data_referencia": event.fields.get("data_referencia", record.data_referencia),
            "year": event.fields.get("year", record.year),
            "revision": int(event.fields.get("revision", record.revision + 1)),
            "superseded_by": event.fields.get("superseded_by", record.superseded_by),
            "evidence_ref": event.fields.get("evidence_ref", record.evidence_ref),
            "source": record.source,
            "orgao_id": record.orgao_id,
            "orgao_nome": record.orgao_nome,
            "fornecedor_id": record.fornecedor_id,
            "fornecedor_nome": record.fornecedor_nome,
        }
        updated.append(record_from_mapping(payload))
    return tuple(updated)


def records_from_mappings(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> tuple[ContractRecord, ...]:
    return tuple(record_from_mapping(row) for row in rows)
