#!/usr/bin/env python3
"""Reproducible pSEO snapshot release toward web-cfg.

Does NOT auto-publish editorially unsafe content. Steps:
  1. export snapshot to temp dir
  2. validate
  3. compare with previous web-cfg/data/pseo (if present)
  4. page-level changelog
  5. atomic copy into web-cfg/data/pseo (optional --apply)
  6. optionally run web-cfg build:site
  7. emit PR-ready package notes

Usage:
  python -m scripts.pseo.release_snapshot \\
    --web-cfg /path/to/webcfg \\
    --as-of YYYY-MM-DD \\
    [--apply] [--build]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def page_changelog(old_dir: Path | None, new_dir: Path) -> list[dict]:
    """Coarse changelog by page id across public JSON bodies."""
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Release pSEO snapshot to web-cfg")
    ap.add_argument("--web-cfg", type=Path, required=True)
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--apply", action="store_true", help="Atomic copy into web-cfg/data/pseo")
    ap.add_argument("--build", action="store_true", help="Run npm run build:site after apply")
    ap.add_argument("--out-notes", type=Path, default=None)
    args = ap.parse_args(argv)

    web_cfg = args.web_cfg.resolve()
    target = web_cfg / "data" / "pseo"
    if not web_cfg.exists():
        print(f"web-cfg not found: {web_cfg}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="pseo-release-") as td:
        tmp = Path(td) / "snapshot"
        tmp.mkdir()
        cmd = [
            sys.executable,
            "-m",
            "scripts.pseo.export_web_cfg",
            "--out",
            str(tmp),
            "--as-of",
            args.as_of,
            "--validate",
        ]
        print("export:", " ".join(cmd))
        r = subprocess.run(cmd, check=False)
        if r.returncode != 0:
            print("export failed", file=sys.stderr)
            return r.returncode

        old = target if target.exists() else None
        changes = page_changelog(old, tmp)
        man = _load_json(tmp / "manifest.json") or {}
        notes = {
            "as_of": args.as_of,
            "dataset_hash": man.get("dataset_hash"),
            "schema_version": man.get("schema_version"),
            "changelog": changes,
            "apply": bool(args.apply),
            "note": (
                "Snapshot released for web-cfg consumption only. "
                "Human page approval uses page_material_hash — global hash churn "
                "does not auto-publish. Run review.py for material changes."
            ),
        }
        notes_path = args.out_notes or (web_cfg / "seo" / "pseo-snapshot-release-notes.json")
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        notes_path.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"changelog_count": len(changes), "notes": str(notes_path)}, indent=2))

        if args.apply:
            # atomic-ish: copy to sibling then rename
            staging = target.parent / f".pseo-staging-{man.get('dataset_hash', 'x')[:12]}"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(tmp, staging)
            backup = target.parent / f".pseo-backup-{date.today().isoformat()}"
            if target.exists():
                if backup.exists():
                    shutil.rmtree(backup)
                target.rename(backup)
            staging.rename(target)
            print(f"applied snapshot to {target} (backup {backup if backup.exists() else 'n/a'})")

        if args.build:
            if not args.apply:
                print("--build requires --apply", file=sys.stderr)
                return 2
            br = subprocess.run(["npm", "run", "build:site"], cwd=str(web_cfg), check=False)
            return br.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
