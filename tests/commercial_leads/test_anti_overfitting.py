"""Ensure sector/relevance rules do not hardcode specific CNPJs or razao sociais."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES = [
    ROOT / "scripts/commercial_leads/sector_fit.py",
    ROOT / "scripts/commercial_leads/contract_relevance.py",
    ROOT / "scripts/commercial_leads/commercial_validity.py",
]


def test_no_hardcoded_cnpj_in_classifiers() -> None:
    for path in MODULES:
        text = path.read_text(encoding="utf-8")
        # 14-digit sequences that look like CNPJs
        import re

        hits = re.findall(r"(?<!\d)\d{14}(?!\d)", text)
        # allow none
        assert not hits, f"{path} contains hardcoded CNPJ digits: {hits}"


def test_no_top20_company_name_allowlist() -> None:
    banned_names = [
        "BRANIX EMPREENDIMENTOS",
        "CONSTRUBRÁS",
        "FAK EMPREENDIMENTOS",
        "PROJESOL ENGENHARIA",
        "KARAIBA CONSULTORIA",
        "COSTA OESTE SERVICOS",
        "PAX COMERCIO DE PNEUS",
        "MG AUTO PECAS",
    ]
    for path in MODULES:
        text = path.read_text(encoding="utf-8").upper()
        for name in banned_names:
            assert name.upper() not in text, f"{path} hardcodes company name {name}"


def test_holdout_not_embedded_in_classifier_source() -> None:
    holdout = ROOT / "evals/commercial_leads/holdout-v1.jsonl"
    assert holdout.is_file()
    # classifier must not import holdout file
    for path in MODULES:
        text = path.read_text(encoding="utf-8")
        assert "holdout-v1" not in text
        assert "evals/commercial_leads" not in text
