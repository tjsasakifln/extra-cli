"""Helpers for the unified official acts model (migration 052).

Provides idempotent upsert helpers used by DOE/DOM/CIGA crawlers:

- ``compute_record_hash`` — stable content fingerprint
- ``upsert_resource`` — official_act_resources
- ``upsert_acts`` — batch official_acts via SQL function
- ``upsert_act`` — single-act convenience wrapper
- ``add_link`` / ``add_classification`` / ``add_match`` / ``link_source_observation``

Usage::

    from scripts.schema.official_acts import OfficialActsStore, compute_record_hash

    store = OfficialActsStore(dsn)
    rh = compute_record_hash("ciga_ckan", "ABC-1", "Homologação ...")
    act_id = store.upsert_act({
        "source": "ciga_ckan",
        "external_id": "ABC-1",
        "record_hash": rh,
        "title": "Homologação ...",
        "publication_date": "2026-07-01",
        "date_semantics": "publication_from_source_data",
        "category": "homologacao",
        "category_source": "classifier",
        "category_confidence": "high",
        "municipio": "Florianópolis",
        "uf": "SC",
        "raw_json": {"codigo": "ABC-1"},
        "run_id": "run-123",
    })
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

_logger = logging.getLogger(__name__)

DEFAULT_DSN_ENV = ("LOCAL_DATALAKE_DSN", "DATABASE_URL", "TEST_DSN")


def _resolve_dsn(dsn: str | None = None) -> str:
    if dsn:
        return dsn
    for key in DEFAULT_DSN_ENV:
        value = os.getenv(key)
        if value:
            return value
    raise RuntimeError(
        "No database DSN provided. Set LOCAL_DATALAKE_DSN / DATABASE_URL / TEST_DSN "
        "or pass dsn= explicitly."
    )


def compute_record_hash(
    source: str,
    external_id: str | None = None,
    title: str | None = None,
    raw_text: str | None = None,
    publication_date: str | date | None = None,
    extra: str | None = None,
) -> str:
    """Compute a stable sha256 fingerprint for an official act observation.

    Preference order for identity material:
    1. source + external_id (when source provides a stable codigo)
    2. source + title + publication_date + raw_text head
    """
    parts: list[str] = [source or ""]
    if external_id:
        parts.append(f"id:{external_id.strip()}")
    else:
        if title:
            parts.append(f"title:{(title or '').strip().lower()}")
        if publication_date is not None:
            parts.append(f"pub:{publication_date}")
        if raw_text:
            parts.append(f"body:{(raw_text or '')[:2000].strip().lower()}")
    if extra:
        parts.append(f"x:{extra}")
    material = "|".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)!r} is not JSON serializable")


def _normalize_record(rec: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a Python dict for upsert_official_acts JSONB payload."""
    out: dict[str, Any] = dict(rec)
    if not out.get("source"):
        raise ValueError("record requires 'source'")
    if not out.get("record_hash"):
        out["record_hash"] = compute_record_hash(
            str(out["source"]),
            external_id=out.get("external_id"),
            title=out.get("title"),
            raw_text=out.get("raw_text"),
            publication_date=out.get("publication_date"),
        )
    # Dates as ISO strings for JSONB cast in SQL
    for key in ("publication_date", "edition_date", "event_date"):
        val = out.get(key)
        if isinstance(val, datetime):
            out[key] = val.date().isoformat()
        elif isinstance(val, date):
            out[key] = val.isoformat()
    return out


class OfficialActsStore:
    """Thin PostgreSQL store for official acts upserts."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = _resolve_dsn(dsn)

    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg2 is required for OfficialActsStore") from exc

        conn = psycopg2.connect(self.dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def upsert_resource(self, **kwargs: Any) -> int:
        """Upsert an official_act_resources row. Returns resource id."""
        params = {
            "p_source": kwargs.get("source"),
            "p_resource_id": kwargs.get("resource_id"),
            "p_package_id": kwargs.get("package_id"),
            "p_package_name": kwargs.get("package_name"),
            "p_title": kwargs.get("title"),
            "p_resource_url": kwargs.get("resource_url"),
            "p_format": kwargs.get("format"),
            "p_content_sha256": kwargs.get("content_sha256"),
            "p_etag": kwargs.get("etag"),
            "p_last_modified": kwargs.get("last_modified"),
            "p_size_bytes": kwargs.get("size_bytes"),
            "p_run_id": kwargs.get("run_id"),
            "p_fetch_status": kwargs.get("fetch_status", "discovered"),
            "p_metadata": json.dumps(kwargs.get("metadata") or {}, default=_json_default),
        }
        if not params["p_source"]:
            raise ValueError("source is required")

        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT public.upsert_official_act_resource(
                        %(p_source)s, %(p_resource_id)s, %(p_package_id)s,
                        %(p_package_name)s, %(p_title)s, %(p_resource_url)s,
                        %(p_format)s, %(p_content_sha256)s, %(p_etag)s,
                        %(p_last_modified)s, %(p_size_bytes)s, %(p_run_id)s,
                        %(p_fetch_status)s, %(p_metadata)s::jsonb
                    )
                    """,
                    params,
                )
                row = cur.fetchone()
                return int(row[0])

    def upsert_acts(
        self, records: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """Batch upsert acts. Returns list of {action, act_id, record_hash, source}."""
        if not records:
            return []
        payload = [_normalize_record(r) for r in records]
        blob = json.dumps(payload, default=_json_default)
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT action, act_id, record_hash, source
                    FROM public.upsert_official_acts(%s::jsonb)
                    """,
                    (blob,),
                )
                rows = cur.fetchall()
        return [
            {
                "action": r[0],
                "act_id": int(r[1]),
                "record_hash": r[2],
                "source": r[3],
            }
            for r in rows
        ]

    def upsert_act(self, record: Mapping[str, Any]) -> int:
        """Upsert a single act; returns act_id."""
        results = self.upsert_acts([record])
        if not results:
            raise RuntimeError("upsert_acts returned no rows for single record")
        return int(results[0]["act_id"])

    def add_link(
        self,
        act_id: int,
        url: str,
        *,
        link_type: str = "source_page",
        title: str | None = None,
        mime_type: str | None = None,
        content_sha256: str | None = None,
        is_primary: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        """Insert or ignore a link for an act. Returns link id."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.official_act_links (
                        act_id, link_type, url, title, mime_type,
                        content_sha256, is_primary, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (act_id, url) DO UPDATE SET
                        link_type = EXCLUDED.link_type,
                        title = COALESCE(EXCLUDED.title, official_act_links.title),
                        mime_type = COALESCE(EXCLUDED.mime_type, official_act_links.mime_type),
                        content_sha256 = COALESCE(
                            EXCLUDED.content_sha256, official_act_links.content_sha256
                        ),
                        is_primary = EXCLUDED.is_primary OR official_act_links.is_primary,
                        metadata = COALESCE(official_act_links.metadata, '{}'::jsonb)
                                   || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
                    RETURNING id
                    """,
                    (
                        act_id,
                        link_type,
                        url,
                        title,
                        mime_type,
                        content_sha256,
                        is_primary,
                        json.dumps(metadata or {}, default=_json_default),
                    ),
                )
                return int(cur.fetchone()[0])

    def add_classification(
        self,
        act_id: int,
        category: str,
        *,
        confidence: str | None = None,
        method: str = "deterministic_rules",
        classifier_version: str | None = None,
        evidence: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        sync_act: bool = True,
    ) -> int:
        """Append a classification snapshot; optionally denormalize onto the act."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.official_act_classifications (
                        act_id, category, confidence, method,
                        classifier_version, evidence, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        act_id,
                        category,
                        confidence,
                        method,
                        classifier_version,
                        evidence,
                        json.dumps(metadata or {}, default=_json_default),
                    ),
                )
                class_id = int(cur.fetchone()[0])
                if sync_act:
                    cur.execute(
                        """
                        UPDATE public.official_acts
                        SET category = %s,
                            category_confidence = COALESCE(%s, category_confidence),
                            category_source = CASE
                                WHEN %s = 'source_native' THEN 'source_native'
                                WHEN %s = 'manual' THEN 'manual'
                                ELSE 'classifier'
                            END,
                            classification_evidence = COALESCE(%s, classification_evidence),
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (category, confidence, method, method, evidence, act_id),
                    )
                return class_id

    def add_match(
        self,
        act_id: int,
        *,
        match_type: str,
        target_table: str,
        target_id: str,
        match_method: str | None = None,
        match_score: float | None = None,
        match_confidence: str | None = None,
        matched_by: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        """Link an act to a bid/contract/opportunity row (idempotent)."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.official_act_matches (
                        act_id, match_type, target_table, target_id,
                        match_method, match_score, match_confidence,
                        matched_by, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (act_id, match_type, target_table, target_id)
                    DO UPDATE SET
                        match_method = COALESCE(
                            EXCLUDED.match_method, official_act_matches.match_method
                        ),
                        match_score = COALESCE(
                            EXCLUDED.match_score, official_act_matches.match_score
                        ),
                        match_confidence = COALESCE(
                            EXCLUDED.match_confidence, official_act_matches.match_confidence
                        ),
                        matched_by = COALESCE(
                            EXCLUDED.matched_by, official_act_matches.matched_by
                        ),
                        is_active = TRUE,
                        matched_at = NOW(),
                        metadata = COALESCE(official_act_matches.metadata, '{}'::jsonb)
                                   || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
                    RETURNING id
                    """,
                    (
                        act_id,
                        match_type,
                        target_table,
                        target_id,
                        match_method,
                        match_score,
                        match_confidence,
                        matched_by,
                        json.dumps(metadata or {}, default=_json_default),
                    ),
                )
                return int(cur.fetchone()[0])

    def link_source_observation(
        self,
        act_id: int,
        *,
        source: str,
        record_hash: str,
        external_id: str | None = None,
        resource_fk: int | None = None,
        run_id: str | None = None,
        source_url: str | None = None,
        raw_json: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        """Record that another source observed the same canonical act."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.official_act_source_links (
                        act_id, source, external_id, record_hash,
                        resource_fk, run_id, source_url, raw_json, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb
                    )
                    ON CONFLICT (source, record_hash) DO UPDATE SET
                        act_id = EXCLUDED.act_id,
                        external_id = COALESCE(
                            EXCLUDED.external_id, official_act_source_links.external_id
                        ),
                        resource_fk = COALESCE(
                            EXCLUDED.resource_fk, official_act_source_links.resource_fk
                        ),
                        run_id = COALESCE(EXCLUDED.run_id, official_act_source_links.run_id),
                        source_url = COALESCE(
                            EXCLUDED.source_url, official_act_source_links.source_url
                        ),
                        raw_json = COALESCE(
                            EXCLUDED.raw_json, official_act_source_links.raw_json
                        ),
                        observed_at = NOW(),
                        metadata = COALESCE(official_act_source_links.metadata, '{}'::jsonb)
                                   || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
                    RETURNING id
                    """,
                    (
                        act_id,
                        source,
                        external_id,
                        record_hash,
                        resource_fk,
                        run_id,
                        source_url,
                        json.dumps(raw_json, default=_json_default) if raw_json is not None else None,
                        json.dumps(metadata or {}, default=_json_default),
                    ),
                )
                return int(cur.fetchone()[0])
