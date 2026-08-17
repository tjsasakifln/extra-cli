"""Deterministic extractors. No LLM. Heuristics record rule, version and confidence."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from scripts.official_contract_semantics.constants import (
    EXTRACTOR_VERSION,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_PARSER_ERROR,
    SCHEMA_VERSION,
    SOURCE_KINDS,
    VALUE_SEMANTICS,
)
from scripts.official_contract_semantics.identity import (
    clip_excerpt,
    normalize_cnpj,
    observation_id_for,
    raw_record_hash_for,
)
from scripts.official_contract_semantics.models import (
    DocumentError,
    ExtractionRejection,
    ExtractResult,
    OfficialContractObservation,
    SourceUnavailability,
)
from scripts.official_contract_semantics.validate import ObservationValidationError, validate_mapping

VALUE_FIELD_TO_SEMANTIC = {
    "valor_estimado": "valor_estimado",
    "valor_total_estimado": "valor_estimado",
    "estimated_value": "valor_estimado",
    "valor_homologado": "valor_homologado",
    "valor_adjudicado": "valor_homologado",
    "awarded_value": "valor_homologado",
    "valor_contratado": "valor_contratado",
    "valor_assinado": "valor_contratado",
    "valor_unitario": "valor_unitario",
    "preco_unitario": "valor_unitario",
    "valor_global": "valor_global",
    "valor_mensal": "valor_mensal",
    "valor_anual": "valor_anual",
    "valor_medido": "valor_medido",
    "valor_pago": "valor_pago",
    "valor_saldo": "valor_saldo",
    "valor_integral_nominal": "valor_integral_nominal",
}

SEMANTIC_ALIASES = {
    "estimado": "valor_estimado",
    "estimativa": "valor_estimado",
    "homologado": "valor_homologado",
    "adjudicado": "valor_homologado",
    "contratado": "valor_contratado",
    "assinado": "valor_contratado",
    "unitario": "valor_unitario",
    "unitário": "valor_unitario",
    "global": "valor_global",
    "mensal": "valor_mensal",
    "anual": "valor_anual",
    "medido": "valor_medido",
    "pago": "valor_pago",
    "saldo": "valor_saldo",
    "integral_nominal": "valor_integral_nominal",
    "valor_integral_nominal": "valor_integral_nominal",
}

UNIT_FIELD_KEYS = ("unit", "unidade", "unidade_medida")
QUANTITY_FIELD_KEYS = ("quantity", "quantidade", "qtd")
REGIME_FIELD_KEYS = ("execution_regime", "regime", "regime_execucao")
MODALITY_FIELD_KEYS = ("procurement_modality", "modalidade", "modalidade_licitacao")
PERIOD_START_KEYS = ("period_start", "data_inicio", "vigencia_inicio", "start_at")
PERIOD_END_KEYS = ("period_end", "data_fim", "vigencia_fim", "end_at")

_LABEL_UNIT = re.compile(r"unidade(?:\s+de\s+medida)?\s*[:\-]\s*([A-Za-z0-9²³/.]+)", re.I)
_LABEL_QTY = re.compile(r"quantidade\s*[:\-]\s*([\d.,]+)", re.I)
_LABEL_REGIME = re.compile(r"regime(?:\s+de\s+execu[cç][aã]o)?\s*[:\-]\s*([^\n;|]+)", re.I)
_LABEL_MODALITY = re.compile(r"modalidade\s*[:\-]\s*([^\n;|]+)", re.I)
_LABEL_VALUE = re.compile(
    r"valor\s+(estimado|homologado|adjudicado|contratado|assinado|unit[aá]rio|global|mensal|anual|medido|pago|saldo|integral\s+nominal)\s*[:\-]\s*(?:R\$\s*)?([\d.,]+)",
    re.I,
)
_LABEL_BARE_VALUE = re.compile(r"valor\s*[:\-]\s*(?:R\$\s*)?([\d.,]+)", re.I)
_LABEL_PERIOD = re.compile(
    r"vig[eê]ncia\s*[:\-]\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\s*(?:a|at[eé]|–|-)\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
    re.I,
)
_LABEL_AMENDMENT_VALUE = re.compile(r"aditivo\s+de\s+valor\s*[:\-]\s*(?:R\$\s*)?([\d.,]+)", re.I)
_LABEL_AMENDMENT_TERM = re.compile(r"aditivo\s+de\s+prazo\s*[:\-]\s*([^\n;|]+)", re.I)


def _first(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw and raw[key] not in {None, ""}:
            return raw[key]
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    found = str(value).strip()
    return found or None


def _normalize_date(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
        day, month, year = text.split("/")
        return f"{year}-{month}-{day}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text[:10] or ""):
        return text[:10]
    if "T" in text and len(text) >= 10:
        return text
    return text


def _map_semantic(raw: str | None) -> str | None:
    if not raw:
        return None
    folded = raw.strip().casefold().replace(" ", "_")
    if folded in VALUE_SEMANTICS:
        return folded
    return SEMANTIC_ALIASES.get(folded) or VALUE_FIELD_TO_SEMANTIC.get(folded)


def _source_kind(raw: dict[str, Any]) -> str:
    explicit = _text(raw.get("source_kind"))
    if explicit in SOURCE_KINDS:
        return explicit
    kind = (_text(raw.get("document_type") or raw.get("tipo") or raw.get("kind")) or "").casefold()
    if "aditiv" in kind or "amendment" in kind:
        return "amendment"
    if "aviso" in kind or "notice" in kind:
        return "notice"
    if "process" in kind or "edital" in kind:
        return "process_document"
    if "page" in kind or "html" in kind:
        return "official_page"
    return "contract"


def _pick_value(raw: dict[str, Any]) -> tuple[Any, str | None, str | None]:
    explicit_semantic = _map_semantic(_text(raw.get("value_semantic") or raw.get("valor_semantic")))
    if raw.get("value_amount") not in {None, ""}:
        return raw.get("value_amount"), explicit_semantic, "value_amount"
    for field_name, semantic in VALUE_FIELD_TO_SEMANTIC.items():
        if raw.get(field_name) not in {None, ""}:
            return raw.get(field_name), explicit_semantic or semantic, field_name
    # valor_total is ambiguous. Amount may be copied only when an explicit semantic exists.
    if raw.get("valor_total") not in {None, ""}:
        return raw.get("valor_total"), explicit_semantic, "valor_total"
    if raw.get("valor") not in {None, ""}:
        return raw.get("valor"), explicit_semantic, "valor"
    return None, explicit_semantic, None


def draft_from_record(raw: dict[str, Any], *, default_source: str = "fixture") -> dict[str, Any]:
    amount, semantic, amount_field = _pick_value(raw)
    locator = raw.get("locator") if isinstance(raw.get("locator"), dict) else {"json_path": amount_field}
    excerpt_source = _text(raw.get("evidence_excerpt")) or _text(
        raw.get("object_text") or raw.get("objeto") or raw.get("objeto_contrato")
    )
    document_text = raw.get("raw_text") or raw.get("html") or raw
    document_id = _text(raw.get("source_document_id") or raw.get("document_id") or raw.get("id"))
    document_sha = _text(raw.get("source_document_sha256") or raw.get("sha256"))
    if document_sha is None:
        document_sha = raw_record_hash_for(document_text)
    raw_hash = _text(raw.get("raw_record_hash")) or raw_record_hash_for(raw)
    amendment_type = _text(raw.get("amendment_type"))
    if not amendment_type:
        if raw.get("amendment_value_delta") not in {None, ""} and raw.get("amendment_term_delta") not in {None, ""}:
            amendment_type = "prazo_e_valor"
        elif raw.get("amendment_value_delta") not in {None, ""}:
            amendment_type = "valor"
        elif raw.get("amendment_term_delta") not in {None, ""}:
            amendment_type = "prazo"
    draft = {
        "schema_version": SCHEMA_VERSION,
        "source_system": _text(raw.get("source_system") or raw.get("source") or default_source),
        "source_kind": _source_kind(raw),
        "official_url": _text(raw.get("official_url") or raw.get("url") or raw.get("source_url")),
        "source_document_id": document_id,
        "source_document_sha256": document_sha,
        "process_identifier": _text(
            raw.get("process_identifier") or raw.get("process_id") or raw.get("numero_processo")
        ),
        "contracting_entity_identifier": normalize_cnpj(
            _text(raw.get("contracting_entity_identifier") or raw.get("orgao_cnpj") or raw.get("orgao_id"))
        ),
        "supplier_identifier": normalize_cnpj(
            _text(raw.get("supplier_identifier") or raw.get("fornecedor_cnpj") or raw.get("fornecedor_id"))
        ),
        "contract_identifier": _text(
            raw.get("contract_identifier")
            or raw.get("contrato_id")
            or raw.get("numero_controle_pncp")
            or raw.get("contract_id")
        ),
        "observed_at": _text(raw.get("observed_at") or raw.get("data_publicacao")),
        "effective_at": _normalize_date(raw.get("effective_at") or raw.get("data_assinatura")),
        "extractor_version": EXTRACTOR_VERSION,
        "locator": locator,
        "evidence_excerpt": clip_excerpt(excerpt_source),
        "raw_record_hash": raw_hash,
        "object_text": _text(raw.get("object_text") or raw.get("objeto") or raw.get("objeto_contrato")),
        "lot_identifier": _text(raw.get("lot_identifier") or raw.get("lote")),
        "item_identifier": _text(raw.get("item_identifier") or raw.get("item")),
        "unit": _text(_first(raw, UNIT_FIELD_KEYS)),
        "quantity": _first(raw, QUANTITY_FIELD_KEYS),
        "execution_regime": _text(_first(raw, REGIME_FIELD_KEYS)),
        "procurement_modality": _text(_first(raw, MODALITY_FIELD_KEYS)),
        "currency": _text(raw.get("currency")),
        "value_amount": amount,
        "value_semantic": semantic,
        "period_start": _normalize_date(_first(raw, PERIOD_START_KEYS)),
        "period_end": _normalize_date(_first(raw, PERIOD_END_KEYS)),
        "amendment_type": amendment_type,
        "amendment_value_delta": raw.get("amendment_value_delta"),
        "amendment_term_delta": _text(raw.get("amendment_term_delta")),
        "confidence_class": raw.get("confidence_class") or "explicit_structured_field",
        "conflict_group_id": raw.get("conflict_group_id"),
        "status": raw.get("status") or "observed",
        "extraction_rule": raw.get("extraction_rule") or "structured_field_map/1.0",
        "extraction_rule_version": raw.get("extraction_rule_version") or "1.0",
        "supersedes_document_id": _text(raw.get("supersedes_document_id")),
        "supersedes_observation_id": _text(raw.get("supersedes_observation_id")),
        "infer_from_absence": raw.get("infer_from_absence"),
        "assume_missing_if_unpublished": raw.get("assume_missing_if_unpublished"),
        "unit_inferred": raw.get("unit_inferred"),
        "quantity_inferred": raw.get("quantity_inferred"),
        "period_presumed": raw.get("period_presumed"),
        "amendment_presumed": raw.get("amendment_presumed"),
        "merge_cnpj_root_with_establishment": raw.get("merge_cnpj_root_with_establishment"),
        "extra": {
            **dict(raw.get("extra") or {}),
            **{key: raw[key] for key in ("uf", "municipio") if raw.get(key)},
        },
    }
    draft["observation_id"] = observation_id_for(draft)
    return draft


def _finalize(draft: dict[str, Any]) -> OfficialContractObservation:
    return validate_mapping(draft)


def extract_record(raw: dict[str, Any], *, default_source: str = "fixture") -> ExtractResult:
    if (
        raw.get("fetch_error")
        or raw.get("unavailable")
        or (raw.get("http_status") and int(raw.get("http_status") or 0) >= 400)
    ):
        url = _text(raw.get("official_url") or raw.get("url")) or "unknown"
        return ExtractResult(
            observations=(),
            rejections=(),
            document_errors=(),
            unavailabilities=(
                SourceUnavailability(
                    official_url=url,
                    error_kind=str(raw.get("error_kind") or raw.get("fetch_error") or "http_status"),
                    http_status=int(raw["http_status"]) if raw.get("http_status") else None,
                    message=_text(raw.get("message")),
                ),
            ),
        )
    if raw.get("text") and not any(
        key in raw for key in ("value_amount", "valor_global", "valor_contratado", "unit", "unidade")
    ):
        return extract_text(
            str(raw["text"]),
            identity={key: raw.get(key) for key in raw if key != "text"},
        )
    if raw.get("html") and not raw.get("_from_html"):
        return extract_html(str(raw["html"]), identity={key: raw.get(key) for key in raw if key != "html"})
    try:
        observation = _finalize(draft_from_record(raw, default_source=default_source))
        return ExtractResult(observations=(observation,), rejections=(), document_errors=())
    except ObservationValidationError as exc:
        return ExtractResult(
            observations=(),
            rejections=(
                ExtractionRejection(
                    code=exc.code,
                    message=exc.message,
                    source_document_id=_text(raw.get("source_document_id") or raw.get("document_id")),
                    official_url=_text(raw.get("official_url") or raw.get("url")),
                ),
            ),
            document_errors=(),
        )


def extract_text(text: str, *, identity: dict[str, Any] | None = None) -> ExtractResult:
    base = dict(identity or {})
    if not text or not text.strip():
        return ExtractResult(
            observations=(),
            rejections=(
                ExtractionRejection(
                    code=REASON_INSUFFICIENT_EVIDENCE,
                    message="empty_text",
                    source_document_id=_text(base.get("source_document_id")),
                    official_url=_text(base.get("official_url")),
                ),
            ),
            document_errors=(),
        )
    fields: dict[str, Any] = {}
    unit_match = _LABEL_UNIT.search(text)
    if unit_match:
        fields["unit"] = unit_match.group(1).strip()
        fields["locator"] = {"section": "labeled_text", "char_start": unit_match.start(), "char_end": unit_match.end()}
        fields["evidence_excerpt"] = clip_excerpt(unit_match.group(0))
    qty_match = _LABEL_QTY.search(text)
    if qty_match:
        fields["quantity"] = qty_match.group(1)
    regime_match = _LABEL_REGIME.search(text)
    if regime_match:
        fields["execution_regime"] = regime_match.group(1).strip()
    modality_match = _LABEL_MODALITY.search(text)
    if modality_match:
        fields["procurement_modality"] = modality_match.group(1).strip()
    value_match = _LABEL_VALUE.search(text)
    if value_match:
        fields["value_semantic"] = _map_semantic(value_match.group(1))
        fields["value_amount"] = value_match.group(2)
        fields["evidence_excerpt"] = clip_excerpt(value_match.group(0))
        fields["locator"] = {
            "section": "labeled_text",
            "char_start": value_match.start(),
            "char_end": value_match.end(),
        }
    else:
        bare = _LABEL_BARE_VALUE.search(text)
        if bare:
            fields["value_amount"] = bare.group(1)
            fields["evidence_excerpt"] = clip_excerpt(bare.group(0))
    period_match = _LABEL_PERIOD.search(text)
    if period_match:
        fields["period_start"] = period_match.group(1)
        fields["period_end"] = period_match.group(2)
    value_delta = _LABEL_AMENDMENT_VALUE.search(text)
    if value_delta:
        fields["amendment_value_delta"] = value_delta.group(1)
        fields["source_kind"] = "amendment"
    term_delta = _LABEL_AMENDMENT_TERM.search(text)
    if term_delta:
        fields["amendment_term_delta"] = term_delta.group(1).strip()
        fields["source_kind"] = "amendment"
    if not fields:
        return ExtractResult(
            observations=(),
            rejections=(
                ExtractionRejection(
                    code=REASON_INSUFFICIENT_EVIDENCE,
                    message="no_explicit_labeled_fields",
                    source_document_id=_text(base.get("source_document_id")),
                    official_url=_text(base.get("official_url")),
                    evidence_excerpt=clip_excerpt(text),
                ),
            ),
            document_errors=(),
        )
    merged = {**base, **fields}
    merged.setdefault("source_kind", base.get("source_kind") or "process_document")
    merged.setdefault("confidence_class", "explicit_labeled_text")
    merged.setdefault("extraction_rule", "labeled_text/1.0")
    merged.setdefault("extraction_rule_version", "1.0")
    merged.setdefault("raw_text", text)
    if "source_document_sha256" not in merged:
        merged["source_document_sha256"] = raw_record_hash_for(text)
    return extract_record(merged)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self.labeled: dict[str, str] = {}
        self._capture_label: str | None = None
        self._label_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag in {"th", "dt"}:
            self._capture_label = tag
            self._label_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._table is not None and self._row is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag in {"th", "dt"} and self._capture_label:
            self._capture_label = " ".join("".join(self._label_buf).split())
        elif tag in {"td", "dd"} and isinstance(self._capture_label, str) and self._capture_label:
            self.labeled[self._capture_label.casefold()] = " ".join("".join(self._label_buf).split())
            self._capture_label = None
            self._label_buf = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
        if self._capture_label is not None:
            self._label_buf.append(data)


def _fold_header(value: str) -> str:
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in nfkd if not unicodedata.combining(character))


def _header_index(headers: list[str], *needles: str) -> int | None:
    folded = [_fold_header(item) for item in headers]
    for needle in needles:
        target = _fold_header(needle)
        for index, header in enumerate(folded):
            if target in header:
                return index
    return None


def extract_html(html: str, *, identity: dict[str, Any] | None = None) -> ExtractResult:
    base = dict(identity or {})
    try:
        parser = _TableParser()
        parser.feed(html)
    except Exception as exc:  # noqa: BLE001 — isolate parser errors per document
        return ExtractResult(
            observations=(),
            rejections=(),
            document_errors=(
                DocumentError(
                    code=REASON_PARSER_ERROR,
                    message=str(exc),
                    source_document_id=_text(base.get("source_document_id")),
                    official_url=_text(base.get("official_url")),
                    source_document_sha256=raw_record_hash_for(html),
                ),
            ),
        )
    observations: list[OfficialContractObservation] = []
    rejections: list[ExtractionRejection] = []
    base.setdefault("source_document_sha256", raw_record_hash_for(html))
    base.setdefault("source_kind", base.get("source_kind") or "official_page")
    if parser.labeled:
        mapped: dict[str, Any] = {}
        for label, value in parser.labeled.items():
            if "unidade" in label:
                mapped["unit"] = value
            elif "quantidade" in label:
                mapped["quantity"] = value
            elif "regime" in label:
                mapped["execution_regime"] = value
            elif "modalidade" in label:
                mapped["procurement_modality"] = value
            elif "valor" in label:
                mapped["value_amount"] = value
                mapped["value_semantic"] = _map_semantic(label)
        if mapped:
            merged = {
                **base,
                **mapped,
                "confidence_class": "explicit_table_cell",
                "extraction_rule": "html_labeled_cell/1.0",
                "locator": {"section": "labeled_html"},
                "_from_html": True,
            }
            result = extract_record(merged)
            observations.extend(result.observations)
            rejections.extend(result.rejections)
    for table_index, table in enumerate(parser.tables):
        if not table:
            continue
        headers = table[0]
        unit_i = _header_index(headers, "unidade", "unit")
        qty_i = _header_index(headers, "quantidade", "qtd", "quantity")
        value_i = _header_index(headers, "valor", "preço", "preco")
        item_i = _header_index(headers, "item", "descri")
        semantic_i = _header_index(headers, "semant", "tipo de valor")
        if unit_i is None and qty_i is None and value_i is None:
            continue
        for row_index, row in enumerate(table[1:], start=1):
            mapped = {
                "unit": row[unit_i] if unit_i is not None and unit_i < len(row) else None,
                "quantity": row[qty_i] if qty_i is not None and qty_i < len(row) else None,
                "value_amount": row[value_i] if value_i is not None and value_i < len(row) else None,
                "item_identifier": row[item_i] if item_i is not None and item_i < len(row) else str(row_index),
                "value_semantic": _map_semantic(row[semantic_i])
                if semantic_i is not None and semantic_i < len(row)
                else None,
                "object_text": row[item_i] if item_i is not None and item_i < len(row) else base.get("object_text"),
                "confidence_class": "explicit_table_cell",
                "extraction_rule": "html_table/1.0",
                "locator": {"table": f"table[{table_index}]", "cell": f"row[{row_index}]"},
                "evidence_excerpt": clip_excerpt(" | ".join(row)),
            }
            result = extract_record(
                {
                    **base,
                    **mapped,
                    "_from_html": True,
                    "source_kind": base.get("source_kind") or "official_page",
                }
            )
            observations.extend(result.observations)
            rejections.extend(result.rejections)
    if not observations and not rejections:
        return extract_text(re.sub(r"<[^>]+>", " ", html), identity=base)
    unique = {item.observation_id: item for item in observations}
    return ExtractResult(
        observations=tuple(sorted(unique.values(), key=lambda item: item.observation_id)),
        rejections=tuple(rejections),
        document_errors=(),
    )


def extract_processed_document(raw: dict[str, Any]) -> ExtractResult:
    document = raw.get("document") if isinstance(raw.get("document"), dict) else raw
    identity = {
        "source_system": document.get("source_id") or document.get("portal_family") or "process_documents",
        "source_kind": "process_document",
        "official_url": document.get("download_url") or document.get("source_page_url"),
        "source_document_id": document.get("internal_id") or document.get("official_id"),
        "source_document_sha256": document.get("sha256"),
        "process_identifier": document.get("administrative_process_id") or document.get("procurement_id"),
        "contract_identifier": document.get("contract_id"),
        "observed_at": document.get("published_at") or document.get("fetched_at"),
    }
    if raw.get("html"):
        return extract_html(str(raw["html"]), identity=identity)
    if raw.get("text"):
        return extract_text(str(raw["text"]), identity=identity)
    return extract_record({**identity, **{key: value for key, value in raw.items() if key != "document"}})


def _iter_payload(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "records" in payload and isinstance(payload["records"], list):
            return list(payload["records"])
        if "contracts" in payload and isinstance(payload["contracts"], list):
            return list(payload["contracts"])
        if "observations" in payload and isinstance(payload["observations"], list):
            return list(payload["observations"])
        if "document" in payload or "text" in payload or "html" in payload:
            return [payload]
        return [payload]
    return [payload]


def extract_payload(payload: Any) -> ExtractResult:
    observations: list[OfficialContractObservation] = []
    rejections: list[ExtractionRejection] = []
    errors: list[DocumentError] = []
    unavailabilities: list[SourceUnavailability] = []
    for item in _iter_payload(payload):
        if not isinstance(item, dict):
            errors.append(DocumentError(code=REASON_PARSER_ERROR, message="payload_item_not_object"))
            continue
        if item.get("document") or item.get("sha256") and item.get("download_url"):
            result = extract_processed_document(item)
        else:
            result = extract_record(item)
        observations.extend(result.observations)
        rejections.extend(result.rejections)
        errors.extend(result.document_errors)
        unavailabilities.extend(result.unavailabilities)
    unique = {item.observation_id: item for item in observations}
    return ExtractResult(
        observations=tuple(sorted(unique.values(), key=lambda item: item.observation_id)),
        rejections=tuple(rejections),
        document_errors=tuple(errors),
        unavailabilities=tuple(unavailabilities),
    )


def extract_path(path: str | Path) -> ExtractResult:
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return ExtractResult(
            observations=(),
            rejections=(),
            document_errors=(DocumentError(code=REASON_PARSER_ERROR, message=str(exc)),),
        )
    suffix = target.suffix.lower()
    if suffix in {".html", ".htm"}:
        return extract_html(
            text,
            identity={
                "source_system": "fixture",
                "source_kind": "official_page",
                "official_url": f"fixture://{target.name}",
                "source_document_id": target.name,
                "source_document_sha256": raw_record_hash_for(text),
            },
        )
    if suffix == ".txt":
        return extract_text(
            text,
            identity={
                "source_system": "fixture",
                "source_kind": "process_document",
                "official_url": f"fixture://{target.name}",
                "source_document_id": target.name,
                "source_document_sha256": raw_record_hash_for(text),
            },
        )
    if suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return extract_payload(rows)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return ExtractResult(
            observations=(),
            rejections=(),
            document_errors=(
                DocumentError(
                    code=REASON_PARSER_ERROR,
                    message=str(exc),
                    source_document_id=target.name,
                    source_document_sha256=raw_record_hash_for(text),
                ),
            ),
        )
    return extract_payload(payload)


def extract_many_paths(paths: list[str | Path] | tuple[str | Path, ...]) -> ExtractResult:
    observations: list[OfficialContractObservation] = []
    rejections: list[ExtractionRejection] = []
    errors: list[DocumentError] = []
    unavailabilities: list[SourceUnavailability] = []
    for path in paths:
        result = extract_path(path)
        observations.extend(result.observations)
        rejections.extend(result.rejections)
        errors.extend(result.document_errors)
        unavailabilities.extend(result.unavailabilities)
    unique = {item.observation_id: item for item in observations}
    return ExtractResult(
        observations=tuple(sorted(unique.values(), key=lambda item: item.observation_id)),
        rejections=tuple(rejections),
        document_errors=tuple(errors),
        unavailabilities=tuple(unavailabilities),
    )
