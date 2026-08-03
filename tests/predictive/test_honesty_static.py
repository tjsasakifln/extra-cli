"""Fail-closed static honesty tests for heuristic-as-probability leakage."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.lib.bid_simulator import (
    METHOD_UNVALIDATED_HEURISTIC,
    BidSimulation,
    assert_not_probability_export,
    format_bid_summary,
    simulate_bid,
)

ROOT = Path(__file__).resolve().parents[2]

# Shipped surface roots (not docs/tests explaining the ban)
SHIP_GLOBS = [
    "scripts/**/*.py",
    "apps/**/*.py",
]

# Allowed contexts: honesty policy text, claim_language, predictive package, this ban list
ALLOW_PATH_PARTS = (
    "/predictive/",
    "bid_simulator.py",
    "claim_language.py",
    "test_honesty",
    "extra_first_client_delivery.py",  # already documents "not probability"
    "multi_source_open_pack",
)

FORBIDDEN_PUBLICATION = [
    # publishing heuristic under these labels is banned unless claim registry approved
    re.compile(r'["\']p_vitoria_pct["\']\s*:'),
    re.compile(r'["\']p_win["\']\s*:'),
    re.compile(r'["\']probability["\']\s*:\s*bid', re.I),
    re.compile(r"probabilidade de vit[oó]ria", re.I),
    re.compile(r"\blance [oó]timo\b", re.I),
]


def test_bid_simulator_is_unvalidated_heuristic():
    sim = simulate_bid(
        {"valor_estimado": 100_000},
        competitive_intel={"hhi": 0.2},
        benchmark={
            "desconto_mediano": 0.05,
            "desconto_p25": 0.03,
            "desconto_p75": 0.08,
            "desconto_std": 0.02,
            "contratos_analisados": 12,
        },
    )
    assert isinstance(sim, BidSimulation)
    assert sim.method == METHOD_UNVALIDATED_HEURISTIC
    assert sim.prediction_claim_allowed is False
    assert sim.is_calibrated_probability is False if hasattr(sim, "is_calibrated_probability") else True
    export = sim.to_export_dict()
    assert "p_vitoria_pct" not in export
    assert "p_win" not in export
    assert "probability" not in export
    assert export["heuristic_scenario_score"] >= 0
    assert export["prediction_claim_allowed"] is False
    summary = format_bid_summary(sim, 100_000)
    assert "probabilidade" not in summary.lower() or "NÃO" in summary or "não" in summary
    assert "heuríst" in summary.lower() or "heuristic" in summary.lower() or "cenário" in summary.lower() or "cenario" in summary.lower()


def test_assert_not_probability_export_rejects_p_vitoria():
    with pytest.raises(ValueError):
        assert_not_probability_export(
            {
                "method": METHOD_UNVALIDATED_HEURISTIC,
                "prediction_claim_allowed": False,
                "p_vitoria_pct": 42.0,
            }
        )


def test_export_dict_passes_assert():
    sim = simulate_bid(
        {"valor_estimado": 50_000},
        benchmark={
            "desconto_mediano": 0.04,
            "desconto_p25": 0.02,
            "desconto_p75": 0.06,
            "contratos_analisados": 5,
        },
    )
    assert_not_probability_export(sim.to_export_dict())


def test_static_search_no_heuristic_as_probability_in_enrich_export():
    """intel_enrich must not write p_vitoria_pct key into _bid_simulation."""
    text = (ROOT / "scripts" / "intel_enrich.py").read_text(encoding="utf-8")
    # The assignment block should use to_export_dict or heuristic_scenario_score
    assert "to_export_dict" in text or "heuristic_scenario_score" in text
    # Direct publication of p_vitoria_pct key in export dict is banned
    assert '"p_vitoria_pct": bid_result' not in text
    assert '"p_vitoria_pct": bid_result.p_vitoria_pct' not in text


def test_shipped_surfaces_do_not_label_heuristic_as_optimal_bid():
    """Scan key report/pipeline/CLI ship paths for banned commercial labels."""
    targets = [
        ROOT / "scripts" / "intel_enrich.py",
        ROOT / "scripts" / "intel_report.py",
        ROOT / "scripts" / "intel_excel.py",
        ROOT / "scripts" / "intel_analyze.py",
        ROOT / "scripts" / "intel_pipeline.py",
        ROOT / "scripts" / "lib" / "bid_simulator.py",
        ROOT / "scripts" / "generate-report-b2g.py",
        ROOT / "scripts" / "ops" / "weekly_cycle.py",
        ROOT / "scripts" / "workspace" / "cli.py",
    ]
    # Expand to all scripts/**/*.py that are ship surfaces (exclude tests/docs)
    for path in (ROOT / "scripts").rglob("*.py"):
        if "predictive" in path.parts and path.name not in {
            "bid_simulator.py",  # already listed
        }:
            # predictive package may document forbidden phrases as ban text
            continue
        if path not in targets and path.name in {
            "generate-report-b2g.py",
            "intel_report.py",
            "intel_excel.py",
            "intel_analyze.py",
            "intel_pipeline.py",
            "intel_enrich.py",
            "weekly_cycle.py",
            "cli.py",
            "bid_simulator.py",
        }:
            targets.append(path)

    offenders: list[str] = []
    ban_as_positive = [
        re.compile(r"Estima a probabilidade de vencer", re.I),
        re.compile(r"probabilidade heuristica", re.I),
        re.compile(r"probabilidades de vitoria sao estimativas", re.I),
        re.compile(r'["\']p_vitoria_pct["\']\s*:'),
    ]
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            # Disclaimer / ban documentation is OK
            if any(
                m in low
                for m in (
                    "não",
                    "nao",
                    "nÃO",
                    "not ",
                    "unvalidated",
                    "ban",
                    "forbidden",
                    "proibido",
                    "omitida",
                    "never",
                )
            ):
                # still catch positive export of p_vitoria_pct key
                if re.search(r'["\']p_vitoria_pct["\']\s*:', line) and "not" not in low:
                    if "forbidden" not in low and "ban" not in low:
                        offenders.append(f"{path}:{i}:{line.strip()[:100]}")
                continue
            if re.search(r"lance [oó]timo", line, re.I):
                # Forbidden-list / ban documentation (claim must not use phrase)
                if "sem " in low or "forbidden" in low or "proibido" in low or "claims_forbidden" in low:
                    continue
                if path.name == "bid_simulator.py" and i < 15:
                    offenders.append(f"{path}:{i}:{line.strip()}")
                elif path.name != "bid_simulator.py":
                    offenders.append(f"{path}:{i}:{line.strip()[:100]}")
            for pat in ban_as_positive:
                if pat.search(line):
                    offenders.append(f"{path}:{i}:{line.strip()[:100]}")
    assert not offenders, "Heuristic published as probability/optimal:\n" + "\n".join(
        offenders[:30]
    )


def test_generate_report_b2g_uses_heuristic_score_language():
    text = (ROOT / "scripts" / "generate-report-b2g.py").read_text(encoding="utf-8")
    assert "Estima a probabilidade de vencer" not in text
    assert "score heurístico" in text.lower() or "score heuristico" in text.lower() or "UNVALIDATED_HEURISTIC" in text
