#!/usr/bin/env python3
"""*rank-next read-only entrypoint for extra-dod-roi.

Composes snapshot → DoD summary → graph → candidates → ROI rank.
Does NOT modify product files or DOD.md.
Optional --write-state only under squads/extra-dod-roi/state/.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# allow running as script from repo root or scripts dir
SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from snapshot_state import collect_snapshot, repo_root_from  # noqa: E402
from parse_dod import parse_dod  # noqa: E402
from graph_build import build_default_graph  # noqa: E402
from score_roi import load_weights, rank_candidates  # noqa: E402


def _load_story_state(root: Path, story_id: str) -> dict[str, Any] | None:
    p = root / ".aiox" / "state" / "stories" / f"{story_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _story_done(root: Path, story_id: str) -> bool:
    """True when AIOX story is Done with po_closed and non-FAIL QA."""
    st = _load_story_state(root, story_id)
    if not st:
        return False
    if st.get("status") != "Done" or not st.get("po_closed"):
        return False
    verdict = (st.get("qa_verdict") or "").upper()
    return verdict in {"PASS", "CONCERNS", "WAIVED"}


def _mark_completed(c: dict[str, Any], reason: str) -> None:
    c["status"] = "COMPLETED"
    c["why_unlocked"] = f"COMPLETED — {reason}"
    c["completion_reason"] = reason


def apply_completion_filters(
    root: Path,
    candidates: list[dict[str, Any]],
    divergences: list[str],
) -> list[dict[str, Any]]:
    """Demote candidates whose underlying AIOX work is already Done+po_closed.

    Prevents thrashing force-next on finished ranking[0] items.
    """
    rules: list[tuple[str, list[str], str]] = [
        (
            "cand-qa-po-e3-stories",
            ["B2G-E3.S1", "B2G-E3.S2"],
            "B2G-E3.S1/S2 Done with independent QA/PO (do not re-bind)",
        ),
        (
            "cand-full-suite-schema-debt",
            ["ROI-cand-full-suite-schema-debt"],
            "ROI-cand-full-suite-schema-debt Done with QA PASS + PO close",
        ),
        (
            "cand-coverage-slice-pending-collection",
            ["ROI-cand-coverage-slice-pending-collection"],
            "ROI-cand-coverage-slice-pending-collection Done with QA PASS + PO close (M2 N>0 provenance)",
        ),
        (
            "cand-coverage-scale-m2-more-entities",
            ["ROI-cand-coverage-scale-m2-more-entities"],
            "ROI-cand-coverage-scale-m2-more-entities Done with QA PASS + PO close",
        ),
        (
            "cand-dod-unit-test-evidence-pack",
            ["ROI-cand-dod-unit-test-evidence-pack"],
            "ROI-cand-dod-unit-test-evidence-pack Done with QA PASS + PO close",
        ),

        (
            "cand-workspace-daily-evidence-pack",
            ["ROI-cand-workspace-daily-evidence-pack"],
            "ROI-cand-workspace-daily-evidence-pack Done with QA/PO",
        ),
        (
            "cand-post-merge-truth-gate-honesty",
            ["ROI-cand-post-merge-truth-gate-honesty"],
            "ROI-cand-post-merge-truth-gate-honesty Done with QA/PO",
        ),
        (
            "cand-golden-path-pncp-health",
            ["ROI-cand-golden-path-pncp-health"],
            "ROI-cand-golden-path-pncp-health Done with QA PASS + PO close",
        ),
    ]
    by_id = {c["id"]: c for c in candidates}
    for cand_id, story_ids, reason in rules:
        c = by_id.get(cand_id)
        if not c:
            continue
        if all(_story_done(root, sid) for sid in story_ids):
            _mark_completed(c, reason)
            divergences.append(f"Candidate {cand_id} marked COMPLETED: {reason}")
    # Also: open draft PR for same head branch is not enough alone; story Done is authority
    return [c for c in candidates if c.get("status") == "UNLOCKED"]


def build_candidates(
    snapshot: dict[str, Any],
    matrix: dict[str, Any],
    graph: dict[str, Any],
    root: Path | None = None,
) -> tuple[list[dict], list[dict], list[str]]:
    """Heuristic but grounded candidates from real brownfield state (2026-07-17)."""
    divergences: list[str] = []
    blockers: list[dict] = []
    candidates: list[dict] = []
    root = root or repo_root_from(Path.cwd())

    git = snapshot.get("git") or {}
    open_prs = snapshot.get("open_prs") or {}
    if isinstance(open_prs, dict):
        open_prs = []
    open_prs = open_prs or []
    pr12 = next((p for p in open_prs if p.get("number") == 12), None)
    on_truth_branch = (git.get("branch") or "").startswith("fix/pre-vps-final-truth-gate")
    main_head = git.get("main_head")
    head = git.get("head")
    ops = snapshot.get("ops_truth_docs") or {}
    has_truth_docs = all(
        ops.get(k) for k in ("PRE-VPS-FINAL-TRUTH.md", "PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md")
    )
    # PR #12 truth-gate: open, or already merged into main (offline gate landed, live still blocked)
    pr12_merged_on_main = (not pr12) and has_truth_docs and (git.get("on_main") or head == main_head)

    if pr12:
        divergences.append(
            f"PR #12 OPEN ({pr12.get('headRefName')}) is NOT merged into main — "
            "resilience truth-gate work must not be treated as mainline complete."
        )
    elif pr12_merged_on_main:
        divergences.append(
            "PR #12 truth-gate appears MERGED into main (no open PR #12; truth docs present). "
            "Offline gate may be on main — still NOT PRE_VPS_FINAL_READY without live canary + PG evidence."
        )
    if head and main_head and head != main_head:
        divergences.append(
            f"Current HEAD {head[:8]} differs from origin/main {main_head[:8]} "
            f"(ahead={git.get('ahead')}, behind={git.get('behind')})."
        )
    if matrix.get("veto"):
        divergences.append(
            f"DoD veto active: {matrix['veto'].get('reason')}"
        )
    for sc in matrix.get("superseded_claims") or []:
        divergences.append(f"Superseded claim: {sc.get('claim')} → {sc.get('current')} ({sc.get('source')})")

    # --- BLOCKED items ---
    blockers.append(
        {
            "id": "blk-live-canary-pg",
            "title": "Live canary + real PostgreSQL evidence for PRE_VPS_FINAL_READY",
            "status": "BLOCKED",
            "owner": "Tiago / ops host",
            "cause": "Requires DATABASE_URL/live network canary; offline fixtures insufficient",
            "evidence": "PR #12 (merged or open); docs/operations/PRE-VPS-FINAL-TRUTH.md; make pre-vps-live-canary",
            "unlock_condition": "Live canary run with real PG evidence, exit 0, recorded artifacts",
            "next_test": "make pre-vps-live-canary  # with live env",
            "alternate_local_roi": "cand-qa-po-e3-stories",
        }
    )
    blockers.append(
        {
            "id": "blk-vps-provision",
            "title": "Provision VPS + enable timers (E3.S3)",
            "status": "BLOCKED",
            "owner": "Tiago",
            "cause": "PRE_VPS_FINAL_READY not achieved; human infra decision",
            "evidence": "DOD §44 claims forbidden; PRE-VPS-READINESS checklist",
            "unlock_condition": "PRE_VPS_FINAL_READY with proof + explicit go for provision",
            "next_test": "docs/operations/PRE-VPS-READINESS.md checklist",
            "alternate_local_roi": "cand-coverage-operational-stages",
        }
    )
    blockers.append(
        {
            "id": "blk-coverage-95",
            "title": "Operational coverage >= 95% (1039/1093)",
            "status": "BLOCKED",
            "owner": "delivery + data ops",
            "cause": "Strict operational coverage still 0/1093; long path of per-entity collection",
            "evidence": "DOD update cycle B2G 2026-07-17; output/coverage/",
            "unlock_condition": "Operational stages complete for >=1039 entities with provenance",
            "next_test": "python -m scripts coverage / workspace coverage commands",
            "alternate_local_roi": "cand-coverage-slice-pending-collection",
        }
    )

    # --- UNLOCKED candidates (conservative, material DoD progress) ---
    # 1. Truth-gate PR path: finish if open; if merged, residual honesty verification on main
    conflict_pr12 = []
    if pr12 or on_truth_branch:
        conflict_pr12 = [
            "PR #12 / branch fix/pre-vps-final-truth-gate-20260717 already carries this work — do not duplicate; finish or review it"
        ]

    if pr12 or on_truth_branch:
        candidates.append(
            {
                "id": "cand-finish-pr12-truth-gate",
                "title": "Concluir trilha PR #12 (truth gate): CI resilience-gate verde + merge readiness honesta (sem restaurar READY)",
                "status": "UNLOCKED",
                "dod_refs": ["§44 LOCAL_RESILIENCE_READY SUPERSEDED", "PRE_VPS offline gates", "no false green"],
                "why_unlocked": "Work already exists on open PR/branch; remaining is verification/CI/honest merge path, not greenfield",
                "value": {
                    "gate_value": 5,
                    "unlock_power": 4,
                    "operational_impact": 3,
                    "risk_reduction": 5,
                    "evidence_gain": 5,
                },
                "cost": {
                    "effort": 2,
                    "uncertainty": 2,
                    "external_dependency": 2,
                    "change_surface": 2,
                },
                "justification": "Elimina divergência main vs truth-gate e impede falso verde; desbloqueia conversa de live canary com base honesta.",
                "risks": [
                    "Merge sem live canary poderia ser mal interpretado como PRE_VPS_FINAL_READY",
                    "CI flake",
                ],
                "dependencies": ["offline resilience tests green"],
                "conflicts": conflict_pr12,
                "acceptance_criteria": [
                    "CI resilience-gate green on PR #12",
                    "DoD/docs remain NOT_READY for PRE_VPS_FINAL_READY",
                    "No LOCAL_RESILIENCE_READY seal restored without new proof",
                ],
                "test_commands": [
                    "make pre-vps-final-gate-offline",
                    "pytest tests/test_local_resilience.py -q",
                ],
                "planned_files": ["docs/operations/*", "CI only if needed — prefer finish existing PR"],
            }
        )
    elif pr12_merged_on_main:
        candidates.append(
            {
                "id": "cand-post-merge-truth-gate-honesty",
                "title": "Pós-merge PR #12: revalidar offline gate na main e impedir restauração de selos READY sem live proof",
                "status": "UNLOCKED",
                "dod_refs": ["§44 NOT_READY", "PRE_VPS_FINAL_READY still blocked", "no false green"],
                "why_unlocked": "PR #12 merged; residual work is verify main still honest and offline gate green",
                "value": {
                    "gate_value": 4,
                    "unlock_power": 3,
                    "operational_impact": 2,
                    "risk_reduction": 5,
                    "evidence_gain": 4,
                },
                "cost": {
                    "effort": 1,
                    "uncertainty": 1,
                    "external_dependency": 1,
                    "change_surface": 1,
                },
                "justification": "Barato e crítico após merge: garantir que main não promoveu PRE_VPS_FINAL_READY; base limpa para live canary humano.",
                "risks": ["Narrativa de merge confundida com readiness live"],
                "dependencies": ["main contains truth-gate commits"],
                "conflicts": [],
                "acceptance_criteria": [
                    "make pre-vps-final-gate-offline green on main",
                    "DOD/docs still forbid LOCAL_RESILIENCE_READY and PRE_VPS_FINAL_READY without live proof",
                    "No new false-green health path introduced",
                ],
                "test_commands": [
                    "make pre-vps-final-gate-offline",
                    "python3 -m scripts.ops.health --env development; test exit != 0 without live evidence",
                ],
                "planned_files": ["docs/operations/* only if residual drift", "no product rewrite"],
            }
        )

    # 2. Independent QA/PO close for E3 stories
    candidates.append(
        {
            "id": "cand-qa-po-e3-stories",
            "title": "QA/PO independentes fecham E3.S1/E3.S2 (InReview → Done) sem inflar selos",
            "status": "UNLOCKED",
            "dod_refs": ["§44.4 claim 5 stories InReview", "story lifecycle"],
            "why_unlocked": "Não depende de VPS; processo local AIOX; stories existem",
            "value": {
                "gate_value": 4,
                "unlock_power": 3,
                "operational_impact": 2,
                "risk_reduction": 4,
                "evidence_gain": 4,
            },
            "cost": {
                "effort": 2,
                "uncertainty": 1,
                "external_dependency": 1,
                "change_surface": 1,
            },
            "justification": "Barato, reduz risco de story Done sem prova, e é pré-condição citada para PRE_VPS_FINAL_READY.",
            "risks": ["Self-approval se implementador atuar como único QA"],
            "dependencies": ["story files for E3.S1/S2 or epic-pre-vps-truth"],
            "conflicts": [],
            "acceptance_criteria": [
                "QA gate file with PASS/CONCERNS/FAIL",
                "PO close only after acceptable verdict",
                "No READY seal changes beyond authorized claims",
            ],
            "test_commands": ["review story gates", "pytest resilience subset if code claimed"],
            "planned_files": ["docs/stories/*", ".aiox/state/stories/*"],
        }
    )

    # 3. Operational coverage slice — pending_collection entities
    candidates.append(
        {
            "id": "cand-coverage-slice-pending-collection",
            "title": "Fatia vertical de cobertura operacional: desbloquear pending_collection com proveniência (N entidades, não 95%)",
            "status": "UNLOCKED",
            "dod_refs": ["cobertura operacional 0/1093", "pending_collection=714", "95% meta"],
            "why_unlocked": "Registry 1093 existe; pipeline de estágios existe; pode avançar N entidades sem VPS",
            "value": {
                "gate_value": 3,
                "unlock_power": 4,
                "operational_impact": 5,
                "risk_reduction": 3,
                "evidence_gain": 4,
            },
            "cost": {
                "effort": 4,
                "uncertainty": 3,
                "external_dependency": 3,
                "change_surface": 3,
            },
            "justification": "Único caminho material para sair de 0% cobertura operacional; ROI alto em impacto operacional mesmo com esforço maior.",
            "risks": [
                "Confundir sinal comercial (116) com cobertura operacional",
                "Dependência de fontes externas rate-limit",
            ],
            "dependencies": ["source registry sync", "coverage contract multi-metric"],
            "conflicts": [],
            "acceptance_criteria": [
                "N>0 entities advanced in operational stages with run_id/raw/sha",
                "Report does not claim 95%",
                "commercial_signal remains separate metric",
            ],
            "test_commands": [
                "pytest tests/ -k coverage -q",
                "python -m scripts workspace coverage (or project equivalent)",
            ],
            "planned_files": ["scripts/coverage/*", "scripts/source_registry/*", "output/coverage/"],
        }
    )

    # 4. Full suite / schema debt that blocks confidence
    candidates.append(
        {
            "id": "cand-full-suite-schema-debt",
            "title": "Reduzir dívida que faz Test All (full suite) skipped / schema views falharem",
            "status": "UNLOCKED",
            "dod_refs": ["Suíte global completa verde (unchecked)", "CI Test All skipped"],
            "why_unlocked": "Local/CI work; no VPS; improves evidence quality",
            "value": {
                "gate_value": 3,
                "unlock_power": 3,
                "operational_impact": 2,
                "risk_reduction": 4,
                "evidence_gain": 4,
            },
            "cost": {
                "effort": 3,
                "uncertainty": 3,
                "external_dependency": 1,
                "change_surface": 3,
            },
            "justification": "Aumenta confiança do gate e reduz falso verde por testes não rodados.",
            "risks": ["Wide surface", "env-specific failures"],
            "dependencies": ["local db-up optional for database tests"],
            "conflicts": [],
            "acceptance_criteria": [
                "Critical full-suite path documented green or remaining skips justified",
                "No hiding skipped critical tests",
            ],
            "test_commands": ["make test", "make test-all (documented)"],
            "planned_files": ["tests/*", "supabase/* views", "CI workflow if needed"],
        }
    )

    # 5c. Prove existing unit tests against DoD §13 checkboxes (evidence pack)
    candidates.append(
        {
            "id": "cand-dod-unit-test-evidence-pack",
            "title": "Pacote de evidência: reexecutar testes unitários que provam itens DoD §13/§3 (sem falso verde)",
            "status": "UNLOCKED",
            "dod_refs": ["§13.1 unit tests", "§3 universe baseline 1093"],
            "why_unlocked": "Tests already exist; needs independent re-run + DoD checkbox evidence mapping",
            "value": {
                "gate_value": 5,
                "unlock_power": 4,
                "operational_impact": 2,
                "risk_reduction": 4,
                "evidence_gain": 5,
            },
            "cost": {
                "effort": 2,
                "uncertainty": 1,
                "external_dependency": 1,
                "change_surface": 1,
            },
            "justification": "Cheap high evidence_gain: close many DoD unit-test checkboxes with real pytest of shipped code.",
            "risks": ["Over-marking without mapping", "DB-only tests skipped"],
            "dependencies": [],
            "conflicts": [],
            "acceptance_criteria": [
                "Evidence pack lists each DoD checkbox with pytest nodeid + exit 0",
                "Only HIGH-confidence mapped items; no mark without re-run",
                "DoD.md updated only for proven items after independent QA",
            ],
            "test_commands": [
                "pytest tests/test_universe.py tests/test_common.py tests/test_geocode.py -q",
                "pytest tests/test_coverage_states.py tests/test_freshness_gate.py -q",
            ],
            "planned_files": [
                "docs/ops/session-*/dod-unit-evidence/",
                "DOD.md",
                "docs/stories/*",
            ],
        }
    )

    # 5b. Scale operational coverage beyond first provenance slice
    candidates.append(
        {
            "id": "cand-coverage-scale-m2-more-entities",
            "title": "Escalar M2 operacional: promover mais entidades com proveniência (sem claim 95%)",
            "status": "UNLOCKED",
            "dod_refs": ["operational_source_coverage < 95%", "pending_collection residual"],
            "why_unlocked": "First N-slice landed; still far from 95%; offline+PG paths exist",
            "value": {
                "gate_value": 4,
                "unlock_power": 5,
                "operational_impact": 5,
                "risk_reduction": 3,
                "evidence_gain": 4,
            },
            "cost": {
                "effort": 4,
                "uncertainty": 3,
                "external_dependency": 3,
                "change_surface": 3,
            },
            "justification": "Material path from 5/1093 toward gate 95% without false green.",
            "risks": ["Rate limits", "SLA decay on old artifacts"],
            "dependencies": ["cand-coverage-slice provenance machinery"],
            "conflicts": [],
            "acceptance_criteria": [
                "M2 numerator increases by N>0 vs previous evidence pack",
                "No 95% claim unless measured >=95%",
                "commercial_signal remains separate",
            ],
            "test_commands": [
                "pytest tests/unit/source_registry/test_promote_from_evidence.py -q",
                "python -m scripts.coverage.coverage_contract_cli report --offline",
            ],
            "planned_files": [
                "scripts/source_registry/acquisition/*",
                "data/entity_source_registry.jsonl",
                "docs/ops/session-*/",
            ],
        }
    )

    # 5. Golden path PNCP reliability
    candidates.append(
        {
            "id": "cand-golden-path-pncp-health",
            "title": "Estabilizar golden path PNCP (timeout) e source health observável",
            "status": "UNLOCKED",
            "dod_refs": ["golden path PNCP falhou por timeout", "source health"],
            "why_unlocked": "Code/ops local; improves daily utility and evidence",
            "value": {
                "gate_value": 2,
                "unlock_power": 3,
                "operational_impact": 4,
                "risk_reduction": 3,
                "evidence_gain": 3,
            },
            "cost": {
                "effort": 3,
                "uncertainty": 3,
                "external_dependency": 4,
                "change_surface": 2,
            },
            "justification": "Utilidade diária e saúde de fonte; external_dependency alta limita ROI vs truth-gate/QA.",
            "risks": ["PNCP rate limits", "flaky network"],
            "dependencies": ["resilience adapters"],
            "conflicts": [],
            "acceptance_criteria": [
                "Reproducible golden path result recorded (pass or honest degraded health)",
                "No success claim on timeout",
            ],
            "test_commands": ["make golden-path-quick", "python scripts/golden_path.py --help"],
            "planned_files": ["scripts/golden_path.py", "scripts/crawl/*", "scripts/ops/*"],
        }
    )

    # 6. Workspace daily path smoke evidence pack
    candidates.append(
        {
            "id": "cand-workspace-daily-evidence-pack",
            "title": "Pacote de evidência reproduzível do workspace cotidiano (today/opportunities/dossier/coverage)",
            "status": "UNLOCKED",
            "dod_refs": ["workspace cotidiano executa comandos", "evidências utilizáveis"],
            "why_unlocked": "CLI exists per DoD narrative; needs fresh evidence pack",
            "value": {
                "gate_value": 2,
                "unlock_power": 2,
                "operational_impact": 4,
                "risk_reduction": 2,
                "evidence_gain": 5,
            },
            "cost": {
                "effort": 2,
                "uncertainty": 2,
                "external_dependency": 2,
                "change_surface": 1,
            },
            "justification": "Baixo esforço, alto evidence_gain; não fecha 95% mas fortalece claims permitidos.",
            "risks": ["May need local DB"],
            "dependencies": ["workspace CLI module"],
            "conflicts": [],
            "acceptance_criteria": [
                "Commands run with exit codes recorded",
                "Artifacts under output/ or docs/ops session folder",
            ],
            "test_commands": ["python -m scripts.workspace --help || true"],
            "planned_files": ["docs/ops/session-*", "output/*"],
        }
    )

    # If PR12 work is "already done" on branch, finishing it is still the top
    # Mark conflict for greenfield reimplementation of resilience
    candidates.append(
        {
            "id": "cand-do-not-rebuild-resilience-core",
            "title": "(Anti-candidato) Reescrever núcleo de resiliência do zero",
            "status": "CONFLICT",
            "dod_refs": ["§44 delivery already exists (PR #12 open or merged)"],
            "why_unlocked": "N/A — conflict with active or already-landed work",
            "value": {
                "gate_value": 1,
                "unlock_power": 1,
                "operational_impact": 1,
                "risk_reduction": 0,
                "evidence_gain": 1,
            },
            "cost": {
                "effort": 5,
                "uncertainty": 4,
                "external_dependency": 2,
                "change_surface": 5,
            },
            "justification": "Duplicaria PR #12; ROI péssimo e viola filtro de não-duplicação.",
            "risks": ["Massive regression"],
            "dependencies": [],
            "conflicts": ["PR #12 open or merged truth-gate"],
            "acceptance_criteria": [],
            "test_commands": [],
            "planned_files": [],
        }
    )

    # Demote finished ROI slices, then only UNLOCKED enter ranking set
    unlocked = apply_completion_filters(root, candidates, divergences)
    return unlocked, blockers, divergences


def format_report(result: dict[str, Any], top_n: int) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append("extra-dod-roi :: *rank-next (READ-ONLY)")
    lines.append("=" * 72)
    lines.append(f"generated_at: {result['generated_at']}")
    lines.append(f"branch: {result['git'].get('branch')}  HEAD: {(result['git'].get('head') or '')[:12]}")
    lines.append(f"main:   {(result['git'].get('main_head') or '')[:12]}")
    lines.append(f"DOD.md sha256: {(result.get('dod_hash') or '')[:16]}…")
    lines.append(f"snapshot confidence: {result.get('snapshot_confidence')}")
    lines.append(f"DoD items: {result['dod_summary'].get('item_count')} total, "
                 f"{result['dod_summary'].get('done_count')} checked-done, "
                 f"{result['dod_summary'].get('open_count')} open/unchecked")
    lines.append("")
    lines.append("## Divergences (main / PRs / docs)")
    for d in result.get("divergences") or []:
        lines.append(f"- {d}")
    if not result.get("divergences"):
        lines.append("- (none detected)")
    lines.append("")
    lines.append("## Active seals (conservative)")
    lines.append("- LOCAL_RESILIENCE_READY: NOT_READY (superseded)")
    lines.append("- PRE_VPS_FINAL_READY: NOT_READY")
    lines.append("- VPS_OPERATIONAL / PROJECT_DONE: NOT_READY")
    lines.append("")
    lines.append(f"## Top {top_n} UNLOCKED by ROI")
    for i, c in enumerate(result.get("ranking") or [], 1):
        lines.append("")
        lines.append(f"### {i}. {c['id']}  ROI={c['roi']}")
        lines.append(f"    {c['title']}")
        lines.append(f"    value_sum={c.get('value_sum')} cost_sum={c.get('cost_sum')}")
        lines.append(f"    impact(gate/unlock/ops/risk/evid)={c['value']}")
        lines.append(f"    cost(effort/uncert/ext/surface)={c['cost']}")
        lines.append(f"    deps: {', '.join(c.get('dependencies') or []) or '—'}")
        lines.append(f"    risks: {'; '.join(c.get('risks') or []) or '—'}")
        lines.append(f"    why: {c.get('justification')}")
        if c.get("conflicts"):
            lines.append(f"    conflicts: {c['conflicts']}")
    lines.append("")
    lines.append("## Selected for *execute-next")
    sel = result.get("selected")
    if sel:
        lines.append(f"- id: {sel['id']}")
        lines.append(f"- title: {sel['title']}")
        lines.append(f"- ROI: {sel['roi']}")
        lines.append(f"- AC: {sel.get('acceptance_criteria')}")
        lines.append(f"- tests: {sel.get('test_commands')}")
    else:
        lines.append("- NONE (NO_UNLOCKED_WORK)")
    lines.append("")
    lines.append("## Attractive alternatives discarded / lower rank reasons")
    for item in result.get("discarded_attractive") or []:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Blockers (not ranked as UNLOCKED)")
    for b in result.get("blockers") or []:
        lines.append(f"- {b['id']}: {b['title']}")
        lines.append(f"    owner={b.get('owner')} unlock={b.get('unlock_condition')}")
    lines.append("")
    lines.append("## Guardrails")
    lines.append("- No DOD.md mutations performed")
    lines.append("- No product code mutations performed")
    lines.append("- No branch created")
    lines.append("- READY seals NOT restored without proof")
    lines.append("=" * 72)
    return "\n".join(lines)


def run_rank_next(
    root: Path,
    top_n: int = 5,
    write_state: bool = False,
    fetch: bool = False,
) -> dict[str, Any]:
    snapshot = collect_snapshot(root, fetch_remote=fetch)
    dod_path = root / "DOD.md"
    matrix = parse_dod(dod_path) if dod_path.is_file() else {
        "item_count": 0, "done_count": 0, "open_count": 0,
        "superseded_claims": [], "veto": {}, "dod_sha256": None,
    }
    graph = build_default_graph({"notes": ["default domain graph for Extra B2G"]})
    unlocked, blockers, divergences = build_candidates(snapshot, matrix, graph, root=root)
    weights = load_weights(SQUAD_DIR / "data" / "roi-weights.yaml")
    ranked = rank_candidates(unlocked, weights)
    top = ranked[:top_n]
    selected = top[0] if top else None

    discarded = []
    if len(ranked) > 1:
        for c in ranked[1:6]:
            discarded.append(
                f"{c['id']} ROI={c['roi']} preterido vs #1: menor combinação gate+risco+evidência ou maior custo/dependência externa"
            )
    discarded.append(
        "cand-do-not-rebuild-resilience-core: CONFLICT com PR #12 — duplicação proibida"
    )
    discarded.append(
        "blk-live-canary-pg: BLOCKED por dependência externa (live DB/network) — não desbloqueado artificialmente"
    )
    discarded.append(
        "VPS provision: BLOCKED até PRE_VPS_FINAL_READY e decisão humana"
    )

    result = {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read-only",
        "command": "rank-next",
        "git": snapshot.get("git"),
        "dod_hash": (snapshot.get("dod") or {}).get("sha256") or matrix.get("dod_sha256"),
        "snapshot_confidence": snapshot.get("confidence"),
        "open_prs": snapshot.get("open_prs"),
        "dod_summary": {
            "item_count": matrix.get("item_count"),
            "done_count": matrix.get("done_count"),
            "open_count": matrix.get("open_count"),
            "superseded_claims": matrix.get("superseded_claims"),
            "forbidden_claims": matrix.get("forbidden_claims"),
            "veto": matrix.get("veto"),
        },
        "graph_critical_path": graph.get("critical_path"),
        "divergences": divergences,
        "ranking": top,
        "full_ranking_ids": [c["id"] for c in ranked],
        "selected": selected,
        "selected_id": selected["id"] if selected else None,
        "discarded_attractive": discarded,
        "blockers": blockers,
        "weights_version": weights.get("version"),
    }

    if write_state:
        out_dir = SQUAD_DIR / "state" / "rankings"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = result["generated_at"].replace(":", "").replace("-", "")
        out = out_dir / f"{ts}-rank-next.json"
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        latest = out_dir / "latest.json"
        latest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result["state_path"] = str(out.relative_to(root)) if out.is_relative_to(root) else str(out)

        snap_dir = SQUAD_DIR / "state" / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        sp = snap_dir / f"{ts}-snapshot.json"
        sp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        req_dir = SQUAD_DIR / "state" / "requirements"
        req_dir.mkdir(parents=True, exist_ok=True)
        # store summary only to keep size reasonable
        summary = {
            k: matrix[k]
            for k in matrix
            if k != "items"
        }
        summary["items_sample"] = (matrix.get("items") or [])[:50]
        (req_dir / "latest-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        gdir = SQUAD_DIR / "state" / "graphs"
        gdir.mkdir(parents=True, exist_ok=True)
        (gdir / "latest-graph.json").write_text(
            json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        bdir = SQUAD_DIR / "state" / "blockers"
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / "latest.json").write_text(
            json.dumps(blockers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="extra-dod-roi *rank-next (read-only)")
    p.add_argument("--repo", default=None)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--write-state", action="store_true", help="Write only under squads/extra-dod-roi/state/")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--json", action="store_true", help="Machine JSON only")
    p.add_argument("-o", "--output", default=None, help="Write full JSON report to path")
    args = p.parse_args(argv)

    root = Path(args.repo).resolve() if args.repo else repo_root_from()
    result = run_rank_next(root, top_n=args.top, write_state=args.write_state, fetch=args.fetch)

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_report(result, args.top))
        if args.write_state and result.get("state_path"):
            print(f"\n[state written] {result['state_path']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
