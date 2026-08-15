"""Drive the shipped CLI entry point on the real Track A cohort."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.decision_unit_intelligence.cli import main
from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS
from scripts.decision_unit_intelligence.operator_pack import build_card
from scripts.decision_unit_intelligence.providers.historical_campaign import load_campaign_index
from scripts.decision_unit_intelligence.runner import run_account


def test_cli_plan_and_run_track_a(tmp_path: Path):
    plan = tmp_path / "cohort.json"
    assert main(["plan", "--out", str(plan), "--limit", "30"]) == 0
    manifest = json.loads(plan.read_text(encoding="utf-8"))
    assert manifest["n"] == 30
    assert [a["cnpj"] for a in manifest["accounts"]] == TRACK_A_CNPJS

    run_dir = tmp_path / "run1"
    operator = tmp_path / "operator"
    rc = main(
        [
            "run",
            "--out",
            str(run_dir),
            "--operator-out",
            str(operator),
            "--manifest",
            str(plan),
        ]
    )
    assert rc == 0
    written = list((run_dir / "accounts").glob("*.json"))
    assert len(written) == 30
    cohort = json.loads((run_dir / "affiliation_cohort.json").read_text(encoding="utf-8"))
    assert cohort["n"] == 30
    assert cohort["cnpjs"] == TRACK_A_CNPJS
    assert "uplift" in cohort and "delta" in cohort["uplift"]
    assert "contradictions" in cohort
    assert "next_recommendation" in cohort
    assert "QSA_ONLY" in cohort["remaining_blockers"]
    assert cohort["auto_send"] is False
    assert cohort["invented_cargo_or_empresa"] is False
    funnel = json.loads((run_dir / "funnel.json").read_text(encoding="utf-8"))
    assert funnel["accounts"] == 30
    assert "decision_unit_reachability_rate" in funnel
    assert funnel["blocked_excluded_from_rate"] == funnel["classes"].get("BLOCKED", 0)
    cards = json.loads((operator / "cards.json").read_text(encoding="utf-8"))
    assert cards["n"] == 30
    md = (operator / "cards.md").read_text(encoding="utf-8")
    assert "AÇÃO" in md or "AÇÃO:" in md or "**AÇÃO:**" in md
    # No account with a defensible route is a commercial failure just for missing named email.
    index = load_campaign_index()
    for card in cards["cards"]:
        cnpj = card["cnpj"]
        row = index.get(cnpj) or {}
        has_person_and_phone = bool(row.get("qsa") or row.get("qsa2")) and bool(row.get("telefone") or row.get("Telefone principal"))
        if has_person_and_phone:
            assert card["route_class"] != "R0_NO_ACTIONABLE_ROUTE"
            assert card["terminal"] != "EXHAUSTED"
            if card["primary_route"] == "COMPANY_SWITCHBOARD":
                assert "pedir por" in (card["exact_next_action"] or "").lower()
                assert "Não alegar que o telefone pertence à pessoa." in (card.get("do_not_claim") or [])


def test_operator_card_keeps_passive_email_verification_fail_closed() -> None:
    account = run_account(TRACK_A_CNPJS[0])
    email_route = next(route for route in account.routes if "@" in (route.channel_value or ""))
    account.recommendation.primary_route_id = email_route.route_id
    email_route.extra["email_verification"] = {
        "dns": "RESOLVED",
        "mx": "MX_PRESENT",
        "catch_all": "UNKNOWN_NOT_PROBED",
        "smtp": "SKIPPED_POLICY",
        "final_classification": "UNVERIFIED_DIRECT_CANDIDATE",
    }
    account.extra["email_verification"] = [email_route.extra["email_verification"]]

    card = build_card(account)

    assert card["verification_status"] == "CANDIDATE_UNVERIFIED"
    assert card["email_send_ready"] is False
    assert card["email_verification"]["mx"] == "MX_PRESENT"
    assert card["email_verification_reports"][0]["smtp"] == "SKIPPED_POLICY"


def test_cli_replay_is_deterministic(tmp_path: Path):
    plan = tmp_path / "cohort.json"
    main(["plan", "--out", str(plan), "--limit", "5"])
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert main(["run", "--out", str(a), "--manifest", str(plan)]) == 0
    assert main(["run", "--out", str(b), "--manifest", str(plan)]) == 0
    assert main(["replay", "--run-a", str(a), "--run-b", str(b)]) == 0
    # Compare hashes stored on accounts
    ha = {p.stem: json.loads(p.read_text())["replay_hash"] for p in (a / "accounts").glob("*.json")}
    hb = {p.stem: json.loads(p.read_text())["replay_hash"] for p in (b / "accounts").glob("*.json")}
    assert ha == hb
