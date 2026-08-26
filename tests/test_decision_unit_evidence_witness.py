from __future__ import annotations

import base64
import gzip
import hashlib

from scripts.decision_unit_intelligence import evidence as evidence_module
from scripts.decision_unit_intelligence.evidence import (
    MAX_PAGE_DOCUMENT_WITNESS_BASE64_CHARS,
    MAX_PAGE_DOCUMENT_WITNESS_BYTES,
    PAGE_DOCUMENT_WITNESS_SCHEMA,
    make_evidence,
    make_page_document_witness,
    verified_page_document_bytes,
)
from scripts.decision_unit_intelligence.models import EpistemicClass


def test_page_document_witness_round_trips_exact_utf8_bytes() -> None:
    content = "CNPJ 12.345.678/0001-90 | Contato: licitações@empresa.com.br"
    witness = make_page_document_witness(content)

    assert witness is not None
    assert verified_page_document_bytes(
        witness,
        expected_sha256=str(witness["sha256"]),
    ) == content.encode("utf-8")


def test_page_document_witness_rejects_oversized_base64_before_decode() -> None:
    witness = {
        "schema": PAGE_DOCUMENT_WITNESS_SCHEMA,
        "encoding": "gzip+base64+utf8",
        "sha256": "a" * 64,
        "raw_size_bytes": 1,
        "compressed_size_bytes": 1,
        "content_gzip_b64": "A" * (MAX_PAGE_DOCUMENT_WITNESS_BASE64_CHARS + 1),
    }

    assert verified_page_document_bytes(witness, expected_sha256="a" * 64) is None


def test_page_document_witness_rejects_bounded_gzip_bomb() -> None:
    raw = b"x" * (MAX_PAGE_DOCUMENT_WITNESS_BYTES + 1)
    compressed = gzip.compress(raw, mtime=0)
    witness = {
        "schema": PAGE_DOCUMENT_WITNESS_SCHEMA,
        "encoding": "gzip+base64+utf8",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "raw_size_bytes": len(raw),
        "compressed_size_bytes": len(compressed),
        "content_gzip_b64": base64.b64encode(compressed).decode("ascii"),
    }

    assert (
        verified_page_document_bytes(
            witness,
            expected_sha256=str(witness["sha256"]),
        )
        is None
    )


def test_implicit_collection_time_does_not_destabilize_evidence_id(monkeypatch) -> None:
    times = iter(("2026-08-26T12:00:00Z", "2026-08-26T12:00:01Z"))
    monkeypatch.setattr(evidence_module, "now_iso", lambda: next(times))

    first = make_evidence(
        field="inferred_email",
        value="candidate@example.com",
        epistemic_class=EpistemicClass.INFERRED,
        source_type="email_pattern_inference",
        source_id="pattern-1",
        extraction_method="org-email-pattern.v1",
    )
    second = make_evidence(
        field="inferred_email",
        value="candidate@example.com",
        epistemic_class=EpistemicClass.INFERRED,
        source_type="email_pattern_inference",
        source_id="pattern-1",
        extraction_method="org-email-pattern.v1",
    )

    assert first.evidence_id == second.evidence_id
    assert first.observed_at != second.observed_at


def test_explicit_observation_time_remains_bound_into_evidence_id() -> None:
    common = {
        "field": "email",
        "value": "contato@example.com",
        "epistemic_class": EpistemicClass.OBSERVED,
        "source_type": "company_website",
        "source_url": "https://example.com/contato",
        "document_sha256": "a" * 64,
        "extraction_method": "public_page_exact_text",
    }
    first = make_evidence(**common, observed_at="2026-08-26T12:00:00Z")
    second = make_evidence(**common, observed_at="2026-08-26T12:00:01Z")

    assert first.evidence_id != second.evidence_id
