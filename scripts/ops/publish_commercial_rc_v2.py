#!/usr/bin/env python3
"""Publish client-ready-frozen-rc-v2 from a generated pack (isolated DSN only).

Steps:
  1) Run live_consulting_pack (sector-filtered A–E + executive PDF/XLSX)
  2) Write historical CHANGES_REQUESTED for RC v1 (never overwrite silently)
  3) Write user-acceptance.json PENDING_HUMAN for new run_id/product_rc_sha
  4) Reconcile checksums across pack files
  5) Assemble staging artifact client-ready-frozen-rc-v2

Never sets ACCEPTED. Never touches VPS/prod/soak.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ops.client_ready_consulting_cycle import (  # noqa: E402
    CAMPAIGN_ID,
    FROZEN_RC_ARTIFACT_NAME,
    FROZEN_RC_V1_ARTIFACT_NAME,
    FROZEN_RC_V1_PRODUCT_SHA,
    FROZEN_RC_V1_RUN_ID,
    FROZEN_RC_V1_STATUS,
    REQUIRED_IDENTITY_FILES,
    sha256_file,
)
from scripts.ops.live_consulting_pack import run_pack  # noqa: E402


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_checksums(pack_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(pack_dir.rglob("*")):
        if not p.is_file() or p.name == "checksums.json":
            continue
        if p.suffix.lower() not in {".json", ".csv", ".xlsx", ".pdf", ".md", ".html"}:
            continue
        rel = str(p.relative_to(pack_dir)).replace("\\", "/")
        out[rel] = sha256_file(p)
    return out


# Identity product set for stable non-git product_rc_sha (no tip chasing).
# Exclude pack-manifest so product_rc_sha can be written into it without circularity.
PRODUCT_RC_MEMBERS: tuple[str, ...] = (
    "executive-report.pdf",
    "consulting-pack.xlsx",
    "executive-summary.md",
    "deliverable_a.json",
    "deliverable_b.json",
    "deliverable_c.json",
    "deliverable_d.json",
    "deliverable_e.json",
)


def content_product_rc_sha(pack_dir: Path) -> str:
    """SHA-256 over sorted name+file digests of identity products (not a git commit)."""
    h = hashlib.sha256()
    h.update(b"extra-client-ready-frozen-rc-v2/product-rc/1.0\n")
    for name in PRODUCT_RC_MEMBERS:
        p = pack_dir / name
        if not p.is_file():
            raise FileNotFoundError(f"missing product member for content_rc_sha: {name}")
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_file(p).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def integrity_gate(pack_dir: Path, acceptance: dict[str, Any]) -> list[str]:
    """Fail-closed: real files vs checksums vs acceptance package_checksums."""
    divergences: list[str] = []
    ck_path = pack_dir / "checksums.json"
    if not ck_path.is_file():
        return ["missing_checksums_json"]
    checksums = json.loads(ck_path.read_text(encoding="utf-8"))
    # recompute
    actual = compute_checksums(pack_dir)
    for name, digest in actual.items():
        if name not in checksums:
            divergences.append(f"checksums_missing_key:{name}")
        elif checksums[name] != digest:
            divergences.append(f"checksums_mismatch:{name}")
    for name in REQUIRED_IDENTITY_FILES:
        # aliases
        candidates = [name]
        if name == "executive-report.pdf":
            candidates.append("extra_live_consulting_pack.pdf")
        if name == "consulting-pack.xlsx":
            candidates.append("extra_live_consulting_pack.xlsx")
        if name == "executive-summary.md":
            candidates.append("executive_summary.md")
        found = None
        for c in candidates:
            p = pack_dir / c
            if p.is_file():
                found = (c, sha256_file(p))
                break
        if not found:
            divergences.append(f"missing_identity_file:{name}")
            continue
        rel, digest = found
        acc_ck = (acceptance.get("package_checksums") or {}).get(name) or (
            acceptance.get("package_checksums") or {}
        ).get(rel)
        if acc_ck and acc_ck != digest:
            divergences.append(f"acceptance_mismatch:{name}")
        listed = checksums.get(name) or checksums.get(rel)
        if listed and listed != digest:
            divergences.append(f"checksums_identity_mismatch:{name}")
    return divergences


def write_v1_history(campaign_dir: Path) -> None:
    hist = {
        "artifact_name": FROZEN_RC_V1_ARTIFACT_NAME,
        "run_id": FROZEN_RC_V1_RUN_ID,
        "product_rc_sha": FROZEN_RC_V1_PRODUCT_SHA,
        "status": FROZEN_RC_V1_STATUS,
        "reason": (
            "Commercial rejection: non-engineering objects in E/C, organ ranking by "
            "general volume, invalid price panels, non-executive PDF/XLSX, hash drift"
        ),
        "recorded_at": utc_now(),
        "note": "Historical only — not silently overwritten by v2",
    }
    path = campaign_dir / "rc-v1-CHANGES_REQUESTED.json"
    path.write_text(json.dumps(hist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def assemble_v2(
    *,
    campaign_dir: Path,
    pack_dir: Path,
    staging_dir: Path,
    run_id: str,
    product_rc_sha: str,
    acceptance: dict[str, Any],
) -> dict[str, Any]:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    members = {
        "executive-report.pdf": [
            "executive-report.pdf",
            "extra_live_consulting_pack.pdf",
        ],
        "consulting-pack.xlsx": [
            "consulting-pack.xlsx",
            "extra_live_consulting_pack.xlsx",
        ],
        "executive-summary.md": [
            "executive-summary.md",
            "executive_summary.md",
        ],
        "pack-manifest.json": ["pack-manifest.json"],
        "checksums.json": ["checksums.json"],
        "deliverable_a.json": ["deliverable_a.json"],
        "deliverable_b.json": ["deliverable_b.json"],
        "deliverable_c.json": ["deliverable_c.json"],
        "deliverable_d.json": ["deliverable_d.json"],
        "deliverable_e.json": ["deliverable_e.json"],
    }
    # optional campaign-level reconciliation
    extra_members = {
        "package-reconciliation.json": campaign_dir / "package-reconciliation.json",
        "user-acceptance.json": campaign_dir / "user-acceptance.json",
        "rc-v1-CHANGES_REQUESTED.json": campaign_dir / "rc-v1-CHANGES_REQUESTED.json",
    }

    file_sha: dict[str, str] = {}
    sources: dict[str, str] = {}
    missing: list[str] = []
    for art, cands in members.items():
        data = None
        src = ""
        for c in cands:
            p = pack_dir / c
            if p.is_file():
                data = p.read_bytes()
                src = str(p)
                break
        if data is None:
            missing.append(art)
            continue
        dest = staging_dir / art
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        file_sha[art] = hashlib.sha256(data).hexdigest()
        sources[art] = src

    for art, p in extra_members.items():
        if p.is_file():
            dest = staging_dir / art
            dest.write_bytes(p.read_bytes())
            file_sha[art] = sha256_file(dest)
            sources[art] = str(p)

    if missing:
        return {"status": "FAIL", "error": "missing_members", "missing": missing}

    # Rewrite checksums.json to list ONLY files actually staged (no orphan refs)
    product_sha = {
        k: v
        for k, v in file_sha.items()
        if k
        not in {
            "checksums.json",
            "ARTIFACT-IDENTITY.json",
            "user-acceptance.json",
            "package-reconciliation.json",
            "rc-v1-CHANGES_REQUESTED.json",
        }
    }
    # Include deliverables + required identity products present on disk
    for p in staging_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(staging_dir)).replace("\\", "/")
        if rel in {
            "checksums.json",
            "ARTIFACT-IDENTITY.json",
            "ARTIFACT-IDENTITY.sha256",
            "user-acceptance.json",
            "package-reconciliation.json",
            "rc-v1-CHANGES_REQUESTED.json",
        }:
            continue
        product_sha[rel] = sha256_file(p)
    ck_path = staging_dir / "checksums.json"
    ck_path.write_text(
        json.dumps(product_sha, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    file_sha["checksums.json"] = sha256_file(ck_path)

    identity = {
        "run_id": run_id,
        "product_rc_sha": product_rc_sha,
        "file_sha256": {
            k: v for k, v in file_sha.items() if k != "ARTIFACT-IDENTITY.json"
        },
        "freeze_date": utc_now(),
        "production_touched": False,
        "soak_touched": False,
        "artifact_name": FROZEN_RC_ARTIFACT_NAME,
        "classification": "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW",
        "prior_rc": {
            "artifact_name": FROZEN_RC_V1_ARTIFACT_NAME,
            "run_id": FROZEN_RC_V1_RUN_ID,
            "product_rc_sha": FROZEN_RC_V1_PRODUCT_SHA,
            "status": FROZEN_RC_V1_STATUS,
        },
        "sources": sources,
        "self_hash_policy": "excluded — ARTIFACT-IDENTITY.sha256 sidecar",
        "assembled_at": utc_now(),
    }
    id_path = staging_dir / "ARTIFACT-IDENTITY.json"
    id_path.write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    id_sha = sha256_file(id_path)
    (staging_dir / "ARTIFACT-IDENTITY.sha256").write_text(
        f"{id_sha}  ARTIFACT-IDENTITY.json\n", encoding="utf-8"
    )
    id_loaded = json.loads(id_path.read_text(encoding="utf-8"))
    if "ARTIFACT-IDENTITY.json" in (id_loaded.get("file_sha256") or {}):
        return {"status": "FAIL", "error": "identity_self_hash_forbidden"}

    divergences: list[str] = []
    acc_ck = acceptance.get("package_checksums") or {}
    for name in REQUIRED_IDENTITY_FILES:
        if name not in file_sha:
            divergences.append(f"missing:{name}")
            continue
        if name in acc_ck and acc_ck[name] != file_sha[name]:
            divergences.append(f"mismatch:{name}")
    # checksums.json keys must exist as real staged files
    for name, digest in product_sha.items():
        p = staging_dir / name
        if not p.is_file():
            divergences.append(f"checksums_orphan:{name}")
        elif sha256_file(p) != digest:
            divergences.append(f"checksums_mismatch:{name}")
    if divergences:
        return {"status": "FAIL", "error": "integrity", "divergences": divergences}

    return {
        "status": "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW",
        "artifact_name": FROZEN_RC_ARTIFACT_NAME,
        "staging_dir": str(staging_dir),
        "run_id": run_id,
        "product_rc_sha": product_rc_sha,
        "file_sha256": file_sha,
        "identity_sha256": id_sha,
        "production_touched": False,
        "soak_touched": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Publish commercial RC v2")
    p.add_argument("--dsn", required=True)
    p.add_argument(
        "--out",
        default=str(
            _PROJECT_ROOT / "artifacts/campaigns" / CAMPAIGN_ID / "pack-v2"
        ),
    )
    p.add_argument(
        "--campaign-dir",
        default=str(_PROJECT_ROOT / "artifacts/campaigns" / CAMPAIGN_ID),
    )
    p.add_argument(
        "--staging",
        default=str(
            _PROJECT_ROOT
            / "artifacts/campaigns"
            / CAMPAIGN_ID
            / FROZEN_RC_ARTIFACT_NAME
        ),
    )
    p.add_argument("--uf", default="SC")
    p.add_argument("--export-limit", type=int, default=50)
    p.add_argument("--skip-pack", action="store_true", help="Reuse existing pack-v2")
    p.add_argument("--e-evidence", default=None)
    args = p.parse_args(argv)

    pack_dir = Path(args.out)
    campaign_dir = Path(args.campaign_dir)
    staging_dir = Path(args.staging)
    campaign_dir.mkdir(parents=True, exist_ok=True)

    write_v1_history(campaign_dir)

    if not args.skip_pack:
        e_path = Path(args.e_evidence) if args.e_evidence else None
        pack = run_pack(
            dsn=args.dsn,
            out_dir=pack_dir,
            uf=args.uf,
            export_limit=args.export_limit,
            e_evidence=e_path,
        )
    else:
        pm = pack_dir / "pack-manifest.json"
        pack = json.loads(pm.read_text(encoding="utf-8")) if pm.is_file() else {}

    run_id = str(pack.get("run_id") or "")
    if not run_id:
        print(json.dumps({"status": "FAIL", "error": "missing_run_id"}))
        return 2

    # Final aliases then content-addressed product_rc_sha (stable; not git HEAD tip)
    for src, dst in (
        ("extra_live_consulting_pack.pdf", "executive-report.pdf"),
        ("extra_live_consulting_pack.xlsx", "consulting-pack.xlsx"),
        ("executive_summary.md", "executive-summary.md"),
    ):
        sp, dp = pack_dir / src, pack_dir / dst
        if sp.is_file():
            dp.write_bytes(sp.read_bytes())

    product_rc_sha = content_product_rc_sha(pack_dir)
    pm_path = pack_dir / "pack-manifest.json"
    if pm_path.is_file():
        try:
            pm = json.loads(pm_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pm = {}
        pm["run_id"] = run_id
        pm["product_rc_sha"] = product_rc_sha
        pm["product_rc_scheme"] = "content_sha256_v1"
        # git_sha is provenance only — freeze identity is product_rc_sha
        pm["git_sha_provenance"] = pm.get("git_sha") or pack.get("git_sha")
        pm_path.write_text(json.dumps(pm, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    checksums = compute_checksums(pack_dir)
    (pack_dir / "checksums.json").write_text(
        json.dumps(checksums, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # package-reconciliation
    recon = {
        "status": "PASS",
        "run_id": run_id,
        "product_rc_sha": product_rc_sha,
        "artifact_name": FROZEN_RC_ARTIFACT_NAME,
        "same_run_id": True,
        "checksums_reconciled": True,
        "identity_self_hash": False,
        "production_touched": False,
        "soak_touched": False,
        "generated_at": utc_now(),
        "files": {
            k: checksums.get(k) or checksums.get(v)
            for k, v in {
                "executive-report.pdf": "extra_live_consulting_pack.pdf",
                "consulting-pack.xlsx": "extra_live_consulting_pack.xlsx",
                "executive-summary.md": "executive-summary.md",
                "pack-manifest.json": "pack-manifest.json",
            }.items()
        },
    }
    # fill actual
    for k in list(recon["files"].keys()):
        pth = pack_dir / k
        if pth.is_file():
            recon["files"][k] = sha256_file(pth)
    (campaign_dir / "package-reconciliation.json").write_text(
        json.dumps(recon, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    package_checksums = {
        "executive-report.pdf": sha256_file(pack_dir / "executive-report.pdf"),
        "consulting-pack.xlsx": sha256_file(pack_dir / "consulting-pack.xlsx"),
        "executive-summary.md": sha256_file(pack_dir / "executive-summary.md"),
        "pack-manifest.json": sha256_file(pack_dir / "pack-manifest.json"),
        "checksums.json": sha256_file(pack_dir / "checksums.json"),
    }
    for name in (
        "deliverable_a.json",
        "deliverable_b.json",
        "deliverable_c.json",
        "deliverable_d.json",
        "deliverable_e.json",
    ):
        if (pack_dir / name).is_file():
            package_checksums[name] = sha256_file(pack_dir / name)

    acceptance = {
        "status": "PENDING_HUMAN",
        "campaign_id": CAMPAIGN_ID,
        "pr": "https://github.com/tjsasakifln/extra-cli/pull/131",
        "run_id": run_id,
        "rc_sha": product_rc_sha,
        "package_checksums": package_checksums,
        "accepted_by": None,
        "accepted_at": None,
        "notes": (
            "Commercial RC v2 (sector-filtered engineering). "
            "RC v1 remains CHANGES_REQUESTED historically. "
            "Agent must not rebind ACCEPT."
        ),
        "agent_auto_accept_forbidden": true_literal(),
        "decision_options": ["ACCEPTED", "REJECTED", "CHANGES_REQUESTED"],
        "freeze": {
            "pack_run_id": run_id,
            "product_rc_sha": product_rc_sha,
            "artifact_name": FROZEN_RC_ARTIFACT_NAME,
            "as_of": utc_now(),
            "prior_rc": {
                "run_id": FROZEN_RC_V1_RUN_ID,
                "product_rc_sha": FROZEN_RC_V1_PRODUCT_SHA,
                "status": FROZEN_RC_V1_STATUS,
            },
        },
        "binding": {
            "pack_run_id": run_id,
            "rc_sha": product_rc_sha,
            "valid": True,
            "checked_at": utc_now(),
        },
        "classification": "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW",
    }
    (campaign_dir / "user-acceptance.json").write_text(
        json.dumps(acceptance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    div = integrity_gate(pack_dir, acceptance)
    if div:
        print(json.dumps({"status": "FAIL", "error": "integrity_gate", "divergences": div}, indent=2))
        return 2

    # Commercial honesty gates on E
    e_path = pack_dir / "deliverable_e.json"
    if e_path.is_file():
        e = json.loads(e_path.read_text(encoding="utf-8"))
        for rec in e.get("recommendations") or []:
            lab = (rec.get("sector_classification") or {}).get("label")
            if lab in {"NON_ENGINEERING", "EXCLUDED_CATEGORY"}:
                print(
                    json.dumps(
                        {
                            "status": "FAIL",
                            "error": "non_engineering_in_e",
                            "label": lab,
                            "titulo": rec.get("titulo"),
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 2

    result = assemble_v2(
        campaign_dir=campaign_dir,
        pack_dir=pack_dir,
        staging_dir=staging_dir,
        run_id=run_id,
        product_rc_sha=product_rc_sha,
        acceptance=acceptance,
    )
    # copy pack checksums into campaign for visibility
    shutil.copy2(pack_dir / "checksums.json", campaign_dir / "pack" / "checksums.json") if (
        campaign_dir / "pack"
    ).is_dir() else None
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW" else 2


def true_literal() -> bool:
    return True


if __name__ == "__main__":
    raise SystemExit(main())
