"""Small, read-only PNCP fact projection for CONFENGE contract news.

The persisted lake supplies candidate identities. Each selected identity is
confirmed on its exact official endpoint before any fact reaches the web owner.
No collector, ingestion row, campaign, dispatch or commercial lock is mutated.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.contracts_identity import normalize_supplier_identity
from scripts.historical_contract_authority.aec import AEC_TOKENS, aec_disposition
from scripts.official_contract_semantics.http_client import FetchResult, fetch_official
from scripts.public_exports.market_radar import (
    PNCP_ID_RE,
    UF_CODES,
    _opaque,
    sanitize_text,
)
from scripts.public_exports.market_radar import (
    POINTER_SCHEMA as RADAR_POINTER_SCHEMA,
)
from scripts.public_exports.market_radar import (
    SNAPSHOT_SCHEMA as RADAR_SCHEMA,
)

SCHEMA = "confenge.contract-news-facts/v1"
MAX_REQUESTS = 20
MAX_RECHECKS = 5
MAX_PUBLISHED_IDS = 10_000
MAX_BODY_BYTES = 256 * 1024
MAX_SNAPSHOT_BYTES = 512 * 1024
MAX_RADAR_BYTES = 4 * 1024**3
SOURCE_MAX_AGE = dt.timedelta(hours=26)
CLOCK_SKEW = dt.timedelta(minutes=5)
SOURCE_TIMEZONE = ZoneInfo("America/Sao_Paulo")
ENGINEERING_OBJECT = re.compile(
    r"\b(?:obras?\b|construc\w*|paviment\w*|edific\w*|reforma\w*|drenagem\b|saneamento\b|"
    r"terraplen\w*|infraestrutura\b|engenharia\b|recapeamento\b|asfalt\w*|cbuq\b|"
    r"microrevestimento\b|pontes?\b|viaduto\w*|contencao\b|recuperacao estrutural\b)"
)
SOURCE_SQL = """
SELECT contrato_id, max(valor_total) AS candidate_value
FROM public.pncp_supplier_contracts
WHERE is_active
  AND supplier_id_type = 'CNPJ'
  AND quality_state = 'VALID'
  AND data_publicacao_fonte BETWEEN %s::date AND %s::date
  AND objeto_contrato ILIKE ANY(%s)
  AND NOT (contrato_id = ANY(%s))
GROUP BY contrato_id
ORDER BY max(valor_total) DESC NULLS LAST, contrato_id
LIMIT %s
"""
SOURCE_CLOCK_SQL = """
SELECT transaction_timestamp(), max(COALESCE(last_seen_at, ingested_at))
FROM public.pncp_supplier_contracts
WHERE is_active
  AND supplier_id_type = 'CNPJ'
  AND quality_state = 'VALID'
  AND data_publicacao_fonte BETWEEN %s::date AND %s::date
"""
RECHECK_SQL = """
SELECT DISTINCT contrato_id FROM public.pncp_supplier_contracts
WHERE contrato_id = ANY(%s)
ORDER BY contrato_id
"""
RADAR_COLUMNS = (
    "rowid", "id", "object", "buyer_id", "buyer_name", "uf", "city", "supplier_id", "supplier_name",
    "value_cents", "published_at", "starts_at", "ends_at", "source_updated_at", "source_url", "expiry_eligible",
)


class ExportError(RuntimeError):
    """A bounded fact export could not be completed safely."""


def _utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ExportError("timezone_missing")
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _source_clock(value: Any) -> dt.datetime | None:
    """PNCP clocks without an offset are interpreted in its Brazilian timezone."""
    if not isinstance(value, (str, dt.datetime)) or not value:
        return None
    try:
        parsed = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SOURCE_TIMEZONE)
    return parsed.astimezone(dt.UTC)


def _date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ExportError("invalid_source_date")
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ExportError("invalid_source_date") from exc


def _text(value: Any, *, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise ExportError("missing_source_text")
    normalized = " ".join(value.replace("\x00", " ").split())
    # Keep the full permitted object; silently truncating it can change scope.
    if not minimum <= len(normalized) <= maximum:
        raise ExportError("source_text_out_of_bounds")
    cleaned = sanitize_text(normalized, limit=maximum)
    if len(cleaned) < minimum:
        raise ExportError("missing_source_text")
    return cleaned


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ExportError("invalid_value")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ExportError("invalid_value") from exc
    if not amount.is_finite() or amount < 0 or amount >= Decimal("1000000000000000"):
        raise ExportError("invalid_value")
    if amount.as_tuple().exponent < -4:
        raise ExportError("value_precision_exceeds_source_contract")
    return amount


def source_urls(contract_id: str) -> tuple[str, str]:
    match = PNCP_ID_RE.fullmatch(contract_id)
    if match is None or int(match.group(2)) < 1:
        raise ExportError("invalid_official_id")
    cnpj, sequence, year = match.groups()
    return (
        f"https://pncp.gov.br/app/contratos/{cnpj}/{year}/{int(sequence)}",
        f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{year}/{int(sequence)}",
    )


def normalize_official(
    payload: Mapping[str, Any],
    *,
    contract_id: str,
    checked_at: dt.datetime,
    source_sha256: str,
    correction: bool = False,
) -> dict[str, Any]:
    """Allowlisted official facts only; lake value never enters this output."""
    portal_url, api_url = source_urls(contract_id)
    if payload.get("numeroControlePNCP") != contract_id:
        raise ExportError("official_identity_mismatch")
    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ExportError("invalid_source_digest")
    kind = payload.get("tipoContrato")
    # Initial contract only. Empenho (7), concessions and other instruments
    # require separate editorial semantics and are deliberately not inferred.
    if not isinstance(kind, dict) or type(kind.get("id")) is not int or kind["id"] != 1:
        raise ExportError("not_initial_contract")
    if payload.get("receita") is not False:
        raise ExportError("not_expense_contract")
    if payload.get("tipoPessoa") != "PJ":
        raise ExportError("supplier_not_legal_entity")
    supplier_identity = normalize_supplier_identity(
        payload.get("niFornecedor"),
        declared_type=payload.get("tipoPessoa"),
        country=payload.get("codigoPaisFornecedor"),
    )
    if supplier_identity.supplier_id_type != "CNPJ":
        raise ExportError("invalid_supplier_identity")
    buyer = payload.get("orgaoEntidade")
    if not isinstance(buyer, dict) or buyer.get("cnpj") != contract_id[:14]:
        raise ExportError("buyer_identity_mismatch")
    object_text = _text(payload.get("objetoContrato"), maximum=5120, minimum=40)
    eligible, _reason = aec_disposition(object_text)
    folded = "".join(
        char for char in unicodedata.normalize("NFKD", object_text.casefold())
        if not unicodedata.combining(char)
    )
    if not eligible or not ENGINEERING_OBJECT.search(folded):
        raise ExportError("object_not_engineering")
    published = _source_clock(payload.get("dataPublicacaoPncp"))
    if published is None or published > checked_at + CLOCK_SKEW:
        raise ExportError("invalid_source_publication")
    today = checked_at.astimezone(SOURCE_TIMEZONE).date()
    publication_day = published.astimezone(SOURCE_TIMEZONE).date()
    if not correction and not today - dt.timedelta(days=6) <= publication_day <= today:
        raise ExportError("outside_publication_window")
    amount = _decimal(payload.get("valorGlobal"))
    value_kind = "valorGlobal"
    if amount is None or amount == 0:
        amount = _decimal(payload.get("valorInicial"))
        value_kind = "valorInicial"
    if amount is None or amount <= 0:
        raise ExportError("no_positive_explicit_contract_value")
    signed = _date(payload.get("dataAssinatura"))
    starts = _date(payload.get("dataVigenciaInicio"))
    ends = _date(payload.get("dataVigenciaFim"))
    if signed and signed > today.isoformat():
        raise ExportError("future_signature")
    if starts and ends and starts > ends:
        raise ExportError("inverted_validity")
    updated = _source_clock(payload.get("dataAtualizacao"))
    if payload.get("dataAtualizacao") and (updated is None or updated > checked_at + CLOCK_SKEW):
        raise ExportError("invalid_source_update")
    unit = payload.get("unidadeOrgao")
    unit = unit if isinstance(unit, dict) else {}
    state = unit.get("ufSigla")
    state = state if isinstance(state, str) and state in UF_CODES else None
    city = _text(unit["municipioNome"], maximum=100) if unit.get("municipioNome") else None
    return {
        "id": contract_id,
        "buyer": _text(buyer.get("razaoSocial"), maximum=300, minimum=3),
        "supplier": _text(payload.get("nomeRazaoSocialFornecedor"), maximum=300, minimum=3),
        "supplier_type": "PJ",
        "object": object_text,
        "value": {"amount": format(amount, "f"), "kind": value_kind, "currency": "BRL"},
        "source_url": portal_url,
        "source_api_url": api_url,
        "source_published_at": _utc(published),
        "signed_at": signed,
        "starts_at": starts,
        "ends_at": ends,
        "source_checked_at": _utc(checked_at),
        "source_updated_at": _utc(updated) if updated else None,
        "source_sha256": source_sha256,
        "administrative_location": {"city": city, "state": state},
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise urllib.error.HTTPError(req.full_url, code, "redirect_refused", headers, fp)


class _BoundedResponse:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.status = response.status

    def __enter__(self) -> _BoundedResponse:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.response.close()

    def read(self) -> bytes:
        content = self.response.read(MAX_BODY_BYTES + 1)
        if len(content) > MAX_BODY_BYTES:
            raise OSError("official_response_too_large")
        return content


def fetch_contract(contract_id: str) -> FetchResult:
    """One HTTPS request to the identity-derived PNCP host, no redirects/retry."""
    _portal, api_url = source_urls(contract_id)
    client = urllib.request.build_opener(_NoRedirect())

    def bounded_opener(request: urllib.request.Request, timeout: float) -> _BoundedResponse:
        if request.full_url != api_url:
            raise OSError("official_endpoint_mismatch")
        return _BoundedResponse(client.open(request, timeout=timeout))  # noqa: S310 - exact generated HTTPS endpoint

    return fetch_official(api_url, timeout_s=15, retries=0, rate_limit_s=0.25, opener=bounded_opener)


def load_published_ids(path: Path | None) -> tuple[list[str], list[str]]:
    """The web owner sends all published IDs and at most five due for recheck."""
    if path is None:
        return [], []
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ExportError("published_id_file_too_large")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"published_ids", "recheck_ids"}:
        raise ExportError("invalid_published_id_contract")
    known, recheck = raw["published_ids"], raw["recheck_ids"]
    if not isinstance(known, list) or not isinstance(recheck, list):
        raise ExportError("invalid_published_id_contract")
    if len(known) > MAX_PUBLISHED_IDS or len(recheck) > MAX_RECHECKS:
        raise ExportError("published_id_limit_exceeded")
    for item in known + recheck:
        if not isinstance(item, str):
            raise ExportError("invalid_official_id")
        source_urls(item)
    if len(set(known)) != len(known) or len(set(recheck)) != len(recheck) or not set(recheck) <= set(known):
        raise ExportError("invalid_recheck_membership")
    return known, recheck


def select_candidates(
    connection: Any,
    *,
    now: dt.datetime,
    published_ids: Sequence[str],
    recheck_ids: Sequence[str],
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Run inside a read-only repeatable-read transaction, without live HTTP."""
    today = now.astimezone(SOURCE_TIMEZONE).date()
    start = today - dt.timedelta(days=6)
    with connection.cursor() as cursor:
        cursor.execute(SOURCE_CLOCK_SQL, (start, today))
        source_as_of, ingestion_latest = cursor.fetchone()
        if not isinstance(source_as_of, dt.datetime) or source_as_of.tzinfo is None:
            raise ExportError("invalid_lake_clock")
        if source_as_of > now + CLOCK_SKEW or now - source_as_of > SOURCE_MAX_AGE:
            raise ExportError("invalid_lake_clock")
        if ingestion_latest is not None:
            if not isinstance(ingestion_latest, dt.datetime) or ingestion_latest.tzinfo is None:
                raise ExportError("invalid_ingestion_clock")
            if ingestion_latest > now + CLOCK_SKEW or now - ingestion_latest > SOURCE_MAX_AGE:
                raise ExportError("stale_lake_ingestion")
        cursor.execute(RECHECK_SQL, (list(recheck_ids),))
        present = {item[0] for item in cursor.fetchall()}
        due = [identity for identity in recheck_ids if identity in present]
        cursor.execute(
            SOURCE_SQL,
            (start, today, [f"%{token}%" for token in AEC_TOKENS], list(published_ids), MAX_REQUESTS - len(due)),
        )
        fresh = []
        for row in cursor.fetchall():
            try:
                source_urls(row[0])
            except (ExportError, TypeError):
                continue
            if row[0] not in published_ids and row[0] not in fresh:
                fresh.append(row[0])
        if fresh and ingestion_latest is None:
            raise ExportError("missing_ingestion_clock")
    return fresh, due, {
        "source_as_of": _utc(source_as_of),
        "ingestion_latest_at": _utc(ingestion_latest) if ingestion_latest else None,
        "window_start": start.isoformat(),
        "window_end": today.isoformat(),
    }


def _identity_from_radar_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ExportError("invalid_radar_source_url")
    match = re.fullmatch(r"https://pncp\.gov\.br/app/contratos/(\d{14})/(\d{4})/([1-9]\d{0,5})", value)
    if match is None:
        raise ExportError("invalid_radar_source_url")
    cnpj, year, sequence = match.groups()
    return f"{cnpj}-2-{int(sequence):06d}/{year}"


def _radar_meta(meta: Any, now: dt.datetime) -> dict[str, Any]:
    if not isinstance(meta, dict) or any(meta.get(k) != value for k, value in {
        "schema": RADAR_SCHEMA, "producer": "extra-cli", "source": "PNCP", "state": "READY",
        "value_aggregation": False,
    }.items()):
        raise ExportError("invalid_radar_metadata")
    clocks = {key: _source_clock(meta.get(key)) for key in ["generated_at", "source_as_of", "ingestion_latest_at"]}
    for key, maximum in [("generated_at", dt.timedelta(hours=36)), ("source_as_of", SOURCE_MAX_AGE),
                         ("ingestion_latest_at", SOURCE_MAX_AGE)]:
        clock = clocks[key]
        if clock is None or clock > now + CLOCK_SKEW or now - clock > maximum:
            raise ExportError("stale_or_invalid_radar_clock")
    if clocks["source_as_of"] > clocks["generated_at"] or clocks["ingestion_latest_at"] > clocks["generated_at"]:
        raise ExportError("inverted_radar_clocks")
    if type(meta.get("record_count")) is not int or meta["record_count"] < 1:
        raise ExportError("invalid_radar_count")
    return meta


def select_from_radar(
    pointer_path: Path,
    *,
    now: dt.datetime,
    published_ids: Sequence[str],
    recheck_ids: Sequence[str],
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Consume the producer's existing verified snapshot with no DB credential.

    The original PNCP identity is recovered from its canonical portal URL, then
    confirmed again by the official detail endpoint. Radar amount is never a
    published fact. SQLite opens the same verified inode through an owned FD.
    """
    pointer_descriptor = os.open(pointer_path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(pointer_descriptor)
        if not stat.S_ISREG(info.st_mode) or not 100 <= info.st_size <= 128 * 1024:
            raise ExportError("invalid_radar_pointer")
        with os.fdopen(os.dup(pointer_descriptor), "rb") as stream:
            pointer = json.load(stream)
    finally:
        os.close(pointer_descriptor)
    if not isinstance(pointer, dict) or pointer.get("schema") != RADAR_POINTER_SCHEMA:
        raise ExportError("invalid_radar_pointer")
    digest = pointer.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ExportError("invalid_radar_digest")
    if pointer.get("file") != f"snapshot-{digest}.sqlite":
        raise ExportError("invalid_radar_filename")
    size = pointer.get("bytes")
    if type(size) is not int or not 4096 <= size <= MAX_RADAR_BYTES:
        raise ExportError("invalid_radar_size")
    radar_meta = _radar_meta(pointer.get("meta"), now)
    root = pointer_path.parent.resolve(strict=True)
    descriptor = os.open(root / pointer["file"], os.O_RDONLY | os.O_NOFOLLOW)
    try:
        file_info = os.fstat(descriptor)
        if not stat.S_ISREG(file_info.st_mode) or file_info.st_size != size or file_info.st_mode & 0o222:
            raise ExportError("invalid_radar_file_boundary")
        computed = hashlib.sha256()
        deadline = time.monotonic() + 120
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                if time.monotonic() > deadline:
                    raise ExportError("radar_digest_timeout")
                computed.update(chunk)
        if computed.hexdigest() != digest:
            raise ExportError("radar_digest_mismatch")
        db = sqlite3.connect(f"file:/proc/self/fd/{descriptor}?mode=ro&immutable=1", uri=True, timeout=2)
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA temp_store=MEMORY")
            deadline = time.monotonic() + 30
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ExportError("invalid_radar_sqlite_version")
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ExportError("radar_integrity_failure")
            table_types = dict(db.execute("SELECT name,type FROM sqlite_schema WHERE name IN ('contracts','metadata')"))
            if table_types != {"contracts": "table", "metadata": "table"}:
                raise ExportError("invalid_radar_tables")
            if tuple(row[1] for row in db.execute("PRAGMA table_info(contracts)")) != RADAR_COLUMNS:
                raise ExportError("invalid_radar_columns")
            stored = db.execute("SELECT value FROM metadata WHERE key='meta'").fetchone()
            if stored is None or json.loads(stored[0]) != radar_meta:
                raise ExportError("radar_metadata_mismatch")
            if db.execute("SELECT count(*) FROM contracts").fetchone()[0] != radar_meta["record_count"]:
                raise ExportError("radar_count_mismatch")
            present: set[str] = set()
            if recheck_ids:
                slots = ",".join("?" for _ in recheck_ids)
                for opaque_id, url in db.execute(
                    f"SELECT id,source_url FROM contracts WHERE id IN ({slots})",  # noqa: S608 - placeholders only
                    [_opaque("contract", identity) for identity in recheck_ids],
                ):
                    identity = _identity_from_radar_url(url)
                    if _opaque("contract", identity) != opaque_id:
                        raise ExportError("radar_identity_mismatch")
                    present.add(identity)
            due = [identity for identity in recheck_ids if identity in present]
            today = now.astimezone(SOURCE_TIMEZONE).date()
            start = today - dt.timedelta(days=6)
            clauses = ["published_at BETWEEN ? AND ?", "(" + " OR ".join("object LIKE ?" for _ in AEC_TOKENS) + ")"]
            params: list[Any] = [start.isoformat(), today.isoformat(), *[f"%{token}%" for token in AEC_TOKENS]]
            if published_ids:
                clauses.append("id NOT IN (" + ",".join("?" for _ in published_ids) + ")")
                params.extend(_opaque("contract", identity) for identity in published_ids)
            params.append(MAX_REQUESTS - len(due))
            # Every clause is a literal or a bounded placeholder list; all
            # record values remain separate bound parameters.
            sql = (
                "SELECT id,source_url FROM contracts WHERE " + " AND ".join(clauses)  # noqa: S608 - placeholders only
                + " ORDER BY value_cents DESC,id LIMIT ?"
            )
            fresh = []
            for opaque_id, url in db.execute(sql, params):
                identity = _identity_from_radar_url(url)
                if _opaque("contract", identity) != opaque_id:
                    raise ExportError("radar_identity_mismatch")
                fresh.append(identity)
            return fresh, due, {
                "source_as_of": radar_meta["source_as_of"],
                "ingestion_latest_at": radar_meta["ingestion_latest_at"],
                "window_start": start.isoformat(), "window_end": today.isoformat(),
                "radar_source_as_of": radar_meta["source_as_of"],
                "radar_generated_at": radar_meta["generated_at"],
                "radar_sha256": digest, "radar_contract": RADAR_SCHEMA,
            }
        finally:
            db.close()
    finally:
        os.close(descriptor)


def build_snapshot(
    new_ids: Sequence[str],
    *,
    recheck_ids: Sequence[str],
    requested_rechecks: Sequence[str],
    metadata: Mapping[str, Any],
    fetch: Callable[[str], FetchResult] = fetch_contract,
    clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
) -> dict[str, Any]:
    if len(new_ids) + len(recheck_ids) > MAX_REQUESTS or len(requested_rechecks) > MAX_RECHECKS:
        raise ExportError("request_budget_exceeded")
    if set(new_ids) & set(recheck_ids) or len(set(new_ids)) != len(new_ids) or len(set(recheck_ids)) != len(recheck_ids):
        raise ExportError("duplicate_candidate_identity")
    records: list[dict[str, Any]] = []
    dispositions: list[dict[str, str]] = [
        {"id": identity, "status": "unavailable", "reason": "not_in_persisted_lake"}
        for identity in requested_rechecks if identity not in recheck_ids
    ]
    excluded: Counter[str] = Counter()
    requests = 0
    unavailable = 0
    for identity in [*recheck_ids, *new_ids]:
        source_urls(identity)
        response = fetch(identity)
        requests += 1
        correction = identity in recheck_ids
        if (
            not response.ok or response.status != 200 or response.body is None or response.sha256 is None
            or response.url != source_urls(identity)[1]
            or len(response.body.encode("utf-8")) > MAX_BODY_BYTES
            or hashlib.sha256(response.body.encode("utf-8")).hexdigest() != response.sha256
        ):
            reason = "official_source_unavailable"
            excluded[reason] += 1
            unavailable += 1
            if correction:
                dispositions.append({"id": identity, "status": "unavailable", "reason": reason})
            continue
        try:
            payload = json.loads(response.body, parse_float=Decimal)
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            reason = "invalid_official_payload"
            excluded[reason] += 1
            unavailable += 1
            if correction:
                dispositions.append({"id": identity, "status": "unavailable", "reason": reason})
            continue
        try:
            record = normalize_official(
                payload, contract_id=identity, checked_at=clock(),
                source_sha256=response.sha256, correction=correction,
            )
        except ExportError as exc:
            reason = str(exc)
            excluded[reason] += 1
            if correction:
                dispositions.append({"id": identity, "status": "ineligible", "reason": reason})
            continue
        records.append(record)
        if correction:
            dispositions.append({"id": identity, "status": "verified", "reason": "official_payload_confirmed"})
    # Repeated upstream errors must not masquerade as an empty success snapshot.
    if requests and unavailable == requests:
        raise ExportError("all_official_requests_unavailable")
    records.sort(key=lambda item: (-Decimal(item["value"]["amount"]), item["id"]))
    return {
        "schema": SCHEMA,
        "producer": "extra-cli",
        "generated_at": _utc(clock()),
        **dict(metadata),
        "source_timezone_without_offset": "America/Sao_Paulo",
        "selection": {
            "candidate_limit": MAX_REQUESTS,
            "official_requests": requests,
            "verified_records": len(records),
            "excluded": dict(sorted(excluded.items())),
            "coverage": "bounded_recent_engineering_candidates_not_a_national_ranking",
        },
        "records": records,
        "recheck_results": dispositions,
    }


@contextlib.contextmanager
def _output_lock(output: Path) -> Iterator[None]:
    import fcntl

    if not output.parent.is_dir() or output.is_symlink():
        raise ExportError("output_boundary_not_provisioned")
    lock_path = output.with_name(f".{output.name}.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ExportError("export_already_running") from exc
        yield
    finally:
        os.close(descriptor)


def write_snapshot(output: Path, snapshot: Mapping[str, Any]) -> str:
    encoded = (json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise ExportError("snapshot_too_large")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o440)
        os.replace(temporary, output)
        directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    return hashlib.sha256(encoded).hexdigest()


def export_from_radar(
    *, pointer_path: Path, output: Path, published_file: Path | None = None,
    producer_commit: str | None = None,
) -> dict[str, Any]:
    published, requested = load_published_ids(published_file)
    with _output_lock(output):
        new_ids, due, metadata = select_from_radar(
            pointer_path, now=dt.datetime.now(dt.UTC), published_ids=published, recheck_ids=requested,
        )
        if producer_commit is not None:
            if not re.fullmatch(r"[a-f0-9]{40}", producer_commit):
                raise ExportError("invalid_producer_commit")
            metadata["producer_commit"] = producer_commit
        snapshot = build_snapshot(new_ids, recheck_ids=due, requested_rechecks=requested, metadata=metadata)
        digest = write_snapshot(output, snapshot)
    return {"ok": True, "schema": SCHEMA, "sha256": digest, **snapshot["selection"]}


def export_from_postgres(*, dsn: str, output: Path, published_file: Path | None = None) -> dict[str, Any]:
    try:
        import psycopg2
    except ImportError as exc:
        raise ExportError("psycopg2_dependency_unavailable") from exc
    published, requested = load_published_ids(published_file)
    with _output_lock(output):
        connection = psycopg2.connect(
            dsn, connect_timeout=10, application_name="confenge-contract-news-facts-v1",
            options="-c default_transaction_read_only=on -c statement_timeout=60000 -c lock_timeout=3000",
        )
        try:
            connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
            new_ids, due, metadata = select_candidates(
                connection, now=dt.datetime.now(dt.UTC), published_ids=published, recheck_ids=requested,
            )
            connection.rollback()
        finally:
            connection.close()
        # HTTP never holds an open database transaction or collector lock.
        snapshot = build_snapshot(new_ids, recheck_ids=due, requested_rechecks=requested, metadata=metadata)
        digest = write_snapshot(output, snapshot)
    return {"ok": True, "schema": SCHEMA, "sha256": digest, **snapshot["selection"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export verified recent PNCP facts for CONFENGE news")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--published-ids", type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--dsn", default="dbname=pncp_datalake")
    source.add_argument("--radar-pointer", type=Path)
    parser.add_argument("--producer-commit")
    args = parser.parse_args(argv)
    try:
        if args.radar_pointer:
            result = export_from_radar(
                pointer_path=args.radar_pointer, output=args.output,
                published_file=args.published_ids, producer_commit=args.producer_commit,
            )
        else:
            result = export_from_postgres(dsn=args.dsn, output=args.output, published_file=args.published_ids)
    except ExportError as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}))
        return 75 if str(exc) == "export_already_running" else 1
    except Exception:  # noqa: BLE001 - do not expose DSNs, SQL values or response bodies in scheduler logs
        print(json.dumps({"ok": False, "reason": "export_dependency_failed"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
