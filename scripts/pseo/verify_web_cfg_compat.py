#!/usr/bin/env python3
"""Read-only web-cfg consumer compatibility verifier for pSEO exports.

This module **never writes inside the web-cfg tree**. It may only:
  1. read a web-cfg consumer path (data/pseo if present)
  2. optionally run a local export into an extra-cli out dir
  3. validate contract / compute page-level changelog
  4. write notes/evidence under --out (extra-cli artifacts or cwd)

Removed permanently (do not reintroduce):
  - --apply / atomic copy into web-cfg/data/pseo
  - --build / npm run build:site
  - shutil.copytree / rename / backup under web-cfg

Usage:
  python -m scripts.pseo.verify_web_cfg_compat \\
    --web-cfg /path/to/webcfg \\
    --as-of YYYY-MM-DD \\
    --out artifacts/pseo/web_cfg_compat_notes.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# Flags that must never exist on this CLI (adversarial guard for tests/docs).
FORBIDDEN_WRITE_FLAGS = frozenset(
    {
        "apply",
        "build",
        "write-consumer",
        "install",
        "deploy",
        "publish",
        "promote",
    }
)


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def page_changelog(old_dir: Path | None, new_dir: Path) -> list[dict]:
    """Coarse changelog by page id across public JSON bodies (read-only)."""
    keys = (
        "markets",
        "agencies",
        "prices",
        "competition",
        "opportunities",
        "problem_service",
    )
    changes: list[dict] = []
    for key in keys:
        new_rows = _load_json(new_dir / f"{key}.json") or []
        old_rows = (_load_json(old_dir / f"{key}.json") if old_dir else None) or []
        old_by_id = {r.get("id") or r.get("slug"): r for r in old_rows if isinstance(r, dict)}
        new_by_id = {r.get("id") or r.get("slug"): r for r in new_rows if isinstance(r, dict)}
        for pid, row in new_by_id.items():
            if pid not in old_by_id:
                changes.append({"id": pid, "kind": key, "change": "added"})
            elif json.dumps(old_by_id[pid], sort_keys=True, default=str) != json.dumps(
                row, sort_keys=True, default=str
            ):
                changes.append({"id": pid, "kind": key, "change": "modified"})
        for pid in old_by_id:
            if pid not in new_by_id:
                changes.append({"id": pid, "kind": key, "change": "removed"})
    return changes


def _assert_no_write_flags(argv: list[str] | None) -> None:
    if not argv:
        return
    # Normalize --foo / --foo=bar
    for raw in argv:
        if not raw.startswith("--"):
            continue
        name = raw[2:].split("=", 1)[0].replace("-", "_")
        if name in FORBIDDEN_WRITE_FLAGS:
            raise SystemExit(
                f"flag --{name.replace('_', '-')} is forbidden: "
                "web-cfg consumer is read-only (apply/build removed)"
            )


def main(argv: list[str] | None = None) -> int:
    _assert_no_write_flags(argv)

    ap = argparse.ArgumentParser(
        description=(
            "Verify pSEO export compatibility with web-cfg (READ-ONLY). "
            "Does not write into web-cfg; does not apply or build the consumer."
        )
    )
    ap.add_argument("--web-cfg", type=Path, required=True, help="Path to web-cfg repo (read-only)")
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Existing export directory to compare (skip local export if set)",
    )
    ap.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Optional fixture for a local export into a temp dir under --work-dir",
    )
    ap.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Working dir for temporary export (default: system temp; never under web-cfg)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/pseo/web_cfg_compat_notes.json"),
        help="Notes/changelog path under extra-cli (NOT under web-cfg)",
    )
    # Deprecated aliases that must fail closed if reintroduced as writers
    ap.add_argument(
        "--out-notes",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,  # alias for --out
    )
    args = ap.parse_args(argv)

    web_cfg = args.web_cfg.resolve()
    if not web_cfg.exists():
        print(f"web-cfg not found: {web_cfg}", file=sys.stderr)
        return 2

    notes_path = (args.out_notes or args.out).resolve()
    # Hard fail if notes would land inside the consumer tree
    try:
        notes_path.relative_to(web_cfg)
        print(
            f"ERROR: --out must not be under web-cfg consumer tree: {notes_path}",
            file=sys.stderr,
        )
        return 2
    except ValueError:
        pass  # notes outside web-cfg — good

    consumer_pseo = web_cfg / "data" / "pseo"
    old = consumer_pseo if consumer_pseo.is_dir() else None

    # Resolve export directory: provided, or run export into work/temp (never web-cfg)
    cleanup_tmp: tempfile.TemporaryDirectory[str] | None = None
    if args.export_dir is not None:
        export_dir = args.export_dir.resolve()
        if not export_dir.is_dir():
            print(f"export-dir not found: {export_dir}", file=sys.stderr)
            return 2
    else:
        if args.work_dir is not None:
            work = args.work_dir.resolve()
            work.mkdir(parents=True, exist_ok=True)
            export_dir = work / "snapshot"
            export_dir.mkdir(parents=True, exist_ok=True)
        else:
            cleanup_tmp = tempfile.TemporaryDirectory(prefix="pseo-compat-")
            export_dir = Path(cleanup_tmp.name) / "snapshot"
            export_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "scripts.pseo.export_web_cfg",
            "--out",
            str(export_dir),
            "--as-of",
            args.as_of,
            "--validate",
        ]
        if args.fixture is not None:
            cmd.extend(["--fixture", str(args.fixture.resolve())])
        print("export:", " ".join(cmd))
        r = subprocess.run(cmd, check=False)  # noqa: S603
        if r.returncode != 0:
            print("export failed", file=sys.stderr)
            if cleanup_tmp is not None:
                cleanup_tmp.cleanup()
            return r.returncode

    try:
        changes = page_changelog(old, export_dir)
        man = _load_json(export_dir / "manifest.json") or {}
        notes = {
            "as_of": args.as_of,
            "dataset_hash": man.get("dataset_hash"),
            "schema_version": man.get("schema_version"),
            "snapshot_status": man.get("snapshot_status"),
            "publish_status": man.get("publish_status"),
            "indexable": man.get("indexable"),
            "changelog": changes,
            "consumer_path": str(consumer_pseo),
            "consumer_present": old is not None,
            "export_dir": str(export_dir),
            "read_only": True,
            "apply": False,
            "build": False,
            "note": (
                "READ-ONLY compatibility check. Does not mutate web-cfg. "
                "PUBLISH_READY is an export snapshot gate, not MERGE_READY for the PR. "
                "CANDIDATE remains the fail-closed default without human approval + classifier gates. "
                "Human page approval uses page_material_hash — global hash churn does not auto-publish."
            ),
        }
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(
            json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "read_only": True,
                    "changelog_count": len(changes),
                    "notes": str(notes_path),
                    "dataset_hash": notes.get("dataset_hash"),
                    "snapshot_status": notes.get("snapshot_status"),
                },
                indent=2,
            )
        )
        return 0
    finally:
        if cleanup_tmp is not None:
            cleanup_tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
