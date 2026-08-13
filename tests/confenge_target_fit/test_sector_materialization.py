"""Sector persistence remains independent and reconsiderable with target-fit."""

from __future__ import annotations

from scripts.confenge_sector import CONSTRUCTION_CONFIRMED
from scripts.confenge_sector import store as sector_store
from scripts.confenge_sector.store import materialize_sector, publish_sector_materialization
from scripts.confenge_target_fit.loader import company_input_from_dict
from scripts.confenge_target_fit.reconcile import archive_orphan_materializations


def test_construction_with_insufficient_target_fit_has_own_materialization() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "12345678",
            "razao_social": "ENGENHARIA EXEMPLO LTDA",
            "cnae_principal": "7112-0/00",
            "contracts": [],
            "source_watermark": "wm-1",
        }
    )

    sector = materialize_sector(company)

    assert sector.sector_class == CONSTRUCTION_CONFIRMED
    assert sector.company_key == "cnpj_root:12345678"
    assert sector.source_watermark == "wm-1"


def test_sector_fingerprint_changes_when_new_evidence_arrives() -> None:
    before = company_input_from_dict(
        {
            "cnpj_raiz": "12345678",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "contracts": [],
        }
    )
    after = company_input_from_dict(
        {
            "cnpj_raiz": "12345678",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "contracts": [
                {
                    "contrato_id": "new-evidence",
                    "objeto_contrato": "execução de obra de pavimentação",
                    "orgao_cnpj": "12340000000100",
                }
            ],
        }
    )

    assert materialize_sector(before).input_fingerprint != materialize_sector(after).input_fingerprint


def test_sector_materialization_uses_only_observed_valid_establishment() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "11222333",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "branch_cnpjs": ["11222333000181", "11222333000100"],
        }
    )

    sector = materialize_sector(company)

    assert sector.representative_cnpj14 == "11222333000181"


def test_sector_materialization_preserves_classifier_version_from_evidence() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "11222333",
            "construction_evidence": {
                "sector_class": "CONSTRUCTION_CONFIRMED",
                "classifier_version": "custom-sector-v2",
            },
        }
    )

    assert materialize_sector(company).sector_version == "custom-sector-v2"


def test_sector_classifier_hash_is_cached(monkeypatch) -> None:  # noqa: ANN001
    calls = 0
    original = sector_store.inspect.getsource

    def counted(value):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return original(value)

    sector_store.sector_classifier_sha256.cache_clear()
    monkeypatch.setattr(sector_store.inspect, "getsource", counted)
    first = sector_store.sector_classifier_sha256()
    second = sector_store.sector_classifier_sha256()
    assert first == second
    assert calls == 3
    sector_store.sector_classifier_sha256.cache_clear()


def test_sector_materialization_does_not_invent_establishment() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "11222333",
            "razao_social": "CONSTRUTORA EXEMPLO LTDA",
            "branch_cnpjs": ["11222333000100"],
        }
    )

    assert materialize_sector(company).representative_cnpj14 is None


def test_sector_evidence_does_not_embed_target_fit_as_sector_proof() -> None:
    company = company_input_from_dict(
        {
            "cnpj_raiz": "11222333",
            "construction_evidence": {
                "sector_class": "CONSTRUCTION_CONFIRMED",
                "confidence": 0.9,
                "provenance": [
                    {"source": "commercial_leads.sector_fit", "classification": "CONFIRMED"},
                    {"source": "confenge_universe.target_fit", "target_fit_class": "TARGET_CONFIRMED"},
                ],
            },
        }
    )

    sector = materialize_sector(company)

    assert sector.sector_evidence == [
        {"source": "commercial_leads.sector_fit", "classification": "CONFIRMED"}
    ]


def test_sector_publish_recomputes_when_classifier_hash_changes() -> None:
    sector = materialize_sector(
        company_input_from_dict(
            {
                "cnpj_raiz": "12345678",
                "razao_social": "ENGENHARIA EXEMPLO LTDA",
                "cnae_principal": "7112-0/00",
            }
        )
    )

    class Cursor:
        def __init__(self, prior):  # noqa: ANN001
            self.prior = prior
            self.statements: list[str] = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=None):  # noqa: ANN001
            self.statements.append(str(sql))

        def fetchone(self):
            return self.prior

    class Connection:
        def __init__(self, prior):  # noqa: ANN001
            self.cursor_instance = Cursor(prior)

        def cursor(self):
            return self.cursor_instance

    common = {
        "sector_class": sector.sector_class,
        "input_fingerprint": sector.input_fingerprint,
        "sector_version": sector.sector_version,
    }
    unchanged = Connection(
        {**common, "sector_classifier_sha256": sector.sector_classifier_sha256}
    )
    assert publish_sector_materialization(unchanged, sector) is False
    assert len(unchanged.cursor_instance.statements) == 1

    stale = Connection({**common, "sector_classifier_sha256": "stale"})
    assert publish_sector_materialization(stale, sector) is True
    assert len(stale.cursor_instance.statements) == 3


def test_orphan_archive_reports_only_rows_actually_deleted() -> None:
    statements: list[str] = []

    class Cursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params=None):  # noqa: ANN001
            statements.append(str(sql))
            self.rowcount = 0 if str(sql).lstrip().startswith("INSERT") else 1

    class Connection:
        def cursor(self):
            return Cursor()

    archived = archive_orphan_materializations(
        Connection(),
        mode="ACTIVE",
        orphan_rows=[
            {
                "company_key": "cnpj_root:12345678",
                "cnpj_raiz": "12345678",
                "target_fit_class": "TARGET_OUT_OF_SCOPE",
            },
            {
                "company_key": "invalid-root",
                "cnpj_raiz": "123",
                "target_fit_class": "TARGET_OUT_OF_SCOPE",
            },
        ],
        source_watermark="wm-1",
    )

    assert archived == {"cnpj_root:12345678"}
    assert any("DELETE FROM confenge_company_target_fit_current" in sql for sql in statements)
