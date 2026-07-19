"""Work registry load/save and initial migration planning from DoD/PRs/ranker."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts.cto.paths import dod_path, repo_root, work_registry_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_registry(root: Path | None = None) -> dict[str, Any]:
    path = work_registry_path(root)
    if not path.is_file():
        return {
            "schema_version": "1.0",
            "updated_at": None,
            "work_items": [],
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"schema_version": "1.0", "work_items": []}
    data.setdefault("work_items", [])
    return data


def save_registry(data: dict[str, Any], root: Path | None = None) -> Path:
    path = work_registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now()
    data.setdefault("schema_version", "1.0")
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def get_by_work_id(registry: dict[str, Any], work_id: str) -> dict[str, Any] | None:
    for item in registry.get("work_items") or []:
        if item.get("work_id") == work_id:
            return item
    return None


def upsert_item(registry: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    items = list(registry.get("work_items") or [])
    wid = item["work_id"]
    for i, existing in enumerate(items):
        if existing.get("work_id") == wid:
            merged = {**existing, **item}
            items[i] = merged
            registry["work_items"] = items
            return merged
    items.append(item)
    registry["work_items"] = items
    return item


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "item"


def build_initial_registry(
    root: Path | None = None,
    *,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build initial work packages (15-35) without exploding per-checkbox issues."""
    root = root or repo_root()
    registry = load_registry(root)
    existing_ids = {i.get("work_id") for i in registry.get("work_items") or []}

    # Seed packages: infrastructure + critical path from audit knowledge
    seeds: list[dict[str, Any]] = [
        {
            "work_id": "cto-autopilot-infra",
            "title": "CTO Autopilot infrastructure (observe/decide/verify)",
            "objective": "Ship deterministic CTO Autopilot CLI with DeepSeek + Grok executor dry-run",
            "type": "ops",
            "area": "cto",
            "priority": "p0",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["§32 tooling", "CLI-first"],
            "acceptance_criteria": [
                "python -m scripts.cto.cli doctor exits 0",
                "tests/cto pass",
                "draft PR exists for feature branch",
            ],
            "test_commands": ["python -m pytest tests/cto -q"],
            "dependencies": [],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "cto-bootstrap",
        },
        {
            "work_id": "stabilize-open-pr-ci",
            "title": "Stabilize open PR CI failures (advance-30d)",
            "objective": "Address red CI on open draft PR without inventing readiness seals",
            "type": "bug",
            "area": "quality",
            "priority": "p0",
            "risk": "high",
            "state": "ready",
            "dod_refs": ["gates CI", "anti false-green"],
            "acceptance_criteria": [
                "Failing checks identified with run URLs",
                "Minimal fix branch or documented blocker with owner",
            ],
            "test_commands": ["python -m pytest tests/ -q --tb=no -x"],
            "dependencies": [],
            "blockers": ["May require human merge decision"],
            "milestone": "LOCAL_READY",
            "origin": "audit-prs",
        },
        {
            "work_id": "integrate-extra-ops-95",
            "title": "Integrate EXTRA-OPS-95 campaign work safely",
            "objective": "Plan integration of campaign branch evidence without false-green claims",
            "type": "ops",
            "area": "platform",
            "priority": "p1",
            "risk": "high",
            "state": "ready",
            "dod_refs": ["coverage operational", "§20"],
            "acceptance_criteria": [
                "Diff vs main summarized",
                "No DoD checkbox flipped without evidence package",
            ],
            "test_commands": ["python -m scripts.ops.source_contract_tests --json"],
            "dependencies": [],
            "blockers": [],
            "milestone": "LOCAL_READY",
            "origin": "audit-prs",
        },
        {
            "work_id": "full-suite-schema-debt",
            "title": "Reduce full-suite schema debt blocking Test All",
            "objective": "Make full suite runnable or document residual schema debt honestly",
            "type": "debt",
            "area": "quality",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["Suíte global completa verde"],
            "acceptance_criteria": [
                "Failing test modules listed",
                "At least one schema/view fix or explicit BLOCKED with next test",
            ],
            "test_commands": ["python -m pytest tests/ -q --tb=line"],
            "dependencies": [],
            "blockers": [],
            "milestone": "LOCAL_READY",
            "origin": "dod-open",
        },
        {
            "work_id": "freshness-coverage-sla",
            "title": "Freshness coverage measurable per entity within SLA",
            "objective": "Instrument and report per-entity freshness vs SLA without claiming 95%",
            "type": "feature",
            "area": "data",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["Freshness coverage mensurável"],
            "acceptance_criteria": [
                "Command produces per-entity freshness report JSON",
                "SLA breaches listed with entity ids",
            ],
            "test_commands": ["python -m pytest tests/ -k freshness -q"],
            "dependencies": [],
            "blockers": [],
            "milestone": "LOCAL_READY",
            "origin": "dod-open",
        },
        {
            "work_id": "recall-stratified-95",
            "title": "Independent stratified recall measurement path",
            "objective": "Build recall sample pipeline with honest NOT_READY until ≥95%",
            "type": "research",
            "area": "quality",
            "priority": "p2",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["Recall independente e estratificado ≥95%"],
            "acceptance_criteria": [
                "Sample design documented",
                "Measurement script produces JSON with strata",
            ],
            "test_commands": ["python -m pytest tests/ -k recall -q"],
            "dependencies": [],
            "blockers": [],
            "milestone": "LOCAL_READY",
            "origin": "dod-open",
        },
        {
            "work_id": "opportunities-open-pipeline",
            "title": "Open opportunities pipeline reliability",
            "objective": "Ensure opportunity_intel list/show/export works with evidence",
            "type": "feature",
            "area": "opportunities",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["§2.1 localizar editais", "workspace CLI"],
            "acceptance_criteria": [
                "cli list --status open returns structured output",
                "export produces CSV/JSON with counts",
            ],
            "test_commands": [
                "python -m pytest tests/ -k opportunity -q",
            ],
            "dependencies": [],
            "blockers": [],
            "milestone": "LOCAL_READY",
            "origin": "product",
        },
        {
            "work_id": "executive-html-cto-panel",
            "title": "Executive HTML CTO panel (derived projection)",
            "objective": "Refresh HTML with DoD counts, PRs, Issues, last CTO decision — no secrets",
            "type": "ops",
            "area": "cto",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["plano executivo"],
            "acceptance_criteria": [
                "refresh-executive updates HTML markers",
                "No API keys in HTML",
            ],
            "test_commands": ["python -m pytest tests/cto/test_executive_sync.py -q"],
            "dependencies": ["cto-autopilot-infra"],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "cto-bootstrap",
        },
        {
            "work_id": "github-issues-queue",
            "title": "GitHub Issues operational queue sync",
            "objective": "Idempotent issues-plan/sync with stable work_id markers",
            "type": "ops",
            "area": "cto",
            "priority": "p0",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["operational queue"],
            "acceptance_criteria": [
                "issues-sync --dry-run lists creates/updates",
                "issues-sync --apply idempotent",
                "open issues ≤ 40",
            ],
            "test_commands": ["python -m pytest tests/cto/test_github_issues.py -q"],
            "dependencies": ["cto-autopilot-infra"],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "cto-bootstrap",
        },
        {
            "work_id": "dod-evidence-discipline",
            "title": "DoD evidence discipline enforcement",
            "objective": "Prevent auto checkbox flips; audit unauthorized DoD mutations",
            "type": "ops",
            "area": "quality",
            "priority": "p0",
            "risk": "high",
            "state": "ready",
            "dod_refs": ["§1 Como usar", "anti false-green"],
            "acceptance_criteria": [
                "Verifier fails if DoD checked without evidence meta",
                "Policy documented in HANDOFF",
            ],
            "test_commands": ["python -m pytest tests/cto/test_verifier.py -q"],
            "dependencies": [],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "policy",
        },
        {
            "work_id": "source-health-pncp-timeout",
            "title": "PNCP golden-path timeout / source health",
            "objective": "Diagnose PNCP timeout and record source health without faking green",
            "type": "bug",
            "area": "data",
            "priority": "p2",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["golden path PNCP"],
            "acceptance_criteria": [
                "Repro command documented",
                "Health status JSON with timeout evidence",
            ],
            "test_commands": ["python -m pytest tests/ -k pncp -q"],
            "dependencies": [],
            "blockers": ["External network dependency"],
            "milestone": "LOCAL_READY",
            "origin": "dod-open",
        },
        {
            "work_id": "contracts-admin-tracking",
            "title": "Administrative contract tracking signals",
            "objective": "Expose contract admin signals: vigência, aditivos, re-tender signals",
            "type": "feature",
            "area": "data",
            "priority": "p2",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["acompanhamento administrativo de contratos"],
            "acceptance_criteria": [
                "CLI or report lists expiring contracts with dates",
                "Evidence JSON with generation timestamp",
            ],
            "test_commands": ["python -m pytest tests/ -k contract -q"],
            "dependencies": [],
            "blockers": [],
            "milestone": "LOCAL_READY",
            "origin": "product",
        },
        {
            "work_id": "reports-pdf-excel-stable",
            "title": "PDF/Excel report generation stability",
            "objective": "Ensure panorama/export paths exit 0 on sample data",
            "type": "feature",
            "area": "reports",
            "priority": "p2",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["Geração de relatórios em PDF e Excel"],
            "acceptance_criteria": [
                "At least one PDF and one Excel generated in CI-safe mode",
            ],
            "test_commands": ["python -m pytest tests/ -k report -q"],
            "dependencies": [],
            "blockers": [],
            "milestone": "LOCAL_READY",
            "origin": "dod-open",
        },
        {
            "work_id": "ranker-advisory-bridge",
            "title": "Ranker advisory bridge into CTO decide",
            "objective": "Feed top ranker candidates into observation for DeepSeek veto/accept",
            "type": "ops",
            "area": "cto",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["extra-dod-roi"],
            "acceptance_criteria": [
                "observe includes ranking.top",
                "decide can veto ranking[0] with reason",
            ],
            "test_commands": ["python -m pytest tests/cto/test_decision_schema.py -q"],
            "dependencies": ["cto-autopilot-infra"],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "cto-bootstrap",
        },
        {
            "work_id": "human-gates-fail-closed",
            "title": "Human gates fail-closed enforcement",
            "objective": "Block merge/deploy/secret ops in executor and decision policy",
            "type": "ops",
            "area": "cto",
            "priority": "p0",
            "risk": "high",
            "state": "ready",
            "dod_refs": ["publication policy"],
            "acceptance_criteria": [
                "Decision authorizing merge is rejected",
                "Executor dry-run refuses main branch",
            ],
            "test_commands": ["python -m pytest tests/cto -q"],
            "dependencies": ["cto-autopilot-infra"],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "policy",
        },
        {
            "work_id": "coverage-operational-progress",
            "title": "Operational coverage progress (honest metrics)",
            "objective": "Advance operational coverage stages with evidence; no 95% claim",
            "type": "feature",
            "area": "data",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["Cobertura operacional ≥95%"],
            "acceptance_criteria": [
                "Coverage report shows numerator/denominator 1093",
                "Gaps list regenerated",
            ],
            "test_commands": ["python -m pytest tests/ -k coverage -q"],
            "dependencies": [],
            "blockers": ["Large data collection effort"],
            "milestone": "LOCAL_READY",
            "origin": "dod-open",
        },
        {
            "work_id": "publication-policy-docs",
            "title": "Canonical publication policy: worktree → draft PR → human merge",
            "objective": "Document and align tooling so no autonomous merge path remains",
            "type": "ops",
            "area": "platform",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["DEVELOPMENT.md branch policy"],
            "acceptance_criteria": [
                "docs/ops/cto-autopilot documents sequence",
                "policies.yaml publication_policy.autonomous_merge=false",
            ],
            "test_commands": ["python -m scripts.cto.cli doctor"],
            "dependencies": [],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "policy",
        },
        {
            "work_id": "budget-and-fallback",
            "title": "API budget limits and DeepSeek fallback",
            "objective": "Pause on budget; BLOCKED_CTO_UNAVAILABLE without inventing work",
            "type": "ops",
            "area": "cto",
            "priority": "p1",
            "risk": "normal",
            "state": "ready",
            "dod_refs": ["cost control"],
            "acceptance_criteria": [
                "Budget counters persisted",
                "Unavailable path returns BLOCK decision",
            ],
            "test_commands": ["python -m pytest tests/cto/test_deepseek_client.py -q"],
            "dependencies": ["cto-autopilot-infra"],
            "blockers": [],
            "milestone": "CTO_AUTOPILOT",
            "origin": "cto-bootstrap",
        },
    ]

    # Optionally fold ranker top ids as research/debt items if not already present
    if observation:
        for cand in (observation.get("ranking") or {}).get("top") or []:
            cid = cand.get("id")
            if not cid:
                continue
            wid = f"ranker-{_slug(str(cid))}"
            if wid in existing_ids or any(s["work_id"] == wid for s in seeds):
                continue
            if len(seeds) >= 32:
                break
            seeds.append(
                {
                    "work_id": wid,
                    "title": f"Ranker candidate: {cid}",
                    "objective": f"Evaluate ranker candidate {cid} as advisory input (not auto-execute)",
                    "type": "research",
                    "area": "quality",
                    "priority": "p3",
                    "risk": "normal",
                    "state": "ready",
                    "dod_refs": [],
                    "acceptance_criteria": [
                        "Candidate still open and unblocked",
                        "Mapped to DoD refs or rejected with reason",
                    ],
                    "test_commands": [],
                    "dependencies": [],
                    "blockers": ["Advisory only until CTO ACCEPT"],
                    "milestone": "LOCAL_READY",
                    "origin": "ranker",
                    "candidate_id": cid,
                }
            )

    for seed in seeds:
        if seed["work_id"] in existing_ids:
            continue
        seed.setdefault("issue_number", None)
        seed.setdefault("evidence", [])
        seed.setdefault("last_synced_at", None)
        upsert_item(registry, seed)

    # Cap at 35 open items
    items = registry.get("work_items") or []
    open_items = [i for i in items if (i.get("state") or "").lower() not in {"done", "closed"}]
    if len(open_items) > 35:
        # keep first 35 by priority order p0,p1,p2,p3
        prio = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
        open_items_sorted = sorted(
            open_items, key=lambda x: prio.get(str(x.get("priority")), 9)
        )
        keep_ids = {i["work_id"] for i in open_items_sorted[:35]}
        registry["work_items"] = [
            i
            for i in items
            if i.get("work_id") in keep_ids
            or (i.get("state") or "").lower() in {"done", "closed"}
        ]

    return registry
