"""#547 — F1–F8 profile reads persisted class, not objeto regex."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_profile_joins_persisted_class_not_objeto_regex() -> None:
    sql = (ROOT / "db/migrations/113_supplier_structural_profile.sql").read_text(encoding="utf-8")
    assert "contract_engineering_class" in sql
    assert "PROJETO_ENGENHARIA" in sql
    assert "OBRA_COM_PROJETO" in sql
    assert "ILIKE" not in sql
    assert "objeto_contrato ~" not in sql
    for col in (
        "n_contracts",
        "v_total",
        "first_sig",
        "last_sig",
        "n_orgaos",
        "ufs",
        "n_active",
        "v_active",
        "v_max",
        "n_proj_24m",
        "n_proj_12m",
        "n_obra_90d",
        "n_obra_active_12m",
        "n_integ_12m",
        "n_before_90d",
        "v_max_before_90d",
        "ufs_before_90d",
        "n_ending_60d",
        "recent_objects",
    ):
        assert col in sql
    assert "UNIQUE INDEX" in sql
    assert "refresh_supplier_structural_profile" in sql
