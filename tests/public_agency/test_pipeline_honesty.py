"""Honesty gates: contacts, mode, fragmentation, population provenance on real pipeline path."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.public_agency import MODE_PROACTIVE, MODE_REACTIVE
from scripts.public_agency.pipeline import run_public_agency_pipeline
from scripts.public_agency.population import load_population_map


def _rows() -> list[dict]:
    return [
        {
            "contrato_id": f"c{i}",
            "orgao_cnpj": "83102373000100",
            "orgao_nome": "PREFEITURA MUNICIPAL DE JUPIÁ",
            "objeto_contrato": obj,
            "valor_total": val,
            "data_publicacao": pub,
            "data_inicio": "2025-01-01",
            "data_fim": "2026-12-31",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        }
        for i, (obj, val, pub) in enumerate(
            [
                ("Obra de pavimentação asfáltica trecho 1", 45000, "2025-03-01"),
                ("Obra de pavimentação asfáltica trecho 2", 45000, "2025-06-01"),
                ("Obra de pavimentação asfáltica trecho 3", 45000, "2026-01-10"),
            ],
            start=1,
        )
    ]


def test_pipeline_does_not_invent_institutional_contact(tmp_path: Path):
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "c",
        as_of=date(2026, 7, 15),
        fixture_rows=_rows(),
        skip_kit=True,
    )
    assert r["status"] == "PASS"
    assert r["leads"], "expected publishable lead from recurring engineering works"
    lead = r["leads"][0]
    contacts = lead["contacts"]
    assert contacts.get("has_institutional") is False
    assert contacts.get("accepted") == []
    assert contacts.get("research_actions"), "research action should be listed without claiming contact"
    fired = {s["signal_id"]: s for s in lead["signals"] if s["status"] == "FIRED"}
    # institutional_contact_available must NOT fire with invented true
    if "institutional_contact_available" in fired:
        raise AssertionError("institutional_contact_available must not FIRE without real contact")
    assert lead["score"]["institutional_accessibility_score"] < 0.5


def test_pipeline_mode_is_proactive_for_historical_contracts(tmp_path: Path):
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "m",
        as_of=date(2026, 7, 15),
        fixture_rows=_rows(),
        skip_kit=True,
    )
    for lead in r["leads"]:
        assert lead["mode"] == MODE_PROACTIVE
        assert lead["mode"] != MODE_REACTIVE
        assert "histórico" in (lead.get("probable_problem") or "").lower() or "proativ" in (
            lead.get("probable_problem") or ""
        ).lower() or "possível necessidade" in (lead.get("probable_problem") or "").lower()


def test_pipeline_fragmentation_uses_same_nature_history(tmp_path: Path):
    r = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "f",
        as_of=date(2026, 7, 15),
        fixture_rows=_rows(),
        skip_kit=True,
    )
    assert r["leads"]
    lead = r["leads"][0]
    frag = lead["fragmentation"]
    assert frag["annual_sum_state"] == "DIRECT_CONTRACTING_SUM_UNKNOWN"
    assert frag["annual_sum_known"] is False
    # three same-nature packages/contracts should surface recurring indicator
    assert "recurring_same_nature_contracting" in (frag.get("indicators") or []) or frag.get(
        "fragmentation_suspected"
    )
    assert float(frag.get("observed_contract_sum_in_sample") or 0) > 0


def test_population_map_is_official_ibge_not_placeholders():
    pops = load_population_map()
    # Jupiá and Águas de Chapecó from official API file
    assert pops.get("4209177")  # Jupiá
    assert pops.get("4200507") == 6036  # Águas de Chapecó real Censo 2022
    # synthetic placeholders must not dominate
    from collections import Counter

    c = Counter(pops.values())
    assert c.most_common(1)[0][1] < 5
    assert 12345 not in pops.values()
    # supplement provenance
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sup = (root / "config/commercial/sc_municipality_population_censo2022_supplement.yaml").read_text(
        encoding="utf-8"
    )
    assert "IBGE" in sup and "4714" in sup
    assert "DO NOT hand-edit" in sup
