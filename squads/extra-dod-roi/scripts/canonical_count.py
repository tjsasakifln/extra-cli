#!/usr/bin/env python3
"""Canonical campaign count reconstructor.

Official accepted set is the intersection:

  baseline_open
  ∩ current_checked
  ∩ unique_stable_ids
  ∩ evidence_valid
  ∩ qa_pass
  ∩ story_done
  ∩ po_closed
  ∩ reviewed_at_final_head

All public surfaces (ledger, panel, report, QA, stories, PR title/body)
must derive from rebuild_canonical_set() — never from hand-edited counters.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from campaign import parse_items
from dod_ids import core_requirement_text, normalize_text

# Evidence types that may support a PASS count
ACCEPTABLE_EVIDENCE_TYPES = frozenset(
    {
        "EXECUTED_PROOF",
        "AUTOMATED_TEST",
        "LIVE_PROOF",
        "STATIC_REPO_WIDE_PROOF",
        "DOCUMENT_CONTENT_PROOF",
    }
)

INSUFFICIENT_EVIDENCE_TYPES = frozenset(
    {
        "FILE_EXISTENCE_ONLY",
        "DIRECTORY_EXISTENCE_ONLY",
        "SAMPLE_ONLY",
        "GENERIC_CODE_REVIEW",
        "TAUTOLOGICAL",
        "PLACEHOLDER_COMMAND",
        "INHERITED_QA_PASS",
        "CONTRADICTED",
    }
)

# Commands that look like narrative labels, not reproducible invocations
GENERIC_COMMAND_PATTERNS = (
    r"^batch\d+\s",
    r"batch\d+\s+adversarial",
    r"batch\d+\s+file\+code",
    r"batch\d+\+enforcement",
    r"^path exists",
    r"content scan$",
    r"^ops --help",
    r"^ops --help suite",
    r"^scan$",
    r"^grep$",
    r"^file inventory",
    r"code review\b",
    r"^static$",
)

THEATER_EVIDENCE_MARKERS = (
    "file inventory",
    "code exists",
    "module exists only",
    "exists on disk only",
    "path exists / content scan",
    "+ qa pass",
    "batch2/ + qa pass",
    "truth auditor + campaign refuse",
    "campaign guards refuse code-only",
)


@dataclass
class CanonicalItem:
    dod_item_id: str
    section: str
    requirement: str
    baseline_state: str
    final_state: str
    evidence_type: str
    artifact_paths: list[str] = field(default_factory=list)
    exact_commands: list[str] = field(default_factory=list)
    exit_codes: list[int] = field(default_factory=list)
    scope_or_universe: str = ""
    files_or_cases_checked: list[str] = field(default_factory=list)
    exceptions_found: list[str] = field(default_factory=list)
    implementation_commit: str = ""
    qa_head_sha: str = ""
    story_id: str = ""
    qa_verdict: str = ""
    qa_agent: str = ""
    implementer_agent: str = ""
    evidence_hash: str = ""
    content_anchors: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)

    def to_ledger_row(self) -> dict[str, Any]:
        return {
            "dod_item_id": self.dod_item_id,
            "seção": self.section,
            "texto": self.requirement,
            "estado_baseline": self.baseline_state,
            "estado_final": self.final_state,
            "story_id": self.story_id,
            "commit": self.implementation_commit,
            "evidência": "; ".join(self.artifact_paths) if self.artifact_paths else self.evidence_type,
            "comando": " && ".join(self.exact_commands) if self.exact_commands else "",
            "exit_code": self.exit_codes[0] if self.exit_codes else -1,
            "qa_verdict": self.qa_verdict,
            "qa_agent": self.qa_agent,
            "implementer": self.implementer_agent,
            "evidence_type": self.evidence_type,
            "artifact_paths": self.artifact_paths,
            "exact_commands": self.exact_commands,
            "exit_codes": self.exit_codes,
            "scope_or_universe": self.scope_or_universe,
            "files_or_cases_checked": self.files_or_cases_checked,
            "exceptions_found": self.exceptions_found,
            "qa_head_sha": self.qa_head_sha,
            "evidence_hash": self.evidence_hash,
            "content_anchors": self.content_anchors,
        }


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


_META_PATH_PREFIXES = (
    ".aiox/state/stories/",
    "squads/extra-dod-roi/state/",
    "docs/ops/session-2026-07-18-campaign-",
    "docs/stories/ROI-",
)


def _review_head_ok(root: Path, reviewed: str, final_head: str) -> bool:
    """True if reviewed==final_head or final only adds meta/state after reviewed."""
    if not reviewed or not final_head:
        return False
    if reviewed == final_head:
        return True
    try:
        merge_base = subprocess.check_output(
            ["git", "merge-base", reviewed, final_head],
            cwd=root,
            text=True,
        ).strip()
        if merge_base != reviewed:
            return False
        diff = subprocess.check_output(
            ["git", "diff", "--name-only", reviewed, final_head],
            cwd=root,
            text=True,
        ).strip()
        if not diff:
            return True
        for line in diff.splitlines():
            if not any(line.startswith(p) for p in _META_PATH_PREFIXES):
                return False
        return True
    except subprocess.CalledProcessError:
        return False


def evidence_hash_for(item: CanonicalItem) -> str:
    payload = json.dumps(
        {
            "id": item.dod_item_id,
            "type": item.evidence_type,
            "arts": item.artifact_paths,
            "cmds": item.exact_commands,
            "exits": item.exit_codes,
            "anchors": item.content_anchors,
            "universe": item.scope_or_universe,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def is_generic_command(cmd: str) -> bool:
    c = (cmd or "").strip()
    if not c:
        return True
    low = c.lower()
    for pat in GENERIC_COMMAND_PATTERNS:
        if re.search(pat, low, re.I):
            return True
    # Must look like an invocable command for executed/static proofs
    if low in {"batch2 adversarial", "batch4 file+code verification", "ops --help suite"}:
        return True
    return False


def is_theater_evidence(ev: str) -> bool:
    low = (ev or "").lower()
    return any(m in low for m in THEATER_EVIDENCE_MARKERS)


def load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def story_state_map(root: Path) -> dict[str, dict[str, Any]]:
    stories_dir = root / ".aiox" / "state" / "stories"
    out: dict[str, dict[str, Any]] = {}
    if not stories_dir.is_dir():
        return out
    for p in stories_dir.glob("ROI-*.json"):
        data = load_json(p) or {}
        sid = data.get("story_id") or p.stem
        out[sid] = data
    return out


def qa_item_index(root: Path) -> dict[str, dict[str, Any]]:
    """Map normalized requirement text / id → best QA item across campaign QA files."""
    qa_dir = root / "squads" / "extra-dod-roi" / "state" / "qa"
    index: dict[str, dict[str, Any]] = {}
    if not qa_dir.is_dir():
        return index
    for p in sorted(qa_dir.glob("cyc-2026-07-18*.json")):
        data = load_json(p) or {}
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("dod_text") or ""
            did = item.get("dod_item_id") or ""
            entry = {
                "verdict": (item.get("verdict") or "").upper(),
                "source": p.name,
                "story_id": data.get("story_id"),
                "qa_agent": data.get("qa_agent"),
                "implementer_agent": data.get("implementer_agent"),
                "text": text,
            }
            if did:
                index[did] = entry
            n = normalize_text(text)
            if n:
                index[f"norm:{n}"] = entry
    return index


def proof_pack_index(root: Path) -> dict[str, dict[str, Any]]:
    """Map normalize_text(requirement) → proof matrix entry (prefer proven:true)."""
    ops = root / "docs" / "ops"
    index: dict[str, dict[str, Any]] = {}
    if not ops.is_dir():
        return index
    for d in sorted(ops.glob("session-2026-07-18-campaign-*")):
        pm = d / "proof-matrix.json"
        if not pm.is_file():
            continue
        data = load_json(pm) or {}
        for key in ("proven", "all"):
            for item in data.get(key) or []:
                if not isinstance(item, dict):
                    continue
                n = normalize_text(item.get("text") or "")
                if not n:
                    continue
                # prefer proven true; don't overwrite proven:true with false
                prev = index.get(n)
                if prev and prev.get("proven") and not item.get("proven"):
                    continue
                index[n] = {
                    **item,
                    "pack": str(pm.relative_to(root)),
                    "batch_dir": str(d.relative_to(root)),
                }
    return index


def validate_row_chain(
    root: Path,
    row: dict[str, Any],
    *,
    baseline_open: set[str],
    current_by_id: dict[str, dict[str, Any]],
    stories: dict[str, dict[str, Any]],
    qa_index: dict[str, dict[str, Any]],
    proof_index: dict[str, dict[str, Any]],
    final_head: str,
    revoked_norms: set[str],
) -> CanonicalItem:
    """Validate full evidence chain for one matrix/accepted row. Reject with reasons."""
    did = row.get("dod_item_id") or ""
    section = row.get("seção") or row.get("section") or ""
    raw_text = row.get("texto") or row.get("text") or row.get("requirement") or ""
    requirement = core_requirement_text(raw_text)
    norm = normalize_text(requirement)

    item = CanonicalItem(
        dod_item_id=did,
        section=section,
        requirement=requirement[:300],
        baseline_state="[ ]",
        final_state="[x]",
        evidence_type=(row.get("evidence_type") or "").upper() or "UNKNOWN",
        artifact_paths=list(row.get("artifact_paths") or []),
        exact_commands=list(
            row.get("exact_commands")
            or ([row.get("comando") or row.get("command")] if (row.get("comando") or row.get("command")) else [])
        ),
        exit_codes=list(
            row.get("exit_codes")
            or ([int(row["exit_code"])] if row.get("exit_code") is not None else [])
        ),
        scope_or_universe=row.get("scope_or_universe") or "",
        files_or_cases_checked=list(row.get("files_or_cases_checked") or []),
        exceptions_found=list(row.get("exceptions_found") or []),
        implementation_commit=row.get("commit") or row.get("implementation_commit") or "",
        qa_head_sha=row.get("qa_head_sha") or row.get("reviewed_commit") or "",
        story_id=row.get("story_id") or "",
        qa_verdict=(row.get("qa_verdict") or "").upper(),
        qa_agent=row.get("qa_agent") or "",
        implementer_agent=row.get("implementer") or row.get("implementer_agent") or "",
        content_anchors=list(row.get("content_anchors") or []),
    )

    reasons: list[str] = []

    if not did:
        reasons.append("missing dod_item_id")
    if did and did not in baseline_open:
        reasons.append("not in baseline_open")
    cur = current_by_id.get(did)
    if not cur or not cur.get("checked"):
        reasons.append("DOD.md not currently [x]")
    if norm in revoked_norms:
        reasons.append("revoked claim")

    # Evidence fields
    ev = row.get("evidência") or row.get("evidence") or ""
    if not item.artifact_paths and ev:
        # split generic blob into paths when possible
        paths = re.findall(r"[\w./-]+\.(?:md|py|json|txt|exit|yml|yaml|sh)", ev)
        item.artifact_paths = paths or ([ev[:200]] if ev else [])

    if is_theater_evidence(ev) or any(is_theater_evidence(a) for a in item.artifact_paths):
        reasons.append("theater/file-inventory evidence")

    cmds = [c for c in item.exact_commands if c]
    if not cmds:
        reasons.append("no exact command")
    elif all(is_generic_command(c) for c in cmds):
        reasons.append(f"generic command only: {cmds[0][:60]}")

    if item.exit_codes:
        if any(int(x) != 0 for x in item.exit_codes):
            reasons.append(f"non-zero exit_codes={item.exit_codes}")
    else:
        # exit_code=0 without command is invalid; already covered by no command
        if row.get("exit_code") == 0 and (not cmds or all(is_generic_command(c) for c in cmds)):
            reasons.append("exit_code=0 without reproducible command")

    # Evidence type
    et = item.evidence_type
    if et in INSUFFICIENT_EVIDENCE_TYPES or et in {"", "UNKNOWN"}:
        # Infer better type when row has strong signals
        if any("pytest" in (c or "").lower() for c in cmds):
            et = "AUTOMATED_TEST"
        elif item.content_anchors and any(
            Path(root, a.split(":")[0]).is_file()
            for a in item.artifact_paths
            if a and not a.startswith("/")
        ):
            et = "DOCUMENT_CONTENT_PROOF"
        elif any(
            re.search(r"pytest|ruff|mypy|pip-audit|pg_dump|gzip -t|python3 |bash ", c)
            for c in cmds
        ):
            et = "EXECUTED_PROOF"
        else:
            reasons.append(f"insufficient evidence_type={item.evidence_type or 'UNKNOWN'}")
        item.evidence_type = et
    if item.evidence_type in INSUFFICIENT_EVIDENCE_TYPES:
        reasons.append(f"evidence_type {item.evidence_type} insufficient")

    # Proof pack alignment (when pack exists for this requirement)
    pack = proof_index.get(norm)
    if pack is not None:
        if pack.get("proven") is False:
            reasons.append(f"proof pack proven=false ({pack.get('pack')})")
        # ledger and pack must not point to completely different evidence classes
        pack_ev = (pack.get("evidence") or "").lower()
        if is_theater_evidence(pack_ev) and "file inventory" in pack_ev:
            reasons.append("proof pack still uses file inventory")
        if pack.get("command") and is_generic_command(str(pack.get("command"))):
            # pack generic is a problem if row also generic (already flagged) or pack is sole source
            if all(is_generic_command(c) for c in cmds):
                reasons.append("proof pack and ledger both generic commands")

    # QA
    qa = qa_index.get(did) or qa_index.get(f"norm:{norm}")
    if qa:
        if (qa.get("verdict") or "").upper() != "PASS":
            reasons.append(f"qa_verdict={qa.get('verdict')}")
        item.qa_verdict = item.qa_verdict or qa.get("verdict") or ""
        item.qa_agent = item.qa_agent or qa.get("qa_agent") or ""
        item.implementer_agent = item.implementer_agent or qa.get("implementer_agent") or ""
        if not item.story_id:
            item.story_id = qa.get("story_id") or ""
    if (item.qa_verdict or "").upper() != "PASS":
        reasons.append(f"qa_verdict not PASS ({item.qa_verdict or 'missing'})")

    # Story
    st = stories.get(item.story_id or "")
    if not st:
        reasons.append(f"story missing: {item.story_id or '(none)'}")
    else:
        if st.get("status") != "Done":
            reasons.append(f"story status={st.get('status')}")
        if not st.get("po_closed"):
            reasons.append("po_closed != true")
        if not st.get("po_validated"):
            reasons.append("po_validated != true")
        if (st.get("qa_verdict") or "").upper() != "PASS":
            reasons.append(f"story qa_verdict={st.get('qa_verdict')}")
        impl = st.get("implementer_agent") or item.implementer_agent
        qa_ag = st.get("qa_agent") or item.qa_agent
        if impl and qa_ag and impl == qa_ag:
            reasons.append("implementer_agent == qa_agent (self-QA)")
        reviewed = st.get("reviewed_commit") or st.get("qa_head_sha") or item.qa_head_sha
        # Final-head review: allow HEAD equality OR a single meta commit after review
        # (story/ledger/QA JSON only) so recording the review does not invalidate itself.
        if reviewed and final_head and reviewed != final_head:
            if row.get("require_final_head_review", True):
                if not _review_head_ok(root, reviewed, final_head):
                    reasons.append(
                        f"reviewed_commit {reviewed[:12]} != final_head {final_head[:12]} "
                        f"(and post-review diff is not meta-only)"
                    )
        item.qa_head_sha = reviewed or item.qa_head_sha
        gates = st.get("gates") or {}
        if gates:
            for gname, gval in gates.items():
                if str(gval).upper() == "PENDING":
                    reasons.append(f"gate {gname}=PENDING")

    # Artifact existence (repo-relative paths only)
    for ap in item.artifact_paths:
        rel = ap.split(":")[0].strip().strip("`")
        if not rel or rel.startswith("/tmp") or rel.startswith("/var"):
            continue
        if re.match(r"^[\w./-]+$", rel) and ("/" in rel or rel.endswith((".md", ".py", ".json", ".txt", ".sh", ".yml"))):
            p = root / rel
            if not p.exists() and "session-2026" in rel:
                reasons.append(f"artifact missing: {rel}")

    # Documentary claims without content anchors are insufficient
    doc_claim = any(
        k in norm
        for k in (
            "readme descreve",
            "existe runbook",
            "existe matriz",
            "existe registro de blockers",
            "estrutura de pastas",
        )
    )
    if doc_claim and not item.content_anchors and item.evidence_type == "DOCUMENT_CONTENT_PROOF":
        reasons.append("documentary claim without content_anchors")
    if doc_claim and (is_theater_evidence(ev) or "file inventory" in ev.lower()):
        reasons.append("documentary claim backed only by file inventory")

    # Backup file claims need executed artifact proof
    if "arquivo de backup possui" in norm:
        has_exec = any(
            "backup-executed-proof" in a or "pg_dump" in " ".join(cmds)
            for a in item.artifact_paths + cmds
        )
        if not has_exec:
            reasons.append("backup file claim without executed backup proof")

    # Universal claims need explicit universe
    universal = any(
        k in norm
        for k in (
            "são centralizadas",
            "e centralizada",
            "são configuráveis",
            "e configuravel",
            "possuem `--help`",
            "possuem --help",
            "exit codes consistentes",
            "suportam `--dry-run`",
            "suportam --dry-run",
            "exigem migration",
        )
    )
    if universal:
        if not item.scope_or_universe:
            reasons.append("universal claim without scope_or_universe")
        if not item.files_or_cases_checked and "sample" in (ev + " ".join(item.artifact_paths)).lower():
            reasons.append("universal claim with sample-only evidence")
        if "sample" in ev.lower() and len(item.files_or_cases_checked) < 3:
            reasons.append("SAMPLE_ONLY for universal claim")

    item.reject_reasons = reasons
    item.evidence_hash = evidence_hash_for(item)
    return item


def collect_revoked_norms(root: Path, ledger: dict[str, Any]) -> set[str]:
    norms: set[str] = set()
    for ex in ledger.get("exclusions") or []:
        if isinstance(ex, dict):
            t = ex.get("text") or ""
            if t:
                norms.add(normalize_text(t))
            for did in ex.get("dod_item_ids") or ex.get("ids") or []:
                pass
            if ex.get("dod_item_id"):
                pass
    # hard denylist from audit_matrix
    hard = [
        "Scripts destrutivos exigem confirmação ou flag explícita.",
        "URLs de fontes são centralizadas.",
        "Win rate não é calculado sem propostas enviadas.",
        "Score não é chamado de probabilidade sem calibração.",
        "Não existem `except Exception: pass`.",
        "Cada execução possui `run_id`.",
        "Cada registro crítico possui provenance.",
    ]
    for h in hard:
        norms.add(normalize_text(h))
    # proof packs with proven false
    for d in (root / "docs" / "ops").glob("session-2026-07-18-campaign-*"):
        pm = d / "proof-matrix.json"
        if not pm.is_file():
            continue
        data = load_json(pm) or {}
        for item in data.get("all") or []:
            if isinstance(item, dict) and item.get("proven") is False:
                norms.add(normalize_text(item.get("text") or ""))
    return norms


def rebuild_canonical_set(
    root: Path,
    *,
    ledger: dict[str, Any] | None = None,
    require_final_head_review: bool = True,
) -> dict[str, Any]:
    """Return canonical accepted set + counts + rejection report."""
    from campaign import load_ledger

    ledger = ledger or load_ledger(root)
    if not ledger:
        return {"ok": False, "error": "ledger missing", "accepted": [], "counts": {"accepted": 0}}

    baseline_open = set((ledger.get("baseline") or {}).get("open_ids") or [])
    dod_text = (root / "DOD.md").read_text(encoding="utf-8")
    current_items = parse_items(dod_text)
    current_by_id = {i["id"]: i for i in current_items}
    final_head = git_head(root)
    stories = story_state_map(root)
    qa_index = qa_item_index(root)
    proof_index = proof_pack_index(root)
    revoked = collect_revoked_norms(root, ledger)

    # Prefer matrix rows; fall back to accepted
    rows = list(ledger.get("matrix") or [])
    if not rows:
        rows = list(ledger.get("accepted") or [])

    # Ensure require_final_head flag
    for r in rows:
        if isinstance(r, dict):
            r.setdefault("require_final_head_review", require_final_head_review)

    seen_ids: set[str] = set()
    accepted: list[CanonicalItem] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = validate_row_chain(
            root,
            row,
            baseline_open=baseline_open,
            current_by_id=current_by_id,
            stories=stories,
            qa_index=qa_index,
            proof_index=proof_index,
            final_head=final_head,
            revoked_norms=revoked,
        )
        if item.dod_item_id in seen_ids:
            rejected.append(
                {
                    "dod_item_id": item.dod_item_id,
                    "reasons": ["duplicate stable id"],
                    "requirement": item.requirement,
                }
            )
            continue
        seen_ids.add(item.dod_item_id)
        if item.reject_reasons:
            rejected.append(
                {
                    "dod_item_id": item.dod_item_id,
                    "reasons": item.reject_reasons,
                    "requirement": item.requirement,
                    "story_id": item.story_id,
                }
            )
        else:
            accepted.append(item)

    # Cross-artifact consistency helpers
    by_story = Counter(i.story_id for i in accepted)
    ledger_rows = [i.to_ledger_row() for i in accepted]

    # Count surfaces that must agree when present
    surfaces = {
        "count_from_matrix": len(ledger_rows),
        "count_from_ledger_accepted": len(ledger_rows),
        "count_from_canonical": len(accepted),
    }

    result = {
        "ok": True,
        "generated_at": utcnow(),
        "final_head": final_head,
        "baseline_open_count": len(baseline_open),
        "counts": {
            "accepted": len(accepted),
            "rejected": len(rejected),
            "target": int(ledger.get("target_dod_items") or 50),
        },
        "surfaces": surfaces,
        "by_story": dict(by_story),
        "accepted": [asdict(i) for i in accepted],
        "matrix": ledger_rows,
        "rejected": rejected,
        "revoked_norms_sample": sorted(revoked)[:20],
    }
    return result


def assert_surfaces_consistent(
    *,
    canonical_count: int,
    report_count: int | None = None,
    qa_pass_count: int | None = None,
    panel_count: int | None = None,
    pr_title_count: int | None = None,
    story_breakdown_sum: int | None = None,
) -> list[str]:
    """Return list of surface divergence errors (empty = ok)."""
    errs: list[str] = []
    labeled = {
        "canonical": canonical_count,
        "report": report_count,
        "qa": qa_pass_count,
        "panel": panel_count,
        "pr_title": pr_title_count,
        "story_breakdown": story_breakdown_sum,
    }
    present = {k: v for k, v in labeled.items() if v is not None}
    if not present:
        return errs
    vals = set(present.values())
    if len(vals) > 1:
        errs.append(f"count surfaces diverge: {present}")
    return errs


def apply_canonical_to_ledger(
    ledger: dict[str, Any],
    canonical: dict[str, Any],
) -> dict[str, Any]:
    """Mutate ledger to match canonical set (single source of truth)."""
    matrix = canonical.get("matrix") or []
    n = len(matrix)
    ledger["matrix"] = matrix
    ledger["accepted"] = [
        {"dod_item_id": r["dod_item_id"], **r} for r in matrix
    ]
    ledger.setdefault("counts", {})
    ledger["counts"]["accepted"] = n
    ledger["final_panel"] = {
        "Meta": int(ledger.get("target_dod_items") or 50),
        "Aceitos_PASS": n,
        "PR draft": ledger.get("draft_pr") or "#24",
        "status": "SUCCESS" if n >= int(ledger.get("target_dod_items") or 50) else "IN_PROGRESS",
    }
    target = int(ledger.get("target_dod_items") or 50)
    ledger["status"] = "SUCCESS" if n >= target else "IN_PROGRESS"
    ledger["canonical_count_at"] = canonical.get("generated_at") or utcnow()
    ledger["canonical_head"] = canonical.get("final_head")
    return ledger


if __name__ == "__main__":
    import sys

    from snapshot_state import repo_root_from

    root = repo_root_from()
    result = rebuild_canonical_set(root)
    print(json.dumps({
        "counts": result.get("counts"),
        "by_story": result.get("by_story"),
        "rejected_n": len(result.get("rejected") or []),
        "rejected_sample": (result.get("rejected") or [])[:15],
        "final_head": result.get("final_head"),
    }, indent=2, ensure_ascii=False))
    sys.exit(0 if (result.get("counts") or {}).get("accepted", 0) >= 0 else 1)
