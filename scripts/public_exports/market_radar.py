"""Build the public Market Radar projection from the persisted PNCP datalake.

This producer is deliberately one way: a read-only, repeatable-read PostgreSQL
snapshot becomes an immutable, sanitized SQLite file.  The public web process
receives no PostgreSQL credential and cannot write the projection.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import decimal
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

POINTER_SCHEMA = "confenge.market-radar.pointer/v1"
SNAPSHOT_SCHEMA = "confenge.market-radar/v1"
PNCP_ID_RE = re.compile(r"^(\d{14})-2-(\d{6})/(\d{4})$")
DIGITS_14_RE = re.compile(r"^\d{14}$")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
CPF_LABEL_RE = re.compile(r"(?i)\bCPF\s*[:.-]?\s*\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b")
PHONE_LABEL_RE = re.compile(
    r"(?i)\b(?:tel(?:efone)?|cel(?:ular)?|whatsapp)\s*[:.-]?\s*"
    r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-.\s]?\d{4}\b"
)
LONG_IDENTIFIER_RE = re.compile(
    r"(?<!\d)(?:\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[-.\s]?\d{2}|"
    r"\d{2}[.\s-]?\d{3}[.\s-]?\d{3}[/\s-]?\d{4}[-.\s]?\d{2})(?!\d)"
)
FORMATTED_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?55[-.\s]*)?(?:\(\d{2}\)|\d{2}[-.\s])[-.\s]*"
    r"\d{4,5}[-.\s]+\d{4}(?!\d)"
)
SNAPSHOT_FILE_RE = re.compile(r"^snapshot-([0-9a-f]{64})\.sqlite$")
UF_CODES = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)
MAX_SOURCE_AGE = dt.timedelta(hours=48)
MAX_SOURCE_CLOCK_SKEW = dt.timedelta(minutes=5)
MIN_FREE_BYTES = 4 * 1024**3
VALUE_NOTE = (
    "A consolidação não distingue valor global, inicial ou estimado; "
    "os valores não são totalizados e não representam pagamentos."
)
LIMITATIONS = [
    "Recorte de contratos PNCP persistidos, com publicação original nos últimos 24 meses; não é cobertura censitária.",
    "Somente fornecedores pessoa jurídica (CNPJ) e registros classificados como VALID entram na projeção.",
    "Fim de vigência registrado é sinal para pesquisa, não confirmação de nova licitação ou renovação.",
    "A localização exibida é a unidade compradora e não prova o local de execução.",
    VALUE_NOTE,
]
REQUIRED_COLUMNS = {
    "id",
    "contrato_id",
    "orgao_cnpj",
    "orgao_nome",
    "fornecedor_cnpj",
    "fornecedor_nome",
    "objeto_contrato",
    "valor_total",
    "data_inicio",
    "data_fim",
    "data_publicacao_fonte",
    "uf",
    "municipio",
    "ingested_at",
    "is_active",
    "data_assinatura",
    "data_publicacao",
    "last_seen_at",
    "source_updated_at",
    "supplier_id_type",
    "status_normalized",
    "quality_state",
}
REQUIRED_COLUMN_TYPES = {
    "id": {"integer", "bigint"},
    "contrato_id": {"text"},
    "orgao_cnpj": {"text"},
    "orgao_nome": {"text"},
    "fornecedor_cnpj": {"text"},
    "fornecedor_nome": {"text"},
    "objeto_contrato": {"text"},
    "valor_total": {"numeric"},
    "data_inicio": {"date"},
    "data_fim": {"date"},
    "data_publicacao_fonte": {"date"},
    "data_assinatura": {"date"},
    "data_publicacao": {"date"},
    "uf": {"text"},
    "municipio": {"text"},
    "ingested_at": {"timestamp with time zone"},
    "last_seen_at": {"timestamp with time zone"},
    "source_updated_at": {"timestamp with time zone"},
    "supplier_id_type": {"text"},
    "status_normalized": {"text"},
    "quality_state": {"text"},
    "is_active": {"boolean"},
}

SCHEMA_SQL = """
PRAGMA user_version=1;
CREATE TABLE contracts (
    rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE CHECK(length(id)=24),
    object TEXT NOT NULL,
    buyer_id TEXT NOT NULL CHECK(length(buyer_id)=24),
    buyer_name TEXT NOT NULL,
    uf TEXT,
    city TEXT,
    supplier_id TEXT NOT NULL CHECK(length(supplier_id)=24),
    supplier_name TEXT NOT NULL,
    value_cents INTEGER,
    published_at TEXT NOT NULL,
    starts_at TEXT,
    ends_at TEXT,
    source_updated_at TEXT,
    source_url TEXT NOT NULL,
    expiry_eligible INTEGER NOT NULL CHECK(expiry_eligible IN (0,1))
);
CREATE INDEX contracts_published_idx ON contracts(published_at DESC, id);
CREATE INDEX contracts_uf_published_idx ON contracts(uf, published_at DESC, id);
CREATE INDEX contracts_buyer_idx ON contracts(buyer_id, published_at DESC, id);
CREATE INDEX contracts_supplier_idx ON contracts(supplier_id, published_at DESC, id);
CREATE INDEX contracts_expiry_idx ON contracts(expiry_eligible, ends_at, id);
CREATE INDEX contracts_value_idx ON contracts(value_cents DESC, id);
CREATE VIRTUAL TABLE contract_search USING fts5(
    object,
    content='contracts',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

UPSERT_SQL = """
INSERT INTO contracts (
  id, object, buyer_id, buyer_name, uf, city, supplier_id, supplier_name,
  value_cents, published_at, starts_at, ends_at, source_updated_at,
  source_url, expiry_eligible
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(id) DO UPDATE SET
  object=excluded.object,
  buyer_id=excluded.buyer_id,
  buyer_name=excluded.buyer_name,
  uf=excluded.uf,
  city=excluded.city,
  supplier_id=excluded.supplier_id,
  supplier_name=excluded.supplier_name,
  value_cents=excluded.value_cents,
  published_at=excluded.published_at,
  starts_at=excluded.starts_at,
  ends_at=excluded.ends_at,
  source_updated_at=excluded.source_updated_at,
  source_url=excluded.source_url,
  expiry_eligible=excluded.expiry_eligible
"""

SOURCE_SQL = """
SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
       objeto_contrato, valor_total, data_inicio, data_fim,
       data_publicacao_fonte, uf, municipio, source_updated_at,
       supplier_id_type, status_normalized, quality_state
FROM public.pncp_supplier_contracts
WHERE is_active
  AND supplier_id_type = 'CNPJ'
  AND quality_state = 'VALID'
  AND data_publicacao_fonte >= (%s::date - make_interval(months => %s))
  AND data_publicacao_fonte <= %s::date
ORDER BY contrato_id,
         source_updated_at ASC NULLS FIRST,
         last_seen_at ASC NULLS FIRST,
         id ASC
"""

COUNTS_SQL = """
SELECT
  count(*) FILTER (
    WHERE is_active
      AND COALESCE(data_publicacao_fonte, data_assinatura, data_publicacao)
          >= (%s::date - make_interval(months => %s))
      AND COALESCE(data_publicacao_fonte, data_assinatura, data_publicacao) <= %s::date
  ) AS candidate_rows,
  count(*) FILTER (
    WHERE is_active
      AND supplier_id_type = 'CNPJ'
      AND quality_state = 'VALID'
      AND data_publicacao_fonte >= (%s::date - make_interval(months => %s))
      AND data_publicacao_fonte <= %s::date
  ) AS qualified_rows,
  max(COALESCE(last_seen_at, ingested_at)) FILTER (
    WHERE is_active
      AND supplier_id_type = 'CNPJ'
      AND quality_state = 'VALID'
      AND data_publicacao_fonte >= (%s::date - make_interval(months => %s))
      AND data_publicacao_fonte <= %s::date
  ) AS ingestion_latest_at
FROM public.pncp_supplier_contracts
"""


class ExportError(RuntimeError):
    """The projection was refused before publication."""


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _date(value: Any) -> dt.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _opaque(kind: str, value: str) -> str:
    return hashlib.sha256(f"market-radar/v1:{kind}:{value}".encode()).hexdigest()[:24]


def sanitize_text(value: Any, *, limit: int) -> str:
    """Remove contact data that occasionally appears in public free text."""
    text = " ".join(str(value or "").replace("\x00", " ").split())
    text = EMAIL_RE.sub("[contato removido]", text)
    text = CPF_LABEL_RE.sub("[documento removido]", text)
    text = PHONE_LABEL_RE.sub("[contato removido]", text)
    text = FORMATTED_PHONE_RE.sub("[contato removido]", text)
    text = LONG_IDENTIFIER_RE.sub("[documento removido]", text)
    return text[:limit].strip()


def _value_cents(value: Any) -> tuple[int | None, bool]:
    """Return cents without claiming what monetary field produced the value."""
    if value is None or value == "":
        return None, False
    try:
        amount = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, ValueError):
        return None, True
    if not amount.is_finite() or amount < 0 or amount > decimal.Decimal("9000000000000000"):
        return None, True
    cents = int((amount * 100).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))
    return cents, False


def normalize_contract(row: Mapping[str, Any], *, today: dt.date) -> tuple[Any, ...] | None:
    """Apply the public allowlist. Raw identifiers never enter the tuple."""
    if str(row.get("supplier_id_type") or "").upper() != "CNPJ":
        return None
    if str(row.get("quality_state") or "").upper() != "VALID":
        return None
    match = PNCP_ID_RE.fullmatch(str(row.get("contrato_id") or "").strip())
    buyer_raw = re.sub(r"\D", "", str(row.get("orgao_cnpj") or ""))
    supplier_raw = re.sub(r"\D", "", str(row.get("fornecedor_cnpj") or ""))
    if (
        not match
        or not DIGITS_14_RE.fullmatch(buyer_raw)
        or not DIGITS_14_RE.fullmatch(supplier_raw)
        or buyer_raw != match.group(1)
    ):
        return None
    published = _date(row.get("data_publicacao_fonte"))
    if published is None:
        return None
    start = _date(row.get("data_inicio"))
    end = _date(row.get("data_fim"))
    status = str(row.get("status_normalized") or "").upper()
    expiry_eligible = int(
        status == "ACTIVE_PROVEN"
        and start is not None
        and end is not None
        and end >= today
        and start <= today
    )
    value_cents, _ = _value_cents(row.get("valor_total"))
    object_text = sanitize_text(row.get("objeto_contrato"), limit=2_000)
    buyer_name = sanitize_text(row.get("orgao_nome"), limit=300)
    supplier_name = sanitize_text(row.get("fornecedor_nome"), limit=300)
    if not object_text or not buyer_name or not supplier_name:
        return None
    official_id = match.group(0)
    source_url = (
        f"https://pncp.gov.br/app/contratos/{match.group(1)}/"
        f"{match.group(3)}/{int(match.group(2))}"
    )
    return (
        _opaque("contract", official_id),
        object_text,
        _opaque("buyer", buyer_raw),
        buyer_name,
        (
            uf
            if (uf := str(row.get("uf") or "").strip().upper()) in UF_CODES
            else None
        ),
        sanitize_text(row.get("municipio"), limit=100) or None,
        _opaque("supplier", supplier_raw),
        supplier_name,
        value_cents,
        published.isoformat(),
        start.isoformat() if start else None,
        end.isoformat() if end else None,
        _iso(row.get("source_updated_at")),
        source_url,
        expiry_eligible,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    """Make the completed SQLite bytes durable before publishing their name."""
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":  # Directory handles are not fsync-able on Windows.
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_pointer(path: Path, document: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".current-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            os.chmod(temporary, 0o440)
        elif path.exists():
            os.chmod(path, 0o600)
        os.replace(temporary, path)
        if os.name != "posix":
            os.chmod(path, 0o440)
        _fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def _current_snapshot(output_dir: Path) -> tuple[str | None, int | None]:
    """Return only a strictly validated local snapshot name and byte estimate."""
    pointer_path = output_dir / "current.json"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None, None
    name = pointer.get("file")
    size = pointer.get("bytes")
    if (
        pointer.get("schema") != POINTER_SCHEMA
        or not isinstance(name, str)
        or SNAPSHOT_FILE_RE.fullmatch(name) is None
        or not isinstance(size, int)
        or size <= 0
    ):
        return None, None
    candidate = (output_dir / name).resolve()
    if candidate.parent != output_dir or not candidate.is_file():
        return None, None
    return name, size


def _ensure_free_space(output_dir: Path) -> None:
    """Keep enough headroom to build beside the current immutable snapshot."""
    _, current_size = _current_snapshot(output_dir)
    expected = current_size or 0
    required = max(MIN_FREE_BYTES, expected * 2 + 512 * 1024**2)
    free = shutil.disk_usage(output_dir).free
    if free < required:
        raise ExportError(
            f"insufficient_disk_space: free={free} required={required}; current pointer preserved"
        )


def _prune_snapshots(output_dir: Path, *, current_name: str, keep: int = 3) -> None:
    """Retain current plus the two newest predecessors, only after publication."""
    if keep < 1 or SNAPSHOT_FILE_RE.fullmatch(current_name) is None:
        raise ExportError("unsafe snapshot retention parameters")
    safe_files: list[Path] = []
    for candidate in output_dir.glob("snapshot-*.sqlite"):
        resolved = candidate.resolve()
        if (
            resolved.parent == output_dir
            and SNAPSHOT_FILE_RE.fullmatch(candidate.name) is not None
            and candidate.is_file()
        ):
            safe_files.append(candidate)
    predecessors = sorted(
        (path for path in safe_files if path.name != current_name),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for stale in predecessors[max(0, keep - 1) :]:
        if os.name != "posix":
            os.chmod(stale, 0o600)
        stale.unlink()
    _fsync_directory(output_dir)


def _validate_source_freshness(source_meta: Mapping[str, Any]) -> None:
    source_as_of = source_meta.get("source_as_of")
    latest = source_meta.get("ingestion_latest_at")
    if not isinstance(source_as_of, dt.datetime) or not isinstance(latest, dt.datetime):
        raise ExportError("source_stale: ingestion timestamp is unavailable")
    if source_as_of.tzinfo is None:
        source_as_of = source_as_of.replace(tzinfo=dt.UTC)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=dt.UTC)
    age = source_as_of.astimezone(dt.UTC) - latest.astimezone(dt.UTC)
    if age > MAX_SOURCE_AGE or age < -MAX_SOURCE_CLOCK_SKEW:
        raise ExportError(
            "source_stale: latest eligible observation is outside the accepted 48-hour window"
        )


def _validate_sqlite(path: Path, expected_count: int) -> None:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        check = connection.execute("PRAGMA quick_check").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        count = connection.execute("SELECT count(*) FROM contracts").fetchone()[0]
        fts_count = connection.execute("SELECT count(*) FROM contract_search").fetchone()[0]
        if check != "ok" or version != 1 or count != expected_count or fts_count != count or count <= 0:
            raise ExportError(
                f"snapshot validation failed: quick_check={check!r}, user_version={version}, "
                f"contracts={count}, fts={fts_count}, expected={expected_count}"
            )
        leaked = connection.execute(
            "SELECT 1 FROM contracts WHERE supplier_id GLOB '*[^0-9a-f]*' "
            "OR buyer_id GLOB '*[^0-9a-f]*' OR id GLOB '*[^0-9a-f]*' LIMIT 1"
        ).fetchone()
        if leaked:
            raise ExportError("non-opaque identity escaped projection")
    finally:
        connection.close()


def build_snapshot(
    rows: Iterable[Mapping[str, Any]],
    *,
    output_dir: Path,
    source_meta: Mapping[str, Any],
    today: dt.date,
    generated_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build, validate and atomically publish one immutable snapshot."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o2750)
    if output_dir.stat().st_mode & 0o7777 != 0o2750:
        os.chmod(output_dir, 0o2750)  # noqa: S103 - preserve existing root-provisioned SGID without chmod
    generated_at = generated_at or dt.datetime.now(dt.UTC)
    _validate_source_freshness(source_meta)
    _ensure_free_space(output_dir)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".building-", suffix=".sqlite", dir=output_dir)
    os.close(descriptor)
    temporary = Path(temporary_name)
    counters = {"source_rows": 0, "rejected_rows": 0, "invalid_values": 0}
    meta: dict[str, Any] | None = None
    try:
        db = sqlite3.connect(temporary)
        try:
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("PRAGMA temp_store=FILE")
            db.executescript(SCHEMA_SQL)
            batch: list[tuple[Any, ...]] = []
            for row in rows:
                counters["source_rows"] += 1
                normalized = normalize_contract(row, today=today)
                if normalized is None:
                    counters["rejected_rows"] += 1
                    continue
                if row.get("valor_total") is not None and normalized[8] is None:
                    counters["invalid_values"] += 1
                batch.append(normalized)
                if len(batch) >= 5_000:
                    db.executemany(UPSERT_SQL, batch)
                    batch.clear()
            if batch:
                db.executemany(UPSERT_SQL, batch)
            record_count = int(db.execute("SELECT count(*) FROM contracts").fetchone()[0])
            if record_count <= 0:
                raise ExportError("projection refused: no eligible contracts")
            qualified_rows = int(source_meta.get("qualified_rows", counters["source_rows"]))
            candidate_rows = int(source_meta.get("candidate_rows", qualified_rows))
            if counters["source_rows"] != qualified_rows:
                raise ExportError(
                    "source count mismatch: "
                    f"streamed={counters['source_rows']} qualified={qualified_rows}"
                )
            if not (0 < record_count <= qualified_rows <= candidate_rows):
                raise ExportError(
                    "invalid source counts: expected 0 < records <= qualified <= candidates, got "
                    f"{record_count}, {qualified_rows}, {candidate_rows}"
                )
            excluded_count = candidate_rows - record_count
            meta = {
                "schema": SNAPSHOT_SCHEMA,
                "generated_at": _iso(generated_at),
                "source_as_of": _iso(source_meta["source_as_of"]),
                "ingestion_latest_at": _iso(source_meta.get("ingestion_latest_at")),
                "window_start": _iso(source_meta["window_start"]),
                "window_end": _iso(source_meta["window_end"]),
                "record_count": record_count,
                "source_row_count": counters["source_rows"],
                "qualified_row_count": qualified_rows,
                "excluded_count": excluded_count,
                "deduplicated_count": max(
                    0, counters["source_rows"] - counters["rejected_rows"] - record_count
                ),
                "rejected_after_select_count": counters["rejected_rows"],
                "invalid_value_count": counters["invalid_values"],
                "coverage_note": (
                    "Contratos PNCP persistidos com publicação original no recorte, "
                    "fornecedor CNPJ e qualidade VALID; cobertura não censitária."
                ),
                "source": "PNCP",
                "producer": "extra-cli",
                "source_schema_contract_sha256": source_meta.get("source_schema_contract_sha256"),
                "state": "READY",
                "value_note": VALUE_NOTE,
                "value_aggregation": False,
                "limitations": LIMITATIONS,
            }
            db.execute("INSERT INTO contract_search(contract_search) VALUES('rebuild')")
            # rank=1 also compares an external-content FTS index with contracts.
            db.execute(
                "INSERT INTO contract_search(contract_search, rank) "
                "VALUES('integrity-check', 1)"
            )
            db.execute("ANALYZE")
            db.execute("PRAGMA optimize")
            db.execute(
                "INSERT INTO metadata VALUES (?,?)",
                ("meta", json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
            )
            db.commit()
        finally:
            db.close()

        _validate_sqlite(temporary, record_count)
        _fsync_file(temporary)
        digest = _sha256_file(temporary)
        final = output_dir / f"snapshot-{digest}.sqlite"
        if final.resolve().parent != output_dir:
            raise ExportError("unsafe immutable snapshot path")
        if final.exists():
            if final.stat().st_size != temporary.stat().st_size or _sha256_file(final) != digest:
                raise ExportError("immutable snapshot filename collision")
            temporary.unlink()
        else:
            os.chmod(temporary, 0o440)
            os.replace(temporary, final)
            _fsync_directory(output_dir)

        if meta is None:  # defensive: a validated non-empty DB always sets it
            raise ExportError("snapshot metadata was not created")
        pointer = {
            "schema": POINTER_SCHEMA,
            "file": final.name,
            "sha256": digest,
            "bytes": final.stat().st_size,
            "meta": meta,
        }
        _write_pointer(output_dir / "current.json", pointer)
        _prune_snapshots(output_dir, current_name=final.name, keep=3)
        return pointer
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _require_schema(connection: Any) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='pncp_supplier_contracts' "
            "ORDER BY ordinal_position"
        )
        available = dict(cursor.fetchall())
    missing = sorted(REQUIRED_COLUMNS - available.keys())
    if missing:
        raise ExportError("live schema missing required columns: " + ", ".join(missing))
    mismatches = sorted(
        f"{name}={available[name]}"
        for name, expected in REQUIRED_COLUMN_TYPES.items()
        if available.get(name) not in expected
    )
    if mismatches:
        raise ExportError("live schema has incompatible required types: " + ", ".join(mismatches))
    projection = [(name, available[name]) for name in sorted(REQUIRED_COLUMN_TYPES)]
    return hashlib.sha256(
        json.dumps(projection, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _source_metadata(connection: Any, *, months: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT transaction_timestamp(), current_date")
        source_as_of, today = cursor.fetchone()
        cursor.execute(
            COUNTS_SQL,
            (today, months, today, today, months, today, today, months, today),
        )
        candidate_rows, qualified_rows, ingestion_latest_at = cursor.fetchone()
    return {
        "source_as_of": source_as_of,
        "ingestion_latest_at": ingestion_latest_at,
        "window_start": today - dt.timedelta(days=1),  # replaced below by PostgreSQL calendar arithmetic
        "window_end": today,
        "candidate_rows": int(candidate_rows),
        "qualified_rows": int(qualified_rows),
        "today": today,
    }


def _calendar_window_start(connection: Any, *, today: dt.date, months: int) -> dt.date:
    with connection.cursor() as cursor:
        cursor.execute("SELECT (%s::date - make_interval(months => %s))::date", (today, months))
        start = _date(cursor.fetchone()[0])
        if start is None:
            raise ExportError("source publication window is not a calendar date")
        return start


def _stream_rows(connection: Any, *, today: dt.date, months: int, batch_size: int) -> Iterator[dict[str, Any]]:
    try:
        import psycopg2.extras
    except ImportError as exc:  # pragma: no cover - production dependency gate
        raise ExportError("psycopg2 is required for the datalake export") from exc
    cursor = connection.cursor(
        name="market_radar_public_v1",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    cursor.itersize = batch_size
    try:
        cursor.execute(SOURCE_SQL, (today, months, today))
        while True:
            batch = cursor.fetchmany(batch_size)
            if not batch:
                break
            yield from batch
    finally:
        cursor.close()


@contextlib.contextmanager
def _exclusive_lock(output_dir: Path) -> Iterator[None]:
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - deployment is Linux
        raise ExportError("kernel flock is required on the deployment host") from exc
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    lock_path = output_dir / ".export.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ExportError("another market-radar export is active") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def export_from_postgres(
    *,
    dsn: str,
    output_dir: Path,
    months: int = 24,
    batch_size: int = 5_000,
    statement_timeout_ms: int = 600_000,
) -> dict[str, Any]:
    """Run the read-only database export. No source row is mutated."""
    # Root provisions the SGID output directory. The producer's private primary
    # group must not grant access to unrelated web runtime configuration.
    import grp
    import stat

    try:
        boundary = output_dir.stat()
        web_group = grp.getgrnam("confenge-web").gr_gid
    except (OSError, KeyError) as exc:
        raise ExportError("output boundary must be provisioned before activation") from exc
    if (
        not output_dir.is_dir()
        or output_dir.is_symlink()
        or boundary.st_uid != os.geteuid()
        or boundary.st_gid != web_group
        or stat.S_IMODE(boundary.st_mode) != 0o2750
        or web_group in {os.getegid(), *os.getgroups()}
    ):
        raise ExportError("output boundary or producer group membership is unsafe")
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - production dependency gate
        raise ExportError("psycopg2 is required for the datalake export") from exc
    if months != 24:
        raise ExportError("market-radar/v1 has a fixed 24-month publication window")
    connection = psycopg2.connect(
        dsn,
        connect_timeout=15,
        application_name="extra-market-radar-public-v1",
        options=f"-c default_transaction_read_only=on -c statement_timeout={statement_timeout_ms}",
    )
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
        schema_hash = _require_schema(connection)
        source_meta = _source_metadata(connection, months=months)
        source_meta["source_schema_contract_sha256"] = schema_hash
        source_meta["window_start"] = _calendar_window_start(
            connection, today=source_meta["today"], months=months
        )
        with _exclusive_lock(output_dir):
            pointer = build_snapshot(
                _stream_rows(
                    connection,
                    today=source_meta["today"],
                    months=months,
                    batch_size=batch_size,
                ),
                output_dir=output_dir,
                source_meta=source_meta,
                today=source_meta["today"],
            )
        connection.rollback()
        return pointer
    finally:
        connection.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export the sanitized PNCP Market Radar projection")
    parser.add_argument("--dsn", default="dbname=pncp_datalake", help="PostgreSQL DSN (default uses local peer auth)")
    parser.add_argument("--output-dir", type=Path, default=Path("/var/lib/confenge-market-radar"))
    parser.add_argument("--months", type=int, default=24, choices=(24,))
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--statement-timeout-ms", type=int, default=600_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 100 <= args.batch_size <= 20_000:
        raise SystemExit("--batch-size must be between 100 and 20000")
    try:
        result = export_from_postgres(
            dsn=args.dsn,
            output_dir=args.output_dir,
            months=args.months,
            batch_size=args.batch_size,
            statement_timeout_ms=args.statement_timeout_ms,
        )
    except ExportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 75 if "another" in str(exc) else 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": result["schema"],
                "file": result["file"],
                "sha256": result["sha256"],
                "bytes": result["bytes"],
                "record_count": result["meta"]["record_count"],
                "source_as_of": result["meta"]["source_as_of"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
