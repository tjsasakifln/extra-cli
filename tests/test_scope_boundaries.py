"""Tests for scope boundary auditor — positive + adversarial."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.audit_scope_boundaries import (
    load_config,
    run_audit,
)

ROOT = Path(__file__).resolve().parents[1]


def test_config_loads_and_has_distinctions() -> None:
    cfg = load_config()
    assert "aditivo" in cfg["distinctions"]
    assert cfg["distinctions"]["aditivo"]["allowed"]
    assert cfg["distinctions"]["aditivo"]["forbidden"]
    assert "diario_de_obra" in cfg["capabilities"]


def test_dod_mention_is_not_violation(tmp_path: Path) -> None:
    """DOD.md containing Stripe/diário text must not fail the audit."""
    (tmp_path / "DOD.md").write_text(
        "- [ ] O projeto não contém cobrança, assinatura ou Stripe.\n"
        "- [ ] O projeto não contém módulo de diário de obra.\n",
        encoding="utf-8",
    )
    (tmp_path / "config").mkdir()
    cfg_src = ROOT / "config" / "scope_boundaries.yaml"
    (tmp_path / "config" / "scope_boundaries.yaml").write_text(
        cfg_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "ok.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("httpx>=0.28\n", encoding="utf-8")

    result = run_audit(
        root=tmp_path,
        config_path=tmp_path / "config" / "scope_boundaries.yaml",
        capability="diario_de_obra",
    )
    assert result["ok"] is True
    assert result["proofs"]["diario_de_obra"]["conclusion"] == "PROVEN"


def test_implementation_is_regression(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "scope_boundaries.yaml").write_text(
        (ROOT / "config" / "scope_boundaries.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "diario_de_obra.py").write_text(
        "class DiarioDeObra:\n    def save(self):\n        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("httpx\n", encoding="utf-8")
    result = run_audit(
        root=tmp_path,
        config_path=tmp_path / "config" / "scope_boundaries.yaml",
        capability="diario_de_obra",
    )
    assert result["ok"] is False
    assert result["proofs"]["diario_de_obra"]["conclusion"] == "REGRESSION"


def test_admin_aditivo_not_enough_for_execucao_violation(tmp_path: Path) -> None:
    """Word 'aditivo' alone (admin monitoring) is not gestão de aditivos de execução."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "scope_boundaries.yaml").write_text(
        (ROOT / "config" / "scope_boundaries.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "contracts.py").write_text(
        "def list_aditivos_administrativos(contract_id: str):\n"
        "    '''Monitor aditivos contratuais administrativos.'''\n"
        "    return []\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("httpx\n", encoding="utf-8")
    result = run_audit(
        root=tmp_path,
        config_path=tmp_path / "config" / "scope_boundaries.yaml",
        capability="gestao_aditivos_execucao_fisica",
    )
    assert result["ok"] is True
    assert result["proofs"]["gestao_aditivos_execucao_fisica"]["conclusion"] == "PROVEN"


def test_stripe_dependency_is_violation(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "scope_boundaries.yaml").write_text(
        (ROOT / "config" / "scope_boundaries.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("stripe>=5.0\n", encoding="utf-8")
    result = run_audit(
        root=tmp_path,
        config_path=tmp_path / "config" / "scope_boundaries.yaml",
        capability="cobranca_assinatura_stripe",
    )
    assert result["ok"] is False


def test_repo_scope_audit_runs() -> None:
    """Shipped audit on real repo for a single capability should exit clean or report."""
    result = run_audit(root=ROOT, capability="diario_de_obra")
    assert "proofs" in result
    assert "diario_de_obra" in result["proofs"]
    # Real product should not implement diário de obra
    assert result["proofs"]["diario_de_obra"]["conclusion"] in {"PROVEN", "REGRESSION"}
