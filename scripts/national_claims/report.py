"""Secret-free JSON/MD observability for a claim payload."""

from __future__ import annotations

from typing import Any


def observability(payload: dict[str, Any], *, cost_ms: float | None = None) -> dict[str, Any]:
    partitions = list(payload.get("partitions") or [])
    return {
        "contract_version": payload.get("contract_version"),
        "claim_id": payload.get("claim_id"),
        "authorization_state": payload.get("authorization_state"),
        "consumer_view": payload.get("consumer_view"),
        "nacional_completo": payload.get("nacional_completo"),
        "universe": {
            "national_universe_id": payload.get("national_universe_id"),
            "catalog_hash": payload.get("catalog_hash"),
            "method_version": payload.get("method_version"),
            "kinds": {
                kind: {
                    "universe_id": bundle.get("universe_id"),
                    "catalog_hash": bundle.get("catalog_hash"),
                    "expected_partitions": bundle.get("expected_partitions"),
                }
                for kind, bundle in (payload.get("universes") or {}).items()
            },
        },
        "expected": payload.get("partitions_expected"),
        "attempted": payload.get("partitions_attempted"),
        "closed": payload.get("partitions_closed"),
        "by_status": _by_status(partitions),
        "partitions": [
            {
                "partition_id": item.get("partition_id"),
                "status": item.get("status"),
                "attempted": item.get("attempted"),
                "reason": item.get("reason"),
                "next_action": item.get("next_action"),
            }
            for item in partitions
        ],
        "identity": payload.get("identity"),
        "freshness": {
            "status": payload.get("freshness_status"),
            "reason": payload.get("freshness_reason"),
            "as_of": payload.get("as_of"),
        },
        "claim_state": payload.get("authorization_state"),
        "blockers": payload.get("blockers"),
        "reason_codes": payload.get("reason_codes"),
        "limitations": payload.get("limitations"),
        "diff_vs_prior": {
            "lkg_status": payload.get("lkg_status"),
            "lkg_ref": payload.get("lkg_ref"),
            "invalidation_triggers": payload.get("invalidation_triggers"),
        },
        "next_action": payload.get("next_action"),
        "cost_ms": cost_ms,
        "content_hash": payload.get("content_hash"),
        "pii": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# National claims observability",
        "",
        f"- claim_id: `{report.get('claim_id')}`",
        f"- authorization_state: `{report.get('authorization_state')}`",
        f"- consumer_view: `{report.get('consumer_view')}`",
        f"- nacional_completo: `{report.get('nacional_completo')}`",
        f"- universe: `{((report.get('universe') or {}).get('national_universe_id'))}`",
        f"- expected/attempted/closed: {report.get('expected')}/{report.get('attempted')}/{report.get('closed')}",
        f"- freshness: `{(report.get('freshness') or {}).get('status')}`",
        f"- next_action: `{report.get('next_action')}`",
        f"- cost_ms: `{report.get('cost_ms')}`",
        "",
        "## Reason codes",
        "",
    ]
    for code in report.get("reason_codes") or []:
        lines.append(f"- `{code}`")
    if not report.get("reason_codes"):
        lines.append("- (none)")
    lines.extend(["", "## Partitions", ""])
    for item in report.get("partitions") or []:
        lines.append(
            f"- `{item.get('partition_id')}` {item.get('status')} "
            f"attempted={item.get('attempted')} reason={item.get('reason')}"
        )
    lines.extend(["", "## Identity", ""])
    identity = report.get("identity") or {}
    lines.append(
        f"- mapped={identity.get('mapped')} source_wide={identity.get('source_wide')} "
        f"unmappable={identity.get('unmappable')}"
    )
    lines.append(f"- proves_entity_coverage={identity.get('proves_entity_coverage')}")
    lines.extend(["", "## Diff vs prior", ""])
    diff = report.get("diff_vs_prior") or {}
    lines.append(f"- lkg_status: `{diff.get('lkg_status')}`")
    lines.append(f"- invalidation_triggers: `{diff.get('invalidation_triggers')}`")
    lines.append("")
    return "\n".join(lines)


def _by_status(partitions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in partitions:
        status = str(item.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return counts
