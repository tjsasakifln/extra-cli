"""Rolling hot-set: when a lead exits, another ESR enters (not a fixed list of 50)."""

from __future__ import annotations


def select_hot_set(
    reservoir: list[dict],
    *,
    active: list[str],
    exited: set[str],
    capacity: int = 50,
) -> list[str]:
    """Ranked rolling window over EMAIL_SEND_READY reservoir.

    Exit reasons (SENT/REPLIED/DNC/BOUNCED/STALE/...) remove roots from active;
    next ranked reservoir members fill until capacity.
    """
    remaining = [
        r
        for r in reservoir
        if r.get("cnpj_raiz") not in exited and r.get("email_send_ready")
    ]
    # Prefer prior active order, then reservoir rank
    active_keep = [r for r in active if r not in exited]
    ranked = [str(r["cnpj_raiz"]) for r in remaining if r.get("cnpj_raiz")]
    out: list[str] = []
    seen: set[str] = set()
    for root in active_keep + ranked:
        if root in seen:
            continue
        seen.add(root)
        out.append(root)
        if len(out) >= capacity:
            break
    return out


def test_hot_set_rolls_when_lead_exits() -> None:
    reservoir = [
        {"cnpj_raiz": f"{i:08d}", "email_send_ready": True, "rank": i} for i in range(1, 81)
    ]
    active = [f"{i:08d}" for i in range(1, 51)]
    exited = {"00000001", "00000002", "00000003"}  # SENT/REPLIED/DNC
    hot = select_hot_set(reservoir, active=active, exited=exited, capacity=50)
    assert len(hot) == 50
    assert "00000001" not in hot
    assert "00000002" not in hot
    assert "00000003" not in hot
    # Next ranked fill
    assert "00000051" in hot
    assert "00000052" in hot
    assert "00000053" in hot


def test_hot_set_never_exceeds_reservoir() -> None:
    reservoir = [{"cnpj_raiz": "00000001", "email_send_ready": True}]
    hot = select_hot_set(reservoir, active=[], exited=set(), capacity=50)
    assert hot == ["00000001"]
