"""#346 — immutable AlertaLicitação import, conservative reconcile, miss ranking.

AlertaLicitação is a complementary external snapshot, never absolute truth.
Unknown layout, non-equivalent windows, or totals that do not close block
measurement. Ambiguous matches stay unresolved; weak similarity never merges.

This module is the fail-closed core of issue #346. It does not implement
adapters, retire the XLS, or claim parity with extra-cli crawlers.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = 1
LAYOUT_VERSION = "alertalicitacao-tabular-v1"
PROVENANCE = "alertalicitacao"

ReconcileState = Literal[
    "found_both",
    "extra_only",
    "alerta_only",
    "matched_with_difference",
    "unresolved",
]

GAP_TYPES = (
    "fonte_nao_cadastrada",
    "adapter_inexistente",
    "ente_nao_vinculado",
    "paginacao",
    "freshness",
    "parser",
    "deduplicacao",
    "filtro",
    "diario_oficial",
    "portal_proprio",
    "publicacao_ainda_ausente",
    "falso_positivo",
    "fora_do_universo",
    "desconhecido",
)

COMPARABLE_FIELDS = (
    "url",
    "objeto",
    "ente",
    "modalidade",
    "published_at",
)

class AlertaImportError(ValueError):
    """Fail-closed import / reconcile error. Never shrinks misses."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_payload(obj: Any) -> str:
    return sha256_bytes(_canonical_json(obj).encode("utf-8"))


def compute_import_id(*, file_sha256: str, layout_version: str = LAYOUT_VERSION) -> str:
    """Deterministic import identity: same file bytes + layout → same id."""
    if not file_sha256 or len(file_sha256) != 64:
        raise AlertaImportError("file_sha256 must be a 64-char hex digest")
    material = f"{layout_version}:{file_sha256}".encode()
    return hashlib.sha256(material).hexdigest()


def _fold(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _norm_identity(row: dict[str, Any]) -> str:
    original = _fold(row.get("original_id") or row.get("identificador") or row.get("id"))
    if original:
        return original
    url = _fold(row.get("url"))
    if url:
        return f"url:{url}"
    composite = "|".join(
        (
            _fold(row.get("ente")),
            _fold(row.get("objeto")),
            _fold(row.get("published_at") or row.get("data")),
            _fold(row.get("modalidade")),
        )
    )
    if composite.strip("|"):
        return f"composite:{sha256_payload(composite)[:16]}"
    raise AlertaImportError("row is missing identifier, url and composite fields")


@dataclass(frozen=True)
class AlertaRow:
    original_id: str
    url: str | None
    objeto: str | None
    ente: str | None
    modalidade: str | None
    published_at: str | None
    municipio: str | None
    esfera: str | None
    natureza_objeto: str | None
    source_platform: str | None
    in_universe: bool
    extras: dict[str, Any] = field(default_factory=dict)
    provenance: str = PROVENANCE

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(frozen=True)
class ExtraRow:
    identity: str
    url: str | None = None
    objeto: str | None = None
    ente: str | None = None
    modalidade: str | None = None
    published_at: str | None = None
    municipio: str | None = None
    esfera: str | None = None
    natureza_objeto: str | None = None
    source_platform: str | None = None
    in_universe: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImportResult:
    import_id: str
    file_sha256: str
    layout_version: str
    filename: str
    imported_at: str
    row_count: int
    rows: tuple[AlertaRow, ...]
    row_hashes: tuple[str, ...]
    content_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "import_id": self.import_id,
            "file_sha256": self.file_sha256,
            "layout_version": self.layout_version,
            "filename": self.filename,
            "imported_at": self.imported_at,
            "row_count": self.row_count,
            "content_hash": self.content_hash,
            "row_hashes": list(self.row_hashes),
            "rows": [row.as_dict() for row in self.rows],
            "provenance": PROVENANCE,
        }


@dataclass(frozen=True)
class ReconcileDecision:
    identity: str
    state: ReconcileState
    alerta: AlertaRow | None
    extra: ExtraRow | None
    differing_fields: tuple[str, ...] = ()
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "state": self.state,
            "alerta": None if self.alerta is None else self.alerta.as_dict(),
            "extra": None if self.extra is None else self.extra.as_dict(),
            "differing_fields": list(self.differing_fields),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GapRecord:
    identity: str
    gap_type: str
    probable_cause: str
    evidence: str
    next_action: str
    public_source_attempted: bool
    ente: str | None
    source_platform: str | None
    municipio: str | None
    esfera: str | None
    modalidade: str | None
    natureza_objeto: str | None
    business_relevance: float
    reuse_factor: float
    implementation_effort: float
    fragility: float
    expected_unique_recall_gain: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterRank:
    adapter_key: str
    n_misses: int
    expected_unique_recall_gain: float
    business_relevance: float
    reuse_factor: float
    implementation_effort: float
    score: float
    uncertainty: str
    snapshot_ref: str
    components: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReconciliationReport:
    import_id: str
    window_start: str
    window_end: str
    filter_hash: str
    decisions: tuple[ReconcileDecision, ...]
    gaps: tuple[GapRecord, ...]
    ranking: tuple[AdapterRank, ...]
    counts: dict[str, int]
    closed: bool
    blockers: tuple[str, ...]
    report_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "import_id": self.import_id,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "filter_hash": self.filter_hash,
            "counts": dict(self.counts),
            "closed": self.closed,
            "blockers": list(self.blockers),
            "report_hash": self.report_hash,
            "decisions": [d.as_dict() for d in self.decisions],
            "gaps": [g.as_dict() for g in self.gaps],
            "ranking": [r.as_dict() for r in self.ranking],
            "alerta_is_absolute_truth": False,
        }


def _row_from_mapping(raw: dict[str, Any]) -> AlertaRow:
    aliases = {
        "identificador": "original_id",
        "id": "original_id",
        "link": "url",
        "objeto_compra": "objeto",
        "orgao": "ente",
        "data": "published_at",
        "data_publicacao": "published_at",
        "plataforma": "source_platform",
        "fonte": "source_platform",
    }
    normalized: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for key, value in raw.items():
        folded = _fold(key).replace(" ", "_")
        dest = aliases.get(folded, folded)
        if dest in {
            "original_id",
            "url",
            "objeto",
            "ente",
            "modalidade",
            "published_at",
            "municipio",
            "esfera",
            "natureza_objeto",
            "source_platform",
            "in_universe",
        }:
            normalized[dest] = value
        else:
            extras[dest] = value
    original = str(normalized.get("original_id") or "").strip()
    if not original:
        original = _norm_identity({**normalized, **extras})
    in_universe = normalized.get("in_universe", True)
    if isinstance(in_universe, str):
        in_universe = in_universe.strip().lower() not in {"0", "false", "nao", "não", "no"}
    return AlertaRow(
        original_id=original,
        url=(str(normalized["url"]).strip() or None) if normalized.get("url") else None,
        objeto=(str(normalized["objeto"]).strip() or None) if normalized.get("objeto") else None,
        ente=(str(normalized["ente"]).strip() or None) if normalized.get("ente") else None,
        modalidade=(str(normalized["modalidade"]).strip() or None)
        if normalized.get("modalidade")
        else None,
        published_at=(str(normalized["published_at"]).strip() or None)
        if normalized.get("published_at")
        else None,
        municipio=(str(normalized["municipio"]).strip() or None)
        if normalized.get("municipio")
        else None,
        esfera=(str(normalized["esfera"]).strip() or None) if normalized.get("esfera") else None,
        natureza_objeto=(str(normalized["natureza_objeto"]).strip() or None)
        if normalized.get("natureza_objeto")
        else None,
        source_platform=(str(normalized["source_platform"]).strip() or None)
        if normalized.get("source_platform")
        else None,
        in_universe=bool(in_universe),
        extras=extras,
    )


def _parse_json_rows(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8-sig")
    stripped = text.lstrip()
    if stripped.startswith("["):
        payload = json.loads(stripped)
        if not isinstance(payload, list):
            raise AlertaImportError("JSON array import must be a list of objects")
        return [dict(item) for item in payload]
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AlertaImportError(f"invalid JSONL at line {line_no}: {exc}") from exc
        if not isinstance(item, dict):
            raise AlertaImportError(f"JSONL line {line_no} is not an object")
        rows.append(item)
    return rows


def _parse_csv_rows(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise AlertaImportError("CSV import has no header")
    return [dict(row) for row in reader]


def parse_tabular_rows(raw: bytes, filename: str) -> list[dict[str, Any]]:
    """Narrow I/O adapter. Decision logic never depends on a mocked parser.

    Binary Excel layouts (.xls/.xlsx) fail closed unless a registered parser
    is present. Golden fixtures and ops snapshots use JSON/CSV/JSONL so the
    import/reconcile contract stays deterministic without XML parsers.
    """
    name = filename.rsplit("/", 1)[-1].casefold()
    if not raw:
        raise AlertaImportError("empty AlertaLicitação payload")
    if name.endswith((".json", ".jsonl")):
        return _parse_json_rows(raw)
    if name.endswith(".csv"):
        return _parse_csv_rows(raw)
    if name.endswith((".xls", ".xlsx")):
        raise AlertaImportError(
            "unknown or unsupported Excel layout without a registered parser; "
            "export to csv/jsonl or register a layout adapter"
        )
    raise AlertaImportError(f"unknown AlertaLicitação layout for {filename}")


def import_alerta(
    raw: bytes,
    *,
    filename: str,
    imported_at: str | None = None,
    layout_version: str = LAYOUT_VERSION,
) -> ImportResult:
    """Immutable import: same bytes + layout yield the same import_id and hashes."""
    file_sha = sha256_bytes(raw)
    import_id = compute_import_id(file_sha256=file_sha, layout_version=layout_version)
    mappings = parse_tabular_rows(raw, filename)
    rows = tuple(_row_from_mapping(item) for item in mappings)
    if not rows:
        raise AlertaImportError("import produced zero rows")
    seen: set[str] = set()
    for row in rows:
        if not row.original_id:
            raise AlertaImportError("imported row lost its original identifier")
        if row.provenance != PROVENANCE:
            raise AlertaImportError("imported row lost alertalicitacao provenance")
        seen.add(row.original_id)
    row_hashes = tuple(sha256_payload(row.as_dict()) for row in rows)
    return ImportResult(
        import_id=import_id,
        file_sha256=file_sha,
        layout_version=layout_version,
        filename=Path(filename).name,
        imported_at=imported_at or _utc_now(),
        row_count=len(rows),
        rows=rows,
        row_hashes=row_hashes,
        content_hash=sha256_payload(list(row_hashes)),
    )


def import_alerta_path(path: str | Path, *, imported_at: str | None = None) -> ImportResult:
    file_path = Path(path)
    return import_alerta(file_path.read_bytes(), filename=file_path.name, imported_at=imported_at)


def _index_alerta(rows: tuple[AlertaRow, ...]) -> dict[str, list[AlertaRow]]:
    index: dict[str, list[AlertaRow]] = defaultdict(list)
    for row in rows:
        index[row.original_id].append(row)
    return index


def _index_extra(rows: tuple[ExtraRow, ...]) -> dict[str, list[ExtraRow]]:
    index: dict[str, list[ExtraRow]] = defaultdict(list)
    for row in rows:
        if not row.identity:
            raise AlertaImportError("extra-cli row missing identity")
        index[row.identity].append(row)
    return index


def _field_diffs(alerta: AlertaRow, extra: ExtraRow) -> tuple[str, ...]:
    diffs: list[str] = []
    for field_name in COMPARABLE_FIELDS:
        left = _fold(getattr(alerta, field_name))
        right = _fold(getattr(extra, field_name))
        if left and right and left != right:
            diffs.append(field_name)
    return tuple(diffs)


def classify_gap(row: AlertaRow, *, registered_sources: frozenset[str]) -> GapRecord:
    """Assign a public-source resolution attempt and a conservative cause."""
    platform = _fold(row.source_platform)
    if not row.in_universe:
        gap_type = "fora_do_universo"
        cause = "linha fora do universo canônico da Extra"
        action = "excluir do ranking de adapter; manter no relatório de fora-de-universo"
    elif platform in {"dou", "diario oficial", "diario_oficial"}:
        gap_type = "diario_oficial"
        cause = "publicação observada em diário oficial sem adapter operacional"
        action = "medir ganho de um adapter de diário antes de implementar"
    elif platform in {"portal_proprio", "portal próprio", "transparencia", "transparência"}:
        gap_type = "portal_proprio"
        cause = "publicação em portal próprio do ente"
        action = "aguardar ranking #346 antes de novo adapter de portal"
    elif platform and platform not in registered_sources:
        gap_type = "fonte_nao_cadastrada"
        cause = f"plataforma '{row.source_platform}' ausente do cadastro de fontes"
        action = "cadastrar a fonte e reabrir VALIDATE do adapter"
    elif platform and platform in registered_sources:
        gap_type = "adapter_inexistente"
        cause = "fonte cadastrada sem adapter operacional para este miss"
        action = "priorizar adapter pelo ranking de ganho marginal"
    elif not row.ente:
        gap_type = "ente_nao_vinculado"
        cause = "ente ausente ou não vinculado ao universo"
        action = "vincular ente antes de atribuir miss ao crawler"
    else:
        gap_type = "desconhecido"
        cause = "causa não atribuível sem evidência adicional"
        action = "manter unresolved operacional até nova evidência"
    if gap_type not in GAP_TYPES:
        raise AlertaImportError(f"illegal gap_type {gap_type}")
    relevance = 1.0 if row.in_universe else 0.0
    reuse = 0.7 if gap_type in {"adapter_inexistente", "fonte_nao_cadastrada", "portal_proprio"} else 0.3
    effort = 2.0 if gap_type in {"paginacao", "freshness", "filtro"} else 5.0
    gain = 1.0 if row.in_universe else 0.0
    return GapRecord(
        identity=row.original_id,
        gap_type=gap_type,
        probable_cause=cause,
        evidence=f"alerta_only:{row.original_id}:url={row.url or ''}:platform={row.source_platform or ''}",
        next_action=action,
        public_source_attempted=True,
        ente=row.ente,
        source_platform=row.source_platform,
        municipio=row.municipio,
        esfera=row.esfera,
        modalidade=row.modalidade,
        natureza_objeto=row.natureza_objeto,
        business_relevance=relevance,
        reuse_factor=reuse,
        implementation_effort=effort,
        fragility=0.4,
        expected_unique_recall_gain=gain,
    )


def _rank_from_gaps(gaps: tuple[GapRecord, ...], snapshot_ref: str) -> tuple[AdapterRank, ...]:
    grouped: dict[str, list[GapRecord]] = defaultdict(list)
    for gap in gaps:
        if gap.gap_type == "fora_do_universo":
            continue
        key = gap.source_platform or gap.gap_type
        grouped[key].append(gap)
    ranks: list[AdapterRank] = []
    for key, items in grouped.items():
        gain = sum(g.expected_unique_recall_gain for g in items)
        relevance = sum(g.business_relevance for g in items) / len(items)
        reuse = max(g.reuse_factor for g in items)
        effort = min(g.implementation_effort for g in items)
        if effort <= 0:
            raise AlertaImportError("implementation_effort must be > 0")
        score = (gain * relevance * reuse) / effort
        ranks.append(
            AdapterRank(
                adapter_key=key,
                n_misses=len(items),
                expected_unique_recall_gain=gain,
                business_relevance=relevance,
                reuse_factor=reuse,
                implementation_effort=effort,
                score=score,
                uncertainty="components_explicit;alerta_not_ground_truth",
                snapshot_ref=snapshot_ref,
                components={
                    "expected_unique_recall_gain": gain,
                    "business_relevance": relevance,
                    "reuse_factor": reuse,
                    "implementation_effort": effort,
                },
            )
        )
    ranks.sort(key=lambda r: (-r.score, -r.n_misses, r.adapter_key))
    return tuple(ranks)


def reconcile(
    imported: ImportResult,
    extra_rows: tuple[ExtraRow, ...],
    *,
    window_start: str,
    window_end: str,
    filters: dict[str, Any] | None = None,
    registered_sources: frozenset[str] | None = None,
) -> ReconciliationReport:
    """Reconcile one imported snapshot with extra-cli findings on the same window."""
    if not window_start or not window_end:
        raise AlertaImportError("window_start and window_end are required")
    if window_end < window_start:
        raise AlertaImportError("window is not equivalent: window_end precedes window_start")
    sources = registered_sources or frozenset()
    alerta_idx = _index_alerta(imported.rows)
    extra_idx = _index_extra(extra_rows)
    identities = sorted(set(alerta_idx) | set(extra_idx))
    decisions: list[ReconcileDecision] = []
    for identity in identities:
        alerta_hits = alerta_idx.get(identity, [])
        extra_hits = extra_idx.get(identity, [])
        if len(alerta_hits) > 1 or len(extra_hits) > 1:
            decisions.append(
                ReconcileDecision(
                    identity=identity,
                    state="unresolved",
                    alerta=alerta_hits[0] if alerta_hits else None,
                    extra=extra_hits[0] if extra_hits else None,
                    reason="ambiguous_identity_multiple_rows",
                )
            )
            continue
        if alerta_hits and extra_hits:
            diffs = _field_diffs(alerta_hits[0], extra_hits[0])
            state: ReconcileState = "matched_with_difference" if diffs else "found_both"
            decisions.append(
                ReconcileDecision(
                    identity=identity,
                    state=state,
                    alerta=alerta_hits[0],
                    extra=extra_hits[0],
                    differing_fields=diffs,
                )
            )
            continue
        if alerta_hits:
            decisions.append(
                ReconcileDecision(
                    identity=identity,
                    state="alerta_only",
                    alerta=alerta_hits[0],
                    extra=None,
                )
            )
            continue
        decisions.append(
            ReconcileDecision(
                identity=identity,
                state="extra_only",
                alerta=None,
                extra=extra_hits[0],
            )
        )

    counts = Counter(d.state for d in decisions)
    expected_states = {
        "found_both",
        "extra_only",
        "alerta_only",
        "matched_with_difference",
        "unresolved",
    }
    blockers: list[str] = []
    if set(counts) - expected_states:
        blockers.append("illegal_reconcile_state")
    alerta_accounted = (
        counts["found_both"]
        + counts["alerta_only"]
        + counts["matched_with_difference"]
        + sum(1 for d in decisions if d.state == "unresolved" and d.alerta is not None)
    )
    extra_accounted = (
        counts["found_both"]
        + counts["extra_only"]
        + counts["matched_with_difference"]
        + sum(1 for d in decisions if d.state == "unresolved" and d.extra is not None)
    )
    # Unique imported identities (duplicate original_id already unresolved)
    unique_alerta = len(alerta_idx)
    unique_extra = len(extra_idx)
    if alerta_accounted != unique_alerta:
        blockers.append(
            f"alerta_totals_do_not_close:{alerta_accounted}!={unique_alerta}"
        )
    if extra_accounted != unique_extra:
        blockers.append(f"extra_totals_do_not_close:{extra_accounted}!={unique_extra}")
    if len(decisions) != len(identities):
        blockers.append("decision_count_mismatch")

    gaps = tuple(
        classify_gap(d.alerta, registered_sources=sources)
        for d in decisions
        if d.state == "alerta_only" and d.alerta is not None
    )
    snapshot_ref = f"{imported.filename}:{imported.import_id[:12]}"
    ranking = _rank_from_gaps(gaps, snapshot_ref)
    payload = {
        "import_id": imported.import_id,
        "window_start": window_start,
        "window_end": window_end,
        "filters": filters or {},
        "counts": dict(counts),
        "decisions": [d.as_dict() for d in decisions],
        "gaps": [g.as_dict() for g in gaps],
        "ranking": [r.as_dict() for r in ranking],
    }
    report = ReconciliationReport(
        import_id=imported.import_id,
        window_start=window_start,
        window_end=window_end,
        filter_hash=sha256_payload(filters or {}),
        decisions=tuple(decisions),
        gaps=gaps,
        ranking=ranking,
        counts=dict(counts),
        closed=not blockers,
        blockers=tuple(blockers),
        report_hash=sha256_payload(payload),
    )
    if blockers:
        raise AlertaImportError(";".join(blockers))
    return report
