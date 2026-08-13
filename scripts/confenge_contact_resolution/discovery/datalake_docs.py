"""Lookup public-document contacts already in the local datalake (no re-scrape)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.confenge_contact_resolution.discovery.extract import extract_emails, extract_phones

_EMAIL_IN_TEXT = re.compile(r"(?i)\b([a-z0-9][a-z0-9._%+\-]{0,63}@[a-z0-9][a-z0-9.\-]{1,63}\.[a-z]{2,24})\b")


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")[:14]


def _contains_exact_cnpj(value: str, target: str) -> bool:
    digits = _digits(target)
    if len(digits) != 14:
        return False
    pattern = r"(?<!\d)" + r"[.\-/\s]*".join(re.escape(digit) for digit in digits) + r"(?!\d)"
    return re.search(pattern, value or "") is not None


def lookup_public_docs_for_cnpj(
    cnpj14: str,
    *,
    dsn: str | None = None,
    jsonl_paths: list[Path] | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Return document contact extracts for a CNPJ from DB and/or local artifacts.

    Prefer company-authored signals (email + razao + cnpj co-located).
    """
    cnpj = _digits(cnpj14)
    if len(cnpj) != 14:
        return []
    docs: list[dict[str, Any]] = []
    docs.extend(_from_jsonl_artifacts(cnpj, jsonl_paths=jsonl_paths, limit=limit))
    if len(docs) < limit:
        docs.extend(_from_postgres(cnpj, dsn=dsn, limit=limit - len(docs)))
    return docs[:limit]


def _from_jsonl_artifacts(
    cnpj14: str,
    *,
    jsonl_paths: list[Path] | None,
    limit: int,
) -> list[dict[str, Any]]:
    paths = list(jsonl_paths or [])
    if not paths:
        # Common artifact locations relative to CWD / repo
        candidates = [
            Path("artifacts/confenge/document-contacts.jsonl"),
            Path("artifacts/confenge/public-docs-contacts.jsonl"),
            Path("artifacts/confenge/process-first-national-confirmed/public_docs.jsonl"),
            Path("output/confenge_docs/document-contacts.jsonl"),
            Path(os.environ["CONFENGE_PUBLIC_DOCS_JSONL"]) if os.environ.get("CONFENGE_PUBLIC_DOCS_JSONL") else None,
        ]
        paths = [p for p in candidates if p is not None and p.is_file()]

    root8 = cnpj14[:8] if len(cnpj14) >= 8 else cnpj14
    out: list[dict[str, Any]] = []
    for path in paths:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                # Match full CNPJ or root (process harvest keys by root)
                if cnpj14 not in line and root8 not in line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row_c = _digits(
                    str(
                        row.get("cnpj14")
                        or row.get("cnpj")
                        or row.get("supplier_cnpj")
                        or row.get("company_cnpj")
                        or ""
                    )
                )
                row_root = _digits(str(row.get("cnpj_raiz") or ""))[:8]
                if len(row_c) == 14 and row_c != cnpj14:
                    continue
                if row_c and row_c[:8] != root8:
                    continue
                elif row_root and row_root != root8 and (not row_c or row_c != cnpj14):
                    continue
                docs = _normalize_doc_row(row, cnpj14)
                out.extend(docs)
                if len(out) >= limit:
                    return out
        except OSError:
            continue
    return out


def _normalize_doc_row(row: dict[str, Any], cnpj14: str) -> list[dict[str, Any]]:
    """Map heterogeneous document rows into public_docs adapter shape."""
    out: list[dict[str, Any]] = []
    email = row.get("email") or row.get("contato_email") or row.get("email_contato")
    phone = row.get("phone") or row.get("telefone") or row.get("contato_telefone")
    name = row.get("name") or row.get("nome") or row.get("representante") or row.get("responsavel")
    cargo = row.get("cargo") or row.get("funcao") or row.get("role")
    text = row.get("text") or row.get("extracted_text") or row.get("content") or ""
    if not email and text:
        emails = extract_emails(str(text))
        email = emails[0] if emails else None
    if not phone and text:
        phones = extract_phones(str(text))
        phone = phones[0] if phones else None
    if not email and not phone and not name:
        # Nested contacts array
        for c in row.get("contacts") or []:
            if not isinstance(c, dict):
                continue
            out.extend(_normalize_doc_row({**row, **c, "contacts": None, "text": None}, cnpj14))
        return out
    if not email and not phone and not name:
        return []
    # Exact CNPJ binding is necessary but does not by itself prove authorship.
    strength = "document_contact"
    blob = f"{text} {row.get('razao_social') or ''} {email or ''}"
    explicit_row_cnpj = _digits(
        str(row.get("cnpj14") or row.get("cnpj") or row.get("supplier_cnpj") or row.get("company_cnpj") or "")
    )
    source_url = str(row.get("url") or row.get("source_url") or row.get("document_url") or "")
    source_host = (urlparse(source_url).hostname or "").lower()
    exact_cnpj = _contains_exact_cnpj(blob, cnpj14) or explicit_row_cnpj == cnpj14
    if exact_cnpj and bool(row.get("company_authored") or row.get("company_authored_likely")):
        strength = "company_authored_document"
    elif exact_cnpj and (source_host == "gov.br" or source_host.endswith(".gov.br")):
        strength = "official_cnpj_linked_document"
    out.append(
        {
            "email": str(email).strip() if email else None,
            "phone": str(phone).strip() if phone else None,
            "name": str(name).strip() if name else None,
            "cargo": str(cargo).strip() if cargo else None,
            "url": row.get("url") or row.get("source_url") or row.get("document_url"),
            "document_id": row.get("document_id") or row.get("id") or row.get("doc_id"),
            "document": row.get("document_type") or row.get("doc_type") or row.get("tipo"),
            "doc_type": row.get("doc_type") or row.get("tipo") or "public_doc",
            "source_published_at": row.get("source_published_at")
            or row.get("source_date")
            or row.get("document_date")
            or row.get("data"),
            "observed_at": row.get("observed_at"),
            "verified_at": row.get("verified_at"),
            "evidence_strength": strength,
            "cnpj14": cnpj14,
        }
    )
    return out


def _from_postgres(cnpj14: str, *, dsn: str | None, limit: int) -> list[dict[str, Any]]:
    """Best-effort queries against known tables; silent if schema absent."""
    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn or limit <= 0:
        return []
    try:
        import psycopg
    except ImportError:
        try:
            import psycopg2 as psycopg  # type: ignore
        except ImportError:
            return []

    queries = [
        # Generic contact extract tables (if present)
        """
        SELECT email, telefone AS phone, nome AS name, cargo, source_url AS url,
               document_id, doc_type, source_date::text
        FROM public.document_contacts
        WHERE regexp_replace(cnpj, '\\D', '', 'g') = %s
        LIMIT %s
        """,
        """
        SELECT email, telefone AS phone, responsavel AS name, NULL AS cargo,
               url, id::text AS document_id, tipo AS doc_type, data::text AS source_date
        FROM public.pncp_document_contacts
        WHERE regexp_replace(cnpj, '\\D', '', 'g') = %s
        LIMIT %s
        """,
        # Fallback: scan extracted text fields when table exists
        """
        SELECT NULL AS email, NULL AS phone, NULL AS name, NULL AS cargo,
               source_url AS url, id::text AS document_id, 'extracted_text' AS doc_type,
               NULL::text AS source_date, created_at::text AS observed_at,
               left(extracted_text, 4000) AS text,
               razao_social
        FROM public.document_text_extracts
        WHERE regexp_replace(cnpj, '\\D', '', 'g') = %s
          AND extracted_text IS NOT NULL
        LIMIT %s
        """,
    ]
    out: list[dict[str, Any]] = []
    try:
        conn = psycopg.connect(dsn)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return []
    try:
        with conn.cursor() as cur:
            for sql in queries:
                if len(out) >= limit:
                    break
                try:
                    cur.execute(sql, (cnpj14, limit - len(out)))
                    cols = [d[0] for d in cur.description] if cur.description else []
                    for row in cur.fetchall() or []:
                        d = dict(zip(cols, row, strict=False))
                        out.extend(_normalize_doc_row(d, cnpj14))
                except Exception:  # noqa: BLE001
                    try:
                        conn.rollback()
                    except Exception as rb_exc:  # noqa: BLE001
                        _ = rb_exc
                    continue
    finally:
        try:
            conn.close()
        except Exception as close_exc:  # noqa: BLE001
            _ = close_exc
    return out[:limit]
