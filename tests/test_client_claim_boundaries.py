"""Client claim guard tests — positive + adversarial."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.audit_client_claim_boundaries import scan_claims

ROOT = Path(__file__).resolve().parents[1]


def test_disclaimer_not_flagged() -> None:
    result = scan_claims(
        root=ROOT,
        extra_text={
            "docs/sample.md": "O sistema não promete vitória garantida nem aprovação garantida.\n",
        },
    )
    open_paths = [f["path"] for f in result["open_findings"]]
    assert "docs/sample.md" not in open_paths


def test_forbidden_claim_flagged() -> None:
    result = scan_claims(
        root=ROOT,
        extra_text={
            "templates/pitch.md": "Garantimos vitória garantida em todas as licitações.\n",
        },
    )
    assert result["ok"] is False
    assert any(f["path"] == "templates/pitch.md" for f in result["open_findings"])


def test_dod_exceptions() -> None:
    """Scanning real repo: DOD prohibitions themselves should be excepted."""
    result = scan_claims(root=ROOT)
    dod_open = [f for f in result["open_findings"] if f["path"] == "DOD.md"]
    assert dod_open == []


def test_lawyer_claim() -> None:
    result = scan_claims(
        root=ROOT,
        extra_text={
            "templates/legal.md": "Nosso software substitui o advogado em recursos administrativos.\n",
        },
    )
    assert any(f["claim_id"] == "replaces_lawyer" for f in result["open_findings"])


def test_auto_sign_claim() -> None:
    result = scan_claims(
        root=ROOT,
        extra_text={
            "templates/x.md": "Oferecemos assinatura automática dos documentos da Extra.\n",
        },
    )
    assert any(f["claim_id"] == "auto_sign" for f in result["open_findings"])
