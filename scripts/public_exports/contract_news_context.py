"""Bounded, identity-linked official evidence for the contract-news editor.

This is part of the existing read-only projection, not an acquisition crawler.
Only a contract's explicitly linked PNCP purchase and its own listed documents
are read. Document text is private editorial evidence, never public article copy.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.public_exports.market_radar import sanitize_text
from scripts.public_exports.pdf_extract import verified_wheel

SCHEMA = "confenge.contract-news-context/v1"
PURCHASE_ID = re.compile(r"^(\d{14})-1-(\d{6})/(\d{4})$")
CONTRACT_ID = re.compile(r"^(\d{14})-2-(\d{6})/(\d{4})$")
MAX_PURCHASES = 5
MAX_NEW_DOCUMENT_CONTRACTS = 2
MAX_RECHECK_DOCUMENT_CONTRACTS = 2
MAX_DOCUMENTS = 3
MAX_NEW_DOCUMENT_PROBES = 10
MAX_DOCUMENT_REQUESTS = (MAX_NEW_DOCUMENT_CONTRACTS + 1) * MAX_DOCUMENTS
MAX_JSON_BYTES = 256 * 1024
MAX_PDF_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_DOCUMENT_TEXT = 64_000
MAX_CONTEXT_SECONDS = 120
DOCUMENT_ROTATION_SECONDS = 4 * 60 * 60
SOURCE_TIMEZONE = ZoneInfo("America/Sao_Paulo")


class ContextError(ValueError):
    """Stable private diagnostic, without raw text, URLs or personal data."""


@dataclass(frozen=True)
class EvidenceResponse:
    url: str
    status: int
    body: bytes


def _utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ContextError("context_timezone_missing")
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _text(value: Any, maximum: int = 500) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ContextError("invalid_context_text")
    text = " ".join(value.split())
    if not text or len(text) > maximum:
        raise ContextError("context_text_out_of_bounds")
    text = "".join(c for c in text if unicodedata.category(c) not in {"Cc", "Cf", "Cs"})
    return sanitize_text(text, limit=maximum) or None


def _instant(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ContextError("invalid_context_date")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContextError("invalid_context_date") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SOURCE_TIMEZONE)
    return _utc(parsed)


def _money(value: Any) -> dict[str, str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ContextError("invalid_context_value")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ContextError("invalid_context_value") from exc
    if (not amount.is_finite() or amount < 0 or amount >= Decimal("1000000000000000")
            or amount.as_tuple().exponent < -4):
        raise ContextError("invalid_context_value")
    return {"amount": format(amount, "f"), "currency": "BRL"}


def purchase_urls(identity: str) -> tuple[str, str]:
    match = PURCHASE_ID.fullmatch(identity)
    if match is None or int(match[2]) < 1:
        raise ContextError("invalid_purchase_identity")
    cnpj, sequence, year = match.groups()
    return (
        f"https://pncp.gov.br/app/editais/{cnpj}/{year}/{int(sequence)}",
        f"https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{year}/{int(sequence)}",
    )


def document_urls(identity: str, sequence: int | None = None) -> str:
    match = CONTRACT_ID.fullmatch(identity)
    if match is None or int(match[2]) < 1:
        raise ContextError("invalid_contract_identity")
    cnpj, contract, year = match.groups()
    if sequence is None:
        return f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{year}/{int(contract)}/arquivos"
    if type(sequence) is not int or not 1 <= sequence <= 100_000:
        raise ContextError("invalid_document_sequence")
    return f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/contratos/{year}/{int(contract)}/arquivos/{sequence}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise urllib.error.HTTPError(req.full_url, code, "redirect_refused", headers, fp)


def fetch_evidence(url: str, limit: int, timeout: float) -> EvidenceResponse:
    """Read one generated PNCP URL, without redirects, retries or credentials."""
    if not re.fullmatch(
        r"https://pncp\.gov\.br/(?:api/consulta/v1/orgaos/\d{14}/compras/\d{4}/[1-9]\d{0,5}|"
        r"api/pncp/v1/orgaos/\d{14}/contratos/\d{4}/[1-9]\d{0,5}/arquivos|"
        r"pncp-api/v1/orgaos/\d{14}/contratos/\d{4}/[1-9]\d{0,5}/arquivos/[1-9]\d{0,5})", url,
    ):
        raise ContextError("untrusted_evidence_endpoint")
    request = urllib.request.Request(url, headers={  # noqa: S310 - exact generated HTTPS PNCP URLs
        "User-Agent": "CONFENGE-ContractNewsEvidence/1.0", "Accept": "application/json,application/pdf",
    })
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            if response.status != 200 or len(body) > limit:
                raise ContextError("evidence_response_unavailable")
            return EvidenceResponse(url, response.status, body)
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise ContextError("evidence_transport_unavailable") from exc


def _json(response: EvidenceResponse, expected_url: str) -> Any:
    if (response.url != expected_url or response.status != 200
            or not isinstance(response.body, bytes) or len(response.body) > MAX_JSON_BYTES):
        raise ContextError("invalid_evidence_response")
    try:
        return json.loads(response.body, parse_float=Decimal)
    except (ValueError, UnicodeError) as exc:
        raise ContextError("invalid_evidence_json") from exc


def normalize_purchase(response: EvidenceResponse, identity: str, checked_at: dt.datetime) -> dict[str, Any]:
    portal_url, api_url = purchase_urls(identity)
    raw = _json(response, api_url)
    if (not isinstance(raw, dict) or raw.get("numeroControlePNCP") != identity
            or not isinstance(raw.get("orgaoEntidade"), dict)
            or raw["orgaoEntidade"].get("cnpj") != identity[:14]):
        raise ContextError("purchase_identity_mismatch")
    legal = raw.get("amparoLegal")
    legal = legal if isinstance(legal, dict) else {}
    return {
        "id": identity, "source_url": portal_url, "source_api_url": api_url,
        "source_checked_at": _utc(checked_at), "source_sha256": hashlib.sha256(response.body).hexdigest(),
        "number": _text(raw.get("numeroCompra"), 100), "process": _text(raw.get("processo"), 150),
        "modality": _text(raw.get("modalidadeNome"), 100),
        "dispute_mode": _text(raw.get("modoDisputaNome"), 100),
        "instrument": _text(raw.get("tipoInstrumentoConvocatorioNome"), 150),
        "legal_basis": _text(legal.get("nome"), 250),
        "legal_basis_description": _text(legal.get("descricao"), 1500),
        "object": _text(raw.get("objetoCompra"), 5120),
        "estimated_value": _money(raw.get("valorTotalEstimado")),
        "awarded_value": _money(raw.get("valorTotalHomologado")),
        "published_at": _instant(raw.get("dataPublicacaoPncp")),
        "proposal_opens_at": _instant(raw.get("dataAberturaProposta")),
        "proposal_closes_at": _instant(raw.get("dataEncerramentoProposta")),
    }


def normalize_document_list(response: EvidenceResponse, identity: str) -> tuple[list[dict[str, Any]], int]:
    raw = _json(response, document_urls(identity))
    if not isinstance(raw, list) or len(raw) > 200:
        raise ContextError("invalid_document_list")
    result = []
    seen = set()
    for row in raw:
        if not isinstance(row, dict):
            raise ContextError("invalid_document_list")
        sequence = row.get("sequencialDocumento")
        expected = document_urls(identity, sequence)
        # Accept either published spelling, only when it equals the URL derived
        # from this exact contract and listed sequence. Never fetch arbitrary URLs.
        supplied = row.get("url") or row.get("uri")
        canonical_alias = expected.replace("/pncp-api/v1/", "/api/pncp/v1/")
        if supplied not in {expected, canonical_alias} or sequence in seen:
            raise ContextError("unbound_document_reference")
        seen.add(sequence)
        result.append({
            "id": str(sequence), "title": _text(row.get("titulo") or row.get("tipoDocumentoNome"), 300),
            "url": expected,
        })
    return sorted(result, key=lambda row: int(row["id"]))[:MAX_DOCUMENTS], len(raw)


def _pdf_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))


def extract_pdf_text(raw: bytes, timeout: float = 10) -> dict[str, Any]:
    """Poppler subprocesses have wall, CPU, memory, page and output limits."""
    if not isinstance(raw, bytes) or not raw.startswith(b"%PDF-") or len(raw) > MAX_PDF_BYTES:
        raise ContextError("document_not_bounded_pdf")
    pdfinfo, pdftotext = shutil.which("pdfinfo"), shutil.which("pdftotext")
    with tempfile.TemporaryDirectory(prefix="contract-news-document-") as directory:
        path = Path(directory) / "source.pdf"
        output = Path(directory) / "text.txt"
        path.write_bytes(raw)
        path.chmod(0o600)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
        try:
            if pdfinfo and pdftotext:
                pages_without_text = None
                info = subprocess.run(  # noqa: S603 - argv only; executable resolved from host PATH
                    [pdfinfo, str(path)], capture_output=True, text=True, timeout=timeout,
                    env=env, preexec_fn=_pdf_limits, check=False,
                )
                match = re.search(r"^Pages:\s+(\d+)\s*$", info.stdout, re.MULTILINE)
                if info.returncode != 0 or match is None or not 1 <= int(match[1]) <= MAX_PDF_PAGES:
                    raise ContextError("document_page_limit_or_invalid")
                if re.search(r"^Encrypted:\s+yes", info.stdout, re.MULTILINE):
                    raise ContextError("encrypted_document")
                pages = int(match[1])
                result = subprocess.run(  # noqa: S603 - fixed flags, owned temporary paths
                    [pdftotext, "-layout", "-enc", "UTF-8", str(path), str(output)],
                    capture_output=True, timeout=timeout, env=env, preexec_fn=_pdf_limits, check=False,
                )
            else:
                try:
                    verified_wheel()
                except ValueError as exc:
                    raise ContextError("pdf_dependency_digest_mismatch") from exc
                result = subprocess.run(  # noqa: S603 - pinned local code, owned temporary files
                    [sys.executable, "-S", str(Path(__file__).with_name("pdf_extract.py")), str(path), str(output)],
                    capture_output=True, timeout=timeout * 2, env=env, preexec_fn=_pdf_limits, check=False,
                )
                try:
                    extracted_metadata = json.loads(result.stdout)
                    pages = extracted_metadata.get("pages")
                    pages_without_text = extracted_metadata.get("pages_without_text")
                except (ValueError, AttributeError) as exc:
                    raise ContextError("document_extraction_unavailable") from exc
                if type(pages) is not int or not 1 <= pages <= MAX_PDF_PAGES:
                    raise ContextError("document_page_limit_or_invalid")
            if result.returncode != 0 or not output.is_file() or output.stat().st_size > 1024 * 1024:
                raise ContextError("document_text_unavailable")
            raw_text = output.read_text(encoding="utf-8")
            if pages_without_text is None:
                page_texts = raw_text.split("\f")
                pages_without_text = [number for number in range(1, pages + 1)
                                      if number > len(page_texts) or len(" ".join(page_texts[number - 1].split())) < 40]
            if (not isinstance(pages_without_text, list)
                    or any(type(number) is not int or not 1 <= number <= pages for number in pages_without_text)
                    or len(set(pages_without_text)) != len(pages_without_text)):
                raise ContextError("document_text_coverage_invalid")
            text = _text(raw_text, MAX_DOCUMENT_TEXT)
            if text is None or len(text) < 100:
                raise ContextError("document_requires_ocr")
            return {"text": text, "pages": pages, "text_pages": pages - len(pages_without_text),
                    "pages_without_text": pages_without_text,
                    "extraction_note": ("Há páginas sem texto extraível; plantas e imagens não foram interpretadas."
                                        if pages_without_text else
                                        "Extração textual do PDF, sem interpretação de imagens ou plantas.")}
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            raise ContextError("document_extraction_unavailable") from exc


def enrich_records(
    records: Sequence[dict[str, Any]],
    payloads: Mapping[str, Mapping[str, Any]],
    *,
    recheck_ids: Sequence[str],
    clock: Callable[[], dt.datetime],
    fetch: Callable[[str, int, float], EvidenceResponse] = fetch_evidence,
    extract_pdf: Callable[[bytes, float], dict[str, Any]] = extract_pdf_text,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Enrich highest-value candidates after confirming their contract facts.

    New records rotate every four hours and advance to the next candidate when
    no documentary source is usable. Collect up to two new dossiers so the
    publisher can continue after a rejection. Bound probes, downloads and time.
    """
    deadline = monotonic() + MAX_CONTEXT_SECONDS
    counters: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    purchases: dict[str, dict[str, Any] | None] = {}
    ranked = sorted(records, key=lambda row: (-Decimal(row["value"]["amount"]), row["id"]))
    by_id = {row["id"]: row for row in records}
    rechecks = [by_id[identity] for identity in recheck_ids if identity in by_id]
    recheck_set = set(recheck_ids)
    new_records = [row for row in ranked if row["id"] not in recheck_set]
    if new_records:
        # A monotonically advancing window, not hour-of-day modulo six: the
        # latter would starve positions beyond six when the candidate set is larger.
        offset = (int(clock().timestamp()) // DOCUMENT_ROTATION_SECONDS) % len(new_records)
        new_records = new_records[offset:] + new_records[:offset]

    def read(url: str, limit: int, kind: str) -> EvidenceResponse:
        remaining = deadline - monotonic()
        if remaining < 2:
            raise ContextError("context_time_budget_exhausted")
        counters["requests"] += 1
        counters[kind] += 1
        return fetch(url, limit, min(15, remaining))

    def enrich_purchase(record: dict[str, Any]) -> None:
        raw = payloads[record["id"]]
        context = record["editorial_context"]
        purchase = raw.get("numeroControlePncpCompra", raw.get("numeroControlePNCPCompra"))
        if purchase:
            try:
                _portal, url = purchase_urls(purchase)
                if purchase not in purchases and len(purchases) < MAX_PURCHASES:
                    purchases[purchase] = None
                    purchases[purchase] = normalize_purchase(read(url, MAX_JSON_BYTES, "purchase_requests"), purchase, clock())
                context["procurement"] = purchases.get(purchase)
            except (ContextError, TypeError, OSError, TimeoutError) as exc:
                errors[str(exc) if isinstance(exc, ContextError) else "invalid_purchase_identity"] += 1

    for record in ranked:
        raw = payloads[record["id"]]
        kind, category = raw.get("tipoContrato"), raw.get("categoriaProcesso")
        kind = kind if isinstance(kind, dict) else {}
        category = category if isinstance(category, dict) else {}
        record["editorial_context"] = {
            "schema": SCHEMA,
            "contract": {"number": _text(raw.get("numeroContratoEmpenho"), 150),
                         "type": _text(kind.get("nome"), 150), "category": _text(category.get("nome"), 150)},
            "procurement": None, "documents": [], "documents_status": "not_collected",
            "documents_total": None, "documents_checked_at": None,
        }

    def enrich_documents(record: dict[str, Any]) -> bool:
        context = record["editorial_context"]
        try:
            documents, total = normalize_document_list(
                read(document_urls(record["id"]), MAX_JSON_BYTES, "document_list_requests"), record["id"],
            )
            context["documents_total"] = total
            context["documents_checked_at"] = _utc(clock())
            remaining_downloads = MAX_DOCUMENT_REQUESTS - counters["document_requests"]
            for document in documents[:remaining_downloads]:
                try:
                    response = read(document["url"], MAX_PDF_BYTES, "document_requests")
                    if response.url != document["url"] or response.status != 200:
                        raise ContextError("unbound_document_response")
                    remaining = deadline - monotonic()
                    if remaining < 2:
                        raise ContextError("context_time_budget_exhausted")
                    extracted = extract_pdf(response.body, min(8, remaining / 2))
                    context["documents"].append({
                        **document, "sha256": hashlib.sha256(response.body).hexdigest(),
                        "checked_at": _utc(clock()), **extracted,
                    })
                except (ContextError, OSError, TimeoutError) as exc:
                    errors[str(exc) if isinstance(exc, ContextError) else "document_unavailable"] += 1
            collected = len(context["documents"])
            if collected == total:
                context["documents_status"] = "complete"
            elif collected:
                context["documents_status"] = "partial"
            else:
                context["documents_status"] = "unavailable"
        except (ContextError, OSError, TimeoutError) as exc:
            errors[str(exc) if isinstance(exc, ContextError) else "documents_unavailable"] += 1
            context["documents_status"] = "unavailable"
        return bool(context["documents"] or (context["documents_status"] == "complete" and context["procurement"]))

    recheck_slots = 1 if new_records else MAX_RECHECK_DOCUMENT_CONTRACTS
    selected_rechecks = rechecks[:recheck_slots]
    probed = set()
    for record in selected_rechecks:
        enrich_purchase(record)
        enrich_documents(record)
        probed.add(record["id"])
    ready_new = 0
    for record in new_records[:MAX_NEW_DOCUMENT_PROBES]:
        if (ready_new == MAX_NEW_DOCUMENT_CONTRACTS or counters["document_requests"] == MAX_DOCUMENT_REQUESTS
                or (probed and deadline - monotonic() < 2)):
            break
        enrich_purchase(record)
        if enrich_documents(record):
            ready_new += 1
        probed.add(record["id"])
    # The limited purchase budget serves the documentary candidates first.
    for record in ranked:
        if record["id"] not in probed:
            enrich_purchase(record)
    return {"context_requests": counters["requests"], "context_purchase_requests": counters["purchase_requests"],
            "context_document_list_requests": counters["document_list_requests"],
            "context_document_requests": counters["document_requests"], "context_new_ready": ready_new,
            "context_errors": dict(sorted(errors.items()))}
