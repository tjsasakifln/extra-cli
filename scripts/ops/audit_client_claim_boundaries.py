#!/usr/bin/env python3
"""Guard client-facing surfaces against forbidden product claims.

Uses contextual patterns + exceptions (docs of prohibitions, disclaimers,
tests). Not a naive word list alone.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "scope_boundaries.yaml"


@dataclass
class ClaimFinding:
    claim_id: str
    path: str
    line: int
    snippet: str
    severity: str
    exception_applied: str | None = None


def load_config(path: Path | None = None) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    cfg_path = path or DEFAULT_CONFIG
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid config")
    return data


def _match_glob(path: str, glob: str) -> bool:
    p = path.replace("\\", "/")
    g = glob.replace("\\", "/")
    return fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, g.lstrip("./"))


def _exception_for(path: str, line_text: str, exceptions: list[dict[str, Any]]) -> str | None:
    for ex in exceptions:
        if not isinstance(ex, dict):
            continue
        reason = str(ex.get("reason") or "exception")
        if g := ex.get("path_glob"):
            if _match_glob(path, str(g)):
                return reason
        if rx := ex.get("path_regex"):
            if re.search(str(rx), path) or re.search(str(rx), line_text):
                return reason
    # inline negation on same line always counts
    low = line_text.lower()
    if any(
        n in low
        for n in (
            "não ",
            "nao ",
            "never ",
            "forbidden",
            "proibid",
            "fora de escopo",
            "out of scope",
            "não promete",
            "nao promete",
            "não assume",
            "não assina",
            "não protocola",
            "não substitui",
            "claims_forbidden",
        )
    ):
        return "inline negation/disclaimer"
    return None


def _expand_surfaces(root: Path, globs: list[str], max_files: int = 600) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    # Prefer high-signal client-facing paths first
    priority_dirs = [
        root / "templates",
        root / "config" / "client_profiles",
        root / "scripts" / "ops",
        root / "scripts" / "reports",
        root / "docs" / "architecture",
        root / "docs" / "ops",
    ]
    for base in priority_dirs:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p in seen:
                continue
            if p.suffix.lower() not in {".md", ".html", ".txt", ".py", ".yaml", ".yml", ".j2"}:
                continue
            try:
                if p.stat().st_size > 500_000:
                    continue
            except OSError:
                continue
            seen.add(p)
            files.append(p)
            if len(files) >= max_files:
                return files

    for g in globs:
        if len(files) >= max_files:
            break
        if "**" in g:
            prefix, _, suffix = g.partition("/**/")
            base = root / prefix if prefix else root
            if not base.exists():
                continue
            pattern = suffix or "*"
            for p in base.rglob(pattern.replace("**/", "")):
                if not p.is_file() or p in seen:
                    continue
                rel = str(p.relative_to(root)).replace("\\", "/")
                if fnmatch.fnmatch(rel, g.replace("\\", "/")) or fnmatch.fnmatch(
                    p.name, pattern
                ):
                    try:
                        if p.stat().st_size > 500_000:
                            continue
                    except OSError:
                        continue
                    seen.add(p)
                    files.append(p)
                    if len(files) >= max_files:
                        return files
        else:
            p = root / g
            if p.is_file() and p not in seen:
                seen.add(p)
                files.append(p)
    # Always include DOD.md so exceptions path is exercised, but it is allowlisted
    dod = root / "DOD.md"
    if dod.is_file() and dod not in seen:
        files.append(dod)
    return files


def scan_claims(
    root: Path | None = None,
    config_path: Path | None = None,
    *,
    extra_text: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Scan client surfaces. extra_text maps virtual path -> content (for tests)."""
    root = root or PROJECT_ROOT
    cfg = load_config(config_path)
    patterns = list(cfg.get("client_claim_patterns") or [])
    surfaces = list(cfg.get("client_claim_surfaces") or [])
    exceptions = list(cfg.get("client_claim_exceptions") or [])

    files = _expand_surfaces(root, surfaces)
    findings: list[ClaimFinding] = []
    scanned: list[str] = []

    def process(path_label: str, text: str) -> None:
        scanned.append(path_label)
        for pat in patterns:
            if not isinstance(pat, dict):
                continue
            cid = str(pat.get("id") or "claim")
            regex = str(pat.get("regex") or "")
            sev = str(pat.get("severity") or "high")
            if not regex:
                continue
            try:
                cre = re.compile(regex)
            except re.error:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if not cre.search(line):
                    continue
                ex = _exception_for(path_label, line, exceptions)
                findings.append(
                    ClaimFinding(
                        claim_id=cid,
                        path=path_label,
                        line=i,
                        snippet=line.strip()[:240],
                        severity=sev,
                        exception_applied=ex,
                    )
                )

    for fpath in files:
        try:
            if fpath.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        rel = str(fpath.relative_to(root)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        process(rel, text)

    if extra_text:
        for virt, text in extra_text.items():
            process(virt, text)

    open_findings = [f for f in findings if not f.exception_applied]
    return {
        "ok": len(open_findings) == 0,
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root),
        "surfaces_configured": surfaces,
        "files_scanned": len(scanned),
        "scanned_paths_sample": scanned[:50],
        "findings_total": len(findings),
        "findings_open": len(open_findings),
        "findings_excepted": len(findings) - len(open_findings),
        "findings": [asdict(f) for f in findings],
        "open_findings": [asdict(f) for f in open_findings],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit client claim boundaries")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = scan_claims(root=args.root, config_path=args.config)
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    if args.json or not args.out:
        sys.stdout.write(payload)
    else:
        print(
            f"claim audit ok={result['ok']} open={result['findings_open']} "
            f"excepted={result['findings_excepted']} -> {args.out}"
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
