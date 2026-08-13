"""Tests for PNCP document versioning (#242)."""

from __future__ import annotations

from scripts.process_documents.pncp_document_versions import (
    CandidateInventory,
    apply_fanout,
    classify_status,
    inventory_report,
    record_attempt,
    resume_progress,
    version_document,
)


def _doc(kind: str, body: bytes = b"edital-bytes", **kwargs):
    return version_document(
        kind=kind,
        url=f"https://pncp.gov.br/docs/{kind}",
        body=body,
        mime="application/pdf",
        **kwargs,
    )


def test_actionable_candidate_needs_reconfirmed_official_page() -> None:
    inv = CandidateInventory(candidate_id="c1", official_page=None, official_reconfirmed=False, status="open")
    assert inv.inventory_complete is False
    apply_fanout(
        inv,
        official_page="https://pncp.gov.br/app/editais/1/2026/1",
        official_status="recebendo proposta",
        documents=[_doc("edital"), _doc("tr"), _doc("anexo")],
        items_fetched=True,
        history_fetched=True,
        results_fetched=True,
    )
    assert inv.official_reconfirmed is True
    assert inv.inventory_complete is True
    assert inv.shortlist_eligible is True


def test_documents_record_url_hash_mime_size_version_raw_or_blocker() -> None:
    first = _doc("edital", b"v1")
    assert first.sha256
    assert first.mime == "application/pdf"
    assert first.size == 2
    assert first.version == 1
    assert first.raw_uri.startswith("cas://")
    second = _doc("edital", b"v2", previous=first)
    assert second.version == 2
    blocked = version_document(
        kind="anexo",
        url="https://pncp.gov.br/docs/missing",
        body=b"",
        mime="",
        blocker="http_404",
    )
    assert blocked.blocker == "http_404"


def test_revoked_does_not_remain_open() -> None:
    assert classify_status("Revogado") == "revoked"
    assert classify_status("anulado") == "annulled"
    assert classify_status("suspenso") == "suspended"
    assert classify_status("encerrado") == "closed"
    inv = CandidateInventory(candidate_id="c2", official_page="x", official_reconfirmed=True, status="open")
    apply_fanout(
        inv,
        official_page="x",
        official_status="Revogado",
        documents=[_doc("edital"), _doc("tr"), _doc("anexo")],
        items_fetched=True,
        history_fetched=True,
        results_fetched=True,
    )
    assert inv.status == "revoked"
    assert inv.shortlist_eligible is False


def test_429_resumes_without_losing_progress() -> None:
    attempt = record_attempt("https://pncp.gov.br/docs/edital", 429, 1)
    assert attempt.resume is True
    inv = CandidateInventory(
        candidate_id="c3",
        official_page="x",
        official_reconfirmed=True,
        status="open",
        attempts=[attempt],
    )
    nxt = resume_progress(inv.attempts, attempt.url)
    assert nxt == 2
    report = inventory_report(inv)
    assert report["attempts"][0]["resume"] is True


def test_shortlist_requires_complete_inventory() -> None:
    inv = CandidateInventory(candidate_id="c4", official_page="x", official_reconfirmed=True, status="open")
    apply_fanout(
        inv,
        official_page="x",
        official_status="aberto",
        documents=[_doc("edital")],
        items_fetched=True,
        history_fetched=False,
        results_fetched=True,
    )
    assert inv.inventory_complete is False
    assert inv.shortlist_eligible is False
