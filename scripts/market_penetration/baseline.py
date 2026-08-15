"""Assemble the versioned operational penetration snapshot and emit artifacts.

Wraps the merged #388 snapshot_penetration with dimensions, hashes, sanity,
and a PII-free executive view. Does not reclassify stages.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.market_penetration.facts import (
    BASELINE_SCHEMA,
    UNKNOWN,
    WARMBLY_EVENT_TO_STAGE,
    JoinResult,
    facts_from_join,
)
from scripts.market_penetration.icp_denominator import (
    DEFAULT_RULES,
    IcpRules,
    PenetrationError,
    classify_stage,
    sha256_payload,
    snapshot_penetration,
)
from scripts.market_penetration.sanity import cumulative_from_exclusive, run_sanity

DIMENSION_ORDER = ("region", "size_portfolio", "trigger", "wedge", "route_class")


def rollup_with_rules(join: JoinResult, stage_by_id: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    views: dict[str, list[dict[str, Any]]] = {}
    for dimension in DIMENSION_ORDER:
        grouped: dict[str, Counter[str]] = {}
        for account in join.accounts:
            value = getattr(account.dimensions, dimension) or UNKNOWN
            grouped.setdefault(value, Counter())
            grouped[value][stage_by_id[account.account_id]] += 1
        rows: list[dict[str, Any]] = []
        for value in sorted(grouped):
            counts = grouped[value]
            icp = sum(counts[stage] for stage in counts if stage != UNKNOWN)
            reachable_stages = (
                "ACTIONABLE_ROUTE",
                "CONTACTED",
                "QUALIFIED_CONVERSATION",
                "MEETING",
                "PROPOSAL",
                "CLIENT",
                "EXPANDED_CLIENT",
            )
            rows.append(
                {
                    "value": value,
                    "accounts": sum(counts.values()),
                    "icp": icp,
                    "reachable": sum(counts[stage] for stage in reachable_stages),
                    "contacted_plus": sum(
                        counts[stage]
                        for stage in (
                            "CONTACTED",
                            "QUALIFIED_CONVERSATION",
                            "MEETING",
                            "PROPOSAL",
                            "CLIENT",
                            "EXPANDED_CLIENT",
                        )
                    ),
                    "conversations": counts["QUALIFIED_CONVERSATION"],
                    "proposals": counts["PROPOSAL"],
                    "clients": counts["CLIENT"] + counts["EXPANDED_CLIENT"],
                    "unknown": counts[UNKNOWN],
                }
            )
        views[dimension] = rows
    return views


def _counts_match_exclusive(snapshot: dict[str, Any]) -> None:
    by_stage = snapshot["by_stage"]
    counts = snapshot["counts"]
    icp = sum(
        by_stage[stage]
        for stage in (
            "ICP_ACCOUNT",
            "DECISION_UNIT_KNOWN",
            "ACTIONABLE_ROUTE",
            "CONTACTED",
            "QUALIFIED_CONVERSATION",
            "MEETING",
            "PROPOSAL",
            "CLIENT",
            "EXPANDED_CLIENT",
        )
    )
    reachable = cumulative_from_exclusive(by_stage)["ACTIONABLE_ROUTE"]
    if counts["X_icp"] != icp:
        raise PenetrationError("counts_X_icp_mismatch")
    if counts["Y_reachable"] != reachable:
        raise PenetrationError("counts_Y_reachable_mismatch")
    if counts["Z_contacted"] != by_stage["CONTACTED"]:
        raise PenetrationError("counts_Z_contacted_not_exclusive")
    if counts["N_conversations"] != by_stage["QUALIFIED_CONVERSATION"]:
        raise PenetrationError("counts_N_conversations_mismatch")
    if counts["P_proposals"] != by_stage["PROPOSAL"]:
        raise PenetrationError("counts_P_proposals_mismatch")
    if counts["C_clients"] != by_stage["CLIENT"] + by_stage["EXPANDED_CLIENT"]:
        raise PenetrationError("counts_C_clients_mismatch")


def build_operational_snapshot(
    join: JoinResult,
    *,
    as_of: str,
    rules: IcpRules = DEFAULT_RULES,
    explanations: tuple[str, ...] = (),
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Versioned snapshot: #388 core + dimensions + sanity + hashes."""
    facts = facts_from_join(join)
    core = snapshot_penetration(facts, as_of=as_of, rules=rules)
    _counts_match_exclusive(core)
    stage_by_id = {account.account_id: classify_stage(account.fact, rules) for account in join.accounts}
    dimensions = rollup_with_rules(join, stage_by_id)
    sanity = run_sanity(join, core, dimensions, explanations=explanations, fail_closed=True)
    policy = {
        "icp_rules": rules.as_dict(),
        "warmbly_authoritative_from": "CONTACTED",
        "warmbly_event_map": dict(sorted(WARMBLY_EVENT_TO_STAGE.items())),
        "warmbly_status": join.warmbly_status,
        "warmbly_freshness": {
            "status": join.warmbly_freshness.status,
            "latest_at": join.warmbly_freshness.latest_at,
            "stale": join.warmbly_freshness.stale,
            "reason": join.warmbly_freshness.reason,
        },
        "invented_tam": False,
        "z_contacted_is_exclusive_bucket": True,
        "extra_cli_authority_through": "ACTIONABLE_ROUTE",
    }
    hashes = {
        "snapshot_hash": core["snapshot_hash"],
        "universe_input": join.input_hashes.get("universe"),
        "dui_input": join.input_hashes.get("dui"),
        "warmbly_input": join.input_hashes.get("warmbly"),
    }
    payload: dict[str, Any] = {
        "schema_version": BASELINE_SCHEMA,
        "core_schema_version": core["schema_version"],
        "universe_version": join.universe_version,
        "as_of": as_of,
        "rules_version": rules.version,
        "policy": policy,
        "dimensions": dimensions,
        "denominator": core["denominator"],
        "counts": core["counts"],
        "by_stage": core["by_stage"],
        "uncaptured_account_ids": core["uncaptured_account_ids"],
        "sanity": sanity,
        "inputs": inputs or {},
        "warmbly_authoritative_from": core["warmbly_authoritative_from"],
        "hashes": hashes,
    }
    assembly_body = {
        "as_of": payload["as_of"],
        "universe_version": payload["universe_version"],
        "policy": payload["policy"],
        "dimensions": payload["dimensions"],
        "counts": payload["counts"],
        "by_stage": payload["by_stage"],
        "sanity": [{"name": item["name"], "passed": item["passed"]} for item in sanity],
        "hashes": hashes,
        "invented_tam": False,
    }
    payload["hashes"] = {**hashes, "assembly_hash": sha256_payload(assembly_body)}
    return payload


def render_executive_report(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    policy = payload["policy"]
    warmbly = policy.get("warmbly_freshness") or {}
    lines = [
        "# CONFENGE commercial penetration snapshot",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- universe_version: `{payload['universe_version']}`",
        f"- schema: `{payload['schema_version']}`",
        f"- invented_tam: `{policy.get('invented_tam')}`",
        f"- extra-cli authority through: `{policy.get('extra_cli_authority_through')}`",
        f"- Warmbly authoritative from: `{payload.get('warmbly_authoritative_from')}`",
        f"- Warmbly status: `{policy.get('warmbly_status')}` ({warmbly.get('reason')})",
        f"- assembly_hash: `{payload['hashes']['assembly_hash']}`",
        "",
        "## Headline (exclusive #388 buckets)",
        "",
        f"- X ICP accounts: **{counts['X_icp']}**",
        f"- Y reachable (ACTIONABLE_ROUTE+): **{counts['Y_reachable']}**",
        f"- Z contacted (exclusive CONTACTED, not cumulative): **{counts['Z_contacted']}**",
        f"- N conversations: **{counts['N_conversations']}**",
        f"- P proposals: **{counts['P_proposals']}**",
        f"- C clients: **{counts['C_clients']}**",
        f"- UNKNOWN (queryable): **{counts['UNKNOWN']}**",
        "",
        "## By exclusive stage",
        "",
    ]
    for stage, value in payload["by_stage"].items():
        lines.append(f"- `{stage}`: {value}")
    lines.extend(["", "## Dimensions (aggregates only, no PII)", ""])
    for dimension in DIMENSION_ORDER:
        lines.append(f"### {dimension}")
        lines.append("")
        lines.append(
            "| value | accounts | icp | reachable | contacted+ | conversations | proposals | clients | unknown |"
        )
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in payload["dimensions"].get(dimension) or []:
            lines.append(
                "| {value} | {accounts} | {icp} | {reachable} | {contacted_plus} | {conversations} | {proposals} | {clients} | {unknown} |".format(
                    **row
                )
            )
        lines.append("")
    lines.extend(["## Sanity", ""])
    for check in payload["sanity"]:
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- `{check['name']}`: **{mark}** — {check['detail']}")
    lines.extend(
        [
            "",
            "## Honesty",
            "",
            "- extra-cli does not re-derive CONTACTED+; missing or empty Warmbly is 0 observed / UNKNOWN.",
            "- This file is a consumer snapshot. Warmbly remains the action/outcome authority.",
            "- Uncaptured canonical IDs live in the JSON (`uncaptured_account_ids`); they are not a CRM.",
            "",
        ]
    )
    return "\n".join(lines)


def write_aggregates_csv(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dimension",
        "value",
        "accounts",
        "icp",
        "reachable",
        "contacted_plus",
        "conversations",
        "proposals",
        "clients",
        "unknown",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for dimension in DIMENSION_ORDER:
            for row in payload["dimensions"].get(dimension) or []:
                writer.writerow({"dimension": dimension, **row})


def emit_snapshot(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    if payload.get("denominator", {}).get("invented_tam") is not False:
        raise PenetrationError("invented_tam_must_be_false")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "penetration-snapshot.json"
    csv_path = out_dir / "penetration-aggregates.csv"
    md_path = out_dir / "penetration-executive.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_aggregates_csv(payload, csv_path)
    md_path.write_text(render_executive_report(payload), encoding="utf-8")
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "report": str(md_path),
    }
