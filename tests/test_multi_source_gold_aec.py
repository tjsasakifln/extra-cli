"""Conjunto ouro estratificado — precisão AEC e exclusão de FPs da shortlist."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.multi_source_open_pack.classify_aec import classify_aec
from scripts.ops.multi_source_open_pack.events import classify_event

GOLD = Path(__file__).parent / "fixtures" / "multi_source_open_pack" / "gold_aec_stratified.json"


def _load_gold() -> list[dict]:
    data = json.loads(GOLD.read_text(encoding="utf-8"))
    return list(data["cases"])


def test_gold_file_exists_and_stratified():
    cases = _load_gold()
    assert len(cases) >= 12
    strata = {c["stratum"] for c in cases}
    assert any(s.startswith("false_positive") for s in strata)
    assert any(s.startswith("true_positive") for s in strata)
    assert any(s.startswith("terminal") for s in strata)


def test_gold_aec_precision_global():
    cases = _load_gold()
    labeled = [c for c in cases if "expect_aec" in c]
    correct = 0
    for c in labeled:
        active = c.get("expect_active_dispute", True)
        if c.get("categoria_ato"):
            _, active_ev, _ = classify_event(
                categoria_ato=c["categoria_ato"],
                objeto=c["objeto"],
                status_fonte="publicacao_dom",
                fonte="ciga_ckan",
            )
            active = active_ev
        aec = classify_aec(c["objeto"], is_active_dispute=active)
        if aec.is_aec == bool(c["expect_aec"]):
            correct += 1
        else:
            # surface for debugging
            print("MISS", c["id"], "got", aec.is_aec, aec.category, aec.reason)
    precision = correct / len(labeled)
    assert precision >= 0.95, f"AEC precision {precision:.2%} < 95% ({correct}/{len(labeled)})"


def test_gold_shortlist_fp_exclusion_precision():
    """Nenhum FP evidente pode ser shortlist-eligible."""
    cases = _load_gold()
    # shortlist-eligible = AEC + active dispute
    decisions = []
    for c in cases:
        active = True
        if c.get("categoria_ato"):
            _, active, _ = classify_event(
                categoria_ato=c["categoria_ato"],
                objeto=c["objeto"],
                status_fonte="publicacao_dom",
                fonte="ciga_ckan",
            )
        elif c.get("expect_active_dispute") is False:
            active = False
        aec = classify_aec(c["objeto"], is_active_dispute=active)
        eligible = bool(aec.is_aec and active)
        decisions.append((c, eligible))
        if c.get("expect_shortlist_eligible") is False:
            assert eligible is False, f"FP entrou como elegível: {c['id']} {c['objeto'][:60]}"

    # precision of positive shortlist eligibility on gold
    positives = [c for c, el in decisions if c.get("expect_shortlist_eligible") is True]
    true_pos = sum(1 for c, el in decisions if c.get("expect_shortlist_eligible") is True and el)
    false_pos = sum(1 for c, el in decisions if c.get("expect_shortlist_eligible") is False and el)
    if true_pos + false_pos == 0:
        precision = 1.0
    else:
        precision = true_pos / (true_pos + false_pos)
    assert precision >= 0.98, f"shortlist eligibility precision {precision:.2%}"
    assert false_pos == 0
    assert true_pos == len(positives)


def test_gold_terminal_acts_not_active():
    cases = [c for c in _load_gold() if c.get("stratum", "").startswith("terminal")]
    assert cases
    for c in cases:
        _, active, reason = classify_event(
            categoria_ato=c.get("categoria_ato") or "contrato",
            objeto=c["objeto"],
            status_fonte="publicacao_dom",
            fonte="ciga_ckan",
        )
        assert active is False, c["id"]
        assert reason
