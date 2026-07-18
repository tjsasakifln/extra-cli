#!/usr/bin/env python3
"""Full-matrix semantic audit for campaign PASS rows.

Falsifies claim classes with repo-wide probes. On failure (with --write):
- unchecks the DOD.md line
- drops from accepted/matrix
- appends exclusions
- rewrites batch proof packs so proven:true cannot re-authorize

Exit codes:
  0 = all PASS rows survive falsifiers
  1 = one or more rows failed (or packs disagree)
  2 = ledger/DOD missing or inconsistent
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from dod_ids import normalize_text, stable_dod_id  # noqa: E402
from campaign import (  # noqa: E402
    DEFAULT_TARGET,
    ledger_path,
    load_ledger,
    parse_items,
    reconstruct_accepted_from_diff,
    save_ledger,
    utcnow,
)
from snapshot_state import repo_root_from  # noqa: E402


@dataclass
class FalsifyResult:
    dod_item_id: str
    text: str
    ok: bool
    reason: str
    probe: str


def _iter_py(root: Path) -> list[Path]:
    scripts = root / "scripts"
    if not scripts.is_dir():
        return []
    return [p for p in scripts.rglob("*.py") if p.is_file()]


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def falsify_url_centralization(root: Path, row: dict[str, Any]) -> FalsifyResult:
    """Fail if many scripts hardcode source hosts outside config modules."""
    host_re = re.compile(
        r"https?://(?:pncp\.gov\.br|compras\.gov\.br|transparencia\.gov\.br|"
        r"dados\.gov\.br|servicodados\.ibge\.gov\.br)",
        re.I,
    )
    allow = {
        "scripts/crawl/config.py",
        "scripts/lib/constants.py",
        "scripts/crawl/pncp_contract.py",  # module-level constants OK if few
    }
    hits: list[str] = []
    for p in _iter_py(root):
        rel = str(p.relative_to(root)).replace("\\", "/")
        text = _read(p)
        n = len(host_re.findall(text))
        if n:
            hits.append(f"{rel}:{n}")
    # Centralized if almost all hits are in allow-list OR total scattered files low
    scattered = [h for h in hits if h.split(":")[0] not in allow]
    total_files = len(hits)
    ok = total_files <= 3 and len(scattered) <= 1
    return FalsifyResult(
        dod_item_id=row.get("dod_item_id") or "",
        text=(row.get("texto") or "")[:120],
        ok=ok,
        reason=(
            f"source host hardcodes in {total_files} files"
            f" (scattered={len(scattered)}): {scattered[:8]}"
        ),
        probe="repo-wide source host URL count under scripts/",
    )


def falsify_win_rate(root: Path, row: dict[str, Any]) -> FalsifyResult:
    """Fail if system computes base/default win rates without proposals.

    Evidence that only greps scoring.py is vacuous. Sector defaults
    (base_win_rate) and trackers falsify absolute language-truth claims.
    """
    files_with_win: list[str] = []
    base_defaults: list[str] = []
    bad: list[str] = []
    for p in _iter_py(root):
        rel = str(p.relative_to(root)).replace("\\", "/")
        t = _read(p)
        if re.search(r"\bwin_rate\b|base_win_rate|taxa_de_vitoria", t, re.I):
            files_with_win.append(rel)
        if re.search(r"base_win_rate|get_all_base_win_rates|_SECTOR_BASE_WIN", t):
            base_defaults.append(rel)
        lines = t.splitlines()
        for i, line in enumerate(lines):
            if not re.search(r"win_rate\s*=", line):
                continue
            window = "\n".join(lines[max(0, i - 15) : i + 16])
            if not re.search(r"proposta|proposal|props|enviad|submitted", window, re.I):
                bad.append(f"{rel}:{i+1}")
    # Absolute claim fails if:
    # - sector default win rates exist without proposals, OR
    # - any unguarded win_rate assignment, OR
    # - evidence pack only pointed at scoring.py (vacuous)
    ev = (row.get("evidência") or row.get("evidence") or "").lower()
    vacuous_ev = "scoring.py" in ev and "win_loss" not in ev and "extra_ledger" not in ev
    if base_defaults or bad or vacuous_ev or not files_with_win:
        ok = False
        reason = (
            f"base_defaults={base_defaults[:6]} unguarded={bad[:6]} "
            f"vacuous_ev={vacuous_ev} files_with_win={len(files_with_win)}"
        )
    else:
        ok = True
        reason = f"all win_rate sites proposal-gated: {files_with_win}"
    return FalsifyResult(
        dod_item_id=row.get("dod_item_id") or "",
        text=(row.get("texto") or "")[:120],
        ok=ok,
        reason=reason,
        probe="scripts/** win_rate/base_win_rate + proposal guard",
    )


def falsify_score_not_probability(root: Path, row: dict[str, Any]) -> FalsifyResult:
    """Fail if reports/code label score as probabilidade without calibration."""
    bad: list[str] = []
    for p in _iter_py(root):
        rel = str(p.relative_to(root))
        lines = _read(p).splitlines()
        for i, line in enumerate(lines):
            if re.search(
                r"probabilidade\s*de\s*vit[oó]ria|probabilidade_vitoria|probabilidade de vencer",
                line,
                re.I,
            ):
                window = "\n".join(lines[max(0, i - 10) : i + 11])
                if not re.search(r"calibr", window, re.I):
                    bad.append(f"{rel}:{i+1}:{line.strip()[:80]}")
    ok = len(bad) == 0
    return FalsifyResult(
        dod_item_id=row.get("dod_item_id") or "",
        text=(row.get("texto") or "")[:120],
        ok=ok,
        reason="no uncalibrated probabilidade-de-vitoria labels" if ok else f"hits={bad[:12]}",
        probe="scripts/** probabilidade_vitoria / probabilidade de vencer",
    )


def falsify_except_exception_pass(root: Path, row: dict[str, Any]) -> FalsifyResult:
    bad: list[str] = []
    for p in _iter_py(root):
        lines = _read(p).splitlines()
        for i, line in enumerate(lines):
            if re.search(r"except\s+Exception\s*:\s*pass\b", line):
                bad.append(f"{p.relative_to(root)}:{i+1}")
            elif re.match(r"\s*pass\s*$", line) and i > 0 and re.search(
                r"except\s+Exception", lines[i - 1]
            ):
                bad.append(f"{p.relative_to(root)}:{i+1}")
    return FalsifyResult(
        dod_item_id=row.get("dod_item_id") or "",
        text=(row.get("texto") or "")[:120],
        ok=len(bad) == 0,
        reason=f"count={len(bad)} sample={bad[:5]}",
        probe="except Exception: pass scan",
    )


def falsify_universal_run_id(root: Path, row: dict[str, Any]) -> FalsifyResult:
    """Absolute 'every execution has run_id' — fail unless nearly all entry CLIs define it."""
    entryish = [
        p
        for p in _iter_py(root)
        if p.name in {"cli.py", "__main__.py", "monitor.py", "golden_path.py"}
        or "cli" in p.name
    ]
    with_run = 0
    without: list[str] = []
    for p in entryish:
        t = _read(p)
        if re.search(r"\brun_id\b", t):
            with_run += 1
        else:
            without.append(str(p.relative_to(root)))
    # Absolute claim fails if many entry points lack run_id
    ok = len(without) == 0 and with_run > 0
    return FalsifyResult(
        dod_item_id=row.get("dod_item_id") or "",
        text=(row.get("texto") or "")[:120],
        ok=ok,
        reason=f"entry_with={with_run} without={without[:12]}",
        probe="entry-like modules run_id coverage",
    )


def falsify_destructive_confirm(root: Path, row: dict[str, Any]) -> FalsifyResult:
    restore = _read(root / "scripts" / "restore-database.sh")
    ok = bool(
        re.search(r"confirm|CONFIRM|--force|FORCE|read -p|interactive", restore, re.I)
    )
    return FalsifyResult(
        dod_item_id=row.get("dod_item_id") or "",
        text=(row.get("texto") or "")[:120],
        ok=ok,
        reason="restore-database.sh has confirm/force" if ok else "restore lacks confirm/force",
        probe="scripts/restore-database.sh flags",
    )


def falsify_process_evidence_triad(root: Path, row: dict[str, Any]) -> FalsifyResult:
    """Process principles need real code paths, not narrative."""
    camp = _read(root / "squads" / "extra-dod-roi" / "scripts" / "campaign.py")
    text = (row.get("texto") or "").lower()
    if "evidência verificável" in text or "evidencia verificavel" in text:
        ok = "validate_evidence_quality" in camp and "evidence required" in camp
        return FalsifyResult(
            row.get("dod_item_id") or "",
            (row.get("texto") or "")[:120],
            ok,
            "validate_evidence_quality present" if ok else "no evidence quality gate",
            "campaign.py validate_evidence_quality",
        )
    if "sem execução comprovada" in text or "codigo existente" in text or "código existente" in text:
        ok = "code-only" in camp.lower() or "code_only" in camp
        return FalsifyResult(
            row.get("dod_item_id") or "",
            (row.get("texto") or "")[:120],
            ok,
            "code-only rejection in campaign.py" if ok else "no code-only rejection path",
            "campaign.py code-only markers",
        )
    if "unitário" in text or "unitario" in text or "ponta a ponta" in text:
        ok = "e2e_claim" in camp or "unit_only" in camp
        return FalsifyResult(
            row.get("dod_item_id") or "",
            (row.get("texto") or "")[:120],
            ok,
            "unit-as-e2e rejection present" if ok else "no unit-as-e2e rejection",
            "campaign.py unit vs e2e",
        )
    return FalsifyResult(
        row.get("dod_item_id") or "",
        (row.get("texto") or "")[:120],
        True,
        "not process triad",
        "n/a",
    )


def falsify_theater_evidence(root: Path, row: dict[str, Any]) -> FalsifyResult:
    """Generic: PASS requires non-empty command and exit_code 0; refuse inventory theater."""
    ev = (row.get("evidência") or row.get("evidence") or "").lower()
    cmd = (row.get("comando") or row.get("command") or "").strip()
    try:
        ex = int(row.get("exit_code"))
    except (TypeError, ValueError):
        ex = -1
    theater = any(
        x in ev
        for x in (
            "file inventory",
            "code exists",
            "module exists only",
            "truth auditor + campaign refuse",
            "campaign guards refuse code-only",
        )
    )
    ok = bool(cmd) and ex == 0 and not theater
    return FalsifyResult(
        row.get("dod_item_id") or "",
        (row.get("texto") or "")[:120],
        ok,
        "command+exit0 and non-theater evidence" if ok else f"cmd={bool(cmd)} exit={ex} theater={theater}",
        "row evidence hygiene",
    )


def classify_and_falsify(root: Path, row: dict[str, Any]) -> list[FalsifyResult]:
    text = (row.get("texto") or row.get("text") or "").lower()
    results: list[FalsifyResult] = [falsify_theater_evidence(root, row)]
    if "urls de fontes" in text or "url" in text and "centraliz" in text:
        results.append(falsify_url_centralization(root, row))
    if "win rate" in text or "win_rate" in text:
        results.append(falsify_win_rate(root, row))
    if "probabilidade" in text or ("score" in text and "calibr" in text):
        results.append(falsify_score_not_probability(root, row))
    if "except exception" in text or "except exception: pass" in text:
        results.append(falsify_except_exception_pass(root, row))
    if "run_id" in text and "cada execução" in text:
        results.append(falsify_universal_run_id(root, row))
    if "destrutiv" in text and ("confirma" in text or "flag" in text):
        results.append(falsify_destructive_confirm(root, row))
    if any(
        k in text
        for k in (
            "evidência verificável",
            "evidencia verificavel",
            "sem execução comprovada",
            "sem execucao comprovada",
            "teste unitário isolado",
            "teste unitario isolado",
            "ponta a ponta",
        )
    ):
        results.append(falsify_process_evidence_triad(root, row))
    return results


def uncheck_dod_item(root: Path, item_id: str, section_hint: str, text_hint: str) -> bool:
    """Uncheck matching [x] line by stable id."""
    dod = root / "DOD.md"
    lines = dod.read_text(encoding="utf-8").splitlines()
    section = ""
    out: list[str] = []
    changed = False
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            section = m.group(2).strip()
            out.append(line)
            continue
        m = re.match(r"^(\s*)-\s+\[([xX])\]\s+(.*)$", line)
        if not m:
            out.append(line)
            continue
        indent, body = m.group(1), m.group(3).strip()
        sid = stable_dod_id(section, body)
        if sid == item_id or (
            normalize_text(body) == normalize_text(text_hint)
            and (not section_hint or section_hint[:20] in section)
        ):
            core = re.sub(r"\s+Evid[eê]ncia:.*$", "", body, flags=re.I).strip()
            out.append(f"{indent}- [ ] {core}")
            changed = True
            continue
        out.append(line)
    if changed:
        dod.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


# Claims that must never remain proven:true after audit (hard denylist)
HARD_DENY_PROVEN = {
    normalize_text("Scripts destrutivos exigem confirmação ou flag explícita."),
    normalize_text("URLs de fontes são centralizadas."),
    normalize_text("Win rate não é calculado sem propostas enviadas."),
    normalize_text("Score não é chamado de probabilidade sem calibração."),
    normalize_text("Cada item só é marcado como concluído quando existir evidência verificável."),
    normalize_text("Código existente sem execução comprovada não é considerado concluído."),
    normalize_text("Teste unitário isolado não substitui execução ponta a ponta."),
    normalize_text("Não existem `except Exception: pass`."),
    normalize_text("Cada execução possui `run_id`."),
    normalize_text("Cada registro crítico possui provenance."),
}


def rewrite_batch_packs(root: Path, purged_norms: set[str]) -> list[str]:
    """Ensure proof packs do not mark purged/denied claims as proven:true."""
    notes: list[str] = []
    deny = set(purged_norms) | HARD_DENY_PROVEN
    batch_dirs = list((root / "docs" / "ops").glob("session-2026-07-18-campaign-batch*"))
    for d in batch_dirs:
        pm = d / "proof-matrix.json"
        if not pm.is_file():
            continue
        data = json.loads(pm.read_text(encoding="utf-8"))
        changed = False
        for key in ("proven", "all"):
            for item in data.get(key) or []:
                if not isinstance(item, dict):
                    continue
                n = normalize_text(item.get("text") or "")
                if n in deny and item.get("proven"):
                    item["proven"] = False
                    item["notes"] = (
                        (item.get("notes") or "")
                        + " | REVOKED by audit-matrix falsifier"
                    ).strip(" |")
                    changed = True
        if changed or True:
            # always normalize proven list against deny
            if "proven" in data:
                before = len(data["proven"])
                data["proven"] = [
                    x
                    for x in data["proven"]
                    if x.get("proven")
                    and normalize_text(x.get("text") or "") not in deny
                ]
                if len(data["proven"]) != before:
                    changed = True
            data["audit_matrix_rewritten_at"] = utcnow()
            pm.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            if changed:
                notes.append(f"rewrote {pm}")
        fl = d / "flipped.json"
        if fl.is_file():
            flips = json.loads(fl.read_text(encoding="utf-8"))
            if isinstance(flips, list):
                new_flips = [
                    x
                    for x in flips
                    if normalize_text(x.get("text") or "") not in deny
                ]
                if len(new_flips) != len(flips):
                    fl.write_text(
                        json.dumps(new_flips, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    notes.append(f"rewrote {fl}")
    # batch2 authorized_flips alignment
    qa2 = (
        root
        / "squads"
        / "extra-dod-roi"
        / "state"
        / "qa"
        / "cyc-2026-07-18-batch2-qa.json"
    )
    if qa2.is_file():
        data = json.loads(qa2.read_text(encoding="utf-8"))
        # authorized_flips = only item texts with verdict PASS
        pass_texts = [
            (i.get("text") or i.get("dod_text") or "")
            for i in (data.get("items") or [])
            if i.get("verdict") == "PASS"
        ]
        data["authorized_flips"] = pass_texts
        data["authorized_flips_note"] = (
            "Aligned to item-level PASS only; CONCERNS/FAIL excluded"
        )
        qa2.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        notes.append(f"aligned authorized_flips in {qa2.name}")
    return notes


def audit_matrix(root: Path, *, write: bool = False) -> dict[str, Any]:
    ledger = load_ledger(root)
    if not ledger:
        return {"ok": False, "error": "ledger missing", "exit": 2}
    matrix = list(ledger.get("matrix") or [])
    failures: list[dict[str, Any]] = []
    passes = 0
    for row in matrix:
        if (row.get("qa_verdict") or "").upper() != "PASS":
            failures.append(
                {
                    "dod_item_id": row.get("dod_item_id"),
                    "reason": f"qa_verdict={row.get('qa_verdict')} not PASS",
                    "probe": "verdict",
                }
            )
            continue
        results = classify_and_falsify(root, row)
        row_ok = all(r.ok for r in results)
        if row_ok:
            passes += 1
        else:
            for r in results:
                if not r.ok:
                    failures.append(asdict(r))
    purged_ids: list[str] = []
    pack_notes: list[str] = []
    if write and failures:
        # unique ids to purge
        to_purge = {f.get("dod_item_id") for f in failures if f.get("dod_item_id")}
        purged_norms: set[str] = set()
        by_id = {r.get("dod_item_id"): r for r in matrix}
        new_matrix = []
        for row in matrix:
            did = row.get("dod_item_id")
            if did in to_purge:
                uncheck_dod_item(
                    root,
                    did or "",
                    row.get("seção") or "",
                    row.get("texto") or "",
                )
                purged_ids.append(did or "")
                purged_norms.add(normalize_text(row.get("texto") or ""))
                ledger.setdefault("exclusions", []).append(
                    {
                        "at": utcnow(),
                        "dod_item_id": did,
                        "text": (row.get("texto") or "")[:120],
                        "reason": "audit-matrix falsifier failed",
                        "details": [f for f in failures if f.get("dod_item_id") == did],
                    }
                )
            else:
                new_matrix.append(row)
        ledger["matrix"] = new_matrix
        ledger["accepted"] = [
            a
            for a in (ledger.get("accepted") or [])
            if (a.get("dod_item_id") if isinstance(a, dict) else a) not in to_purge
        ]
        ledger["counts"]["accepted"] = len(new_matrix)
        pack_notes = rewrite_batch_packs(root, purged_norms)
        # SUCCESS gate
        baseline_open = set((ledger.get("baseline") or {}).get("open_ids") or [])
        items = parse_items((root / "DOD.md").read_text(encoding="utf-8"))
        live = reconstruct_accepted_from_diff(baseline_open, items)
        live_pass_ids = {r["dod_item_id"] for r in new_matrix}
        # consistency: matrix must match live checked ∩ baseline open for counted set
        # (live may have unchecked after purge)
        if ledger["counts"]["accepted"] >= int(
            ledger.get("target_dod_items") or DEFAULT_TARGET
        ):
            # only SUCCESS if re-audit would pass — mark pending re-audit
            ledger["status"] = "IN_PROGRESS"
            ledger["post_audit_note"] = (
                "Purged falsified rows; re-run audit-matrix without --write to confirm SUCCESS"
            )
        else:
            ledger["status"] = "IN_PROGRESS"
        ledger["updated_at"] = utcnow()
        save_ledger(root, ledger)

    # final consistency checks on current ledger state
    ledger = load_ledger(root) or ledger
    matrix = list(ledger.get("matrix") or [])
    accepted = ledger.get("accepted") or []
    mids = [r.get("dod_item_id") for r in matrix]
    aids = [
        (a.get("dod_item_id") if isinstance(a, dict) else a) for a in accepted
    ]
    consistency_ok = (
        len(mids) == len(set(mids))
        and set(mids) == set(aids)
        and all((r.get("qa_verdict") or "").upper() == "PASS" for r in matrix)
    )
    # If write mode purged, re-run falsifiers on remaining without write
    remaining_failures: list[dict[str, Any]] = []
    if not write:
        for row in matrix:
            for r in classify_and_falsify(root, row):
                if not r.ok:
                    remaining_failures.append(asdict(r))
    else:
        # after purge, verify remaining
        for row in matrix:
            for r in classify_and_falsify(root, row):
                if not r.ok:
                    remaining_failures.append(asdict(r))

    ok = consistency_ok and len(remaining_failures) == 0 and len(matrix) >= 0
    # SUCCESS only when count>=target AND no remaining failures
    target = int(ledger.get("target_dod_items") or DEFAULT_TARGET)
    if write and ok and len(matrix) >= target:
        ledger["status"] = "SUCCESS"
        ledger["audit_matrix_pass_at"] = utcnow()
        save_ledger(root, ledger)
    elif write and (not ok or len(matrix) < target):
        ledger["status"] = "IN_PROGRESS"
        save_ledger(root, ledger)

    return {
        "ok": ok and len(matrix) >= target if not write else (ok and len(matrix) >= target),
        "pass_rows_checked": passes if not write else len(matrix),
        "matrix_count": len(matrix),
        "target": target,
        "failures": remaining_failures if not write else failures,
        "remaining_failures": remaining_failures,
        "purged_ids": purged_ids,
        "pack_notes": pack_notes,
        "consistency_ok": consistency_ok,
        "status": (load_ledger(root) or {}).get("status"),
        "exit": 0 if (len(remaining_failures) == 0 and consistency_ok) else 1,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="audit-matrix")
    p.add_argument("--repo", default=None)
    p.add_argument("--write", action="store_true", help="Uncheck failures and rewrite packs")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.repo).resolve() if args.repo else repo_root_from()
    result = audit_matrix(root, write=args.write)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"matrix_count={result.get('matrix_count')} target={result.get('target')}")
        print(f"consistency_ok={result.get('consistency_ok')} status={result.get('status')}")
        print(f"purged={result.get('purged_ids')}")
        fails = result.get("remaining_failures") or result.get("failures") or []
        print(f"failures={len(fails)}")
        for f in fails[:20]:
            print(
                f" - {f.get('dod_item_id')}: {f.get('reason', f.get('text', ''))[:100]}"
            )
        for n in result.get("pack_notes") or []:
            print(f" pack: {n}")
    return int(result.get("exit") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
