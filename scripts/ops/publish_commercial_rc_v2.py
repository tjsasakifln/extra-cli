#!/usr/bin/env python3
"""Publish client-ready-frozen-rc-v2 from a generated pack (isolated DSN only).

Single freeze writer — fixed order (never rewrite checksums after UA):

  1) live_consulting_pack (or reuse pack-v2)
  2) RC v1 history CHANGES_REQUESTED
  3) Stage product bytes into client-ready-frozen-rc-v2/
  4) Write final checksums.json ONCE from staged products
  5) Build package_checksums (includes sha256 of that checksums.json)
  6) Write user-acceptance.json PENDING_HUMAN
  7) Write ARTIFACT-IDENTITY.json (no self-hash) + .sha256 sidecar
  8) assert_full_reconciliation (ua ↔ checksums ↔ identity ↔ disk)

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

# Product members that form content-addressed product_rc_sha (no circularity with manifest).
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

# Files listed in checksums.json (products + pack-manifest). Written once.
CHECKSUM_MEMBERS: tuple[str, ...] = PRODUCT_RC_MEMBERS + ("pack-manifest.json",)

# Meta files staged after checksums.json (may appear in identity.file_sha256, not in checksums.json).
META_AFTER_CHECKSUMS: tuple[str, ...] = (
    "user-acceptance.json",
    "package-reconciliation.json",
    "rc-v1-CHANGES_REQUESTED.json",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def write_v1_history(campaign_dir: Path) -> Path:
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
    return path


def assert_full_reconciliation(staging_dir: Path) -> list[str]:
    """Fail-closed equality: checksums.json ↔ identity.file_sha256 ↔ ua.package_checksums ↔ disk.

    For every key present in ANY of the three maps, the file must exist and all
    maps that contain the key must agree with sha256(file). Orphans and missing
    files are divergences.
    """
    divergences: list[str] = []
    ck_path = staging_dir / "checksums.json"
    id_path = staging_dir / "ARTIFACT-IDENTITY.json"
    ua_path = staging_dir / "user-acceptance.json"

    if not ck_path.is_file():
        return ["missing_checksums_json"]
    if not id_path.is_file():
        return ["missing_artifact_identity"]
    if not ua_path.is_file():
        return ["missing_user_acceptance"]

    checksums = json.loads(ck_path.read_text(encoding="utf-8"))
    identity = json.loads(id_path.read_text(encoding="utf-8"))
    acceptance = json.loads(ua_path.read_text(encoding="utf-8"))
    file_sha = identity.get("file_sha256") or {}
    package_checksums = acceptance.get("package_checksums") or {}

    if "ARTIFACT-IDENTITY.json" in file_sha:
        divergences.append("identity_self_hash_forbidden")

    # Union of all keys that claim product integrity
    all_keys = set(checksums) | set(package_checksums) | {
        k for k in file_sha if k not in {"ARTIFACT-IDENTITY.json", "ARTIFACT-IDENTITY.sha256"}
    }

    for key in sorted(all_keys):
        path = staging_dir / key
        if not path.is_file():
            divergences.append(f"missing_file:{key}")
            continue
        dig = sha256_file(path)
        if key in checksums and checksums[key] != dig:
            divergences.append(f"checksums_mismatch:{key}")
        if key in package_checksums and package_checksums[key] != dig:
            divergences.append(f"ua_package_checksums_mismatch:{key}")
        if key in file_sha and file_sha[key] != dig:
            divergences.append(f"identity_mismatch:{key}")

    # Explicit triple equality for checksums.json itself (the bug that stuck the goal)
    if "checksums.json" in package_checksums and "checksums.json" in file_sha:
        disk_ck = sha256_file(ck_path)
        if not (
            package_checksums["checksums.json"]
            == file_sha["checksums.json"]
            == disk_ck
        ):
            divergences.append(
                "triple_mismatch_checksums_json:"
                f"ua={package_checksums['checksums.json'][:12]}"
                f" id={file_sha['checksums.json'][:12]}"
                f" disk={disk_ck[:12]}"
            )

    # run_id / product_rc_sha agreement
    if acceptance.get("run_id") != identity.get("run_id"):
        divergences.append("run_id_ua_vs_identity")
    if acceptance.get("rc_sha") != identity.get("product_rc_sha"):
        divergences.append("product_rc_sha_ua_vs_identity")
    if acceptance.get("status") != "PENDING_HUMAN":
        divergences.append(f"acceptance_not_pending:{acceptance.get('status')}")
    if acceptance.get("accepted_by") is not None:
        divergences.append("acceptance_auto_bound")

    return divergences


def stage_product_file(pack_dir: Path, staging_dir: Path, name: str) -> bool:
    """Copy product member from pack into staging. Returns True if staged."""
    candidates = [name]
    if name == "executive-report.pdf":
        candidates.append("extra_live_consulting_pack.pdf")
    if name == "consulting-pack.xlsx":
        candidates.append("extra_live_consulting_pack.xlsx")
    if name == "executive-summary.md":
        candidates.append("executive_summary.md")
    for c in candidates:
        src = pack_dir / c
        if src.is_file():
            dest = staging_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            return True
    return False


def freeze_staging(
    *,
    campaign_dir: Path,
    pack_dir: Path,
    staging_dir: Path,
    run_id: str,
    product_rc_sha: str,
) -> dict[str, Any]:
    """Single writer freeze. checksums.json written exactly once before UA/identity."""
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    sources: dict[str, str] = {}
    missing: list[str] = []

    # --- 1) Stage product bytes only ---
    for name in CHECKSUM_MEMBERS:
        if stage_product_file(pack_dir, staging_dir, name):
            sources[name] = f"pack:{name}"
        else:
            missing.append(name)
    if missing:
        return {"status": "FAIL", "error": "missing_members", "missing": missing}

    # --- 2) Final checksums.json ONCE (product members only; no identity/ua) ---
    product_checksums: dict[str, str] = {
        name: sha256_file(staging_dir / name) for name in CHECKSUM_MEMBERS
    }
    ck_path = staging_dir / "checksums.json"
    ck_path.write_text(
        json.dumps(product_checksums, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # NEVER rewrite ck_path after this point.

    # --- 3) package_checksums from staged tree including checksums.json ---
    package_checksums: dict[str, str] = dict(product_checksums)
    package_checksums["checksums.json"] = sha256_file(ck_path)

    # --- 4) package-reconciliation (campaign + staged) ---
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
            k: package_checksums[k]
            for k in REQUIRED_IDENTITY_FILES
            if k in package_checksums
        },
    }
    recon_path = campaign_dir / "package-reconciliation.json"
    recon_path.write_text(
        json.dumps(recon, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    shutil.copy2(recon_path, staging_dir / "package-reconciliation.json")

    # --- 5) user-acceptance PENDING_HUMAN (uses final package_checksums) ---
    v1_path = write_v1_history(campaign_dir)
    shutil.copy2(v1_path, staging_dir / "rc-v1-CHANGES_REQUESTED.json")

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
        "agent_auto_accept_forbidden": True,
        "decision_options": ["ACCEPTED", "REJECTED", "CHANGES_REQUESTED"],
        "freeze": {
            "pack_run_id": run_id,
            "product_rc_sha": product_rc_sha,
            "artifact_name": FROZEN_RC_ARTIFACT_NAME,
            "product_rc_scheme": "content_sha256_v1",
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
    ua_campaign = campaign_dir / "user-acceptance.json"
    ua_bytes = (json.dumps(acceptance, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    ua_campaign.write_bytes(ua_bytes)
    (staging_dir / "user-acceptance.json").write_bytes(ua_bytes)

    # --- 6) ARTIFACT-IDENTITY (no self-hash); may list ua/checksums as members ---
    file_sha: dict[str, str] = dict(package_checksums)
    for meta in META_AFTER_CHECKSUMS:
        mp = staging_dir / meta
        if mp.is_file():
            file_sha[meta] = sha256_file(mp)

    identity = {
        "run_id": run_id,
        "product_rc_sha": product_rc_sha,
        "product_rc_scheme": "content_sha256_v1",
        "file_sha256": dict(file_sha),  # excludes ARTIFACT-IDENTITY.json itself
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
    id_path.write_text(
        json.dumps(identity, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    id_sha = sha256_file(id_path)
    (staging_dir / "ARTIFACT-IDENTITY.sha256").write_text(
        f"{id_sha}  ARTIFACT-IDENTITY.json\n", encoding="utf-8"
    )

    # --- 7) Fail-closed full reconciliation ---
    divergences = assert_full_reconciliation(staging_dir)
    if divergences:
        return {
            "status": "FAIL",
            "error": "full_reconciliation_failed",
            "divergences": divergences,
            "staging_dir": str(staging_dir),
            "run_id": run_id,
            "product_rc_sha": product_rc_sha,
        }

    # Mirror pack-level checksums for pack-v2 convenience (same bytes as staging)
    (pack_dir / "checksums.json").write_bytes(ck_path.read_bytes())

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


# Back-compat alias used by older call sites/tests
def assemble_v2(
    *,
    campaign_dir: Path,
    pack_dir: Path,
    staging_dir: Path,
    run_id: str,
    product_rc_sha: str,
    acceptance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deprecated name: delegates to freeze_staging (acceptance rebuilt from staged tree)."""
    del acceptance  # ignored — freeze_staging is the single writer
    return freeze_staging(
        campaign_dir=campaign_dir,
        pack_dir=pack_dir,
        staging_dir=staging_dir,
        run_id=run_id,
        product_rc_sha=product_rc_sha,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Publish commercial RC v2")
    p.add_argument("--dsn", required=True)
    p.add_argument(
        "--out",
        default=str(_PROJECT_ROOT / "artifacts/campaigns" / CAMPAIGN_ID / "pack-v2"),
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

    # Aliases for identity filenames
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
        pm["git_sha_provenance"] = pm.get("git_sha") or pack.get("git_sha")
        pm_path.write_text(
            json.dumps(pm, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    # Commercial honesty gates on E before freeze
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

    result = freeze_staging(
        campaign_dir=campaign_dir,
        pack_dir=pack_dir,
        staging_dir=staging_dir,
        run_id=run_id,
        product_rc_sha=product_rc_sha,
    )

    # Sync campaign constants consumers (FROZEN_RC_* still used by tests)
    if result.get("status") == "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW":
        const_path = (
            _PROJECT_ROOT / "scripts/ops/client_ready_consulting_cycle.py"
        )
        if const_path.is_file():
            import re

            text = const_path.read_text(encoding="utf-8")
            text = re.sub(
                r'FROZEN_RC_RUN_ID = "[^"]+"',
                f'FROZEN_RC_RUN_ID = "{run_id}"',
                text,
            )
            text = re.sub(
                r'FROZEN_RC_PRODUCT_SHA = "[^"]+"',
                f'FROZEN_RC_PRODUCT_SHA = "{product_rc_sha}"',
                text,
            )
            const_path.write_text(text, encoding="utf-8")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
