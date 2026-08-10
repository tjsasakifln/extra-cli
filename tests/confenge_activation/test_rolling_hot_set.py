"""Rolling hot-set refills; not a sticky Top-50."""

from __future__ import annotations

from scripts.confenge_activation.rolling_hot_set import select_rolling_hot_set


def _lead(root: str, score: float, **kw):
    row = {
        "cnpj_raiz": root,
        "email": f"contato@{root}.com.br",
        "rank_score": score,
        "email_send_ready": True,
        "provenance_chain_valid": True,
        "target_fit_class": "TARGET_CONFIRMED",
    }
    row.update(kw)
    return row


def test_hot_set_size_and_rank() -> None:
    reservoir = [_lead(f"{i:08d}", float(i)) for i in range(100)]
    out = select_rolling_hot_set(reservoir, hot_set_size=10)
    assert out["ACTIVE_HOT_SET"] == 10
    assert out["roots"][0] == "00000099"  # highest score first


def test_evict_dnc_and_refill() -> None:
    reservoir = [_lead(f"{i:08d}", float(i)) for i in range(20)]
    first = select_rolling_hot_set(reservoir, hot_set_size=5)
    top = first["roots"][0]
    second = select_rolling_hot_set(
        reservoir,
        hot_set_size=5,
        dnc={top},
        previous_hot_set=first["roots"],
    )
    assert top not in second["roots"]
    assert second["ACTIVE_HOT_SET"] == 5
    assert top in second["exited"] or top not in second["roots"]


def test_not_capped_at_pilot_sample() -> None:
    reservoir = [_lead(f"{i:08d}", float(i)) for i in range(200)]
    out = select_rolling_hot_set(reservoir, hot_set_size=15)
    assert out["ACTIVE_HOT_SET"] == 15
    assert out["reservoir_eligible"] == 200
