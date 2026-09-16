"""#551 — F9 organs view uses persisted PROJETO_ENGENHARIA only."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_f9_uses_persisted_projeto_and_sc_entities() -> None:
    sql = (ROOT / "db/migrations/114_orgaos_contratantes_projeto.sql").read_text(encoding="utf-8")
    assert "PROJETO_ENGENHARIA" in sql
    assert "contract_engineering_class" in sql
    assert "sc_public_entities" in sql
    assert "in_sc_public_entities" in sql
    assert "ILIKE" not in sql
    for col in (
        "n_proj_12m",
        "n_proj_24m",
        "v_proj_12m",
        "ultimo_contrato",
        "fornecedores_distintos",
        "uf",
        "municipio",
    ):
        assert col in sql
