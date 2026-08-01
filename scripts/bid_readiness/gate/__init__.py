"""Campaign gates: isolation, privacy, campaign, release-candidate, verify."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.bid_readiness.isolation import IsolationError, assert_fileset, assert_isolation, load_lock, repo_root
from scripts.bid_readiness.sanitize import contains_critical_pii


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed argv list, no shell
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None or _module_available(name)


def _module_available(mod: str) -> bool:
    # map CLI names to modules
    mapping = {
        "ruff": "ruff",
        "mypy": "mypy",
        "bandit": "bandit",
        "pytest": "pytest",
    }
    target = mapping.get(mod, mod)
    try:
        __import__(target)
        return True
    except Exception:
        return False


def gate_parallel_isolation() -> int:
    try:
        info = assert_isolation()
        lock = info["lock"]
        files = assert_fileset(str(lock["base_sha"]))
        print(
            json.dumps(
                {
                    "gate": "parallel-isolation",
                    "ok": True,
                    "branch": info["branch"],
                    "head": info["head"],
                    "fileset_count": len(files),
                },
                indent=2,
            )
        )
        return 0
    except IsolationError as exc:
        print(json.dumps({"gate": "parallel-isolation", "ok": False, "error": str(exc)}, indent=2))
        return 1


def gate_privacy() -> int:
    root = repo_root()
    issues: list[str] = []
    scan_roots = [
        root / "artifacts/campaigns/BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01",
        root / "scripts/bid_readiness/fixtures",
        root / "tests/bid_readiness",
        root / "integration-handoff/BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01",
    ]
    for base in scan_roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".zip", ".xlsx"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            hits = contains_critical_pii(text)
            if hits and "REDACTED" not in text and "***" not in text and "[FICTICIO" not in text.upper():
                for h in hits:
                    if h == "cpf" and (
                        "FICTICIO" in text.upper() or "EXAMPLE" in text.upper() or "REDACTED" in text.upper()
                    ):
                        continue
                    if h == "cpf" and "test_" in path.name and "sanitize" in text.lower():
                        continue
                    issues.append(f"{path.relative_to(root)}: {h}")

    art = root / "artifacts/campaigns/BID-SUBMISSION-READINESS-COMPLIANCE-PACK-01"
    if art.exists():
        for path in art.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".pdf", ".docx", ".zip"}:
                issues.append(f"private-looking binary in artifacts: {path}")

    ok = not issues
    print(json.dumps({"gate": "privacy", "ok": ok, "issues": issues[:50]}, indent=2))
    return 0 if ok else 1


def _quality_tools(root: Path) -> dict[str, int]:
    """Run ruff / format-check / mypy / bandit on bid_readiness only.

    Fail-closed when tool is installed and finds issues.
    If tool is missing from the campaign venv, record skip_missing=1 (non-zero)
    only for tools that are required; we install them in campaign evidence runs.
    """
    results: dict[str, int] = {}
    target = "scripts/bid_readiness"

    # ruff check
    if _module_available("ruff"):
        p = _run(
            [sys.executable, "-m", "ruff", "check", target, "--quiet"],
            cwd=root,
        )
        results["ruff"] = p.returncode
        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr, file=sys.stderr)
    else:
        print(json.dumps({"tool": "ruff", "status": "MISSING", "fail_closed": True}))
        results["ruff"] = 1

    # ruff format --check
    if _module_available("ruff"):
        p = _run(
            [sys.executable, "-m", "ruff", "format", "--check", target, "--quiet"],
            cwd=root,
        )
        results["format"] = p.returncode
        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr, file=sys.stderr)
    else:
        results["format"] = 1

    # mypy (soft config: only our package)
    if _module_available("mypy"):
        p = _run(
            [
                sys.executable,
                "-m",
                "mypy",
                target,
                "--ignore-missing-imports",
                "--no-error-summary",
                "--follow-imports=silent",
            ],
            cwd=root,
        )
        # mypy may warn on style; treat exit>1 as hard fail, exit 1 as warnings-as-issues
        results["mypy"] = 0 if p.returncode == 0 else p.returncode
        if p.returncode != 0:
            print(p.stdout[-2000:] if p.stdout else "")
            print(p.stderr[-2000:] if p.stderr else "", file=sys.stderr)
    else:
        print(json.dumps({"tool": "mypy", "status": "MISSING", "fail_closed": True}))
        results["mypy"] = 1

    # bandit
    if _module_available("bandit"):
        p = _run(
            [
                sys.executable,
                "-m",
                "bandit",
                "-q",
                "-r",
                target,
                "-x",
                f"{target}/fixtures",
                "-ll",
            ],
            cwd=root,
        )
        results["bandit"] = p.returncode
        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr, file=sys.stderr)
    else:
        print(json.dumps({"tool": "bandit", "status": "MISSING", "fail_closed": True}))
        results["bandit"] = 1

    return results


def gate_campaign() -> int:
    results: dict[str, int] = {}
    results["isolation"] = gate_parallel_isolation()
    if results["isolation"] != 0:
        return 1
    results["privacy"] = gate_privacy()
    if results["privacy"] != 0:
        return 1

    root = repo_root()
    try:
        import scripts.bid_readiness  # noqa: F401
        import scripts.bid_readiness.pipeline  # noqa: F401
    except Exception as exc:
        print(json.dumps({"gate": "campaign", "ok": False, "error": f"import: {exc}"}))
        return 1
    results["imports"] = 0

    # Quality tools (fail-closed when present; must be present in campaign venv)
    quality = _quality_tools(root)
    results.update(quality)
    if any(v != 0 for v in quality.values()):
        print(json.dumps({"gate": "campaign", "ok": False, "results": results}, indent=2))
        return 1

    # pytest — clear repo pytest.ini addopts (--cov) that break exclusive venv
    proc = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/bid_readiness",
            "-q",
            "--tb=line",
            "-o",
            "addopts=",
        ],
        cwd=root,
    )
    results["pytest"] = proc.returncode
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        print(json.dumps({"gate": "campaign", "ok": False, "results": results}, indent=2))
        return 1

    fixtures = root / "scripts/bid_readiness/fixtures/golden"
    default_case_root = "/tmp/extra-cli-bid-readiness-01/cases"  # noqa: S108  # nosec B108
    case_root = Path(os.environ.get("BID_CASE_ROOT", default_case_root))
    case_dir = case_root / "golden-bid-readiness-01"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    proc2 = _run(
        [
            sys.executable,
            "-m",
            "scripts.bid_readiness",
            "run",
            "--case-id",
            "golden-bid-readiness-01",
            "--requirements",
            str(fixtures / "requirements.json"),
            "--documents",
            str(fixtures / "documents"),
            "--reference-date",
            "2026-07-01",
            "--output",
            str(case_dir),
            "--entity",
            str(fixtures / "entity.json"),
        ],
        cwd=root,
        env=env,
    )
    results["golden"] = proc2.returncode
    print(proc2.stdout)
    if proc2.returncode != 0:
        print(proc2.stderr, file=sys.stderr)
        print(json.dumps({"gate": "campaign", "ok": False, "results": results}, indent=2))
        return 1

    proc3 = _run(
        [sys.executable, "-m", "scripts.bid_readiness", "verify", "--case", str(case_dir)],
        cwd=root,
        env=env,
    )
    results["verify"] = proc3.returncode
    print(proc3.stdout)
    if proc3.returncode != 0:
        print(proc3.stderr, file=sys.stderr)
        print(json.dumps({"gate": "campaign", "ok": False, "results": results}, indent=2))
        return 1

    # Report + package reconciliation (must be green after golden run)
    pkg_recon_path = case_dir / "package" / "package-reconciliation.json"
    rep_recon_path = case_dir / "reports" / "report-reconciliation.json"
    if not pkg_recon_path.is_file() or not rep_recon_path.is_file():
        print(json.dumps({"gate": "campaign", "ok": False, "error": "reconciliation artifacts missing"}))
        results["reconciliation"] = 1
        return 1
    pkg_recon = json.loads(pkg_recon_path.read_text(encoding="utf-8"))
    rep_recon = json.loads(rep_recon_path.read_text(encoding="utf-8"))
    recon_ok = (
        bool(pkg_recon.get("ok")) and bool(rep_recon.get("ok")) and bool(pkg_recon.get("simulation_only_present"))
    )
    results["reconciliation"] = 0 if recon_ok else 1
    if not recon_ok:
        print(
            json.dumps(
                {
                    "gate": "campaign",
                    "ok": False,
                    "package_reconciliation": pkg_recon,
                    "report_reconciliation": rep_recon,
                },
                indent=2,
            )
        )
        return 1

    ok = all(v == 0 for v in results.values())
    print(json.dumps({"gate": "campaign", "ok": ok, "results": results}, indent=2))
    return 0 if ok else 1


def gate_release_candidate() -> int:
    code = gate_campaign()
    if code != 0:
        return code
    root = repo_root()
    lock = load_lock(root)
    git_bin = "/usr/bin/git" if Path("/usr/bin/git").is_file() else "git"
    head = subprocess.check_output(  # noqa: S603
        [git_bin, "rev-parse", "HEAD"],  # noqa: S607
        cwd=str(root),
        text=True,
    ).strip()
    print(
        json.dumps(
            {
                "gate": "release-candidate",
                "ok": True,
                "base_sha": lock["base_sha"],
                "rc_sha": head,
                "campaign_id": lock["campaign_id"],
            },
            indent=2,
        )
    )
    return 0


def gate_verify() -> int:
    return gate_parallel_isolation()


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if not argv:
        print(
            "usage: python3 -m scripts.bid_readiness.gate "
            "<parallel-isolation|privacy|campaign|release-candidate|verify>"
        )
        return 2
    cmd = argv[0]
    mapping = {
        "parallel-isolation": gate_parallel_isolation,
        "privacy": gate_privacy,
        "campaign": gate_campaign,
        "release-candidate": gate_release_candidate,
        "verify": gate_verify,
    }
    if cmd not in mapping:
        print(f"unknown gate: {cmd}")
        return 2
    return mapping[cmd]()
