"""Drive shipped produce() and CLI. Adversarial coverage for the 1.0 envelope."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bid_readiness_public.cli import main
from scripts.bid_readiness_public.compose import load_authorized_manifest
from scripts.bid_readiness_public.forbidden import scan_payload
from scripts.bid_readiness_public.hashing import attach_hash, content_hash
from scripts.bid_readiness_public.ingest_guard import RejectedInputError
from scripts.bid_readiness_public.models import OVERALL_STATES, SCHEMA_VERSION
from scripts.bid_readiness_public.pii import scan_payload_for_pii
from scripts.bid_readiness_public.redaction import public_envelope
from scripts.bid_readiness_public.validators import EnvelopeValidationError
from tests.bid_readiness_public.helpers import (
    CLOCK,
    FIXTURES,
    clean_workbook,
    incomplete_documents,
    produce_happy,
)
from tests.budget_audit.build_fixtures import build_golden


def _assert_flags(payload: dict) -> None:
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["overall_state"] in OVERALL_STATES
    assert payload["human_review_required"] is True
    assert payload["not_legal_conclusion"] is True
    assert payload["publication_authorization"] is False
    assert payload["index_authorization"] is False
    assert payload["content_hash"]
    assert scan_payload(payload) == []
    assert scan_payload_for_pii(payload) == []


def test_happy_path_on_complete_fictional_fixture(tmp_path: Path) -> None:
    payload = produce_happy(tmp_path)
    _assert_flags(payload)
    assert payload["overall_state"] == "READY_FOR_HUMAN_REVIEW"
    assert payload["source_access"] == "private_local"
    assert "REQ-TEC-001" not in payload["summary"]["missing_items"]
    assert "BLOCKED_BY_MISSING_DOCUMENT" not in payload["summary"]["blockers"]
    modules = {finding["finding_id"][:2] for finding in payload["findings"]}
    assert "ED" in modules
    assert "BD" in modules
    assert "AC" in modules
    assert "BR" in modules
    with pytest.raises(EnvelopeValidationError, match="public_export_requires_redacted_fixture"):
        public_envelope(payload)
    redacted_fixture = produce_happy(tmp_path / "redacted", source_access="redacted_fixture")
    public = public_envelope(redacted_fixture)
    assert public["source_access"] == "redacted_fixture"
    assert public["publication_authorization"] is False
    assert public["index_authorization"] is False
    public_body = {key: value for key, value in public.items() if key != "content_hash"}
    assert public["content_hash"] == content_hash(public_body)
    assert public["content_hash"] != payload["content_hash"]


def test_incomplete_package_is_hold_for_data(tmp_path: Path) -> None:
    docs = incomplete_documents(tmp_path / "docs-incomplete")
    payload = produce_happy(tmp_path, documents=docs)
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    reasons = set(payload["reason_codes"])
    assert reasons & {
        "missing_document",
        "insufficient_coverage",
        "BLOCKED_BY_MISSING_DOCUMENT",
        "mapped_from_blocked_by_missing_document",
    }
    assert "REQ-TEC-001" in payload["summary"]["missing_items"] or any(
        "BLOCKED_BY_MISSING_DOCUMENT" in str(item) for item in payload["summary"]["blockers"]
    )


def test_missing_edital_is_hold_unknown_not_negative(tmp_path: Path) -> None:
    payload = produce_happy(tmp_path, edital=None)
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    assert "missing_edital" in payload["reason_codes"]
    statements = " ".join(finding["statement"].lower() for finding in payload["findings"])
    assert "unknown" in statements or "absence" in statements
    assert "inabilit" not in statements


def test_missing_planilha_is_hold(tmp_path: Path) -> None:
    payload = produce_happy(tmp_path, planilha=tmp_path / "does-not-exist.xlsx")
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    assert "missing_planilha" in payload["reason_codes"]


def test_incomplete_document_is_unknown(tmp_path: Path) -> None:
    short = tmp_path / "short.txt"
    short.write_text("x", encoding="utf-8")
    payload = produce_happy(tmp_path, edital=short)
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    assert "incomplete_document" in payload["reason_codes"]


def test_unreadable_pdf_is_unknown(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"%PDF-1.4\nnot-a-real-pdf\x00\xff\xfe")
    payload = produce_happy(tmp_path, edital=pdf)
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    assert any(code in payload["reason_codes"] for code in ("unreadable_pdf", "incomplete_document"))


def test_xlsx_formula_value_conflict_is_risk(tmp_path: Path) -> None:
    golden = build_golden(tmp_path / "golden.xlsx")
    payload = produce_happy(tmp_path, planilha=golden)
    _assert_flags(payload)
    budget = [finding for finding in payload["findings"] if finding["category"] == "budget"]
    assert any(finding["state"] == "RISK" and finding.get("method") for finding in budget)
    assert any(
        "formula_value_conflict" in finding["reason_codes"]
        or "incompatible_unit" in finding["reason_codes"]
        or "arithmetic_divergence" in finding["reason_codes"]
        for finding in budget
    )


def test_incompatible_unit_is_risk(tmp_path: Path) -> None:
    golden = build_golden(tmp_path / "units.xlsx")
    payload = produce_happy(tmp_path, planilha=golden)
    _assert_flags(payload)
    assert any("incompatible_unit" in finding["reason_codes"] for finding in payload["findings"])


def test_contradictory_requirement_is_unknown(tmp_path: Path) -> None:
    edital = tmp_path / "contra.txt"
    edital.write_text(
        "Objeto da licitacao: pavimentacao asfaltica de vias urbanas ficticias com drenagem.\n"
        "Consorcio sera permitido para este certame ficticio conforme item 5.\n"
        "Consorcio vedado para participantes deste certame ficticio conforme item 6.\n"
        "Texto complementar para ultrapassar o limiar de cobertura textual da fixture.\n",
        encoding="utf-8",
    )
    payload = produce_happy(tmp_path, edital=edital)
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    assert "contradictory_requirement" in payload["reason_codes"]
    contra = [finding for finding in payload["findings"] if "contradictory_requirement" in finding["reason_codes"]]
    assert contra
    assert contra[0]["state"] == "UNKNOWN"
    assert contra[0]["contradiction_links"]


def test_missing_acervo_is_hold(tmp_path: Path) -> None:
    payload = produce_happy(tmp_path, acervo=None)
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    assert "missing_acervo" in payload["reason_codes"]


def test_sensitive_acervo_is_risk(tmp_path: Path) -> None:
    store = json.loads((FIXTURES / "acervo.json").read_text(encoding="utf-8"))
    store["professionals"][0]["cpf"] = "123.456.789-00"
    path = tmp_path / "sensitive.json"
    path.write_text(json.dumps(store), encoding="utf-8")
    payload = produce_happy(tmp_path, acervo=path)
    _assert_flags(payload)
    assert any("sensitive_acervo" in finding["reason_codes"] for finding in payload["findings"])


def test_unavailable_engine_is_unknown_hold(tmp_path: Path) -> None:
    payload = produce_happy(tmp_path, engines_available={"edital_case": False})
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    assert "engine_unavailable" in payload["reason_codes"]


def test_reject_before_parse_disallowed_type(tmp_path: Path) -> None:
    evil = tmp_path / "payload.exe"
    evil.write_bytes(b"MZ\x00fake")
    payload = produce_happy(tmp_path, edital=evil)
    _assert_flags(payload)
    assert payload["overall_state"] == "REJECT"
    assert "malware_like" in payload["reason_codes"]


def test_absence_does_not_become_silent_negative(tmp_path: Path) -> None:
    payload = produce_happy(tmp_path, documents=None)
    _assert_flags(payload)
    assert payload["overall_state"] == "HOLD_FOR_DATA"
    statements = " ".join(finding["statement"].lower() for finding in payload["findings"])
    assert "inabilitad" not in statements
    assert "proposta inexequ" not in statements
    assert payload["overall_state"] != "REJECT"


def test_two_runs_same_hash_policy_change_differs(tmp_path: Path) -> None:
    planilha = clean_workbook(tmp_path / "planilha.xlsx")
    first = produce_happy(tmp_path / "a", planilha=planilha)
    second = produce_happy(tmp_path / "b", planilha=planilha)
    assert first["content_hash"] == second["content_hash"]
    third = produce_happy(
        tmp_path / "c",
        planilha=planilha,
        policy={"policy_version": "public-read-bid-readiness-policy/1.0-delta"},
    )
    assert third["content_hash"] != first["content_hash"]
    other = tmp_path / "other.txt"
    other.write_text((FIXTURES / "edital.txt").read_text(encoding="utf-8") + "\nextra line\n", encoding="utf-8")
    fourth = produce_happy(tmp_path / "e", planilha=planilha, edital=other)
    assert fourth["content_hash"] != first["content_hash"]
    changed_entity = produce_happy(
        tmp_path / "f",
        planilha=planilha,
        entity={"cnpj": "12345678000199", "razao_social": "OUTRA EMPRESA FICTICIA"},
    )
    assert changed_entity["query_id"] != first["query_id"]
    assert changed_entity["content_hash"] != first["content_hash"]


def test_authorized_manifest_cannot_escape_to_sibling_prefix(tmp_path: Path) -> None:
    base = tmp_path / "case"
    sibling = tmp_path / "case-evil"
    base.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret", encoding="utf-8")
    manifest = base / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "authorized": True,
                "files": [{"role": "edital", "path": "../case-evil/secret.txt"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RejectedInputError, match="escapes base") as caught:
        load_authorized_manifest(manifest)
    assert caught.value.reason_code == "manifest_path_escape"


def test_authorized_manifest_is_preflighted_before_json_parse(tmp_path: Path) -> None:
    target = tmp_path / "manifest-target.json"
    target.write_text('{"authorized": true}', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.symlink_to(target)

    with pytest.raises(RejectedInputError, match="symlink") as caught:
        load_authorized_manifest(manifest)
    assert caught.value.reason_code == "symlink_blocked"


def test_cli_entity_is_preflighted_before_json_parse(tmp_path: Path) -> None:
    target = tmp_path / "entity-target.json"
    target.write_text('{"razao_social": "PESSOA FICTICIA"}', encoding="utf-8")
    entity = tmp_path / "entity.json"
    entity.symlink_to(target)

    with pytest.raises(RejectedInputError, match="symlink") as caught:
        main(["run", "--entity", str(entity), "--work-dir", str(tmp_path / "work")])
    assert caught.value.reason_code == "symlink_blocked"


def test_cli_run_twice_and_validate(tmp_path: Path) -> None:
    planilha = tmp_path / "planilha.xlsx"
    clean_workbook(planilha)
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    work1 = tmp_path / "w1"
    work2 = tmp_path / "w2"
    common = [
        "run",
        "--edital",
        str(FIXTURES / "edital.txt"),
        "--planilha",
        str(planilha),
        "--documents",
        str(FIXTURES / "documents"),
        "--acervo",
        str(FIXTURES / "acervo.json"),
        "--requirements",
        str(FIXTURES / "requirements.json"),
        "--as-of",
        CLOCK,
        "--entity",
        str(FIXTURES / "entity.json"),
    ]
    assert main([*common, "--work-dir", str(work1), "--out", str(out1)]) == 0
    assert main([*common, "--work-dir", str(work2), "--out", str(out2)]) == 0
    run1 = json.loads(out1.read_text(encoding="utf-8"))
    run2 = json.loads(out2.read_text(encoding="utf-8"))
    assert run1["content_hash"] == run2["content_hash"]
    assert run1["schema_version"] == SCHEMA_VERSION
    assert main(["validate", "--payload", str(out1)]) == 0
    public_out = tmp_path / "public.json"
    with pytest.raises(EnvelopeValidationError, match="public_export_requires_redacted_fixture"):
        main(
            [
                *common,
                "--work-dir",
                str(tmp_path / "private-w3"),
                "--public-out",
                str(public_out),
            ]
        )
    assert not public_out.exists()
    assert (
        main(
            [
                *common,
                "--source-access",
                "redacted_fixture",
                "--work-dir",
                str(tmp_path / "w3"),
                "--out",
                str(tmp_path / "run3.json"),
                "--public-out",
                str(public_out),
            ]
        )
        == 0
    )
    public = json.loads(public_out.read_text(encoding="utf-8"))
    assert public["source_access"] == "redacted_fixture"
    assert public["publication_authorization"] is False
    public_body = {key: value for key, value in public.items() if key != "content_hash"}
    assert public["content_hash"] == content_hash(public_body)
    private = json.loads((tmp_path / "run3.json").read_text(encoding="utf-8"))
    assert private["source_access"] == "redacted_fixture"
    assert public["content_hash"] == private["content_hash"]


def test_public_export_redacts_known_pii_and_rejects_stale_hash(tmp_path: Path) -> None:
    fixture = produce_happy(tmp_path, source_access="redacted_fixture")
    finding = dict(fixture["findings"][0])
    finding["statement"] = (
        "CPF 123.456.789-00; contato pessoa@example.com; assinatura digital; "
        "responsavel PESSOA FICTICIA"
    )
    fixture = attach_hash({**fixture, "findings": [finding, *fixture["findings"][1:]]})

    public = public_envelope(fixture)
    assert "123.456.789-00" not in public["findings"][0]["statement"]
    assert "pessoa@example.com" not in public["findings"][0]["statement"]
    assert "assinatura digital" not in public["findings"][0]["statement"].lower()
    assert scan_payload_for_pii(public) == []

    stale = {**fixture, "overall_state": "REJECT"}
    with pytest.raises(EnvelopeValidationError, match="content_hash_mismatch"):
        public_envelope(stale)


def test_cli_incomplete_package_holds(tmp_path: Path) -> None:
    planilha = tmp_path / "planilha.xlsx"
    clean_workbook(planilha)
    docs = incomplete_documents(tmp_path / "docs-incomplete")
    out = tmp_path / "hold.json"
    assert (
        main(
            [
                "run",
                "--edital",
                str(FIXTURES / "edital.txt"),
                "--planilha",
                str(planilha),
                "--documents",
                str(docs),
                "--acervo",
                str(FIXTURES / "acervo.json"),
                "--requirements",
                str(FIXTURES / "requirements.json"),
                "--as-of",
                CLOCK,
                "--entity",
                str(FIXTURES / "entity.json"),
                "--work-dir",
                str(tmp_path / "hold-work"),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["overall_state"] == "HOLD_FOR_DATA"
