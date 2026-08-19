"""Deterministic pack builder for traffic-opportunity-frontier/1.0."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from scripts.public_read.export import canonical_dumps
from scripts.traffic_frontier.catalog import (
    CATALOG_AS_OF,
    CATALOG_ID,
    EXISTING_ASSETS,
    load_catalog,
)
from scripts.traffic_frontier.contract import load_contract
from scripts.traffic_frontier.gates import evaluate_hard_gates, intellectual_fingerprint
from scripts.traffic_frontier.models import CONSUMER_CONTRACT, SCHEMA, validate_opportunity
from scripts.traffic_frontier.score import compute_frontier_score, demand_from_signals

MAX_PRIORITIZED = 12
PACK_FILES = (
    "manifest.json",
    "opportunities.json",
    "rejected.json",
    "hold_for_data.json",
    "README.md",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _penalties_for(candidate: dict[str, Any], gate: dict[str, Any]) -> list[str]:
    pens: list[str] = []
    if "disconnected_cta" in gate["reject_codes"]:
        pens.append("disconnected_cta")
    if not candidate.get("offer_bridge"):
        pens.append("weak_offer_bridge")
    if float((candidate.get("components") or {}).get("citability") or 0) < 0.35:
        pens.append("thin_citability")
    return pens


def _mark_clones(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reject UF/CNPJ swaps that share fingerprint and insight key."""
    seen: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for item in candidates:
        clone = dict(item)
        fp = intellectual_fingerprint(str(clone.get("question") or ""))
        insight = str(clone.get("unique_insight_key") or "")
        key = f"{fp}|{insight}"
        prior = seen.get(key)
        if prior and not clone.get("clone_of"):
            clone["clone_of"] = prior
            clone["is_geo_clone"] = True
        elif key not in seen:
            seen[key] = str(clone.get("opportunity_id") or fp)
        existing_fp = {intellectual_fingerprint(str(asset.get("fingerprint") or "")) for asset in EXISTING_ASSETS}
        proposed = str(clone.get("proposed_url") or "")
        existing = str(clone.get("existing_url") or "")
        if proposed and any(asset["url"] == proposed for asset in EXISTING_ASSETS) and existing:
            clone.setdefault("duplicate_of", existing)
            clone.setdefault("merge_into", existing)
        if fp in existing_fp and existing:
            clone.setdefault("duplicate_of", existing)
        out.append(clone)
    return out


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Attach score, gate, epistemic block and consumer contract."""
    signal = candidate.get("search_signal") or {}
    job = candidate.get("market_job") or {}
    coverage = candidate.get("coverage") or {}
    demand = demand_from_signals(
        gsc_impressions=float(signal.get("impressions") or 0),
        gsc_clicks=float(signal.get("clicks") or 0),
        gsc_position=float(signal.get("position") or 0),
        market_job_present=bool(job.get("present")),
        market_job_plausibility=float(job.get("plausibility") or 0),
    )
    comps = dict(candidate.get("components") or {})
    gate_input = {
        **candidate,
        "coverage_state": coverage.get("state"),
        "coverage_complete": coverage.get("complete_for_scope"),
        "coverage_kind": coverage.get("kind"),
        "record_count": coverage.get("record_count"),
        "nacional_completo": coverage.get("nacional_completo"),
        "freshness_stale": candidate.get("freshness_stale") or coverage.get("stale"),
    }
    gate = evaluate_hard_gates(gate_input)
    scored = compute_frontier_score(
        search_question_demand=demand["demand_0_1"],
        commercial_pain_ticket=float(comps.get("commercial_pain_ticket") or 0),
        data_coverage_freshness=float(comps.get("data_coverage_freshness") or 0),
        proprietary_differentiation=float(comps.get("proprietary_differentiation") or 0),
        citability=float(comps.get("citability") or 0),
        time_to_publish=float(comps.get("time_to_publish") or 0),
        maintenance_cost=float(comps.get("maintenance_cost") or 0.5),
        penalties=_penalties_for(candidate, gate),
    )
    # High score cannot promote HOLD/REJECT.
    state = gate["state"]

    record = {
        "opportunity_id": candidate["opportunity_id"],
        "family": candidate.get("family"),
        "question": candidate["question"],
        "visitor_job": candidate.get("visitor_job"),
        "search_intent": candidate.get("search_intent"),
        "audience": candidate.get("audience"),
        "funnel_stage": candidate.get("funnel_stage"),
        "commercial_pain": candidate.get("commercial_pain"),
        "offer_bridge": candidate.get("offer_bridge") or {},
        "evidence_sources": list(coverage.get("sources") or []),
        "geographic_scope": candidate.get("geographic_scope"),
        "temporal_scope": candidate.get("temporal_scope"),
        "grain": candidate.get("grain"),
        "coverage_state": coverage.get("state"),
        "coverage_kind": coverage.get("kind"),
        "factual_answer_outline": candidate.get("factual_answer_outline"),
        "unique_insight": candidate.get("unique_insight"),
        "unique_insight_key": candidate.get("unique_insight_key"),
        "calculations": candidate.get("calculations") or {},
        "limitations": list(candidate.get("limitations") or []),
        "prohibited_claims": list(candidate.get("prohibited_claims") or []),
        "suggested_visuals": list(candidate.get("suggested_visuals") or []),
        "suggested_internal_links": list(candidate.get("suggested_internal_links") or []),
        "suggested_cta": candidate.get("suggested_cta") or candidate.get("cta") or "",
        "maintenance_owner": candidate.get("maintenance_owner"),
        "refresh_policy": candidate.get("refresh_policy"),
        "proposed_url": candidate.get("proposed_url"),
        "existing_url": candidate.get("existing_url"),
        "score_dimensions": scored["breakdown"],
        "score": scored["score"],
        "raw_score": scored["raw_score"],
        "score_penalties": scored["penalties"],
        "state": state,
        "gate_reason_codes": gate["reason_codes"],
        "merge_into": gate.get("merge_into"),
        "consumer_contract": dict(CONSUMER_CONTRACT),
        "no_publication_authorization": True,
        "no_index_authorization": True,
        "epistemic": {
            "SEARCH_SIGNAL": {
                "gsc_present": demand["gsc_present"],
                "source": demand["source"],
                "impressions": signal.get("impressions") or 0,
                "clicks": signal.get("clicks") or 0,
                "position": signal.get("position") or 0,
                "related_queries": list(signal.get("related_queries") or []),
                "note": demand["note"],
            },
            "MARKET_JOB": {
                "present": bool(job.get("present")),
                "plausibility": job.get("plausibility"),
                "text": job.get("text"),
            },
            "DATA_COVERAGE": {
                "state": coverage.get("state"),
                "kind": coverage.get("kind"),
                "record_count": coverage.get("record_count"),
                "complete_for_scope": coverage.get("complete_for_scope"),
                "stale": coverage.get("stale"),
                "nacional_completo": coverage.get("nacional_completo"),
                "as_of": coverage.get("as_of"),
                "sources": list(coverage.get("sources") or []),
            },
            "COMMERCIAL_FIT": {
                "pain": candidate.get("commercial_pain"),
                "offer_bridge": candidate.get("offer_bridge"),
                "funnel_stage": candidate.get("funnel_stage"),
            },
            "DISTINCTIVE_EDGE": candidate.get("distinctive_edge"),
            "UNKNOWN": list(candidate.get("unknown") or []),
            "PROHIBITED_CLAIM": list(candidate.get("prohibited_claims") or []),
        },
        "fingerprint": gate["fingerprint"],
    }
    errors = validate_opportunity(record)
    if errors:
        raise ValueError(f"{record['opportunity_id']} invalid: {errors}")
    return record


def _rank_key(item: dict[str, Any]) -> tuple[int, int, str]:
    state_rank = {"READY": 0, "HOLD_FOR_DATA": 1, "REJECT": 2}
    return (state_rank.get(item["state"], 9), -int(item["score"]), item["opportunity_id"])


def select_prioritized(scored: list[dict[str, Any]], limit: int = MAX_PRIORITIZED) -> list[dict[str, Any]]:
    eligible = [item for item in scored if item["state"] != "REJECT"]
    ordered = sorted(eligible, key=_rank_key)
    return ordered[:limit]


def pick_top3(prioritized: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First three READY items with distinct fingerprints (already state-ranked)."""
    chosen: list[dict[str, Any]] = []
    fingerprints: set[str] = set()
    for item in prioritized:
        if item["state"] != "READY":
            continue
        fp = item["fingerprint"]
        if fp in fingerprints:
            continue
        chosen.append(item)
        fingerprints.add(fp)
        if len(chosen) == 3:
            break
    return chosen


def campaign_status(top3: list[dict[str, Any]], *, source_access: str | None = None) -> str:
    if source_access == "blocked_required":
        return "BLOCKED_SOURCE_ACCESS"
    ready = [item for item in top3 if item["state"] == "READY"]
    stages = {item["funnel_stage"] for item in ready}
    fps = {item["fingerprint"] for item in ready}
    if len(ready) == 3 and len(stages) >= 2 and len(fps) == 3:
        return "READY_FOR_WEB_CONSUMER"
    return "BLOCKED_DATA_COVERAGE"


def _editorial_brief(item: dict[str, Any]) -> str:
    calc = item.get("calculations") or {}
    calc_lines = "\n".join(f"- `{key}`: {value}" for key, value in sorted(calc.items(), key=lambda kv: kv[0]))
    prohibited = "\n".join(f"- {claim}" for claim in item.get("prohibited_claims") or [])
    limits = "\n".join(f"- {line}" for line in item.get("limitations") or [])
    links = "\n".join(f"- `{path}`" for path in item.get("suggested_internal_links") or [])
    visuals = "\n".join(f"- {item_}" for item_ in item.get("suggested_visuals") or [])
    return (
        f"# Editorial brief — `{item['opportunity_id']}`\n\n"
        f"**Schema:** `{SCHEMA}`\n"
        f"**State:** `{item['state']}`\n"
        f"**Score:** {item['score']}\n"
        f"**Funnel:** `{item['funnel_stage']}` · **Family:** `{item.get('family')}`\n"
        f"**Authorization:** no_publication_authorization=true · no_index_authorization=true\n\n"
        f"## Question\n\n{item['question']}\n\n"
        f"## Visitor job\n\n{item['visitor_job']}\n\n"
        f"## Factual outline\n\n{item['factual_answer_outline']}\n\n"
        f"## Unique insight\n\n{item['unique_insight']}\n\n"
        f"## Calculations\n\n{calc_lines or '- (none)'}\n\n"
        f"## Limitations\n\n{limits}\n\n"
        f"## Prohibited claims\n\n{prohibited}\n\n"
        f"## Suggested visuals\n\n{visuals or '- (none)'}\n\n"
        f"## Internal links\n\n{links}\n\n"
        f"## CTA\n\n{item['suggested_cta']}\n\n"
        f"## Offer bridge\n\n"
        f"`{((item.get('offer_bridge') or {}).get('service_path'))}` — "
        f"{((item.get('offer_bridge') or {}).get('why'))}\n\n"
        f"This brief is an outline. It is not published HTML and does not authorize index.\n"
    )


def _source_manifest(item: dict[str, Any], *, as_of: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "opportunity_id": item["opportunity_id"],
        "as_of": as_of,
        "catalog_id": CATALOG_ID,
        "evidence_sources": list(item.get("evidence_sources") or []),
        "coverage": item["epistemic"]["DATA_COVERAGE"],
        "reuse": [
            "scripts.organic.demand_graph",
            "scripts.public_read.export.canonical_dumps",
            "scripts.commercial.reajuste_14133.domain.data_base_exact",
            "scripts.lib.value_semantics",
            "scripts.ops.contract_market_intelligence",
            "scripts.national_contract_truth",
        ],
        "select_only": True,
        "backfill": False,
        "no_publication_authorization": True,
        "no_index_authorization": True,
    }


def _method_doc(item: dict[str, Any], *, as_of: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "opportunity_id": item["opportunity_id"],
        "as_of": as_of,
        "grain": item.get("grain"),
        "geographic_scope": item.get("geographic_scope"),
        "temporal_scope": item.get("temporal_scope"),
        "calculations": item.get("calculations") or {},
        "reproducible": True,
        "value_semantics": "integral nominal BRL of the contract instrument when numeric",
        "unknown_policy": "UNKNOWN remains UNKNOWN",
        "nacional_completo": False,
        "extra_1093_used_as_denominator": False,
        "no_publication_authorization": True,
        "no_index_authorization": True,
    }


def _evidence_doc(item: dict[str, Any], *, as_of: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "opportunity_id": item["opportunity_id"],
        "as_of": as_of,
        "epistemic": item["epistemic"],
        "limitations": item.get("limitations") or [],
        "prohibited_claims": item.get("prohibited_claims") or [],
        "gate_reason_codes": item.get("gate_reason_codes") or [],
        "no_publication_authorization": True,
        "no_index_authorization": True,
    }


def _readme(
    *,
    status: str,
    top3: list[dict[str, Any]],
    counts: dict[str, int],
    as_of: str,
) -> str:
    lines = [
        f"# Traffic opportunity frontier `{SCHEMA}`",
        "",
        f"**Campaign status:** `{status}`",
        f"**as_of:** `{as_of}` (frozen snapshot, not wall-clock)",
        "**Consumer:** web-cfg only · producer-only · SELECT-only · no backfill · no publication",
        "",
        "## Authorization",
        "",
        "- `no_publication_authorization=true`",
        "- `no_index_authorization=true`",
        "",
        "This pack does not claim traffic, indexação, lead or receita.",
        "",
        "## Top 3",
        "",
    ]
    if top3:
        for item in top3:
            lines.append(
                f"1. `{item['opportunity_id']}` ({item['funnel_stage']}, {item['state']}, score {item['score']}) — {item['question']}"
            )
    else:
        lines.append("_Fail-closed: no READY top 3._")
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- prioritized: {counts.get('prioritized', 0)}",
            f"- READY: {counts.get('READY', 0)}",
            f"- HOLD_FOR_DATA: {counts.get('HOLD_FOR_DATA', 0)}",
            f"- REJECT: {counts.get('REJECT', 0)}",
            "",
            "## How web-cfg consumes",
            "",
            "1. Read `opportunities.json` for the ranked ≤12.",
            "2. For editorial, open `top3/<id>/editorial_brief.md` plus `evidence.json` and `method.json`.",
            "3. Do not publish or index from this pack. Run the public-read claim gate first.",
            "4. Recorte SC is never Brasil. Extra 1093 is never the national denominator.",
            "",
            "## Reproduce",
            "",
            "```bash",
            f"python3 -m scripts.traffic_frontier --out DIR --as-of {as_of}",
            "```",
            "",
            "Two builds on this catalog emit identical `SHA256SUMS.txt`.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_frontier_pack(
    *,
    as_of: str | None = None,
    candidates: list[dict[str, Any]] | None = None,
    source_access: str | None = None,
) -> dict[str, Any]:
    """Pure pack build over a frozen catalog."""
    contract = load_contract()
    snapshot = as_of or CATALOG_AS_OF
    raw = _mark_clones(candidates if candidates is not None else load_catalog())
    scored = [score_candidate(item) for item in raw]
    scored_sorted = sorted(scored, key=_rank_key)
    prioritized = select_prioritized(scored_sorted)
    rejected = [item for item in scored_sorted if item["state"] == "REJECT"]
    holds = [item for item in scored_sorted if item["state"] == "HOLD_FOR_DATA"]
    top3 = pick_top3(prioritized)
    status = campaign_status(top3, source_access=source_access)
    counts = {
        "scored": len(scored),
        "prioritized": len(prioritized),
        "READY": sum(1 for item in scored if item["state"] == "READY"),
        "HOLD_FOR_DATA": len(holds),
        "REJECT": len(rejected),
        "top3": len(top3),
    }
    manifest = {
        "schema": SCHEMA,
        "contract_version": contract["contract_version"],
        "contract_path": "docs/contracts/traffic-opportunity-frontier-v1.json",
        "catalog_id": CATALOG_ID,
        "as_of": snapshot,
        "campaign_status": status,
        "consumer": contract["consumer"],
        "producer": contract["producer"],
        "score": contract["score"],
        "top3_ids": [item["opportunity_id"] for item in top3],
        "counts": counts,
        "no_publication_authorization": True,
        "no_index_authorization": True,
        "source_access": source_access or "fixtures",
        "reuse": contract["reuse"],
        "issues_ref": {
            "producer": ["#415", "#302", "#400"],
            "consumer": ["web-cfg#65", "web-cfg#73"],
        },
    }
    files: dict[str, str] = {
        "manifest.json": canonical_dumps(manifest) + "\n",
        "opportunities.json": canonical_dumps({"schema": SCHEMA, "as_of": snapshot, "items": prioritized}) + "\n",
        "rejected.json": canonical_dumps({"schema": SCHEMA, "as_of": snapshot, "items": rejected}) + "\n",
        "hold_for_data.json": canonical_dumps({"schema": SCHEMA, "as_of": snapshot, "items": holds}) + "\n",
        "README.md": _readme(status=status, top3=top3, counts=counts, as_of=snapshot),
    }
    top3_files: dict[str, dict[str, str]] = {}
    for item in top3:
        oid = item["opportunity_id"]
        top3_files[oid] = {
            f"{oid}.json": canonical_dumps(item) + "\n",
            "evidence.json": canonical_dumps(_evidence_doc(item, as_of=snapshot)) + "\n",
            "method.json": canonical_dumps(_method_doc(item, as_of=snapshot)) + "\n",
            "editorial_brief.md": _editorial_brief(item),
            "source_manifest.json": canonical_dumps(_source_manifest(item, as_of=snapshot)) + "\n",
        }
    checksum_rows: list[tuple[str, str]] = []
    for name in PACK_FILES:
        checksum_rows.append((sha256_text(files[name]), name))
    for oid in sorted(top3_files):
        for filename, body in sorted(top3_files[oid].items()):
            checksum_rows.append((sha256_text(body), f"top3/{oid}/{filename}"))
    checksum_rows.sort(key=lambda row: row[1])
    sha_body = "".join(f"{digest}  {name}\n" for digest, name in checksum_rows)
    files["SHA256SUMS.txt"] = sha_body
    return {
        "schema": SCHEMA,
        "as_of": snapshot,
        "campaign_status": status,
        "manifest": manifest,
        "prioritized": prioritized,
        "rejected": rejected,
        "holds": holds,
        "top3": top3,
        "files": files,
        "top3_files": top3_files,
        "sha256sums": sha_body,
        "scored": scored_sorted,
    }


def write_frontier_pack(pack: dict[str, Any], output_dir: str | Path) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, body in pack["files"].items():
        (root / name).write_text(body, encoding="utf-8")
    top3_root = root / "top3"
    if top3_root.exists():
        for leftover in sorted(top3_root.glob("*")):
            if leftover.is_dir():
                for child in leftover.iterdir():
                    child.unlink()
                leftover.rmdir()
    for oid, files in pack["top3_files"].items():
        dest = root / "top3" / oid
        dest.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (dest / name).write_text(body, encoding="utf-8")
    return root
