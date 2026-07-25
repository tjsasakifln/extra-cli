"""Case-level verification: hashes, locators, citation integrity, reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.edital_case.extract import load_extraction_blocks
from scripts.edital_case.store import read_json, sha256_file, utc_now


def _excerpt_in_blocks(excerpt: str | None, blocks: list[dict[str, Any]]) -> bool:
    if not excerpt:
        return False
    # normalize whitespace
    needle = " ".join(excerpt.split())
    if len(needle) < 12:
        # short excerpts: require exact line containment
        for b in blocks:
            if needle in " ".join((b.get("text") or "").split()):
                return True
        return False
    # use a window of the excerpt
    core = needle[:80]
    for b in blocks:
        hay = " ".join((b.get("text") or "").split())
        if core in hay:
            return True
    return False


def verify_case(case_dir: Path) -> dict[str, Any]:
    case_dir = Path(case_dir)
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    def ok(name: str, detail: str = "") -> None:
        checks.append({"name": name, "status": "PASS", "detail": detail})

    def fail(name: str, detail: str) -> None:
        checks.append({"name": name, "status": "FAIL", "detail": detail})
        issues.append({"name": name, "detail": detail})

    manifest_path = case_dir / "case-manifest.json"
    if not manifest_path.exists():
        fail("manifest", "case-manifest.json missing")
        return {
            "ok": False,
            "generated_at": utc_now(),
            "checks": checks,
            "issues": issues,
        }
    manifest = read_json(manifest_path)
    for key in (
        "production_touched",
        "soak_touched",
        "vps_accessed",
        "database_used",
    ):
        if manifest.get(key) is not False:
            fail("safety_flags", f"{key} must be false, got {manifest.get(key)!r}")
        else:
            ok("safety_flags." + key, "false")

    inv_path = case_dir / "inventory.json"
    if not inv_path.exists():
        fail("inventory", "missing inventory.json")
        documents = []
    else:
        inventory = read_json(inv_path)
        documents = inventory.get("documents") or []
        ok("inventory", f"{len(documents)} documents")

    # object immutability
    for d in documents:
        sha = d.get("sha256")
        if not sha:
            fail("object_hash", f"{d.get('document_id')} missing sha256")
            continue
        obj = case_dir / "objects" / sha
        if not obj.is_file():
            fail("object_present", f"missing object {sha}")
            continue
        actual = sha256_file(obj)
        if actual != sha:
            fail("object_immutable", f"hash mismatch for {sha}")
        else:
            ok("object_immutable", sha[:12])

    # citation audit on findings + checklist evidence
    fabricated = 0
    checked = 0
    checklist = (
        read_json(case_dir / "checklist.json")
        if (case_dir / "checklist.json").exists()
        else {}
    )
    findings = (
        read_json(case_dir / "findings.json")
        if (case_dir / "findings.json").exists()
        else {}
    )

    def audit_evidence(ev: dict[str, Any], context: str) -> None:
        nonlocal fabricated, checked
        excerpt = ev.get("excerpt")
        doc_id = ev.get("document_id")
        if not excerpt or not doc_id:
            return
        checked += 1
        blocks = load_extraction_blocks(case_dir, doc_id)
        if not blocks:
            fabricated += 1
            fail("citation", f"{context}: no extraction for {doc_id}")
            return
        # page locator consistency
        page = ev.get("page")
        locator = ev.get("locator") or ""
        if page is not None and locator.startswith("page:"):
            try:
                loc_page = int(locator.split(":", 1)[1])
                if loc_page != page:
                    fabricated += 1
                    fail("citation_page", f"{context}: page {page} != {locator}")
                    return
            except ValueError:
                pass
        if not _excerpt_in_blocks(str(excerpt), blocks):
            fabricated += 1
            fail("citation_excerpt", f"{context}: excerpt not found in extraction")
        else:
            ok("citation", context)

    for item in checklist.get("items") or []:
        audit_evidence(item.get("evidence") or {}, f"checklist.{item.get('id')}")
    for f in findings.get("findings") or []:
        if f.get("severity") in {"critical", "high"}:
            audit_evidence(f.get("evidence") or {}, f"finding.{f.get('finding_id')}")

    # sample additional findings
    for f in (findings.get("findings") or [])[:40]:
        audit_evidence(f.get("evidence") or {}, f"finding-sample.{f.get('finding_id')}")

    if fabricated:
        fail("citation_audit", f"{fabricated} fabricated/invalid citations of {checked}")
    else:
        ok("citation_audit", f"0 fabricated of {checked} checked")

    # recommendation fail-closed
    rec_path = case_dir / "recommendation.json"
    if rec_path.exists():
        rec = read_json(rec_path)
        if rec.get("recommendation") == "GO":
            # verify strict conditions still hold in artifact
            critical_bad = [
                i
                for i in (checklist.get("items") or [])
                if i.get("critical")
                and i.get("status")
                not in {"SATISFIED", "NOT_APPLICABLE"}
            ]
            if critical_bad:
                fail("go_gate", "GO with critical items not satisfied")
            else:
                ok("go_gate", "GO conditions structurally ok")
        else:
            ok("go_gate", f"recommendation={rec.get('recommendation')}")
    else:
        fail("recommendation", "missing recommendation.json")

    # reports reconciliation
    recon_path = case_dir / "reports" / "reconciliation.json"
    if recon_path.exists():
        recon = read_json(recon_path)
        if not recon.get("ok"):
            fail("report_reconciliation", str(recon.get("issues")))
        else:
            ok("report_reconciliation", "ok")
    else:
        fail("report_reconciliation", "missing reports/reconciliation.json")

    # required artifacts
    for req in (
        "checklist.json",
        "timeline.json",
        "findings.json",
        "missing-documents.json",
        "evidence-matrix.json",
        "reports/executive-summary.md",
        "reports/triage-report.html",
        "reports/triage-workbook.xlsx",
        "reports/triage-report.pdf",
    ):
        if not (case_dir / req).exists():
            fail("artifact", f"missing {req}")
        else:
            ok("artifact", req)

    return {
        "ok": len(issues) == 0,
        "generated_at": utc_now(),
        "checks": checks,
        "issues": issues,
        "citation_checked": checked,
        "citation_fabricated": fabricated,
        "pass_count": sum(1 for c in checks if c["status"] == "PASS"),
        "fail_count": sum(1 for c in checks if c["status"] == "FAIL"),
    }
