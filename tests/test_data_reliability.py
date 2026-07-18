"""DoD §2.4 — identify untrusted data; no bare percentages without N/limitations."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from scripts.lib.data_reliability import (
    TrustLevel,
    assess_data_reliability,
    attach_reliability_to_run_metadata,
    bare_percentage_is_forbidden,
    format_percentage_with_context,
)
from scripts.lib.claim_language import score_is_not_probability, report_has_limitations


def test_trusted_when_signals_ok() -> None:
    a = assess_data_reliability(
        age_hours=1.0,
        required_fields=["url", "prazo"],
        present_fields=["url", "prazo"],
        provenance_ok=True,
        source_health="ok",
        sample_n=100,
        query_valid=True,
    )
    assert a.trust_level == TrustLevel.TRUSTED
    assert a.is_decision_safe() is True


def test_degraded_on_stale_or_missing_field() -> None:
    a = assess_data_reliability(
        age_hours=30.0,
        required_fields=["url", "prazo"],
        present_fields=["url"],
        provenance_ok=True,
        source_health="ok",
        sample_n=10,
        query_valid=True,
    )
    assert a.trust_level == TrustLevel.DEGRADED
    assert a.is_decision_safe() is False
    assert "prazo" in a.field_flags
    assert a.limitations


def test_untrusted_on_source_down_or_hard_stale() -> None:
    a = assess_data_reliability(
        age_hours=200.0,
        provenance_ok=False,
        source_health="down",
        sample_n=0,
        query_valid=False,
    )
    assert a.trust_level == TrustLevel.UNTRUSTED
    assert not a.is_decision_safe()
    assert any("stale" in r.lower() or "age" in r.lower() for r in a.reasons)


def test_unknown_without_signals() -> None:
    a = assess_data_reliability()
    assert a.trust_level == TrustLevel.UNKNOWN
    assert a.limitations


def test_sparse_signals_not_trusted() -> None:
    """QA CONCERN: sample_n alone must not yield TRUSTED."""
    only_n = assess_data_reliability(sample_n=100)
    assert only_n.trust_level != TrustLevel.TRUSTED
    only_health = assess_data_reliability(source_health="ok")
    assert only_health.trust_level != TrustLevel.TRUSTED


def test_bare_percentage_rejected() -> None:
    bad = bare_percentage_is_forbidden(
        percentage=95.0, denominator_n=None, limitations=None
    )
    assert bad["ok"] is False
    bad2 = bare_percentage_is_forbidden(
        percentage=95.0, denominator_n=1093, limitations=[]
    )
    assert bad2["ok"] is False
    good = bare_percentage_is_forbidden(
        percentage=0.0,
        denominator_n=1093,
        limitations=["Operational coverage still collecting"],
    )
    assert good["ok"] is True


def test_format_percentage_requires_context() -> None:
    with pytest.raises(ValueError):
        format_percentage_with_context(
            percentage=95.0,
            numerator=1039,
            denominator=1093,
            limitations=[],
        )
    txt = format_percentage_with_context(
        percentage=0.0,
        numerator=0,
        denominator=1093,
        limitations=["nenhuma entidade com estágio operacional completo"],
    )
    assert "0/1093" in txt
    assert "limitations" in txt


def test_attach_to_run_metadata() -> None:
    a = assess_data_reliability(sample_n=0, query_valid=False)
    meta = attach_reliability_to_run_metadata({"run_id": "t1"}, a)
    assert meta["data_reliability"]["trust_level"] == "UNTRUSTED"
    assert "Percentual sem denominador N" in meta["claims"]["forbidden"]


def test_composes_with_claim_language() -> None:
    # Score is not probability; reports need limitations — same DoD family.
    assert score_is_not_probability(label="probabilidade", calibrated=False).ok is False
    assert report_has_limitations(["N=0"]).ok is True


def test_cli_demo_and_bare_pct_fail_closed() -> None:
    demo = subprocess.run(
        [sys.executable, "-m", "scripts.lib.data_reliability", "--demo", "--json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert demo.returncode == 0
    payload = json.loads(demo.stdout)
    assert len(payload["demo"]) >= 3
    levels = {row["trust_level"] for row in payload["demo"]}
    assert "TRUSTED" in levels
    assert "UNTRUSTED" in levels

    bare = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.lib.data_reliability",
            "--pct",
            "95",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert bare.returncode == 2
    body = json.loads(bare.stdout)
    assert body["percentage_check"]["ok"] is False
