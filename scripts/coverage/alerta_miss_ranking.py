"""#346 — immutable AlertaLicitação import, conservative reconcile, miss ranking.

AlertaLicitação is a complementary external snapshot, never absolute truth.
Unknown layout, non-equivalent windows, or totals that do not close block
measurement. Ambiguous matches stay unresolved; weak similarity never merges.

This module is the fail-closed core of issue #346. It does not implement
adapters, retire the XLS, or claim parity with extra-cli crawlers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

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

# Conservative host → platform map. Unknown hosts stay unresolved, never guessed.
HOST_PLATFORM = {
    "bnc.org.br": "bnc",
    "www.bnc.org.br": "bnc",
    "in.gov.br": "dou",
    "www.in.gov.br": "dou",
    "e-publica.net": "e-publica",
    "www.e-publica.net": "e-publica",
    "bll.org.br": "bll",
    "www.bll.org.br": "bll",
    "bllcompras.com": "bll",
    "www.bllcompras.com": "bll",
    "pncp.gov.br": "pncp",
    "www.pncp.gov.br": "pncp",
    "joinville.sc.gov.br": "joinville",
    "www.joinville.sc.gov.br": "joinville",
}

OWN_PORTAL_PLATFORMS = frozenset({"portal_proprio", "portal próprio", "transparencia", "transparência", "joinville"})
DIARIO_PLATFORMS = frozenset({"dou", "diario oficial", "diario_oficial"})

# Nominal historical seeds preserved from issues #331–#335 and #261.
# claimed_count is the issue prose, not a measured denominator.
HISTORICAL_SEEDS: tuple[dict[str, Any], ...] = (
    {"identity": "BNC-331", "issue": 331, "label": "BNC", "claimed_count": 34},
    {"identity": "DOU-332", "issue": 332, "label": "DOU", "claimed_count": 14},
    {"identity": "MUN-333", "issue": 333, "label": "portais_municipais", "claimed_count": 2},
    {"identity": "JOI-334", "issue": 334, "label": "Joinville", "claimed_count": 3},
    {"identity": "EPUB-335", "issue": 335, "label": "e-Publica", "claimed_count": 2},
    {"identity": "BLL-261", "issue": 261, "label": "BLL", "claimed_count": 23},
)

RELEVANT_GAP_EXCLUSIONS = frozenset({"fora_do_universo", "falso_positivo"})


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
class PublicSourceResolution:
    attempted: bool
    method: str
    host: str | None
    resolved_platform: str | None
    declared_platform: str | None
    registered: bool
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    resolution: PublicSourceResolution | None = None
    valor: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.resolution is not None:
            payload["resolution"] = self.resolution.as_dict()
        return payload


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
        executive = build_executive(self)
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
            "historical_seeds": executive["historical_seeds"],
            "alerta_is_absolute_truth": False,
            "denominator": executive["denominator"],
            "matched": executive["matched"],
            "alerta_only_relevant": executive["alerta_only_relevant"],
            "false_positives": executive["false_positives"],
            "unknown": executive["unknown"],
            "affected_value": executive["affected_value"],
            "affected_accounts": executive["affected_accounts"],
            "expected_marginal_gain": executive["expected_marginal_gain"],
            "next_source": executive["next_source"],
            "xls_197_status": executive["xls_197_status"],
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
        modalidade=(str(normalized["modalidade"]).strip() or None) if normalized.get("modalidade") else None,
        published_at=(str(normalized["published_at"]).strip() or None) if normalized.get("published_at") else None,
        municipio=(str(normalized["municipio"]).strip() or None) if normalized.get("municipio") else None,
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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_extra_rows(raw: bytes, filename: str) -> tuple[ExtraRow, ...]:
    """Parse the extra-cli side of a versioned window from JSON/CSV/JSONL."""
    if not raw.strip():
        return ()
    mappings = parse_tabular_rows(raw, filename)
    rows: list[ExtraRow] = []
    for item in mappings:
        identity = str(item.get("identity") or item.get("original_id") or item.get("id") or "").strip()
        if not identity:
            raise AlertaImportError("extra-cli row missing identity")
        in_universe = item.get("in_universe", True)
        if isinstance(in_universe, str):
            in_universe = in_universe.strip().lower() not in {"0", "false", "nao", "não", "no"}
        rows.append(
            ExtraRow(
                identity=identity,
                url=_optional_text(item.get("url") or item.get("link")),
                objeto=_optional_text(item.get("objeto") or item.get("objeto_compra")),
                ente=_optional_text(item.get("ente") or item.get("orgao")),
                modalidade=_optional_text(item.get("modalidade")),
                published_at=_optional_text(
                    item.get("published_at") or item.get("data") or item.get("data_publicacao")
                ),
                municipio=_optional_text(item.get("municipio")),
                esfera=_optional_text(item.get("esfera")),
                natureza_objeto=_optional_text(item.get("natureza_objeto")),
                source_platform=_optional_text(
                    item.get("source_platform") or item.get("plataforma") or item.get("fonte")
                ),
                in_universe=bool(in_universe),
            )
        )
    return tuple(rows)


def _published_day(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text or None


def row_in_window(published_at: str | None, window_start: str, window_end: str) -> bool:
    """Missing date stays in-window so measurement never shrinks misses."""
    day = _published_day(published_at)
    if day is None:
        return True
    return window_start <= day <= window_end


def resolve_public_source(row: AlertaRow, *, registered_sources: frozenset[str]) -> PublicSourceResolution:
    """Deterministic public-source attempt: URL host, then declared platform.

    This is not a live crawl. Unmapped hosts remain unmapped.
    """
    host: str | None = None
    resolved: str | None = _fold(row.source_platform) or None
    method = "declared_platform" if resolved else "unresolved_no_url_or_platform"
    if row.url:
        parsed = urlparse(row.url)
        host = (parsed.hostname or "").casefold() or None
        mapped = HOST_PLATFORM.get(host or "")
        if mapped:
            method = "url_host"
            resolved = mapped
        elif host and host.endswith(".gov.br") and not resolved:
            method = "url_host_govbr"
            resolved = "portal_proprio"
        elif host and not mapped and resolved:
            method = "declared_platform_url_unmapped"
        elif host and not mapped:
            method = "url_host_unmapped"
    registered = bool(resolved and resolved in registered_sources)
    return PublicSourceResolution(
        attempted=True,
        method=method,
        host=host,
        resolved_platform=resolved,
        declared_platform=row.source_platform,
        registered=registered,
        evidence=(
            f"method={method};host={host or ''};resolved={resolved or ''};"
            f"declared={row.source_platform or ''};url={row.url or ''};registered={registered}"
        ),
    )


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


def _is_marked_false_positive(row: AlertaRow) -> bool:
    marker = row.extras.get("false_positive", row.extras.get("falso_positivo"))
    if isinstance(marker, bool):
        return marker
    if isinstance(marker, str):
        return marker.strip().lower() in {"1", "true", "sim", "yes"}
    return False


def _row_valor(row: AlertaRow) -> str | None:
    for key in ("valor", "value", "valor_estimado", "affected_value"):
        if key in row.extras and row.extras[key] not in (None, ""):
            return str(row.extras[key])
    return None


def classify_gap(row: AlertaRow, *, registered_sources: frozenset[str]) -> GapRecord:
    """Assign a public-source resolution attempt and a conservative cause."""
    resolution = resolve_public_source(row, registered_sources=registered_sources)
    platform = _fold(resolution.resolved_platform or row.source_platform)
    if _is_marked_false_positive(row):
        gap_type = "falso_positivo"
        cause = "marcação explícita de falso positivo no snapshot versionado"
        action = "não promover adapter; auditar origem do falso positivo"
    elif not row.in_universe:
        gap_type = "fora_do_universo"
        cause = "linha fora do universo canônico da Extra"
        action = "excluir do ranking de adapter; manter no relatório de fora-de-universo"
    elif platform in DIARIO_PLATFORMS:
        gap_type = "diario_oficial"
        cause = "publicação observada em diário oficial sem adapter operacional"
        action = "medir ganho de um adapter de diário antes de implementar"
    elif platform in OWN_PORTAL_PLATFORMS or resolution.method == "url_host_govbr":
        gap_type = "portal_proprio"
        cause = "publicação em portal próprio do ente"
        action = "aguardar ranking #346 antes de novo adapter de portal"
    elif platform and platform not in registered_sources:
        gap_type = "fonte_nao_cadastrada"
        cause = f"plataforma '{resolution.resolved_platform or row.source_platform}' ausente do cadastro de fontes"
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
    commercially_relevant = row.in_universe and gap_type not in RELEVANT_GAP_EXCLUSIONS
    relevance = 1.0 if commercially_relevant else 0.0
    reuse = 0.7 if gap_type in {"adapter_inexistente", "fonte_nao_cadastrada", "portal_proprio"} else 0.3
    effort = 2.0 if gap_type in {"paginacao", "freshness", "filtro"} else 5.0
    gain = 1.0 if commercially_relevant else 0.0
    return GapRecord(
        identity=row.original_id,
        gap_type=gap_type,
        probable_cause=cause,
        evidence=(
            f"alerta_only:{row.original_id}:url={row.url or ''}:"
            f"platform={row.source_platform or ''}:{resolution.evidence}"
        ),
        next_action=action,
        public_source_attempted=resolution.attempted,
        ente=row.ente,
        source_platform=resolution.resolved_platform or row.source_platform,
        municipio=row.municipio,
        esfera=row.esfera,
        modalidade=row.modalidade,
        natureza_objeto=row.natureza_objeto,
        business_relevance=relevance,
        reuse_factor=reuse,
        implementation_effort=effort,
        fragility=0.4,
        expected_unique_recall_gain=gain,
        resolution=resolution,
        valor=_row_valor(row),
    )


def _rank_from_gaps(gaps: tuple[GapRecord, ...], snapshot_ref: str) -> tuple[AdapterRank, ...]:
    grouped: dict[str, list[GapRecord]] = defaultdict(list)
    for gap in gaps:
        if gap.gap_type in RELEVANT_GAP_EXCLUSIONS:
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
        score = round((gain * relevance * reuse) / effort, 10)
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
    windowed_alerta = tuple(row for row in imported.rows if row_in_window(row.published_at, window_start, window_end))
    windowed_extra = tuple(row for row in extra_rows if row_in_window(row.published_at, window_start, window_end))
    if not windowed_alerta and not windowed_extra:
        raise AlertaImportError("window filter produced zero identities on both sides")
    alerta_idx = _index_alerta(windowed_alerta)
    extra_idx = _index_extra(windowed_extra)
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
        blockers.append(f"alerta_totals_do_not_close:{alerta_accounted}!={unique_alerta}")
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


def _historical_relevance(state: str, gap: GapRecord | None) -> str:
    if state == "unresolved":
        return "unresolved"
    if state in {"found_both", "matched_with_difference", "extra_only"}:
        return "no-longer-relevant"
    if gap is not None and gap.gap_type == "fora_do_universo":
        return "out-of-universe"
    if gap is not None and gap.gap_type == "falso_positivo":
        return "false-positive"
    if state == "alerta_only":
        return "still-relevant"
    return "unresolved"


def classify_historical_seeds(report: ReconciliationReport) -> list[dict[str, Any]]:
    """Classify each preserved historical seed from the live reconcile, not old prose."""
    by_identity = {d.identity: d for d in report.decisions}
    gaps = {g.identity: g for g in report.gaps}
    records: list[dict[str, Any]] = []
    for seed in HISTORICAL_SEEDS:
        identity = str(seed["identity"])
        decision = by_identity.get(identity)
        if decision is None:
            records.append(
                {
                    **seed,
                    "state": "missing",
                    "gap_type": None,
                    "relevance": "silently_dropped",
                    "evidence": "historical seed absent from windowed reconcile",
                    "corpus_count": 0,
                }
            )
            continue
        gap = gaps.get(identity)
        records.append(
            {
                **seed,
                "state": decision.state,
                "gap_type": None if gap is None else gap.gap_type,
                "relevance": _historical_relevance(decision.state, gap),
                "evidence": (
                    gap.evidence if gap is not None else f"state={decision.state};reason={decision.reason or ''}"
                ),
                "corpus_count": 1,
            }
        )
    return records


def build_executive(report: ReconciliationReport) -> dict[str, Any]:
    """Executive counts derived from the same reconcile path. Value is UNKNOWN unless present."""
    denom_alerta = sum(1 for d in report.decisions if d.alerta is not None)
    matched = report.counts.get("found_both", 0) + report.counts.get("matched_with_difference", 0)
    relevant_gaps = [g for g in report.gaps if g.gap_type not in RELEVANT_GAP_EXCLUSIONS and g.business_relevance > 0]
    false_positives = sum(1 for g in report.gaps if g.gap_type == "falso_positivo")
    unknown = report.counts.get("unresolved", 0) + sum(1 for g in report.gaps if g.gap_type == "desconhecido")
    valores = [g.valor for g in relevant_gaps if g.valor]
    if valores and len(valores) == len(relevant_gaps):
        affected_value: str | float = "observed:" + ",".join(valores)
    else:
        affected_value = "UNKNOWN"
    accounts = sorted({g.ente for g in relevant_gaps if g.ente})
    affected_accounts: str | list[str] = accounts if accounts else "UNKNOWN"
    top = report.ranking[0] if report.ranking else None
    return {
        "denominator": denom_alerta,
        "matched": matched,
        "alerta_only_relevant": len(relevant_gaps),
        "false_positives": false_positives,
        "unknown": unknown,
        "affected_value": affected_value,
        "affected_accounts": affected_accounts,
        "expected_marginal_gain": 0.0 if top is None else top.score,
        "next_source": None if top is None else top.adapter_key,
        "xls_197_status": "UNKNOWN",
        "historical_seeds": classify_historical_seeds(report),
    }


def run_measurement(
    alerta_raw: bytes,
    extra_raw: bytes,
    *,
    alerta_filename: str,
    extra_filename: str,
    window_start: str,
    window_end: str,
    filters: dict[str, Any] | None = None,
    registered_sources: frozenset[str] | None = None,
    imported_at: str | None = None,
) -> ReconciliationReport:
    """Single shipped path: bytes → import → extra parse → reconcile → rank."""
    imported = import_alerta(alerta_raw, filename=alerta_filename, imported_at=imported_at)
    extra = parse_extra_rows(extra_raw, extra_filename)
    return reconcile(
        imported,
        extra,
        window_start=window_start,
        window_end=window_end,
        filters=filters,
        registered_sources=registered_sources,
    )


def write_ranking_csv(report: ReconciliationReport, path: Path) -> None:
    fieldnames = [
        "rank",
        "adapter_key",
        "n_misses",
        "expected_unique_recall_gain",
        "business_relevance",
        "reuse_factor",
        "implementation_effort",
        "score",
        "uncertainty",
        "snapshot_ref",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, rank in enumerate(report.ranking, start=1):
            writer.writerow(
                {
                    "rank": index,
                    "adapter_key": rank.adapter_key,
                    "n_misses": rank.n_misses,
                    "expected_unique_recall_gain": rank.expected_unique_recall_gain,
                    "business_relevance": rank.business_relevance,
                    "reuse_factor": rank.reuse_factor,
                    "implementation_effort": rank.implementation_effort,
                    "score": rank.score,
                    "uncertainty": rank.uncertainty,
                    "snapshot_ref": rank.snapshot_ref,
                }
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.coverage.alerta_miss_ranking",
        description=(
            "Immutable AlertaLicitação import + conservative reconcile + miss ranking. "
            "AlertaLicitação is not ground truth."
        ),
    )
    parser.add_argument("--alerta", required=True, help="Alerta snapshot (jsonl/json/csv)")
    parser.add_argument("--extra", required=True, help="extra-cli window fixture (jsonl/json/csv)")
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument(
        "--registered-sources",
        default="pncp,ciga",
        help="Comma-separated registered source slugs",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Versioned filter key=value (repeatable). Recorded, not used to invent drops.",
    )
    parser.add_argument("--output", required=True, help="Executive report JSON path")
    parser.add_argument("--csv", default=None, help="Optional ranking CSV path")
    parser.add_argument("--imported-at", default=None)
    return parser


def _parse_filters(items: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise AlertaImportError(f"filter must be key=value: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise AlertaImportError(f"filter key is empty: {item}")
        filters[key] = value.strip()
    return filters


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    alerta_path = Path(args.alerta)
    extra_path = Path(args.extra)
    registered = frozenset(part.strip() for part in args.registered_sources.split(",") if part.strip())
    report = run_measurement(
        alerta_path.read_bytes(),
        extra_path.read_bytes(),
        alerta_filename=alerta_path.name,
        extra_filename=extra_path.name,
        window_start=args.window_start,
        window_end=args.window_end,
        filters=_parse_filters(args.filter),
        registered_sources=registered,
        imported_at=args.imported_at,
    )
    payload = report.as_dict()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.csv:
        write_ranking_csv(report, Path(args.csv))
    summary = {
        "import_id": report.import_id,
        "report_hash": report.report_hash,
        "denominator": payload["denominator"],
        "matched": payload["matched"],
        "alerta_only_relevant": payload["alerta_only_relevant"],
        "false_positives": payload["false_positives"],
        "unknown": payload["unknown"],
        "affected_value": payload["affected_value"],
        "affected_accounts": payload["affected_accounts"],
        "expected_marginal_gain": payload["expected_marginal_gain"],
        "next_source": payload["next_source"],
        "alerta_is_absolute_truth": False,
        "xls_197_status": payload["xls_197_status"],
        "output": str(output),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
