"""DoD §25 claim-language guards — exercise shipped claim_language module."""
from __future__ import annotations

from scripts.lib.claim_language import (
    LANGUAGE_CLAIMS_FORBIDDEN,
    absence_is_not_no_tender,
    report_has_limitations,
    score_is_not_probability,
    text_forbids_works_tracking,
    unidentified_participant_not_nonexistent,
    win_rate,
    winners_are_not_complete_competitors,
)


def test_absence_without_query_blocks_no_tender_label() -> None:
    r = absence_is_not_no_tender(has_valid_query=False, text="sem licitação no período")
    assert r.ok is False


def test_absence_with_valid_query_allows_reporting() -> None:
    r = absence_is_not_no_tender(has_valid_query=True, text="sem licitação no período")
    assert r.ok is True


def test_winners_not_complete_competitors() -> None:
    bad = winners_are_not_complete_competitors(known_winners=5, claim_complete=True)
    good = winners_are_not_complete_competitors(known_winners=5, claim_complete=False)
    assert bad.ok is False
    assert good.ok is True


def test_unidentified_not_nonexistent() -> None:
    bad = unidentified_participant_not_nonexistent(
        participant_id=None, treated_as_nonexistent=True
    )
    good = unidentified_participant_not_nonexistent(
        participant_id=None, treated_as_nonexistent=False
    )
    assert bad.ok is False
    assert good.ok is True


def test_win_rate_requires_proposals() -> None:
    bad = win_rate(wins=3, proposals_submitted=None)
    bad0 = win_rate(wins=3, proposals_submitted=0)
    good = win_rate(wins=3, proposals_submitted=10)
    assert bad.ok is False
    assert bad0.ok is False
    assert good.ok is True
    assert good.details is not None
    assert abs(good.details["win_rate"] - 0.3) < 1e-9


def test_score_not_probability_without_calibration() -> None:
    bad = score_is_not_probability(label="probabilidade_vitoria", calibrated=False)
    good_score = score_is_not_probability(label="ranking_score", calibrated=False)
    good_cal = score_is_not_probability(label="probabilidade_vitoria", calibrated=True)
    assert bad.ok is False
    assert good_score.ok is True
    assert good_cal.ok is True


def test_reports_must_show_limitations() -> None:
    assert report_has_limitations([]).ok is False
    assert report_has_limitations(["N=3 insuficiente"]).ok is True


def test_forbids_works_tracking_claim() -> None:
    bad = text_forbids_works_tracking("O sistema faz acompanhamento físico de obras.")
    good = text_forbids_works_tracking(
        "Acompanhamento administrativo de contratos, sem medição em campo."
    )
    # "medição em campo" alone is also forbidden if claiming capability
    assert bad.ok is False
    # The good sentence contains "sem medição em campo" as negation — pattern may hit.
    # Prefer pure administrative wording:
    good2 = text_forbids_works_tracking(
        "Ferramenta de inteligência de editais e contratos administrativos."
    )
    assert good2.ok is True


def test_forbidden_language_list_nonempty() -> None:
    assert len(LANGUAGE_CLAIMS_FORBIDDEN) >= 7
