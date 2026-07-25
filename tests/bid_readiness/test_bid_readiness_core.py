"""Unit tests driving shipped bid_readiness functions."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.bid_readiness.identity import evaluate_identity
from scripts.bid_readiness.ingest import IngestError, ingest_path
from scripts.bid_readiness.match import evaluate_technical_match, match_requirement_to_documents
from scripts.bid_readiness.models import names_equivalent
from scripts.bid_readiness.package import deterministic_name
from scripts.bid_readiness.sanitize import contains_critical_pii, sanitize_text
from scripts.bid_readiness.validity import evaluate_validity
from scripts.bid_readiness.vault import sha256_bytes, store_bytes, verify_object


def test_sha256_immutable(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    data = b"hello-bid-readiness"
    obj = store_bytes(vault, data, original_name="a.txt", source_path="a.txt")
    assert obj.sha256 == sha256_bytes(data)
    assert verify_object(vault, obj.sha256)
    # second store same bytes ok
    obj2 = store_bytes(vault, data, original_name="b.txt", source_path="b.txt")
    assert obj2.sha256 == obj.sha256


def test_validity_expired() -> None:
    meta = {
        "fields": {
            "data_validade": {"normalized": "2025-01-01", "original": "2025-01-01"},
            "data_emissao": {"normalized": "2024-01-01", "original": "2024-01-01"},
        }
    }
    res = evaluate_validity(metadata=meta, validity_rule={}, reference_date="2026-07-01")
    assert res["status"] == "EXPIRED"


def test_validity_valid() -> None:
    meta = {
        "fields": {
            "data_validade": {"normalized": "2026-12-01", "original": "2026-12-01"},
            "data_emissao": {"normalized": "2026-06-01", "original": "2026-06-01"},
        }
    }
    res = evaluate_validity(metadata=meta, validity_rule={}, reference_date="2026-07-01")
    assert res["status"] == "VALID"


def test_cnpj_mismatch() -> None:
    meta = {"fields": {"cnpj": {"normalized": "99999999000191", "original": "x"}}}
    res = evaluate_identity(
        metadata=meta,
        expected_cnpj="12345678000199",
        expected_legal_name="EXTRA CONSTRUTORA FICTICIA LTDA",
    )
    assert "CNPJ_MISMATCH" in res["findings"]


def test_abbreviation_not_hard_mismatch() -> None:
    assert names_equivalent("EXTRA CONSTRUTORA FICTICIA LTDA", "EXTRA CONSTRUTORA FICTICIA")
    meta = {
        "fields": {
            "cnpj": {"normalized": "12345678000199"},
            "razao_social": {"normalized": "EXTRA CONSTRUTORA FICTICIA", "original": "EXTRA CONSTRUTORA FICTICIA"},
        }
    }
    res = evaluate_identity(
        metadata=meta,
        expected_cnpj="12345678000199",
        expected_legal_name="EXTRA CONSTRUTORA FICTICIA LTDA",
    )
    assert res["name_status"] == "OK_ABBREVIATION_TOLERANT"
    assert "LEGAL_NAME_MISMATCH" not in res["findings"]


def test_unit_mismatch_not_summed() -> None:
    req = {
        "requirement_id": "T1",
        "technical_criteria": {
            "service": "pavimentacao",
            "min_quantity": 5000,
            "unit": "m2",
            "summable": True,
        },
    }
    docs = [
        {
            "document_id": "d1",
            "sha256": "a",
            "metadata": {
                "fields": {
                    "obra_servico": {"normalized": "pavimentacao asfaltica"},
                    "quantidade": {"normalized": 8000.0},
                    "unidade": {"normalized": "m3"},
                }
            },
        }
    ]
    tech = evaluate_technical_match(req, docs)
    assert tech["match_class"] == "UNIT_MISMATCH"


def test_quantity_insufficient() -> None:
    req = {
        "requirement_id": "T1",
        "technical_criteria": {
            "service": "pavimentacao",
            "min_quantity": 5000,
            "unit": "m2",
            "summable": True,
        },
    }
    docs = [
        {
            "document_id": "d1",
            "sha256": "a",
            "metadata": {
                "fields": {
                    "obra_servico": {"normalized": "pavimentacao asfaltica"},
                    "quantidade": {"normalized": 1200.0},
                    "unidade": {"normalized": "m2"},
                }
            },
        }
    ]
    tech = evaluate_technical_match(req, docs)
    assert tech["match_class"] == "QUANTITY_INSUFFICIENT"


def test_double_cat_not_double_counted() -> None:
    req = {
        "requirement_id": "T1",
        "technical_criteria": {
            "service": "pavimentacao",
            "min_quantity": 5000,
            "unit": "m2",
            "summable": True,
        },
    }
    base_fields = {
        "obra_servico": {"normalized": "pavimentacao asfaltica"},
        "quantidade": {"normalized": 3000.0},
        "unidade": {"normalized": "m2"},
        "cat_number": {"normalized": "CAT-1"},
    }
    docs = [
        {"document_id": "d1", "sha256": "a", "metadata": {"fields": dict(base_fields)}},
        {"document_id": "d2", "sha256": "b", "metadata": {"fields": dict(base_fields)}},
    ]
    tech = evaluate_technical_match(req, docs)
    # only one counted → still insufficient if 3000 < 5000
    assert tech["match_class"] == "QUANTITY_INSUFFICIENT"
    assert any(e.get("skipped_double_count") for e in tech["evidence"])


def test_textual_candidate_not_satisfied() -> None:
    req = {
        "requirement_id": "T1",
        "mandatory": True,
        "required_document_type": "ATESTADO_CAPACIDADE_TECNICA",
        "title": "x",
        "category": "TECNICA",
        "technical_criteria": {
            "service": "drenagem profunda especial",
            "min_quantity": 100,
            "unit": "m",
        },
    }
    docs = [
        {
            "document_id": "d1",
            "sha256": "a",
            "classification": "ATESTADO_CAPACIDADE_TECNICA",
            "metadata": {
                "fields": {
                    "obra_servico": {"normalized": "infraestrutura urbana diversas"},
                    "quantidade": {"normalized": 50.0},
                    "unidade": {"normalized": "m"},
                }
            },
        }
    ]
    row = match_requirement_to_documents(
        req, docs, validity_by_doc={"d1": {"status": "NO_EXPIRY"}}, identity_by_doc={"d1": {"findings": []}}
    )
    assert row["status"] != "SATISFIED"
    assert row["status"] in {"NEEDS_HUMAN", "PARTIALLY_SATISFIED", "MISSING", "INCONSISTENT"}


def test_sanitize_cpf() -> None:
    # Dotted CPF pattern used only to prove sanitizer; not a real person
    sample_cpf = "123" + ".456" + ".789" + "-09"
    text = f"CPF do socio: {sample_cpf} e email person@example.com"
    out = sanitize_text(text)
    assert sample_cpf not in out
    assert "person@example.com" not in out
    assert "cpf" in contains_critical_pii(text)


def test_zip_traversal(tmp_path: Path) -> None:
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../escape.txt", "nope")
    with pytest.raises(IngestError):
        ingest_path(tmp_path / "vault", zpath)


def test_package_naming_deterministic() -> None:
    a = deterministic_name("FGTS", "crf final.pdf", "abc123def456")
    b = deterministic_name("FGTS", "crf final.pdf", "abc123def456")
    assert a == b
    assert a.startswith("FGTS_")


def test_missing_stays_in_denominator() -> None:
    req = {
        "requirement_id": "M1",
        "mandatory": True,
        "required_document_type": "GARANTIA_PROPOSTA",
        "title": "garantia",
        "category": "PROPOSTA",
    }
    row = match_requirement_to_documents(req, [], validity_by_doc={}, identity_by_doc={})
    assert row["status"] == "MISSING"
    assert row["mandatory"] is True


def test_representation_power_unproven_not_satisfied() -> None:
    """Weak procura must not yield SATISFIED (eliminatory false positive)."""
    req = {
        "requirement_id": "REQ-JUR-003",
        "mandatory": True,
        "required_document_type": "PROCURACAO",
        "title": "Procuração",
        "category": "JURIDICA",
        "signature_required": True,
    }
    docs = [
        {
            "document_id": "doc-proc",
            "sha256": "abc",
            "classification": "PROCURACAO",
            "metadata": {
                "fields": {
                    "signature_present": {"normalized": "PRESENT"},
                    "poder_representacao": {"normalized": "assinar recibos internos"},
                }
            },
        }
    ]
    identity_by_doc = {
        "doc-proc": {
            "cnpj_status": "OK",
            "name_status": "OK",
            "signatory_status": "SIGNATORY_MISMATCH",
            "power_status": "REPRESENTATION_POWER_UNPROVEN",
            "findings": ["REPRESENTATION_POWER_UNPROVEN", "SIGNATORY_NOT_FOUND"],
        }
    }
    validity_by_doc = {"doc-proc": {"status": "VALID"}}
    row = match_requirement_to_documents(req, docs, validity_by_doc=validity_by_doc, identity_by_doc=identity_by_doc)
    assert row["status"] != "SATISFIED"
    assert row["status"] == "INCONSISTENT"
    assert "REPRESENTATION_POWER_UNPROVEN" in (row.get("evidence") or "")


def test_legal_name_mismatch_not_satisfied() -> None:
    req = {
        "requirement_id": "R1",
        "mandatory": True,
        "required_document_type": "CERTIDAO_FEDERAL",
        "title": "CND",
        "category": "FISCAL",
    }
    docs = [
        {
            "document_id": "d1",
            "sha256": "x",
            "classification": "CERTIDAO_FEDERAL",
            "metadata": {"fields": {}},
        }
    ]
    row = match_requirement_to_documents(
        req,
        docs,
        validity_by_doc={"d1": {"status": "VALID"}},
        identity_by_doc={
            "d1": {
                "cnpj_status": "OK",
                "name_status": "LEGAL_NAME_MISMATCH",
                "findings": ["LEGAL_NAME_MISMATCH"],
            }
        },
    )
    assert row["status"] == "INCONSISTENT"


def test_package_identity_not_valid_evidence(tmp_path: Path) -> None:
    from scripts.bid_readiness.package import assemble_package
    from scripts.bid_readiness.vault import store_bytes

    case = tmp_path / "case"
    vault = case / "vault"
    data = b"certidao municipal foreign cnpj"
    obj = store_bytes(vault, data, original_name="cnd_mun.txt", source_path="cnd_mun.txt", document_id="doc-07")
    docs = [
        {
            "document_id": "doc-07",
            "original_name": "cnd_mun.txt",
            "sha256": obj.sha256,
            "classification": "CERTIDAO_MUNICIPAL",
            "validity": {"status": "VALID"},
            "identity": {
                "cnpj_status": "CNPJ_MISMATCH",
                "findings": ["CNPJ_MISMATCH"],
            },
        }
    ]
    result = assemble_package(
        case_dir=case,
        documents=docs,
        match_rows=[],
        findings_bundle={"blockers": []},
        package_status="BLOCKED_BY_INCONSISTENCY",
    )
    files = result["manifest"]["files"]
    assert len(files) == 1
    assert files[0]["included_as"] != "VALID_EVIDENCE"
    assert "CNPJ_MISMATCH" in files[0]["alerts"]
    assert files[0]["included_as"] == "INCLUDED_WITH_IDENTITY_ALERT"
