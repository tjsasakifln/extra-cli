"""SELECT-only consumer export labeled for web-cfg#155. Not live. No index grant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.bid_readiness_public.hashing import digest
from scripts.bid_readiness_public.models import CONSUMER_ISSUE
from scripts.bid_readiness_public.redaction import public_envelope
from scripts.bid_readiness_public.select_guard import assert_select_only

READ_MODEL_SQL = """SELECT
  schema_version,
  run_id,
  query_id,
  overall_state,
  generated_at,
  as_of,
  expires_at,
  human_review_required,
  not_legal_conclusion,
  publication_authorization,
  index_authorization,
  content_hash,
  producer_version
FROM public_read_bid_readiness_v1.envelopes
WHERE query_id = $1
LIMIT 1
"""


def consumer_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = public_envelope(payload)
    return {
        "schema": "public-read-bid-readiness-consumer-export/1.0",
        "consumer": CONSUMER_ISSUE,
        "no_index": True,
        "publication_authority": False,
        "publication_authorization": False,
        "index_authorization": False,
        "not_live": True,
        "select_only": True,
        "claimed_live": False,
        "page_authorized": False,
        "read_sql": assert_select_only(READ_MODEL_SQL),
        "overall_state": redacted.get("overall_state"),
        "as_of": redacted.get("as_of"),
        "expires_at": redacted.get("expires_at"),
        "human_review_required": True,
        "not_legal_conclusion": True,
        "finding_count": len(redacted.get("findings") or []),
        "payload_content_hash": redacted.get("content_hash"),
        "limitations": redacted.get("limitations") or [],
    }


def write_consumer_export(payload: dict[str, Any], dest: str | Path) -> dict[str, Any]:
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    model = consumer_read_model(payload)
    public = public_envelope(payload)
    (out / "web-cfg-155-read-model.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "web-cfg-155-read-model.sql").write_text(assert_select_only(READ_MODEL_SQL) + "\n", encoding="utf-8")
    (out / "fixture.public.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "consumer": CONSUMER_ISSUE,
        "no_index": True,
        "publication_authority": False,
        "publication_authorization": False,
        "index_authorization": False,
        "page_authorized": False,
        "not_live": True,
        "select_only": True,
        "files": [
            "web-cfg-155-read-model.json",
            "web-cfg-155-read-model.sql",
            "fixture.public.json",
        ],
        "content_hash": digest(model),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
