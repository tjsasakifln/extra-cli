"""Canonical extraction of official PNCP structural fields from a source payload.

Authority for #546: persist tipoContrato, categoriaProcesso, modalidade,
regime de execução, SRP and numeroRetificacao from the PNCP payload — never
infer them from objeto text.

The same mapper is used by live transform (contracts_crawler /
pncp_crawler_adapter) and by archived-payload backfill.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

RULE_VERSION = "pncp-structural-fields-v1"

STRUCTURAL_FIELD_KEYS: tuple[str, ...] = (
    "tipo_contrato_id",
    "tipo_contrato_nome",
    "categoria_processo_id",
    "categoria_processo_nome",
    "modalidade_id",
    "modalidade_nome",
    "regime_execucao_id",
    "regime_execucao_nome",
    "srp",
    "numero_retificacao",
)

_TRUE = frozenset({"true", "t", "1", "sim", "s", "yes", "y"})
_FALSE = frozenset({"false", "f", "0", "nao", "não", "n", "no"})


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, dict):
        return _as_int(
            value.get("id")
            or value.get("codigo")
            or value.get("codigoModalidade")
            or value.get("codigoRegime")
        )
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(float(text)) if "." in text else int(text)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return _as_text(
            value.get("nome")
            or value.get("descricao")
            or value.get("name")
            or value.get("label")
        )
    if isinstance(value, (bool, int, float)):
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _nested_maps(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    nested: list[Mapping[str, Any]] = [payload]
    for key in ("compra", "contratacao", "licitacao", "processoCompra"):
        value = payload.get(key)
        if isinstance(value, dict):
            nested.append(value)
    return tuple(nested)


def extract_pncp_structural_fields(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return official PNCP structural fields from a raw or nested payload.

    Missing source values stay None. This function never inspects
    ``objetoContrato`` / ``objeto_contrato``.
    """
    empty = {key: None for key in STRUCTURAL_FIELD_KEYS}
    if not isinstance(payload, Mapping):
        return empty

    maps = _nested_maps(payload)

    tipo_raw = None
    tipo_id = None
    tipo_nome = None
    categoria_raw = None
    categoria_id = None
    categoria_nome = None
    modalidade_raw = None
    modalidade_id = None
    modalidade_nome = None
    regime_raw = None
    regime_id = None
    regime_nome = None
    srp = None
    numero_retificacao = None

    for item in maps:
        if tipo_raw is None:
            tipo_raw = _first(item, "tipoContrato", "tipo_contrato")
        if tipo_id is None:
            tipo_id = _as_int(_first(item, "tipoContratoId", "tipo_contrato_id", "tipoContrato"))
        if tipo_nome is None:
            tipo_nome = _as_text(
                _first(item, "tipoContratoNome", "tipo_contrato_nome", "tipoContrato")
            )
        if categoria_raw is None:
            categoria_raw = _first(item, "categoriaProcesso", "categoria_processo")
        if categoria_id is None:
            categoria_id = _as_int(
                _first(item, "categoriaProcessoId", "categoria_processo_id", "categoriaProcesso")
            )
        if categoria_nome is None:
            categoria_nome = _as_text(
                _first(
                    item,
                    "categoriaProcessoNome",
                    "categoria_processo_nome",
                    "categoriaProcesso",
                )
            )
        if modalidade_raw is None:
            modalidade_raw = _first(
                item, "modalidade", "modalidadeContratacao", "codigoModalidadeContratacao"
            )
        if modalidade_id is None:
            modalidade_id = _as_int(
                _first(
                    item,
                    "modalidadeId",
                    "modalidade_id",
                    "codigoModalidadeContratacao",
                    "modalidade",
                )
            )
        if modalidade_nome is None:
            modalidade_nome = _as_text(
                _first(
                    item,
                    "modalidadeNome",
                    "modalidade_nome",
                    "nomeModalidade",
                    "modalidade",
                )
            )
        if regime_raw is None:
            regime_raw = _first(item, "regimeExecucao", "regime_execucao")
        if regime_id is None:
            regime_id = _as_int(
                _first(
                    item,
                    "codigoRegimeExecucao",
                    "regimeExecucaoId",
                    "regime_execucao_id",
                    "regimeExecucao",
                )
            )
        if regime_nome is None:
            regime_nome = _as_text(
                _first(
                    item,
                    "regimeExecucaoNome",
                    "nomeRegimeExecucao",
                    "regime_execucao_nome",
                    "regimeExecucao",
                )
            )
        if srp is None:
            srp = _as_bool(
                _first(
                    item,
                    "srp",
                    "compraSrp",
                    "registroPreco",
                    "sistemaRegistroPrecos",
                    "sistemaRegistroPreco",
                )
            )
        if numero_retificacao is None:
            numero_retificacao = _as_int(
                _first(item, "numeroRetificacao", "numero_retificacao", "retificacao")
            )

    if tipo_id is None:
        tipo_id = _as_int(tipo_raw)
    if tipo_nome is None:
        tipo_nome = _as_text(tipo_raw)
    if categoria_id is None:
        categoria_id = _as_int(categoria_raw)
    if categoria_nome is None:
        categoria_nome = _as_text(categoria_raw)
    if modalidade_id is None:
        modalidade_id = _as_int(modalidade_raw)
    if modalidade_nome is None:
        modalidade_nome = _as_text(modalidade_raw)
    if regime_id is None:
        regime_id = _as_int(regime_raw)
    if regime_nome is None:
        regime_nome = _as_text(regime_raw)

    return {
        "tipo_contrato_id": tipo_id,
        "tipo_contrato_nome": tipo_nome,
        "categoria_processo_id": categoria_id,
        "categoria_processo_nome": categoria_nome,
        "modalidade_id": modalidade_id,
        "modalidade_nome": modalidade_nome,
        "regime_execucao_id": regime_id,
        "regime_execucao_nome": regime_nome,
        "srp": srp,
        "numero_retificacao": numero_retificacao,
    }


def attach_structural_fields(
    record: dict[str, Any],
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge extracted official fields onto a transformed contract record."""
    record.update(extract_pncp_structural_fields(payload))
    return record


def plan_structural_backfill(
    payloads: list[Mapping[str, Any]],
    *,
    after_contrato_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Build a resumable, limitable batch of mapped rows from archived payloads.

    Each payload must carry ``numeroControlePNCP`` or ``contrato_id``.
    Rows without a contract id are skipped. Ordering is by contrato_id so
    ``after_contrato_id`` resumes deterministically.
    """
    mapped: list[dict[str, Any]] = []
    for payload in payloads:
        contrato_id = str(
            payload.get("contrato_id")
            or payload.get("numeroControlePNCP")
            or payload.get("numeroControlePncp")
            or ""
        ).strip()
        if not contrato_id:
            continue
        row = {"contrato_id": contrato_id, **extract_pncp_structural_fields(payload)}
        mapped.append(row)
    mapped.sort(key=lambda item: item["contrato_id"])
    if after_contrato_id:
        mapped = [item for item in mapped if item["contrato_id"] > after_contrato_id]
    if limit is not None:
        mapped = mapped[: max(0, int(limit))]
    return mapped
