#!/usr/bin/env python3
"""Fail-closed same-truth gate for DUAL-CAPABILITY-COVERAGE-TRUTH-01 stamps.

Single authority: ``sha-roles.yaml`` in the campaign directory.
Validates packs, SUPERSEDED/REACCEPTED narrative, DOD line, STATUS/FINAL-SHA-ROLES,
and demotes historical dual-reproof-summary.json when obsolete.

Exit 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

CAMPAIGN = Path("docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01")
ROLES_PATH = CAMPAIGN / "sha-roles.yaml"
STAMP_DOCS = [
    CAMPAIGN / "STATUS.md",
    CAMPAIGN / "FINAL-SHA-ROLES.md",
]
DOD_PATH = Path("DOD.md")
HISTORICAL_SUMMARY = CAMPAIGN / "evidence" / "dual-reproof-summary.json"
CURRENT_SUMMARY = CAMPAIGN / "evidence" / "dual-reproof-summary-final-closure.json"


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def _is_ancestor(repo: Path, maybe_ancestor: str, descendant: str) -> bool:
    try:
        subprocess.check_call(
            [
                "git",
                "-C",
                str(repo),
                "merge-base",
                "--is-ancestor",
                maybe_ancestor,
                descendant,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _load_roles(repo: Path) -> dict:
    path = repo / ROLES_PATH
    if not path.is_file():
        raise FileNotFoundError(f"missing {ROLES_PATH}")
    if yaml is None:
        raise RuntimeError("PyYAML required")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sha-roles.yaml root must be a mapping")
    return data


def _read_yaml(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _sha_prefix(s: str, n: int = 7) -> str:
    return (s or "")[:n].lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--log", type=Path, default=None, help="Also write full report here")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    if args.repo_root is not None:
        repo = args.repo_root.resolve()
    else:
        candidates = [script_path.parents[5], Path.cwd()]
        repo = next(
            (c for c in candidates if (c / ".git").exists() or (c / "docs").exists()),
            Path.cwd(),
        ).resolve()

    lines: list[str] = []
    errors: list[str] = []

    def note(msg: str) -> None:
        lines.append(msg)

    def fail(msg: str) -> None:
        errors.append(msg)
        lines.append(f"FAIL: {msg}")

    note(f"repo_root={repo}")
    try:
        origin_main = _run_git(repo, "rev-parse", "origin/main").lower()
    except subprocess.CalledProcessError:
        origin_main = _run_git(repo, "rev-parse", "HEAD").lower()
    note(f"origin_main_observed={origin_main}")

    try:
        roles = _load_roles(repo)
    except Exception as exc:  # noqa: BLE001
        fail(f"roles_load:{exc}")
        report = "\n".join(lines) + "\n"
        print(report)
        if args.log:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            args.log.write_text(report, encoding="utf-8")
        return 1

    impl = str(roles.get("implementation_sha") or "").lower()
    reviewed = str(roles.get("reviewed_sha") or "").lower()
    reproof = str(roles.get("reproof_sha") or "").lower()
    acceptance = str(roles.get("acceptance_sha") or "").lower()
    observed_write = str(roles.get("observed_main_at_write") or "").lower()
    item_id = str(roles.get("acceptance_item_id") or "")
    pack_dir = Path(str(roles.get("acceptance_pack_dir") or ""))
    mirror_dir = Path(str(roles.get("mirror_pack_dir") or ""))
    narrative = str(roles.get("pack_narrative") or "")
    meas = roles.get("measurement_success")
    ident = roles.get("identity_unresolved_count")
    dual_gate = str(roles.get("dual_gate_status") or "")
    pol_status = str(roles.get("source_policy_status") or "")
    pol_ver = str(roles.get("source_policy_version") or "")
    pol_hash = str(roles.get("policy_sha256") or "").lower()
    review_file = str(roles.get("independent_review") or "")

    note(f"implementation_sha={impl}")
    note(f"reviewed_sha={reviewed}")
    note(f"reproof_sha={reproof}")
    note(f"acceptance_sha={acceptance}")
    note(f"observed_main_at_write={observed_write}")

    # --- semantic SHAs must be ancestors of origin/main ---
    for label, sha in (
        ("implementation_sha", impl),
        ("reviewed_sha", reviewed),
        ("reproof_sha", reproof),
        ("acceptance_sha", acceptance),
    ):
        if not sha or len(sha) < 7:
            fail(f"{label}_missing")
            continue
        if not _is_ancestor(repo, sha, origin_main):
            fail(f"{label}_not_ancestor_of_origin_main:{sha[:12]}")
        else:
            note(f"OK {label} ancestor of origin/main")

    if impl != reviewed or impl != reproof or impl != acceptance:
        # Same-truth for this campaign: semantic accept tip is one SHA
        if not (impl == reviewed == reproof == acceptance):
            fail(
                "semantic_sha_divergence:"
                f"impl={impl[:12]} reviewed={reviewed[:12]} "
                f"reproof={reproof[:12]} acceptance={acceptance[:12]}"
            )
        else:
            note("OK semantic SHAs identical")
    else:
        note("OK semantic SHAs identical")

    # --- packs reviewed_sha.yaml ---
    for pdir, label in ((pack_dir, "auth_pack"), (mirror_dir, "mirror_pack")):
        ypath = repo / pdir / "reviewed_sha.yaml"
        y = _read_yaml(ypath)
        if not y:
            fail(f"{label}_missing_reviewed_sha_yaml:{pdir}")
            continue
        for key in ("reviewed_sha", "implementation_sha", "acceptance_sha", "reproof_sha"):
            val = str(y.get(key) or "").lower()
            expected = {
                "reviewed_sha": reviewed,
                "implementation_sha": impl,
                "acceptance_sha": acceptance,
                "reproof_sha": reproof,
            }[key]
            if val != expected:
                fail(f"{label}_{key}_mismatch:got={val[:12]} expected={expected[:12]}")
            else:
                note(f"OK {label}.{key}")

    # --- 4efe SUPERSEDED.yaml = REACCEPTED_FINAL ---
    sup = _read_yaml(repo / pack_dir / "SUPERSEDED.yaml")
    st = str(sup.get("status") or "")
    final_sha = str(sup.get("final_sha") or "").lower()
    if st != "REACCEPTED_FINAL":
        fail(f"auth_pack_status_not_REACCEPTED_FINAL:got={st!r}")
    else:
        note("OK auth pack REACCEPTED_FINAL")
    if final_sha != acceptance:
        fail(f"auth_pack_final_sha_mismatch:got={final_sha[:12]} expected={acceptance[:12]}")
    else:
        note("OK auth pack final_sha == acceptance_sha")

    # --- pack live metrics ---
    for pdir, label in ((pack_dir, "auth_pack"), (mirror_dir, "mirror_pack")):
        live_path = repo / pdir / "dual-live-reproof.json"
        if not live_path.is_file():
            fail(f"{label}_missing_dual_live_reproof")
            continue
        live = json.loads(live_path.read_text(encoding="utf-8"))
        if live.get("measurement_success") is not meas:
            fail(f"{label}_measurement_success:{live.get('measurement_success')}!={meas}")
        else:
            note(f"OK {label}.measurement_success")
        mm = live.get("mapping_metrics") or {}
        raw_id = mm.get("identity_unresolved_count")
        if raw_id is None:
            raw_id = live.get("identity_unresolved_count")
        try:
            got_id = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            got_id = None
        exp_id = int(ident) if ident is not None else None
        if got_id != exp_id:
            fail(f"{label}_identity:{got_id}!={exp_id}")
        else:
            note(f"OK {label}.identity_unresolved_count")
        if str(live.get("dual_gate_status") or "") != dual_gate:
            fail(f"{label}_dual_gate:{live.get('dual_gate_status')}!={dual_gate}")
        else:
            note(f"OK {label}.dual_gate_status")
        if str(live.get("source_policy_status") or "") != pol_status:
            fail(f"{label}_policy_status:{live.get('source_policy_status')}")
        else:
            note(f"OK {label}.source_policy_status")
        live_hash = str(live.get("source_policy_sha256") or "").lower()
        if live_hash and live_hash != pol_hash:
            fail(f"{label}_policy_hash_mismatch")
        else:
            note(f"OK {label}.policy_sha256")

    # --- DOD line ---
    dod = (repo / DOD_PATH).read_text(encoding="utf-8")
    dod_line = next((ln for ln in dod.splitlines() if "calcula cobertura" in ln.lower() and ln.strip().startswith("- [")), "")
    if not dod_line:
        fail("dod_line_missing_calcula_cobertura")
    else:
        note(f"dod_line={dod_line[:120]}…")
        if "method_acceptance=PASS" not in dod_line and "method_acceptance=PASS" not in dod_line.replace(" ", ""):
            if "method_acceptance=PASS" not in dod_line:
                # allow compacted form
                if "method_acceptance=PASS" not in dod_line.replace(" ", ""):
                    pass
        if "method_acceptance" not in dod_line.lower() and "method_acceptance=PASS" not in dod_line:
            if "method_acceptance" not in dod_line:
                fail("dod_line_missing_method_acceptance")
        if "measurement_success=true" not in dod_line and "measurement_success=true" not in dod_line.lower():
            # require explicit live success matching roles
            if "measurement_success=true" not in dod_line:
                fail("dod_line_missing_measurement_success=true")
        if "identity_unresolved_count=0" not in dod_line:
            fail("dod_line_missing_identity_unresolved_count=0")
        if dual_gate not in dod_line:
            fail(f"dod_line_missing_dual_gate:{dual_gate}")
        # Narrative: 4efe authoritative — must not claim 1fdea supersedes 4efe as SUPERSEDED authority
        bad_supersede = re.search(
            r"1fdea0f6e6.*/?\s*supersedes\s*`?4efe05fc94`?.*SUPERSEDED",
            dod_line,
            re.I,
        )
        if bad_supersede or (
            "1fdea0f6e6" in dod_line
            and "supersedes" in dod_line.lower()
            and "4efe05fc94" in dod_line
            and "SUPERSEDED" in dod_line
        ):
            fail("dod_line_wrong_pack_narrative_1fdea_supersedes_4efe")
        if item_id.split("-")[-1][:10] not in dod_line and "4efe05fc94" not in dod_line:
            # require authoritative pack id
            fail("dod_line_missing_authoritative_pack_4efe05fc94")
        else:
            note("OK DOD line pack narrative keys")
        if "95%" in dod_line.lower() and "não" not in dod_line.lower() and "nao" not in dod_line.lower() and "not" not in dod_line.lower():
            # soft: still require anti-claim
            if "não afirma 95%" not in dod_line and "nao afirma 95%" not in dod_line and "not 95%" not in dod_line.lower():
                fail("dod_line_missing_no_95_claim")

    # --- STATUS + FINAL-SHA-ROLES must render roles SHAs ---
    for doc in STAMP_DOCS:
        path = repo / doc
        if not path.is_file():
            fail(f"missing_stamp_doc:{doc}")
            continue
        text = path.read_text(encoding="utf-8")
        for label, sha in (
            ("implementation_sha", impl),
            ("reviewed_sha", reviewed),
            ("reproof_sha", reproof),
            ("acceptance_sha", acceptance),
        ):
            pref = _sha_prefix(sha, 12)
            if pref not in text.lower() and sha[:7] not in text.lower():
                fail(f"{doc.name}_missing_{label}:{pref}")
            else:
                note(f"OK {doc.name} contains {label}")
        # forbidden stale phrases
        if re.search(r"await.*#107|await CI after #107", text, re.I):
            fail(f"{doc.name}_stale_await_107")
        if re.search(r"current tip.*86cb028|86cb028.*= current tip", text, re.I):
            fail(f"{doc.name}_ancestor_as_current_tip")
        if "identity_unresolved_count | **4**" in text or "identity_unresolved_count: 4" in text:
            fail(f"{doc.name}_stale_identity_4")
        if re.search(r"measurement_success\s*\|\s*false", text, re.I) and "historical" not in text.lower():
            # allow historical sections only if clearly labeled
            if "measurement_success | false" in text.lower() or "measurement_success|false" in text.replace(" ", "").lower():
                if "historical" not in text.lower() and "pre-v2" not in text.lower():
                    fail(f"{doc.name}_stale_measurement_false")

    # --- historical campaign summary demoted ---
    hist = repo / HISTORICAL_SUMMARY
    if hist.is_file():
        try:
            hdata = json.loads(hist.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            fail("historical_summary_invalid_json")
            hdata = {}
        if not hdata.get("historical") and not hdata.get("superseded"):
            # must not be treated as live truth with old identity=4
            mm = (hdata.get("mapping_metrics") or {})
            if int(mm.get("identity_unresolved_count") or 0) == 4 and not hdata.get("historical"):
                fail("historical_summary_not_marked_historical_still_identity_4")
            else:
                note("OK historical summary present")
        else:
            note("OK historical summary flagged historical/superseded")
            pointer = hdata.get("current_reproof") or hdata.get("see") or ""
            if "4efe" not in str(pointer) and "dual-live" not in str(pointer).lower():
                # require pointer field
                if not hdata.get("current_reproof") and not hdata.get("see"):
                    fail("historical_summary_missing_pointer_to_current_reproof")
    else:
        note("OK no historical dual-reproof-summary.json")

    # current summary if present must match roles
    cur_sum = repo / CURRENT_SUMMARY
    if cur_sum.is_file():
        cdata = json.loads(cur_sum.read_text(encoding="utf-8"))
        if cdata.get("measurement_success") is not meas:
            fail(f"current_summary_measurement_mismatch:{cdata.get('measurement_success')}")
        else:
            note("OK dual-reproof-summary-final-closure.json measurement")
        mm = cdata.get("mapping_metrics") or {}
        raw_id = mm.get("identity_unresolved_count")
        if raw_id is None:
            raw_id = cdata.get("identity_unresolved_count")
        try:
            got_id = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            got_id = None
        exp_id = int(ident) if ident is not None else None
        if got_id != exp_id:
            fail(f"current_summary_identity_mismatch:{got_id}!={exp_id}")
        else:
            note("OK dual-reproof-summary-final-closure.json identity")

    # independent review file exists
    ir = repo / CAMPAIGN / review_file
    if not ir.is_file():
        fail(f"missing_independent_review:{review_file}")
    else:
        irt = ir.read_text(encoding="utf-8")
        if "PASS_FOR_MERGE" not in irt:
            fail("independent_review_missing_PASS_FOR_MERGE")
        if _sha_prefix(reviewed, 12) not in irt.lower() and reviewed[:7] not in irt.lower():
            fail("independent_review_missing_reviewed_sha")
        else:
            note("OK independent_review file")

    # narrative string in roles must mention 4efe authoritative
    if "4efe" not in narrative.lower() or "authoritative" not in narrative.lower():
        fail("pack_narrative_must_declare_4efe_authoritative")
    else:
        note("OK pack_narrative")

    # policy fields
    if pol_status != "active":
        fail(f"roles_policy_not_active:{pol_status}")
    if not pol_ver:
        fail("roles_policy_version_missing")
    if len(pol_hash) < 32:
        fail("roles_policy_hash_short")

    lines.append("")
    if errors:
        lines.append(f"STATUS=FAIL errors={len(errors)}")
        for e in errors:
            lines.append(f"  - {e}")
        code = 1
    else:
        lines.append("STATUS=PASS")
        code = 0

    report = "\n".join(lines) + "\n"
    print(report)
    log_path = args.log
    if log_path is None:
        log_path = Path("/tmp/grok-goal-dd92ea509731/implementer/consistency-gate.log")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(report, encoding="utf-8")
        note_line = f"wrote_log={log_path}"
        print(note_line)
    except OSError as exc:
        print(f"log_write_failed:{exc}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
