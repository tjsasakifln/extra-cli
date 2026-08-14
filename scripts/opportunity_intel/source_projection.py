"""Source-agnostic projection of raw observations into opportunity_intel.

A raw record from SC Compras, Compras.gov, PCP, TCE, DOE, transparência or
an external platform becomes an observation that keeps ``source`` and
``source_id``. Nothing is rewritten as PNCP. fetched = persisted + rejected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

SUPPORTED_SOURCES = frozenset(
    {
        "pncp",
        "sc_compras",
        "compras_gov",
        "pcp",
        "tce_sc",
        "doe_sc",
        "transparencia",
        "ciga",
        "dom_sc",
        "external",
    }
)

TERMINAL_STATUSES = frozenset(
    {
        "revogado",
        "revoked",
        "anulado",
        "annulled",
        "suspenso",
        "suspended",
        "encerrado",
        "closed",
        "homologado",
        "cancelado",
        "fracassado",
    }
)

REASON_MISSING_SOURCE = "missing_source"
REASON_SOURCE_RENAMED_PNCP = "source_renamed_as_pncp"
REASON_MISSING_IDENTITY = "missing_identity"
REASON_EMPTY_OBJECT = "empty_object"
REASON_UNSUPPORTED_SOURCE = "unsupported_source"
REASON_CLIENT_AUTHORITY = "client_id_not_authority"
FORBIDDEN_TRUTH_KEYS = frozenset({"client_id", "client", "action", "outcome"})


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Observation:
    source: str
    source_id: str
    objeto: str
    orgao_cnpj: str | None
    orgao_nome: str | None
    municipio: str | None
    uf: str | None
    status: str
    identity: str
    payload: dict[str, Any]
    projected_at: str
    history: tuple[dict[str, Any], ...] = ()

    def upsert_key(self) -> tuple[str, str]:
        return self.source, self.source_id


@dataclass(frozen=True)
class Rejection:
    source: str
    source_id: str | None
    reason: str
    detail: str


@dataclass
class ProjectionBatch:
    source: str
    fetched: int
    persisted: list[Observation] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    store: dict[tuple[str, str], Observation] = field(default_factory=dict)

    @property
    def balanced(self) -> bool:
        return self.fetched == len(self.persisted) + len(self.rejected)

    def counts(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "persisted": len(self.persisted),
            "rejected": len(self.rejected),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "fetched": self.fetched,
            "persisted": [asdict(o) for o in self.persisted],
            "rejected": [asdict(r) for r in self.rejected],
            "balanced": self.balanced,
        }


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _payload_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _truth_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Copy the raw body without CRM/client authority fields."""
    return {key: value for key, value in raw.items() if key not in FORBIDDEN_TRUTH_KEYS}


def _extract_source_id(raw: dict[str, Any], source: str) -> str:
    for key in (
        "source_id",
        "sourceId",
        "numero_processo",
        "numeroProcesso",
        "numeroControlePNCP",
        "id",
        "api_id",
        "pncp_id",
    ):
        text = _as_text(raw.get(key))
        if text:
            return text
    return ""


def _extract_status(raw: dict[str, Any]) -> str:
    return _as_text(
        raw.get("status") or raw.get("situacao") or raw.get("situacaoCompra") or raw.get("status_canonico") or "unknown"
    ).lower()


def project_raw(raw: dict[str, Any], *, source: str) -> Observation | Rejection:
    """Project one raw record. Never relabels a non-PNCP source as PNCP."""
    declared = _as_text(raw.get("source") or source).lower()
    if not declared:
        return Rejection(source=source, source_id=None, reason=REASON_MISSING_SOURCE, detail="source ausente")
    if declared not in SUPPORTED_SOURCES:
        return Rejection(
            source=declared,
            source_id=_extract_source_id(raw, declared) or None,
            reason=REASON_UNSUPPORTED_SOURCE,
            detail=f"fonte não projetável: {declared}",
        )
    if declared != "pncp" and (
        _as_text(raw.get("forced_source")).lower() == "pncp" or raw.get("rewrite_as_pncp") is True
    ):
        return Rejection(
            source=declared,
            source_id=_extract_source_id(raw, declared) or None,
            reason=REASON_SOURCE_RENAMED_PNCP,
            detail="projeção recusou rebatizar a fonte como PNCP",
        )
    if any(key in raw for key in FORBIDDEN_TRUTH_KEYS) and not _extract_source_id(raw, declared):
        return Rejection(
            source=declared,
            source_id=None,
            reason=REASON_CLIENT_AUTHORITY,
            detail="client_id/action/outcome não são identidade no truth plane",
        )
    source_id = _extract_source_id(raw, declared)
    if not source_id:
        return Rejection(source=declared, source_id=None, reason=REASON_MISSING_IDENTITY, detail="source_id ausente")
    objeto = _as_text(
        raw.get("objeto")
        or raw.get("objeto_compra")
        or raw.get("objetoCompra")
        or raw.get("descricao")
        or raw.get("titulo")
    )
    if not objeto:
        return Rejection(
            source=declared,
            source_id=source_id,
            reason=REASON_EMPTY_OBJECT,
            detail="objeto vazio",
        )
    orgao_cnpj = _as_text(raw.get("orgao_cnpj") or raw.get("orgaoCNPJ") or raw.get("cnpj")) or None
    orgao_nome = _as_text(raw.get("orgao_nome") or raw.get("orgao_razao_social") or raw.get("orgao")) or None
    return Observation(
        source=declared,
        source_id=source_id,
        objeto=objeto,
        orgao_cnpj=orgao_cnpj,
        orgao_nome=orgao_nome,
        municipio=_as_text(raw.get("municipio")) or None,
        uf=_as_text(raw.get("uf") or raw.get("UF")).upper() or None,
        status=_extract_status(raw),
        identity=f"{declared}:{source_id}",
        payload=_truth_payload(raw),
        projected_at=_utc_now(),
        history=(),
    )


def apply_terminal(existing: Observation, incoming: Observation) -> Observation:
    """Terminal events update state; identity and prior observations stay."""
    if incoming.upsert_key() != existing.upsert_key():
        raise ValueError("terminal update requires the same upsert key")
    same_payload = _payload_fingerprint(existing.payload) == _payload_fingerprint(incoming.payload)
    if existing.status == incoming.status and existing.objeto == (incoming.objeto or existing.objeto) and same_payload:
        return existing
    snapshot = {
        "status": existing.status,
        "payload_sha256": _payload_fingerprint(existing.payload),
        "projected_at": existing.projected_at,
        "objeto": existing.objeto,
    }
    status = incoming.status if incoming.status in TERMINAL_STATUSES else existing.status
    return Observation(
        source=existing.source,
        source_id=existing.source_id,
        objeto=incoming.objeto or existing.objeto,
        orgao_cnpj=incoming.orgao_cnpj or existing.orgao_cnpj,
        orgao_nome=incoming.orgao_nome or existing.orgao_nome,
        municipio=incoming.municipio or existing.municipio,
        uf=incoming.uf or existing.uf,
        status=status,
        identity=existing.identity,
        payload=dict(incoming.payload),
        projected_at=_utc_now(),
        history=existing.history + (snapshot,),
    )


def project_source_batch(
    records: list[dict[str, Any]],
    *,
    source: str,
    store: dict[tuple[str, str], Observation] | None = None,
) -> ProjectionBatch:
    """Idempotent projection. Second insert of the same key updates in place."""
    batch = ProjectionBatch(source=source, fetched=len(records), store=store if store is not None else {})
    for raw in records:
        result = project_raw(raw, source=source)
        if isinstance(result, Rejection):
            batch.rejected.append(result)
            continue
        key = result.upsert_key()
        if key in batch.store:
            result = apply_terminal(batch.store[key], result)
        batch.store[key] = result
        batch.persisted.append(result)
    if not batch.balanced:
        raise RuntimeError(
            f"projection invariant broken: fetched={batch.fetched} "
            f"persisted={len(batch.persisted)} rejected={len(batch.rejected)}"
        )
    return batch


def attach_projection(result: Any, records: list[dict[str, Any]], source: str) -> ProjectionBatch:
    """Hook used by resilience persistence for every non-PNCP source."""
    projection = project_source_batch(records, source=source)
    result.opportunities_persisted = len(projection.persisted)
    provenance = dict(getattr(result, "provenance", {}) or {})
    provenance["source_projection"] = {
        "source": source,
        "fetched": projection.fetched,
        "persisted": len(projection.persisted),
        "rejected": len(projection.rejected),
        "rejection_reasons": [r.reason for r in projection.rejected],
    }
    result.provenance = provenance
    return projection


def counts_by_source(batches: list[ProjectionBatch]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for batch in batches:
        row = out.setdefault(batch.source, {"fetched": 0, "persisted": 0, "rejected": 0})
        row["fetched"] += batch.fetched
        row["persisted"] += len(batch.persisted)
        row["rejected"] += len(batch.rejected)
    return out
