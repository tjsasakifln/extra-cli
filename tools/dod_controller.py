#!/usr/bin/env python3
"""DOD Convergence Controller — persistent harness for DOD.md progress.

Commands:
  scan, status, next, start, verify, accept, block, resume, audit, report

Exit codes: 0 success, 1 validation/business failure, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
DOD_PATH = ROOT / "DOD.md"
DOD_DIR = ROOT / ".dod"
MANIFEST_PATH = DOD_DIR / "manifest.yaml"
STATE_PATH = DOD_DIR / "state.json"
LOG_PATH = DOD_DIR / "log.jsonl"
BLOCKERS_DIR = DOD_DIR / "blockers"
EVIDENCE_DIR = DOD_DIR / "evidence"

VALID_STATES = frozenset(
    {
        "OPEN",
        "IN_PROGRESS",
        "IMPLEMENTED",
        "VERIFIED",
        "ACCEPTED",
        "BLOCKED_HUMAN",
        "BLOCKED_CREDENTIAL",
        "BLOCKED_EXTERNAL",
        "BLOCKED_INFRA",
        "BLOCKED_LIVE",
        "DEFERRED_BY_DOD",
    }
)

BLOCKED_STATES = frozenset(s for s in VALID_STATES if s.startswith("BLOCKED_"))

CATEGORIES = frozenset(
    {
        "MACHINE_ACTIONABLE",
        "HUMAN_ACCEPTANCE",
        "LIVE_OPERATION",
        "EXTERNAL_DEPENDENCY",
        "CREDENTIAL_REQUIRED",
        "INFRASTRUCTURE_REQUIRED",
        "VPS_PHASE",
        "GOVERNANCE",
        "DOCUMENTATION_WITH_PROOF",
        "ACCEPTED_EXISTING",
    }
)

# Priority for next(): lower = earlier.
CATEGORY_PRIORITY = {
    "GOVERNANCE": 10,
    "MACHINE_ACTIONABLE": 20,
    "DOCUMENTATION_WITH_PROOF": 30,
    "HUMAN_ACCEPTANCE": 70,
    "LIVE_OPERATION": 75,
    "EXTERNAL_DEPENDENCY": 80,
    "CREDENTIAL_REQUIRED": 85,
    "INFRASTRUCTURE_REQUIRED": 90,
    "VPS_PHASE": 95,
    "ACCEPTED_EXISTING": 100,
}

CHECKBOX_RE = re.compile(r"^(\s*)- \[([ xX])\] (.+)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
EVIDENCE_INLINE_RE = re.compile(r"Evid[eê]ncia\s*:\s*(.+)$", re.IGNORECASE)

# Path-like tokens in evidence text (conservative).
PATH_TOKEN_RE = re.compile(
    r"(?:`)?((?:docs|output|scripts|tests|config|squads|data)/[A-Za-z0-9_./\-]+|"
    r"[A-Za-z0-9_.\-]+\.(?:md|json|py|yml|yaml|csv|html|sql|txt|xlsx))"
    r"(?:`)?"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class ControllerExit(Exception):
    """Controlled non-zero exit for CLI commands (testable without SystemExit)."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise ControllerExit(msg, code)


def require_yaml() -> Any:
    if yaml is None:
        die("PyYAML is required. Install with: pip install pyyaml", 2)
    return yaml


def slugify(text: str, max_len: int = 48) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        text = "item"
    return text[:max_len].strip("-")


def content_fingerprint(section: str, text: str) -> str:
    """Stable fingerprint independent of line number."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    # Strip trailing evidence clause for fingerprint stability of requirement text.
    core = re.split(r"\s+evid[eê]ncia\s*:", normalized, maxsplit=1)[0].strip()
    payload = f"{section.strip().lower()}||{core}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def make_item_id(section: str, text: str) -> str:
    sec = slugify(section.split(">")[0].strip() if section else "root", 24) or "root"
    return f"DOD-{sec}-{content_fingerprint(section, text)}"


def classify_item(text: str, section: str, checked: bool) -> str:
    t = text.lower()
    s = section.lower()

    if any(
        k in t
        for k in (
            "vps",
            "systemd",
            "provisionamento da vps",
            "operação contínua em vps",
            "host remoto",
        )
    ) or "vps" in s:
        return "VPS_PHASE"

    if any(
        k in t
        for k in (
            "tiago",
            "validação manual registrada por tiago",
            "avaliação humana",
            "considera útil",
            "decisão de tiago",
            "escolha de infraestrutura",
        )
    ):
        return "HUMAN_ACCEPTANCE"

    if any(
        k in t
        for k in (
            "credencial",
            "token",
            "api key",
            "senha",
            "autenticação",
            "login",
        )
    ) and "sem credenciais" not in t:
        return "CREDENTIAL_REQUIRED"

    if any(
        k in t
        for k in (
            "fonte live",
            "execução live",
            "evidência live",
            "coleta live",
            "fonte oficial realizada",
            "pncp",
            "ciga",
            "doe/sc",
        )
    ) and any(k in t for k in ("live", "oficial", "fonte")):
        return "LIVE_OPERATION"

    if any(
        k in t
        for k in (
            "dependência externa",
            "fornecedor",
            "serviço externo",
            "api externa",
            "indisponível",
        )
    ):
        return "EXTERNAL_DEPENDENCY"

    if any(
        k in t
        for k in (
            "infraestrutura",
            "provision",
            "postgres em produção",
            "banco limpo",
            "ambiente controlado",
        )
    ):
        return "INFRASTRUCTURE_REQUIRED"

    if any(
        k in t
        for k in (
            "este arquivo está versionado",
            "documento é tratado",
            "gates consideram",
            "convenção de evidência",
            "alterações de escopo",
            "itens explicitamente marcados",
            "projeto só é considerado",
        )
    ) or "como usar este documento" in s or "estados, aplicabilidade" in s:
        return "GOVERNANCE"

    if any(
        k in t
        for k in (
            "document",
            "readme",
            "adr",
            "handoff",
            "evidência registrada",
            "relatório",
        )
    ) and not any(k in t for k in ("teste", "pytest", "comando", "suite")):
        return "DOCUMENTATION_WITH_PROOF"

    if checked:
        return "ACCEPTED_EXISTING"

    return "MACHINE_ACTIONABLE"


def extract_evidence_refs(text: str) -> list[str]:
    m = EVIDENCE_INLINE_RE.search(text)
    if not m:
        return []
    blob = m.group(1)
    refs = PATH_TOKEN_RE.findall(blob)
    # Also keep short backtick tokens.
    refs.extend(re.findall(r"`([^`]+)`", blob))
    # Dedupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        r = r.strip().strip("`")
        if r and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def evidence_type_for(text: str, category: str) -> str:
    t = text.lower()
    if "teste" in t or "pytest" in t or "suite" in t:
        return "automated_test"
    if "comando" in t or "exit code" in t:
        return "command_exit_0"
    if "sql" in t:
        return "sql_query"
    if "backup" in t or "restauração" in t or "restore" in t:
        return "restore_test"
    if "live" in t or "fonte oficial" in t:
        return "live_source"
    if "tiago" in t or "manual" in t:
        return "human_validation"
    if "relatório" in t or "json" in t or "markdown" in t:
        return "system_report"
    if category == "GOVERNANCE":
        return "governance_process"
    if category == "VPS_PHASE":
        return "vps_operational"
    return "mixed_or_unspecified"


@dataclass
class ParsedItem:
    text: str
    checked: bool
    section: str
    subsection: str | None
    start_line: int
    heading_path: list[str]
    indent: int


def parse_dod(path: Path) -> list[ParsedItem]:
    lines = path.read_text(encoding="utf-8").splitlines()
    heading_stack: list[tuple[int, str]] = []
    items: list[ParsedItem] = []

    for i, line in enumerate(lines, start=1):
        hm = HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            title = hm.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue

        cm = CHECKBOX_RE.match(line)
        if not cm:
            continue
        indent = len(cm.group(1).replace("\t", "    "))
        checked = cm.group(2).lower() == "x"
        text = cm.group(3).strip()
        path_titles = [t for _, t in heading_stack]
        section = " > ".join(path_titles) if path_titles else "(preamble)"
        subsection = path_titles[-1] if path_titles else None
        items.append(
            ParsedItem(
                text=text,
                checked=checked,
                section=section,
                subsection=subsection,
                start_line=i,
                heading_path=path_titles,
                indent=indent,
            )
        )
    return items


def default_item_dict(p: ParsedItem) -> dict[str, Any]:
    item_id = make_item_id(p.section, p.text)
    category = classify_item(p.text, p.section, p.checked)
    fp = content_fingerprint(p.section, p.text)
    evidence_refs = extract_evidence_refs(p.text)
    needs_human = category == "HUMAN_ACCEPTANCE"
    needs_live = category in {"LIVE_OPERATION"} or "live" in p.text.lower()
    needs_db = any(
        k in p.text.lower()
        for k in ("migration", "postgres", "banco", "schema", "sql", "golden path")
    )

    # Initial state: checked items start as ACCEPTED only if evidence looks present;
    # audit may demote. Unchecked start OPEN.
    state = "OPEN"
    if p.checked:
        state = "ACCEPTED"

    return {
        "id": item_id,
        "text": p.text,
        "section": p.section,
        "subsection": p.subsection,
        "location": {
            "start_line": p.start_line,
            "end_line": p.start_line,
            "heading_path": p.heading_path,
        },
        "category": category,
        "state": state,
        "dod_checked": p.checked,
        "evidence_type": evidence_type_for(p.text, category),
        "dependencies": [],
        "blockers": [],
        "acceptance_commands": [],
        "tests": [],
        "files": [],
        "environment": "local",
        "needs_clean_db": needs_db,
        "needs_live_source": needs_live,
        "needs_human_eval": needs_human,
        "evidence": evidence_refs,
        "acceptance_commit": None,
        "acceptance_pr": None,
        "accepted_at": utc_now() if state == "ACCEPTED" and p.checked else None,
        "justification": None,
        "history": [
            {
                "at": utc_now(),
                "event": "scanned",
                "detail": f"line={p.start_line} checked={p.checked}",
            }
        ],
        "content_fingerprint": fp,
        "evidence_audit": None,
        "priority_boost": 0,
    }


def load_manifest() -> dict[str, Any]:
    require_yaml()
    if not MANIFEST_PATH.exists():
        return {
            "schema_version": "1.0",
            "source": "DOD.md",
            "updated_at": None,
            "items": [],
        }
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    if "items" not in data:
        data["items"] = []
    return data


def save_manifest(data: dict[str, Any]) -> None:
    require_yaml()
    DOD_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = utc_now()
    data["schema_version"] = data.get("schema_version", "1.0")
    data["source"] = "DOD.md"
    MANIFEST_PATH.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        ),
        encoding="utf-8",
    )


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "schema_version": "1.0",
            "campaign_id": "DOD-CONVERGENCE-EXTRA-01",
            "updated_at": utc_now(),
            "active_item_id": None,
            "phase": "idle",
        }
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def append_log(event: str, **payload: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"at": utc_now(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def find_item(manifest: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for it in manifest.get("items", []):
        if it.get("id") == item_id:
            return it
    return None


def index_items(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {it["id"]: it for it in items if "id" in it}


def merge_scan(
    existing: list[dict[str, Any]], parsed: list[ParsedItem]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge DOD parse into existing manifest without losing IDs/history."""
    by_fp: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for it in existing:
        by_id[it["id"]] = it
        fp = it.get("content_fingerprint") or content_fingerprint(
            it.get("section", ""), it.get("text", "")
        )
        by_fp[fp] = it

    stats = Counter()
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for p in parsed:
        fresh = default_item_dict(p)
        fp = fresh["content_fingerprint"]
        old = by_fp.get(fp) or by_id.get(fresh["id"])
        if old:
            stats["preserved"] += 1
            # Preserve operational fields; refresh location/text/checked.
            kept_state = old.get("state", fresh["state"])
            # Do not silently reopen ACCEPTED solely because text moved.
            # If checkbox flipped off while ACCEPTED, record divergence.
            if old.get("dod_checked") and not p.checked and kept_state == "ACCEPTED":
                kept_state = "OPEN"
                stats["reopened_unchecked"] += 1
                hist = list(old.get("history") or [])
                hist.append(
                    {
                        "at": utc_now(),
                        "event": "reopened",
                        "detail": "DOD checkbox unmarked; demoted from ACCEPTED",
                    }
                )
                old["history"] = hist
            elif (not old.get("dod_checked")) and p.checked and kept_state != "ACCEPTED":
                # Newly checked in DOD — do not auto-ACCEPT; leave for audit.
                stats["newly_checked"] += 1

            old["text"] = p.text
            old["section"] = p.section
            old["subsection"] = p.subsection
            old["location"] = fresh["location"]
            old["dod_checked"] = p.checked
            old["content_fingerprint"] = fp
            old["id"] = old.get("id") or fresh["id"]
            # Refresh category only if previously default-ish or missing.
            if old.get("category") not in CATEGORIES:
                old["category"] = fresh["category"]
            old["state"] = kept_state if kept_state in VALID_STATES else fresh["state"]
            # Merge evidence refs (union).
            old_ev = list(old.get("evidence") or [])
            for e in fresh["evidence"]:
                if e not in old_ev:
                    old_ev.append(e)
            old["evidence"] = old_ev
            hist = list(old.get("history") or [])
            hist.append(
                {
                    "at": utc_now(),
                    "event": "rescan",
                    "detail": f"line={p.start_line}",
                }
            )
            old["history"] = hist[-50:]
            merged.append(old)
            seen_ids.add(old["id"])
        else:
            stats["added"] += 1
            merged.append(fresh)
            seen_ids.add(fresh["id"])

    # Items that disappeared from DOD.md — keep as orphaned for audit.
    for it in existing:
        if it["id"] not in seen_ids:
            stats["orphaned"] += 1
            hist = list(it.get("history") or [])
            hist.append(
                {
                    "at": utc_now(),
                    "event": "orphaned",
                    "detail": "no longer present in DOD.md",
                }
            )
            it["history"] = hist[-50:]
            it["justification"] = (it.get("justification") or "") + " [ORPHANED_FROM_DOD]"
            merged.append(it)

    return merged, dict(stats)


def audit_evidence_paths(item: dict[str, Any]) -> dict[str, Any]:
    refs = item.get("evidence") or []
    if not refs:
        if item.get("dod_checked"):
            return {
                "status": "unverified",
                "notes": "checked in DOD but no parseable evidence path",
            }
        return {"status": "n/a", "notes": "no evidence refs"}

    found = 0
    missing: list[str] = []
    for ref in refs:
        # Skip pure tokens that are not paths.
        if "/" not in ref and not re.search(r"\.[a-zA-Z0-9]{1,5}$", ref):
            continue
        candidate = ROOT / ref
        if candidate.exists():
            found += 1
        else:
            # try as relative without backticks already stripped
            missing.append(ref)

    if found and not missing:
        return {"status": "ok", "notes": f"{found} path(s) exist"}
    if found and missing:
        return {
            "status": "partial",
            "notes": f"found={found} missing={missing[:5]}",
        }
    if missing:
        return {"status": "missing", "notes": f"missing={missing[:5]}"}
    return {"status": "unverified", "notes": "refs present but not path-like"}


def metrics_from_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = Counter(it.get("state", "OPEN") for it in items)
    by_cat = Counter(it.get("category", "MACHINE_ACTIONABLE") for it in items)
    total = len(items)
    accepted = by_state.get("ACCEPTED", 0)
    return {
        "total": total,
        "accepted": accepted,
        "verified": by_state.get("VERIFIED", 0),
        "in_progress": by_state.get("IN_PROGRESS", 0),
        "implemented": by_state.get("IMPLEMENTED", 0),
        "open": by_state.get("OPEN", 0),
        "blocked": sum(by_state[s] for s in BLOCKED_STATES),
        "deferred": by_state.get("DEFERRED_BY_DOD", 0),
        "acceptance_pct": round(100.0 * accepted / total, 2) if total else 0.0,
        "by_state": dict(by_state),
        "by_category": dict(by_cat),
        "dod_checked_count": sum(1 for it in items if it.get("dod_checked")),
    }


def is_eligible(item: dict[str, Any]) -> bool:
    if item.get("state") in {
        "ACCEPTED",
        "IN_PROGRESS",
        "VERIFIED",
        "DEFERRED_BY_DOD",
        *BLOCKED_STATES,
    }:
        # VERIFIED needs accept path, not re-start as next work.
        if item.get("state") == "VERIFIED":
            return False
        return False
    if item.get("state") not in {"OPEN", "IMPLEMENTED"}:
        return False
    # Skip pure orphans.
    if item.get("justification") and "ORPHANED_FROM_DOD" in str(item.get("justification")):
        return False
    return True


def score_item(item: dict[str, Any]) -> tuple:
    text = (item.get("text") or "").lower()
    section = (item.get("section") or "").lower()
    boost = int(item.get("priority_boost") or 0)

    # Critical-path keywords (lower is better). Normalize accents for match.
    text_ascii = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    critical = 50
    if "suite global completa verde" in text_ascii:
        critical = 0
    elif any(k in text_ascii for k in ("ci obrigatorio", "teste all", "full suite")):
        critical = 1
    elif any(k in text_ascii for k in ("integridade", "reprodut", "golden path")):
        critical = 5
    elif any(k in text_ascii for k in ("cobertura operacional", "95%", "recall")):
        critical = 8
    elif "local" in text_ascii and any(
        k in text_ascii for k in ("pronto", "ready", "operacao")
    ):
        critical = 10
    elif item.get("category") == "GOVERNANCE" and not item.get("dod_checked"):
        critical = 15

    cat_p = CATEGORY_PRIORITY.get(item.get("category", ""), 50)
    # Prefer unchecked items that gate others.
    checked_penalty = 100 if item.get("dod_checked") else 0
    line = (item.get("location") or {}).get("start_line") or 10**9
    return (critical - boost, cat_p, checked_penalty, line, item.get("id", ""))


def select_next(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [it for it in items if is_eligible(it)]
    if not eligible:
        return None
    eligible.sort(key=score_item)
    return eligible[0]


def emit(data: Any, as_json: bool, human: str | None = None) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if human:
            print(human)
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        else:
            print(data)


# ── Commands ──────────────────────────────────────────────────────────────────


def cmd_scan(args: argparse.Namespace) -> int:
    if not DOD_PATH.exists():
        die(f"DOD.md not found at {DOD_PATH}")
    parsed = parse_dod(DOD_PATH)
    manifest = load_manifest()
    existing = list(manifest.get("items") or [])
    merged, stats = merge_scan(existing, parsed)

    # Optional light evidence audit during scan.
    audit_counts = Counter()
    if not args.skip_evidence_audit:
        for it in merged:
            if it.get("dod_checked") and it.get("state") == "ACCEPTED":
                ea = audit_evidence_paths(it)
                it["evidence_audit"] = ea
                audit_counts[ea["status"]] += 1
                # Do not silent-reopen: only flag divergence for report/audit.
                if ea["status"] in {"missing", "unverified"}:
                    it.setdefault("blockers", [])
                    note = f"evidence_audit:{ea['status']}"
                    if note not in it["blockers"]:
                        it["blockers"] = list(it["blockers"]) + [note]

    manifest["items"] = merged
    manifest["scan_stats"] = stats
    manifest["last_scan_at"] = utc_now()
    save_manifest(manifest)

    state = load_state()
    m = metrics_from_items(merged)
    state["metrics"] = m
    state["main_sha"] = _git_head()
    state["phase"] = "audit" if state.get("phase") == "harness" else state.get("phase", "idle")
    nxt = select_next(merged)
    state["next_eligible_id"] = nxt["id"] if nxt else None
    save_state(state)
    append_log("scan", stats=stats, total=m["total"], accepted=m["accepted"])

    payload = {
        "ok": True,
        "stats": stats,
        "metrics": m,
        "evidence_audit_counts": dict(audit_counts),
        "next_eligible_id": state["next_eligible_id"],
        "manifest": str(MANIFEST_PATH),
    }
    human = (
        f"scan ok: total={m['total']} accepted={m['accepted']} "
        f"open={m['open']} added={stats.get('added', 0)} "
        f"preserved={stats.get('preserved', 0)} orphaned={stats.get('orphaned', 0)}\n"
        f"next={state['next_eligible_id']}"
    )
    emit(payload, args.json, human)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    items = list(manifest.get("items") or [])
    if not items:
        die("manifest empty — run scan first")
    m = metrics_from_items(items)
    state = load_state()
    nxt = select_next(items)
    payload = {
        "campaign_id": state.get("campaign_id"),
        "phase": state.get("phase"),
        "active_item_id": state.get("active_item_id"),
        "next_eligible_id": nxt["id"] if nxt else None,
        "main_sha": state.get("main_sha"),
        "metrics": m,
        "critical_path_hint": (nxt.get("text")[:120] if nxt else None),
    }
    human = (
        f"campaign={payload['campaign_id']} phase={payload['phase']}\n"
        f"active={payload['active_item_id']} next={payload['next_eligible_id']}\n"
        f"total={m['total']} ACCEPTED={m['accepted']} VERIFIED={m['verified']} "
        f"IN_PROGRESS={m['in_progress']} OPEN={m['open']} blocked={m['blocked']} "
        f"deferred={m['deferred']} acceptance={m['acceptance_pct']}%\n"
        f"hint: {payload['critical_path_hint']}"
    )
    emit(payload, args.json, human)
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    items = list(manifest.get("items") or [])
    if not items:
        die("manifest empty — run scan first")
    nxt = select_next(items)
    if not nxt:
        payload = {"ok": True, "item": None, "reason": "no eligible items"}
        emit(payload, args.json, "no eligible items")
        return 0
    payload = {
        "ok": True,
        "item": {
            "id": nxt["id"],
            "text": nxt["text"],
            "section": nxt["section"],
            "state": nxt["state"],
            "category": nxt["category"],
            "score": list(score_item(nxt)),
        },
    }
    human = (
        f"next: {nxt['id']}\n"
        f"  state={nxt['state']} category={nxt['category']}\n"
        f"  {nxt['text'][:200]}"
    )
    emit(payload, args.json, human)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    item_id = args.item_id
    manifest = load_manifest()
    item = find_item(manifest, item_id)
    if not item:
        die(f"unknown item: {item_id}", 2)
    if item.get("state") == "ACCEPTED":
        die(f"item already ACCEPTED: {item_id}")
    if item.get("state") in BLOCKED_STATES and not args.force:
        die(f"item blocked ({item.get('state')}); use resume or --force")

    item["state"] = "IN_PROGRESS"
    hist = list(item.get("history") or [])
    hist.append({"at": utc_now(), "event": "start", "detail": "campaign start"})
    item["history"] = hist[-50:]
    save_manifest(manifest)

    state = load_state()
    state["active_item_id"] = item_id
    state["phase"] = "item_cycle"
    state["resume_step"] = "implement"
    state["active_run_id"] = f"run-{utc_now().replace(':', '').replace('-', '')}"
    save_state(state)
    append_log("start", item_id=item_id, run_id=state["active_run_id"])

    # Evidence pack skeleton.
    pack = EVIDENCE_DIR / item_id
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "README.md").write_text(
        f"# Evidence pack — {item_id}\n\n"
        f"Text: {item['text']}\n\n"
        f"Started: {utc_now()}\n"
        f"Run: {state['active_run_id']}\n",
        encoding="utf-8",
    )

    payload = {
        "ok": True,
        "item_id": item_id,
        "state": "IN_PROGRESS",
        "run_id": state["active_run_id"],
        "evidence_dir": str(pack),
    }
    emit(payload, args.json, f"started {item_id} run={state['active_run_id']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    item_id = args.item_id
    manifest = load_manifest()
    item = find_item(manifest, item_id)
    if not item:
        die(f"unknown item: {item_id}", 2)

    criteria_path = EVIDENCE_DIR / item_id / "acceptance_criteria.md"
    if not criteria_path.exists() and not args.allow_missing_criteria:
        die(
            f"missing acceptance criteria file: {criteria_path} "
            "(write criteria before verify, or pass --allow-missing-criteria only for dry harness tests)"
        )

    results: dict[str, Any] = {
        "item_id": item_id,
        "commands": [],
        "tests": [],
        "ok": True,
        "notes": [],
    }

    # Run registered acceptance commands if any.
    import subprocess

    for cmd in item.get("acceptance_commands") or []:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        entry = {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-500:],
            "stderr_tail": proc.stderr[-500:],
        }
        results["commands"].append(entry)
        if proc.returncode != 0:
            results["ok"] = False

    for test in item.get("tests") or []:
        proc = subprocess.run(
            ["python3", "-m", "pytest", test, "-q", "--tb=line"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        entry = {
            "test": test,
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-500:],
        }
        results["tests"].append(entry)
        if proc.returncode != 0:
            results["ok"] = False

    if not (item.get("acceptance_commands") or item.get("tests")):
        results["notes"].append(
            "no acceptance_commands/tests registered; mark verify only with --mark-if-empty"
        )
        if not args.mark_if_empty:
            results["ok"] = False

    pack = EVIDENCE_DIR / item_id
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "verify_result.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if results["ok"]:
        item["state"] = "VERIFIED"
        hist = list(item.get("history") or [])
        hist.append({"at": utc_now(), "event": "verify", "detail": "VERIFIED"})
        item["history"] = hist[-50:]
        save_manifest(manifest)
        append_log("verify", item_id=item_id, ok=True)
        emit(
            {"ok": True, "state": "VERIFIED", "results": results},
            args.json,
            f"VERIFIED {item_id}",
        )
        return 0

    append_log("verify", item_id=item_id, ok=False, results=results)
    emit(
        {"ok": False, "state": item.get("state"), "results": results},
        args.json,
        f"verify FAILED {item_id}",
    )
    return 1


def cmd_accept(args: argparse.Namespace) -> int:
    item_id = args.item_id
    manifest = load_manifest()
    item = find_item(manifest, item_id)
    if not item:
        die(f"unknown item: {item_id}", 2)

    gates: dict[str, Any] = {}
    ok = True

    if item.get("state") not in {"VERIFIED", "ACCEPTED"} and not args.force_from_state:
        gates["state"] = f"must be VERIFIED, got {item.get('state')}"
        ok = False
    else:
        gates["state"] = "ok"

    # Must be on main for full ACCEPTED unless --verified-only branch flag.
    branch = _git_branch()
    head = _git_head()
    on_main = branch in {"main", "master"} or args.allow_non_main
    gates["branch"] = branch
    gates["head"] = head
    if not on_main and not args.allow_non_main:
        gates["main_gate"] = "not on main; max VERIFIED (pass --allow-non-main only for dry harness)"
        ok = False
    else:
        gates["main_gate"] = "ok" if on_main else "bypassed"

    # Evidence pack required.
    pack = EVIDENCE_DIR / item_id
    if not pack.exists() and not args.allow_missing_evidence:
        gates["evidence_pack"] = f"missing {pack}"
        ok = False
    else:
        gates["evidence_pack"] = "ok"

    if not ok and not args.force:
        append_log("accept_denied", item_id=item_id, gates=gates)
        emit({"ok": False, "gates": gates}, args.json, f"accept DENIED {item_id}\n{gates}")
        return 1

    item["state"] = "ACCEPTED"
    item["acceptance_commit"] = head
    item["accepted_at"] = utc_now()
    if args.pr:
        item["acceptance_pr"] = args.pr
    hist = list(item.get("history") or [])
    hist.append(
        {
            "at": utc_now(),
            "event": "accept",
            "detail": f"commit={head} branch={branch}",
        }
    )
    item["history"] = hist[-50:]

    # Flip DOD.md checkbox only when accepting for real on main (or forced).
    if args.update_dod and (on_main or args.force):
        _flip_dod_checkbox(item, checked=True)

    item["dod_checked"] = True if args.update_dod else item.get("dod_checked")
    save_manifest(manifest)

    state = load_state()
    if state.get("active_item_id") == item_id:
        state["active_item_id"] = None
        state["resume_step"] = None
        state["phase"] = "audit"
    state["metrics"] = metrics_from_items(list(manifest.get("items") or []))
    nxt = select_next(list(manifest.get("items") or []))
    state["next_eligible_id"] = nxt["id"] if nxt else None
    save_state(state)
    append_log("accept", item_id=item_id, commit=head, gates=gates)

    payload = {"ok": True, "item_id": item_id, "state": "ACCEPTED", "gates": gates}
    emit(payload, args.json, f"ACCEPTED {item_id} @ {head}")
    return 0


def cmd_block(args: argparse.Namespace) -> int:
    item_id = args.item_id
    kind = args.kind.upper()
    if not kind.startswith("BLOCKED_"):
        kind = f"BLOCKED_{kind}"
    if kind not in BLOCKED_STATES:
        die(f"invalid block kind: {kind}", 2)

    manifest = load_manifest()
    item = find_item(manifest, item_id)
    if not item:
        die(f"unknown item: {item_id}", 2)

    item["state"] = kind
    blockers = list(item.get("blockers") or [])
    blockers.append(args.reason)
    item["blockers"] = blockers
    hist = list(item.get("history") or [])
    hist.append({"at": utc_now(), "event": "block", "detail": f"{kind}: {args.reason}"})
    item["history"] = hist[-50:]
    save_manifest(manifest)

    BLOCKERS_DIR.mkdir(parents=True, exist_ok=True)
    blocker_doc = {
        "item_id": item_id,
        "kind": kind,
        "reason": args.reason,
        "owner": args.owner or "unknown",
        "next_test": args.next_test or "",
        "created_at": utc_now(),
        "resolved_at": None,
        "resume_step": load_state().get("resume_step"),
    }
    bpath = BLOCKERS_DIR / f"{item_id}.json"
    bpath.write_text(json.dumps(blocker_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    state = load_state()
    state["phase"] = "blocked"
    state["active_item_id"] = item_id
    save_state(state)
    append_log("block", item_id=item_id, kind=kind, reason=args.reason)

    emit(
        {"ok": True, "item_id": item_id, "state": kind, "blocker": str(bpath)},
        args.json,
        f"blocked {item_id} as {kind}: {args.reason}",
    )
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    state = load_state()
    item_id = args.item_id or state.get("active_item_id")
    if not item_id:
        die("no active item to resume; pass ITEM_ID")

    manifest = load_manifest()
    item = find_item(manifest, item_id)
    if not item:
        die(f"unknown item: {item_id}", 2)

    bpath = BLOCKERS_DIR / f"{item_id}.json"
    blocker = None
    if bpath.exists():
        blocker = json.loads(bpath.read_text(encoding="utf-8"))

    still_blocked = False
    revalidation = {"checked_at": utc_now(), "still_blocked": False, "notes": []}

    if blocker and not args.mark_resolved:
        # Structural revalidation: if kind requires human/cred/infra, remains blocked
        # unless operator passes --mark-resolved.
        if item.get("state") in BLOCKED_STATES:
            still_blocked = True
            revalidation["still_blocked"] = True
            revalidation["notes"].append(
                "blocker file present; pass --mark-resolved when condition cleared"
            )

    if still_blocked and not args.mark_resolved:
        append_log("resume_still_blocked", item_id=item_id, revalidation=revalidation)
        emit(
            {"ok": False, "still_blocked": True, "item": item, "blocker": blocker},
            args.json,
            f"still blocked: {item_id} ({item.get('state')})",
        )
        return 1

    # Resolve
    if blocker:
        blocker["resolved_at"] = utc_now()
        bpath.write_text(json.dumps(blocker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    item["state"] = "IN_PROGRESS"
    item["blockers"] = []
    hist = list(item.get("history") or [])
    hist.append({"at": utc_now(), "event": "resume", "detail": "blocker resolved"})
    item["history"] = hist[-50:]
    save_manifest(manifest)

    state["phase"] = "item_cycle"
    state["active_item_id"] = item_id
    state["resume_step"] = (blocker or {}).get("resume_step") or "implement"
    save_state(state)
    append_log("resume", item_id=item_id)

    emit(
        {
            "ok": True,
            "item_id": item_id,
            "state": "IN_PROGRESS",
            "resume_step": state["resume_step"],
        },
        args.json,
        f"resumed {item_id} at step={state['resume_step']}",
    )
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    if not DOD_PATH.exists():
        die("DOD.md missing")
    parsed = parse_dod(DOD_PATH)
    manifest = load_manifest()
    items = list(manifest.get("items") or [])
    by_fp = {
        it.get("content_fingerprint")
        or content_fingerprint(it.get("section", ""), it.get("text", "")): it
        for it in items
    }

    divergences: list[dict[str, Any]] = []
    dod_fps: set[str] = set()

    for p in parsed:
        fp = content_fingerprint(p.section, p.text)
        dod_fps.add(fp)
        it = by_fp.get(fp)
        if not it:
            divergences.append(
                {
                    "type": "missing_in_manifest",
                    "line": p.start_line,
                    "text": p.text[:120],
                }
            )
            continue
        if bool(it.get("dod_checked")) != p.checked:
            divergences.append(
                {
                    "type": "checkbox_mismatch",
                    "id": it["id"],
                    "manifest_checked": it.get("dod_checked"),
                    "dod_checked": p.checked,
                }
            )
        if it.get("state") == "ACCEPTED" and not p.checked:
            divergences.append(
                {
                    "type": "accepted_but_unchecked",
                    "id": it["id"],
                }
            )
        if p.checked and it.get("state") not in {"ACCEPTED", "VERIFIED"}:
            divergences.append(
                {
                    "type": "checked_but_not_accepted",
                    "id": it["id"],
                    "state": it.get("state"),
                }
            )
        # Evidence audit for ACCEPTED
        if it.get("state") == "ACCEPTED":
            ea = audit_evidence_paths(it)
            it["evidence_audit"] = ea
            if ea["status"] in {"missing", "unverified"}:
                divergences.append(
                    {
                        "type": "accepted_weak_evidence",
                        "id": it["id"],
                        "audit": ea,
                    }
                )

    for it in items:
        fp = it.get("content_fingerprint") or ""
        if fp and fp not in dod_fps:
            if "ORPHANED_FROM_DOD" not in str(it.get("justification") or ""):
                divergences.append({"type": "orphan_manifest_item", "id": it["id"]})

    save_manifest(manifest)
    m = metrics_from_items(items)
    payload = {
        "ok": len(divergences) == 0,
        "divergence_count": len(divergences),
        "divergences": divergences[:200],
        "metrics": m,
        "parsed_count": len(parsed),
        "manifest_count": len(items),
    }
    append_log("audit", divergence_count=len(divergences))
    human = (
        f"audit: divergences={len(divergences)} parsed={len(parsed)} "
        f"manifest={len(items)} acceptance={m['acceptance_pct']}%"
    )
    emit(payload, args.json, human)
    return 0 if payload["ok"] else 1


def cmd_report(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    items = list(manifest.get("items") or [])
    state = load_state()
    m = metrics_from_items(items)
    nxt = select_next(items)
    active = find_item(manifest, state["active_item_id"]) if state.get("active_item_id") else None

    blocked = [it for it in items if it.get("state") in BLOCKED_STATES]
    weak_accepted = [
        it
        for it in items
        if it.get("state") == "ACCEPTED"
        and (it.get("evidence_audit") or {}).get("status") in {"missing", "unverified"}
    ]

    report = {
        "generated_at": utc_now(),
        "campaign_id": state.get("campaign_id"),
        "phase": state.get("phase"),
        "main_sha": state.get("main_sha") or _git_head(),
        "branch": _git_branch(),
        "metrics": m,
        "active_item": {
            "id": active.get("id"),
            "text": active.get("text"),
            "state": active.get("state"),
        }
        if active
        else None,
        "next_eligible": {
            "id": nxt.get("id"),
            "text": nxt.get("text"),
            "category": nxt.get("category"),
        }
        if nxt
        else None,
        "blocked_items": [
            {"id": b["id"], "state": b["state"], "text": b["text"][:100]}
            for b in blocked[:50]
        ],
        "weak_accepted_sample": [
            {"id": w["id"], "audit": w.get("evidence_audit")} for w in weak_accepted[:30]
        ],
        "work_without_dod_effect_note": (
            "Commits/files/stories are not progress; only ACCEPTED counts."
        ),
    }

    out_path = Path(args.output) if args.output else EVIDENCE_DIR / f"report-{utc_now().replace(':', '')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    state["last_report_path"] = str(out_path)
    state["metrics"] = m
    save_state(state)
    append_log("report", path=str(out_path))

    human = (
        f"DOD Convergence Report — {report['campaign_id']}\n"
        f"phase={report['phase']} branch={report['branch']} sha={report['main_sha']}\n"
        f"total={m['total']} ACCEPTED={m['accepted']} ({m['acceptance_pct']}%) "
        f"VERIFIED={m['verified']} IN_PROGRESS={m['in_progress']} OPEN={m['open']} "
        f"blocked={m['blocked']} deferred={m['deferred']}\n"
        f"active={report['active_item']}\n"
        f"next={report['next_eligible']}\n"
        f"weak_accepted={len(weak_accepted)} blocked_listed={len(blocked)}\n"
        f"wrote {out_path}"
    )
    emit(report if args.json else {"path": str(out_path), "metrics": m}, args.json, human)
    return 0


# ── helpers ───────────────────────────────────────────────────────────────────


def _git_head() -> str | None:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _git_branch() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _flip_dod_checkbox(item: dict[str, Any], checked: bool) -> None:
    """Flip the DOD.md checkbox for item by line number + text match."""
    lines = DOD_PATH.read_text(encoding="utf-8").splitlines()
    loc = item.get("location") or {}
    line_no = loc.get("start_line")
    target_text = item.get("text") or ""
    # Match core text without requiring full evidence string equality.
    core = re.split(r"\s+Evid[eê]ncia\s*:", target_text, maxsplit=1)[0].strip()

    def try_flip(idx: int) -> bool:
        if idx < 0 or idx >= len(lines):
            return False
        m = CHECKBOX_RE.match(lines[idx])
        if not m:
            return False
        body = m.group(3).strip()
        body_core = re.split(r"\s+Evid[eê]ncia\s*:", body, maxsplit=1)[0].strip()
        if body_core != core and body != target_text:
            return False
        mark = "x" if checked else " "
        lines[idx] = f"{m.group(1)}- [{mark}] {m.group(3)}"
        return True

    flipped = False
    if line_no:
        flipped = try_flip(line_no - 1)
    if not flipped:
        for i, line in enumerate(lines):
            if try_flip(i):
                flipped = True
                break
    if not flipped:
        die(f"could not locate DOD checkbox for {item.get('id')}")
    DOD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dod_controller",
        description="DOD Convergence Controller",
    )
    # Shared flags: accept both `tool --json CMD` and `tool CMD --json`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        help="JSON output",
    )
    p.add_argument("--json", action="store_true", help="JSON output")
    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("scan", parents=[common], help="Sync manifest from DOD.md")
    sc.add_argument("--skip-evidence-audit", action="store_true")
    sc.set_defaults(func=cmd_scan)

    st = sub.add_parser("status", parents=[common], help="Show progress")
    st.set_defaults(func=cmd_status)

    nx = sub.add_parser("next", parents=[common], help="Select next eligible item")
    nx.set_defaults(func=cmd_next)

    stt = sub.add_parser("start", parents=[common], help="Start work on item")
    stt.add_argument("item_id")
    stt.add_argument("--force", action="store_true")
    stt.set_defaults(func=cmd_start)

    vf = sub.add_parser("verify", parents=[common], help="Verify item acceptance criteria")
    vf.add_argument("item_id")
    vf.add_argument("--allow-missing-criteria", action="store_true")
    vf.add_argument("--mark-if-empty", action="store_true")
    vf.add_argument("--timeout", type=int, default=600)
    vf.set_defaults(func=cmd_verify)

    ac = sub.add_parser("accept", parents=[common], help="Accept item (strict gates)")
    ac.add_argument("item_id")
    ac.add_argument("--pr", default=None)
    ac.add_argument("--update-dod", action="store_true")
    ac.add_argument("--allow-non-main", action="store_true")
    ac.add_argument("--allow-missing-evidence", action="store_true")
    ac.add_argument("--force", action="store_true")
    ac.add_argument("--force-from-state", action="store_true")
    ac.set_defaults(func=cmd_accept)

    bl = sub.add_parser("block", parents=[common], help="Register structured blocker")
    bl.add_argument("item_id")
    bl.add_argument("--kind", required=True, help="HUMAN|CREDENTIAL|EXTERNAL|INFRA|LIVE")
    bl.add_argument("--reason", required=True)
    bl.add_argument("--owner", default=None)
    bl.add_argument("--next-test", default=None)
    bl.set_defaults(func=cmd_block)

    rs = sub.add_parser("resume", parents=[common], help="Revalidate blocker and resume")
    rs.add_argument("item_id", nargs="?", default=None)
    rs.add_argument("--mark-resolved", action="store_true")
    rs.set_defaults(func=cmd_resume)

    au = sub.add_parser("audit", parents=[common], help="Detect divergences")
    au.set_defaults(func=cmd_audit)

    rp = sub.add_parser("report", parents=[common], help="Executive/technical summary")
    rp.add_argument("--output", default=None)
    rp.set_defaults(func=cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.func(args))
    except ControllerExit as exc:
        return int(exc.code)


if __name__ == "__main__":
    raise SystemExit(main())
