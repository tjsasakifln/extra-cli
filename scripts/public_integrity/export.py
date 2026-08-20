"""SELECT-only consumer export labeled for web-cfg#156. Not live. No index grant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.public_integrity.hashing import digest
from scripts.public_integrity.redaction import public_payload
from scripts.public_integrity.select_guard import assert_select_only

CONSUMER_ISSUE = "web-cfg#156"
READ_MODEL_SQL = """SELECT
  schema_version,
  query_id,
  aggregate_state,
  checked_at,
  as_of,
  expires_at,
  not_legal_conclusion,
  content_hash,
  producer_version
FROM public_read_integrity_v1.queries
WHERE query_id = $1
LIMIT 1
"""


def consumer_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = public_payload(payload)
    sources = redacted.get("sources") or {}
    return {
        "schema": "public-read-integrity-consumer-export/1.0",
        "consumer": CONSUMER_ISSUE,
        "no_index": True,
        "publication_authority": False,
        "not_live": True,
        "select_only": True,
        "claimed_live": False,
        "read_sql": assert_select_only(READ_MODEL_SQL),
        "aggregate_state": redacted.get("aggregate_state"),
        "as_of": redacted.get("as_of"),
        "expires_at": redacted.get("expires_at"),
        "not_legal_conclusion": True,
        "coverage": {
            source_id: {
                "status": (sources.get(source_id) or {}).get("status"),
                "coverage_complete": (sources.get(source_id) or {}).get("coverage_complete"),
                "pages_fetched": (sources.get(source_id) or {}).get("pages_fetched"),
                "as_of": (sources.get(source_id) or {}).get("as_of"),
            }
            for source_id in ("CEIS", "CNEP")
        },
        "record_count": len(redacted.get("records") or []),
        "payload_content_hash": redacted.get("content_hash"),
        "limitations": redacted.get("limitations") or [],
    }


def write_consumer_export(payload: dict[str, Any], dest: str | Path) -> dict[str, Any]:
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    model = consumer_read_model(payload)
    (out / "web-cfg-156-read-model.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "web-cfg-156-read-model.sql").write_text(assert_select_only(READ_MODEL_SQL) + "\n", encoding="utf-8")
    (out / "payload.public.json").write_text(
        json.dumps(public_payload(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "consumer": CONSUMER_ISSUE,
        "no_index": True,
        "publication_authority": False,
        "not_live": True,
        "select_only": True,
        "files": [
            "web-cfg-156-read-model.json",
            "web-cfg-156-read-model.sql",
            "payload.public.json",
        ],
        "content_hash": digest(model),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
