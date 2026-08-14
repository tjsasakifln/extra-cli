"""Contract truth and durability primitives (#309, #312, #314, #319, #306, #304).

Pure classification plus small I/O seams. Raw official payloads are never
mutated; facts receive status/quality labels. Production writers take a
PostgreSQL advisory fence; checkpoints refuse the git/release worktree.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

ACTIVITY_RULE_VERSION = "contract-activity-v1"
QUALITY_RULE_VERSION = "contract-quality-v1"
IDENTITY_RULE_VERSION = "canonical-contract-v1"
PAGINATION_RULE_VERSION = "pagination-reconcile-v1"

ACTIVE_PROVEN = "ACTIVE_PROVEN"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"
TERMINATED = "TERMINATED"
SUSPENDED = "SUSPENDED"
UNKNOWN = "UNKNOWN"
REVIEW = "REVIEW"

VALID = "VALID"
QUARANTINED = "QUARANTINED"

ACTIVITY_STATES = frozenset(
    {ACTIVE_PROVEN, COMPLETED, CANCELLED, TERMINATED, SUSPENDED, UNKNOWN}
)
QUALITY_STATES = frozenset({VALID, REVIEW, QUARANTINED})

PG_FENCE_KEY = 0x45585452  # 'EXTR'
PRODUCTION_STATE_ROOT = Path("/var/lib/extra-consultoria")
FORBIDDEN_CHECKPOINT_PREFIXES = (
    "/opt/extra-consultoria",
    "/opt/extra-cli",
)

_ACTIVE_TOKENS = frozenset(
    {
        "vigente",
        "ativo",
        "ativa",
        "em execucao",
        "em execução",
        "assinado",
        "publicado",
        "active",
    }
)
_COMPLETED_TOKENS = frozenset({"encerrado", "concluido", "concluído", "finalizado", "completed", "findado"})
_CANCELLED_TOKENS = frozenset({"cancelado", "anulado", "cancelled", "canceled"})
_TERMINATED_TOKENS = frozenset({"rescindido", "resilido", "resilído", "terminated", "distratado"})
_SUSPENDED_TOKENS = frozenset({"suspenso", "suspended", "paralisado"})

_TRILLION_BRL = 1_000_000_000_000.0
_PLAUSIBLE_YEAR_MIN = 1994
_PLAUSIBLE_YEAR_MAX = 2100


class CheckpointLocationError(ValueError):
    """Production checkpoint path is inside the release/worktree."""


class WriterFenceBusyError(RuntimeError):
    """A second national writer tried to mutate under an active fence."""


class WriterFenceBypassError(RuntimeError):
    """Production attempted to skip the national writer fence."""


@dataclass(frozen=True)
class ContractActivity:
    state: str
    raw_status: str | None
    rule_version: str
    source: str
    observed_at: str | None
    reasons: tuple[str, ...]

    @property
    def is_active_proven(self) -> bool:
        return self.state == ACTIVE_PROVEN


@dataclass(frozen=True)
class ContractQuality:
    state: str
    rule_version: str
    reasons: tuple[str, ...]
    financial_impact: float | None = None


@dataclass(frozen=True)
class CanonicalContract:
    canonical_contract_id: str
    source: str
    source_contract_id: str
    parent_procurement_id: str | None
    method: str
    rule_version: str
    ambiguous: bool = False


@dataclass
class PaginationReport:
    rule_version: str
    first_total_registros: int | None
    last_total_registros: int | None
    first_total_paginas: int | None
    last_total_paginas: int | None
    fetched: int
    persisted: int
    rejected: int
    unique_ids: int
    duplicate_ids: int
    status: str
    reasons: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_version": self.rule_version,
            "first_total_registros": self.first_total_registros,
            "last_total_registros": self.last_total_registros,
            "first_total_paginas": self.first_total_paginas,
            "last_total_paginas": self.last_total_paginas,
            "fetched": self.fetched,
            "persisted": self.persisted,
            "rejected": self.rejected,
            "unique_ids": self.unique_ids,
            "duplicate_ids": self.duplicate_ids,
            "status": self.status,
            "reasons": list(self.reasons),
            "ok": self.ok,
        }


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _norm_status(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def classify_contract_activity(
    *,
    raw_status: Any = None,
    vigencia_inicio: Any = None,
    vigencia_fim: Any = None,
    today: date | None = None,
    source: str = "pncp",
    observed_at: str | None = None,
    is_active_default: Any = None,
) -> ContractActivity:
    """Absence of proven status/vigência is UNKNOWN — never ACTIVE.

    ``is_active=TRUE`` defaults are ignored. A later event must supply an
    explicit status token or a closed vigência window to leave UNKNOWN.
    """
    del is_active_default  # never proof of activity
    ref = today or date.today()
    raw = None if raw_status is None else str(raw_status).strip()
    token = _norm_status(raw)
    start = _as_date(vigencia_inicio)
    end = _as_date(vigencia_fim)
    reasons: list[str] = []

    if token:
        if token in _CANCELLED_TOKENS:
            return ContractActivity(CANCELLED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _TERMINATED_TOKENS:
            return ContractActivity(TERMINATED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _SUSPENDED_TOKENS:
            return ContractActivity(SUSPENDED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _COMPLETED_TOKENS:
            return ContractActivity(COMPLETED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _ACTIVE_TOKENS:
            if start and end and start > end:
                reasons.append("inverted_vigencia")
                return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, tuple(reasons))
            if end is not None and end < ref:
                return ContractActivity(COMPLETED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("vigencia_ended",))
            if start is None and end is None:
                reasons.append("active_token_without_vigencia")
                return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, tuple(reasons))
            return ContractActivity(ACTIVE_PROVEN, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status+vigencia",))

    if start and end:
        if start > end:
            return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("inverted_vigencia",))
        if end < ref:
            return ContractActivity(COMPLETED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("vigencia_ended",))
        if start <= ref <= end:
            return ContractActivity(ACTIVE_PROVEN, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("vigencia_window",))

    reasons.append("missing_status_and_vigencia")
    return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, tuple(reasons))


def in_active_proven(activity: ContractActivity) -> bool:
    return activity.state == ACTIVE_PROVEN


def classify_contract_quality(
    *,
    data_assinatura: Any = None,
    data_inicio: Any = None,
    data_fim: Any = None,
    data_publicacao: Any = None,
    valor: Any = None,
    today: date | None = None,
) -> ContractQuality:
    """Label implausible dates/values. Raw rows are left untouched."""
    reasons: list[str] = []
    state = VALID
    impact: float | None = None

    dates = {
        "data_assinatura": _as_date(data_assinatura),
        "data_inicio": _as_date(data_inicio),
        "data_fim": _as_date(data_fim),
        "data_publicacao": _as_date(data_publicacao),
    }
    for name, parsed in dates.items():
        if parsed is None:
            raw = {
                "data_assinatura": data_assinatura,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "data_publicacao": data_publicacao,
            }[name]
            if raw not in (None, ""):
                reasons.append(f"unparseable_date:{name}")
                state = QUARANTINED
            continue
        if parsed.year > _PLAUSIBLE_YEAR_MAX or parsed.year >= 8000:
            reasons.append(f"implausible_future_year:{name}:{parsed.isoformat()}")
            state = QUARANTINED
        elif parsed.year < _PLAUSIBLE_YEAR_MIN:
            reasons.append(f"implausible_ancient_year:{name}:{parsed.isoformat()}")
            state = REVIEW if state == VALID else state

    start, end = dates["data_inicio"], dates["data_fim"]
    if start and end and start > end:
        reasons.append("inverted_vigencia")
        state = QUARANTINED

    assinatura, pub = dates["data_assinatura"], dates["data_publicacao"]
    if assinatura and pub and assinatura > pub + (pub - pub):
        # assinatura far after publication is review, not auto-quarantine
        if (assinatura - pub).days > 3650:
            reasons.append("assinatura_far_from_publicacao")
            state = REVIEW if state == VALID else state

    if valor is not None and valor != "":
        try:
            amount = float(valor)
        except (TypeError, ValueError):
            reasons.append("unparseable_value")
            state = QUARANTINED
            amount = None
        if amount is not None:
            impact = amount
            if amount < 0:
                reasons.append("negative_value")
                state = QUARANTINED
            elif amount == 0:
                reasons.append("zero_value_without_semantics")
                state = REVIEW if state == VALID else state
            elif amount > _TRILLION_BRL:
                reasons.append("value_exceeds_one_trillion")
                state = QUARANTINED
            else:
                # Suspicious cents on huge integers (scale-break heuristic).
                if amount >= 10_000_000_000 and "e" in str(amount).lower():
                    reasons.append("scientific_scale_break")
                    state = REVIEW if state == VALID else state
                # Classic centavo-as-real: values like 12345678901 meaning 123M*100
                if amount >= 100_000_000_000:
                    reasons.append("scale_break_suspect")
                    state = QUARANTINED

    if not reasons:
        reasons.append("ok")
    return ContractQuality(state=state, rule_version=QUALITY_RULE_VERSION, reasons=tuple(reasons), financial_impact=impact)


def report_ready_allowed(quality: ContractQuality) -> bool:
    return quality.state != QUARANTINED


def canonical_contract_identity(
    *,
    source: str,
    official_id: str | None = None,
    source_contract_id: str | None = None,
    parent_procurement_id: str | None = None,
    fallback_parts: Iterable[Any] = (),
) -> CanonicalContract:
    """Namespace official IDs per source. Fallback is deterministic."""
    src = (source or "").strip().lower() or "unknown"
    official = (official_id or source_contract_id or "").strip()
    parent = (parent_procurement_id or "").strip() or None
    if official:
        return CanonicalContract(
            canonical_contract_id=f"{src}:{official}",
            source=src,
            source_contract_id=official,
            parent_procurement_id=parent,
            method="official",
            rule_version=IDENTITY_RULE_VERSION,
        )
    parts = [str(part).strip() for part in fallback_parts if part not in (None, "")]
    if parent:
        parts.append(f"parent:{parent}")
    if not parts:
        digest = hashlib.sha256(f"{src}:empty:{parent or ''}".encode()).hexdigest()[:16]
        return CanonicalContract(
            canonical_contract_id=f"{src}:fallback:{digest}",
            source=src,
            source_contract_id=f"fallback:{digest}",
            parent_procurement_id=parent,
            method="fallback",
            rule_version=IDENTITY_RULE_VERSION,
            ambiguous=True,
        )
    payload = "|".join(parts)
    digest = hashlib.sha256(f"{src}:{payload}".encode()).hexdigest()[:20]
    return CanonicalContract(
        canonical_contract_id=f"{src}:fallback:{digest}",
        source=src,
        source_contract_id=f"fallback:{digest}",
        parent_procurement_id=parent,
        method="fallback",
        rule_version=IDENTITY_RULE_VERSION,
    )


def replay_adapters_to_canonical(
    adapter_payloads: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Two adapters on the same official contract → one canonical + N observations."""
    contracts: dict[str, CanonicalContract] = {}
    observations: list[dict[str, Any]] = []
    for payload in adapter_payloads:
        ident = canonical_contract_identity(
            source=str(payload.get("source") or "pncp"),
            official_id=payload.get("official_id") or payload.get("numeroControlePNCP") or payload.get("numeroControlePncpCompra"),
            source_contract_id=payload.get("source_contract_id"),
            parent_procurement_id=payload.get("parent_procurement_id"),
            fallback_parts=payload.get("fallback_parts") or (),
        )
        contracts[ident.canonical_contract_id] = ident
        observations.append(
            {
                "canonical_contract_id": ident.canonical_contract_id,
                "source": ident.source,
                "source_contract_id": ident.source_contract_id,
                "adapter": payload.get("adapter"),
            }
        )
    return {
        "canonical_count": len(contracts),
        "observation_count": len(observations),
        "canonical_ids": sorted(contracts),
        "observations": observations,
        "ambiguous": any(item.ambiguous for item in contracts.values()),
    }


class PaginationReconcile:
    """Accumulate page totals and fail closed on source drift."""

    def __init__(self) -> None:
        self.first_total_registros: int | None = None
        self.last_total_registros: int | None = None
        self.first_total_paginas: int | None = None
        self.last_total_paginas: int | None = None
        self.fetched = 0
        self.persisted = 0
        self.rejected = 0
        self._ids: set[str] = set()
        self.duplicate_ids = 0
        self._page_ids: list[str] = []

    def observe_page(
        self,
        *,
        total_registros: int | None,
        total_paginas: int | None,
        items: Iterable[Mapping[str, Any]],
        id_field: str = "numeroControlePNCP",
    ) -> None:
        if total_registros is not None:
            if self.first_total_registros is None:
                self.first_total_registros = int(total_registros)
            self.last_total_registros = int(total_registros)
        if total_paginas is not None:
            if self.first_total_paginas is None:
                self.first_total_paginas = int(total_paginas)
            self.last_total_paginas = int(total_paginas)
        for item in items:
            item_id = str(item.get(id_field) or item.get("id") or "").strip()
            self.fetched += 1
            if not item_id:
                self.rejected += 1
                continue
            if item_id in self._ids:
                self.duplicate_ids += 1
            self._ids.add(item_id)
            self._page_ids.append(item_id)

    def record_persisted(self, count: int = 1) -> None:
        self.persisted += int(count)

    def record_rejected(self, count: int = 1) -> None:
        self.rejected += int(count)

    def finish(self) -> PaginationReport:
        reasons: list[str] = []
        status = "ok"
        if (
            self.first_total_registros is not None
            and self.last_total_registros is not None
            and self.first_total_registros != self.last_total_registros
        ):
            status = "source_population_drift"
            reasons.append(
                f"totalRegistros {self.first_total_registros} -> {self.last_total_registros}"
            )
        if (
            self.first_total_paginas is not None
            and self.last_total_paginas is not None
            and self.first_total_paginas != self.last_total_paginas
        ):
            status = "source_population_drift"
            reasons.append(f"totalPaginas {self.first_total_paginas} -> {self.last_total_paginas}")
        if self.fetched != self.persisted + self.rejected:
            if status == "ok":
                status = "reconcile_failed"
            reasons.append(f"fetched={self.fetched} != persisted+rejected={self.persisted + self.rejected}")
        if not reasons:
            reasons.append("ok")
        return PaginationReport(
            rule_version=PAGINATION_RULE_VERSION,
            first_total_registros=self.first_total_registros,
            last_total_registros=self.last_total_registros,
            first_total_paginas=self.first_total_paginas,
            last_total_paginas=self.last_total_paginas,
            fetched=self.fetched,
            persisted=self.persisted,
            rejected=self.rejected,
            unique_ids=len(self._ids),
            duplicate_ids=self.duplicate_ids,
            status=status,
            reasons=tuple(reasons),
        )


def isolated_test_environment() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("EXTRA_ISOLATED_TEST") == "1")


def is_production_contracts() -> bool:
    if os.getenv("EXTRA_CONTRACTS_PRODUCTION", "0") == "1":
        return True
    cwd = Path.cwd().as_posix()
    return cwd == "/opt/extra-consultoria" or cwd.startswith("/opt/extra-consultoria/")


def refuse_writer_bypass(*, skip_lock: bool = False, env_skip: str | None = None) -> None:
    """Production units must not skip the fence."""
    env_requested = (env_skip if env_skip is not None else os.getenv("CONTRACTS_SKIP_WRITER_LOCK", "0")) == "1"
    if not (skip_lock or env_requested):
        return
    if isolated_test_environment():
        return
    raise WriterFenceBypassError("national writer bypass refused outside isolated test")


class PostgresWriterFence:
    """Exclusive PostgreSQL advisory lock for national contract writers."""

    def __init__(self, key: int = PG_FENCE_KEY) -> None:
        self.key = key
        self.owned = False
        self._conn: Any = None

    def acquire(self, conn: Any) -> bool:
        cur = conn.cursor()
        try:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (self.key,))
            row = cur.fetchone()
        finally:
            close = getattr(cur, "close", None)
            if callable(close):
                close()
        locked = bool(row[0]) if row else False
        if locked:
            self.owned = True
            self._conn = conn
        return locked

    def release(self) -> None:
        if not self.owned or self._conn is None:
            return
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (self.key,))
        finally:
            close = getattr(cur, "close", None)
            if callable(close):
                close()
        self.owned = False
        self._conn = None

    def run_exclusive(self, conn: Any, mutate) -> Any:
        """Refuse the second writer before calling ``mutate``."""
        if not self.acquire(conn):
            raise WriterFenceBusyError("national writer fence busy")
        try:
            return mutate()
        finally:
            self.release()


def acquire_national_writer_fence(
    dsn: str,
    *,
    skip: bool = False,
    connect: Any = None,
) -> PostgresWriterFence | None:
    """Acquire the PostgreSQL fence used by every national contracts writer.

    Host-local flock is not sufficient. A second writer is refused before
    ``connect`` returns a session that can mutate.
    """
    refuse_writer_bypass(skip_lock=skip)
    if skip or os.getenv("CONTRACTS_SKIP_WRITER_LOCK", "0") == "1":
        return None
    if not dsn:
        raise WriterFenceBypassError("national writer fence requires a DSN")
    if connect is None:
        import psycopg2

        connect = psycopg2.connect
    conn = connect(dsn)
    fence = PostgresWriterFence()
    if not fence.acquire(conn):
        close = getattr(conn, "close", None)
        if callable(close):
            close()
        raise WriterFenceBusyError("national writer fence busy")
    return fence


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_checkpoint_dir(
    requested: str | Path | None,
    *,
    production: bool | None = None,
    repo_root: str | Path | None = None,
    state_root: str | Path | None = None,
) -> Path:
    """Production checkpoints live under /var/lib/extra-consultoria, never the worktree."""
    if production is None:
        production = is_production_contracts()
    repo = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    durable = Path(state_root) if state_root else Path(
        os.getenv("EXTRA_CONTRACTS_STATE_DIR") or str(PRODUCTION_STATE_ROOT)
    )
    if requested:
        raw = Path(requested)
    elif production:
        raw = durable / "checkpoints" / "contracts"
    else:
        raw = repo / "data" / "contracts_checkpoints"
    path = raw.expanduser()
    if not path.is_absolute():
        path = (durable / path) if production else (repo / path)
    path = path.resolve() if path.exists() else Path(os.path.normpath(str(path)))
    if not production:
        return path
    posix = path.as_posix()
    if any(posix == prefix or posix.startswith(prefix + "/") for prefix in FORBIDDEN_CHECKPOINT_PREFIXES):
        raise CheckpointLocationError(f"production checkpoint refuses release tree: {path}")
    if _is_relative_to(path, repo):
        raise CheckpointLocationError(f"production checkpoint refuses git worktree: {path}")
    if not _is_relative_to(path, durable):
        raise CheckpointLocationError(f"production checkpoint must live under {durable}, got {path}")
    return path


def annotate_transformed_contract(record: dict[str, Any], *, raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Attach activity, quality and canonical identity to a transformed row."""
    payload = raw or {}
    activity = classify_contract_activity(
        raw_status=payload.get("situacaoContrato") or payload.get("situacao") or payload.get("status"),
        vigencia_inicio=record.get("data_inicio") or payload.get("dataVigenciaInicio"),
        vigencia_fim=record.get("data_fim") or payload.get("dataVigenciaFim"),
        source="pncp",
        is_active_default=record.get("is_active"),
    )
    quality = classify_contract_quality(
        data_assinatura=record.get("data_assinatura"),
        data_inicio=record.get("data_inicio"),
        data_fim=record.get("data_fim"),
        data_publicacao=record.get("data_publicacao_fonte") or record.get("data_publicacao"),
        valor=record.get("valor_total") or record.get("valor_global") or payload.get("valorGlobal"),
    )
    ident = canonical_contract_identity(
        source=str(record.get("source") or payload.get("source") or "pncp"),
        official_id=record.get("contrato_id") or payload.get("numeroControlePNCP"),
        parent_procurement_id=payload.get("numeroControlePncpCompra"),
    )
    record["status_raw"] = activity.raw_status
    record["status_normalized"] = activity.state
    record["status_rule_version"] = activity.rule_version
    record["status_source"] = activity.source
    record["quality_state"] = quality.state
    record["quality_reasons"] = list(quality.reasons)
    record["quality_rule_version"] = quality.rule_version
    record["report_ready"] = report_ready_allowed(quality)
    record["canonical_contract_id"] = ident.canonical_contract_id
    record["source"] = ident.source
    record["source_contract_id"] = ident.source_contract_id
    record["parent_procurement_id"] = ident.parent_procurement_id
    return record


TRUTH_STAMP_FIELDS = (
    "status_raw",
    "status_normalized",
    "status_rule_version",
    "status_source",
    "quality_state",
    "quality_reasons",
    "quality_rule_version",
    "report_ready",
    "canonical_contract_id",
    "source_contract_id",
    "parent_procurement_id",
)


def stamp_contract_truth_labels(conn: Any, records: Iterable[Mapping[str, Any]]) -> int:
    """Write activity/quality/identity labels after the legacy upsert.

    The historical RPC does not persist these columns. Callers must stamp
    them or the lake stays unlabeled (NULL quality is not report-ready).
    """
    payload = []
    for raw in records:
        contrato_id = str(raw.get("contrato_id") or "").strip()
        if not contrato_id:
            continue
        payload.append(
            {
                "contrato_id": contrato_id,
                "status_raw": raw.get("status_raw"),
                "status_normalized": raw.get("status_normalized"),
                "status_rule_version": raw.get("status_rule_version"),
                "status_source": raw.get("status_source"),
                "quality_state": raw.get("quality_state"),
                "quality_reasons": raw.get("quality_reasons") or [],
                "quality_rule_version": raw.get("quality_rule_version"),
                "report_ready": bool(raw.get("report_ready")),
                "canonical_contract_id": raw.get("canonical_contract_id"),
                "source": raw.get("source"),
                "source_contract_id": raw.get("source_contract_id"),
                "parent_procurement_id": raw.get("parent_procurement_id"),
            }
        )
    if not payload:
        return 0
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE public.pncp_supplier_contracts AS target
            SET status_raw = stamp.status_raw,
                status_normalized = stamp.status_normalized,
                status_rule_version = stamp.status_rule_version,
                status_source = stamp.status_source,
                quality_state = stamp.quality_state,
                quality_reasons = stamp.quality_reasons::jsonb,
                quality_rule_version = stamp.quality_rule_version,
                canonical_contract_id = stamp.canonical_contract_id,
                source = COALESCE(stamp.source, target.source),
                source_contract_id = stamp.source_contract_id,
                parent_procurement_id = stamp.parent_procurement_id
            FROM jsonb_to_recordset(%s::jsonb) AS stamp(
                contrato_id TEXT,
                status_raw TEXT,
                status_normalized TEXT,
                status_rule_version TEXT,
                status_source TEXT,
                quality_state TEXT,
                quality_reasons JSONB,
                quality_rule_version TEXT,
                report_ready BOOLEAN,
                canonical_contract_id TEXT,
                source TEXT,
                source_contract_id TEXT,
                parent_procurement_id TEXT
            )
            WHERE target.contrato_id = stamp.contrato_id
            """,
            (json.dumps(payload, default=str),),
        )
        return int(cur.rowcount or 0)
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()
