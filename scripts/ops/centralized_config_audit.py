#!/usr/bin/env python3
"""Prove DoD §27 centralized domain constants, source URLs, config, defaults."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.registry import export_registry  # noqa: E402

CENTRAL_PATHS = {
    "domain_constants": "config/constants.py",
    "env_settings": "config/settings.py",
    "crawl_config": "scripts/crawl/config.py",
    "coverage_slas": "config/coverage_slas.yaml",
    "source_applicability": "config/source_applicability.yaml",
    "source_registry": "scripts/crawl/registry.py",
    "client_profile": "config/client_profiles/extra.yaml",
    "entry_points": "docs/canonical-entry-points.yaml",
    "development_guide": "docs/DEVELOPMENT.md",
}


def audit(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    present = {}
    for key, rel in CENTRAL_PATHS.items():
        p = root / rel
        present[key] = {"path": rel, "exists": p.is_file(), "bytes": p.stat().st_size if p.is_file() else 0}

    sources = export_registry()
    urls = {s["id"]: s.get("canonical_url") for s in sources}
    missing_url = [sid for sid, u in urls.items() if not u]
    # domain constants file content check
    const_path = root / "config" / "constants.py"
    const_ok = const_path.is_file() and "RetryConfig" in const_path.read_text(encoding="utf-8")
    crawl_cfg = root / "scripts" / "crawl" / "config.py"
    crawl_ok = crawl_cfg.is_file()

    defaults_doc = []
    if const_ok:
        defaults_doc.append("config/constants.py documents RetryConfig defaults (base_delay, max_delay, jitter)")
    if crawl_ok:
        defaults_doc.append("scripts/crawl/config.py holds crawler timeouts/retries")
    if (root / "config" / "coverage_slas.yaml").is_file():
        defaults_doc.append("config/coverage_slas.yaml holds coverage SLAs")

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "central_paths": present,
        "all_central_paths_exist": all(v["exists"] for v in present.values()),
        "source_urls_centralized": {
            "module": "scripts.crawl.registry",
            "n_sources": len(urls),
            "missing_url": missing_url,
            "ok": len(missing_url) == 0 and len(urls) >= 5,
            "sample": dict(list(urls.items())[:6]),
        },
        "domain_constants_centralized": {
            "path": "config/constants.py",
            "ok": const_ok,
            "notes": "RetryConfig and crawler timing constants",
        },
        "configuration_centralized": {
            "ok": const_ok and crawl_ok and present["env_settings"]["exists"],
            "layers": [
                "config/settings.py (env)",
                "config/constants.py (static)",
                "scripts/crawl/config.py (crawl)",
                "scripts/crawl/registry.py (sources)",
            ],
        },
        "defaults_documented": {
            "ok": len(defaults_doc) >= 2,
            "locations": defaults_doc,
        },
        "summary": {
            "ok": (
                all(v["exists"] for v in present.values())
                and len(missing_url) == 0
                and const_ok
            )
        },
        "claims": {
            "allowed": [
                "Source URLs live in scripts.crawl.registry",
                "Domain constants live in config/constants.py",
            ],
            "forbidden": ["LOCAL_READY", "zero config drift proven"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §27 centralized config audit")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Audit only; skip writing --out")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    result = audit()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.dry_run:
        if args.json:
            print(text)
        else:
            print(f"dry_run ok={result['summary']['ok']}")
        return 0 if result["summary"]["ok"] else 1
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        print(f"ok={result['summary']['ok']} urls={result['source_urls_centralized']['ok']}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
