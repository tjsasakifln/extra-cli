#!/usr/bin/env python3
"""Thin acceptance harness for OPERATIONAL-REPORTING-TRACEABILITY-ACCEPT-01.

Orchestrates per-alias proofs against existing product entry points.
Does **not** replace weekly_cycle / golden_path / operational_outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

CAMPAIGN_ID = "OPERATIONAL-REPORTING-TRACEABILITY-ACCEPT-01"
FREEZE_PATH = (
    _ROOT
    / "artifacts"
    / "campaigns"
    / CAMPAIGN_ID
    / "freeze.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    try:
        import shutil

        git_bin = shutil.which("git")
        if not git_bin:
            return "unknown"
        return subprocess.check_output(  # noqa: S603
            [git_bin, "rev-parse", "HEAD"],
            cwd=str(_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _run_mod(module: str, args: list[str], *, env: dict[str, str] | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    cmd = [sys.executable, "-m", module, *args]
    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        env=env or os.environ.copy(),
        timeout=300,
    )
    return {
        "cmd": cmd,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "duration_seconds": round(time.perf_counter() - t0, 4),
    }


def prove_lists(dsn: str, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    res = _run_mod(
        "scripts.reports.operational_outputs",
        ["--dsn", dsn, "--out", str(out), "--json"],
    )
    man = out / "manifest.json"
    proof = {
        "alias_group": "lists",
        "ok": res["exit_code"] == 0 and man.is_file(),
        "run": res,
        "manifest_path": str(man) if man.is_file() else None,
        "manifest_sha256": _sha(man) if man.is_file() else None,
    }
    if man.is_file():
        data = json.loads(man.read_text(encoding="utf-8"))
        proof["status"] = data.get("status")
        proof["reliability"] = data.get("reliability")
        proof["run_id"] = data.get("run_id")
        proof["counts"] = data.get("counts")
        proof["assertion"] = {
            "has_8_csvs": len(list(out.glob("*.csv"))) == 8,
            "has_metadata_fields": all(
                k in data
                for k in (
                    "run_id",
                    "generated_at",
                    "code_sha",
                    "reliability",
                    "limitations",
                    "errors",
                    "artifact_hashes",
                )
            ),
            "zero_is_success_zero": (
                data.get("status") == "SUCCESS_ZERO"
                if sum((data.get("counts") or {}).values()) == 0
                else True
            ),
        }
        proof["ok"] = proof["ok"] and all(proof["assertion"].values())
    return proof


def prove_reports(dsn: str, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    res = _run_mod(
        "scripts.reports.operational_reports",
        ["--dsn", dsn, "--out", str(out), "--json"],
    )
    man = out / "manifest.json"
    proof: dict[str, Any] = {
        "alias_group": "analytical_reports",
        "ok": res["exit_code"] == 0 and man.is_file(),
        "run": res,
        "manifest_path": str(man) if man.is_file() else None,
    }
    if man.is_file():
        data = json.loads(man.read_text(encoding="utf-8"))
        proof["run_id"] = data.get("run_id")
        proof["status"] = data.get("status")
        proof["reliability"] = data.get("reliability")
        proof["assertion"] = {
            "has_reports": bool(data.get("reports")),
            "has_period_or_generated_at": bool(data.get("generated_at") or data.get("period")),
            "has_limitations_key": "limitations" in data,
        }
        proof["ok"] = proof["ok"] and all(proof["assertion"].values())
    return proof


def prove_export_pack(dsn: str, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    res = _run_mod(
        "scripts.reports.operational_export_pack",
        ["--dsn", dsn, "--out", str(out), "--json"],
    )
    man = out / "manifest.json"
    proof: dict[str, Any] = {
        "alias_group": "export_pack",
        "ok": res["exit_code"] == 0 and man.is_file(),
        "run": res,
    }
    if man.is_file():
        data = json.loads(man.read_text(encoding="utf-8"))
        arts = data.get("artifacts") or {}
        pdf = Path((arts.get("pdf") or {}).get("path") or "")
        xlsx = Path((arts.get("excel") or {}).get("path") or "")
        proof["run_id"] = data.get("run_id")
        proof["assertion"] = {
            "pdf_exists": pdf.is_file() and pdf.stat().st_size > 100,
            "pdf_magic": pdf.read_bytes()[:5] == b"%PDF-" if pdf.is_file() else False,
            "xlsx_exists": xlsx.is_file() and xlsx.stat().st_size > 100,
            "shared_meta_run_id": bool(data.get("run_id")),
            "no_demo_fixture_in_manifest": "Demo A" not in json.dumps(data),
        }
        proof["ok"] = proof["ok"] and all(proof["assertion"].values())
        proof["artifact_hashes"] = {
            "pdf": _sha(pdf) if pdf.is_file() else None,
            "xlsx": _sha(xlsx) if xlsx.is_file() else None,
        }
    return proof


def prove_package_final(dsn: str, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "package-final-report.json"
    res = _run_mod(
        "scripts.ops.deliverable_package_final",
        [
            "from-db",
            "--dsn",
            dsn,
            "--out-dir",
            str(out),
            "--out",
            str(report_path),
        ],
    )
    proof: dict[str, Any] = {"alias_group": "package_final", "run": res}
    data: dict[str, Any] = {}
    if report_path.is_file():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    pkg = data.get("package") or {}
    meta = pkg.get("meta") or {}
    proof["run_id"] = pkg.get("run_id") or meta.get("run_id")
    proof["report_path"] = str(report_path) if report_path.is_file() else None
    proof["assertion"] = {
        "status_ok": str(data.get("status") or "").startswith("OK"),
        "reconcile_pass": (data.get("reconcile") or {}).get("status") == "PASS",
        "same_run": (data.get("reconcile") or {}).get("same_run_id") is True,
        "not_fixture": meta.get("fixture") is False,
        "pdf_path": bool(pkg.get("pdf_path")),
        "excel_path": bool(pkg.get("excel_path")),
    }
    proof["ok"] = res["exit_code"] == 0 and all(proof["assertion"].values())
    return proof


def prove_valores(dsn: str, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    res = _run_mod(
        "scripts.reports.valores_report",
        ["--dsn", dsn, "--out-dir", str(out)],
    )
    files = list(out.glob("relatorio-valores-*"))
    proof = {
        "alias_group": "valores",
        "ok": res["exit_code"] == 0 and bool(files),
        "run": res,
        "artifacts": [str(p) for p in files],
        "assertion": {"domain_path_present": any("relatorio-valores" in p.name for p in files)},
    }
    proof["ok"] = proof["ok"] and proof["assertion"]["domain_path_present"]
    return proof


def run_acceptance(dsn: str, out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    executed_sha = _git_sha()
    started = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    proofs = {
        "lists": prove_lists(dsn, out_dir / "lists"),
        "reports": prove_reports(dsn, out_dir / "reports"),
        "export_pack": prove_export_pack(dsn, out_dir / "export"),
        "package_final": prove_package_final(dsn, out_dir / "package_final"),
        "valores": prove_valores(dsn, out_dir / "valores"),
    }
    ok = all(p.get("ok") for p in proofs.values())
    result = {
        "campaign_id": CAMPAIGN_ID,
        "started_at": started,
        "finished_at": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "executed_sha": executed_sha,
        "dsn_host": (dsn.split("@", 1)[1] if "@" in dsn else "configured"),
        "ok": ok,
        "proofs": proofs,
        "freeze_path": str(FREEZE_PATH) if FREEZE_PATH.is_file() else None,
        "note": (
            "Thin harness only — product entry points remain canonical. "
            "Per-alias promotion proofs are expanded in PR3."
        ),
    }
    path = out_dir / "acceptance-run.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n")
    result["path"] = str(path)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ORPT thin acceptance harness")
    p.add_argument(
        "--dsn",
        default=os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL"),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT
        / "artifacts"
        / "campaigns"
        / CAMPAIGN_ID
        / "live"
        / "acceptance",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn required", file=sys.stderr)
        return 2
    if os.environ.get("REQUIRE_REAL_DB") == "1":
        # fail closed if DSN unusable
        try:
            import psycopg2

            conn = psycopg2.connect(args.dsn)
            conn.close()
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"REQUIRE_REAL_DB: {exc}"}))
            return 1
    result = run_acceptance(args.dsn, args.out)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"ok={result['ok']} sha={result['executed_sha']} path={result.get('path')}")
        for name, proof in (result.get("proofs") or {}).items():
            print(f"  {name}: ok={proof.get('ok')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
