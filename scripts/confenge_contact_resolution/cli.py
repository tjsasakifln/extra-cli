"""CLI: single-CNPJ and batch public business contact resolution."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.confenge_contact_resolution.cache import ResolutionCache
from scripts.confenge_contact_resolution.export import write_resolution_artifacts
from scripts.confenge_contact_resolution.models import ServiceContext
from scripts.confenge_contact_resolution.resolver import ContactResolver, ResolverConfig, default_adapters


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _load_cnpj_list(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    cnpjs: list[str] = []
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    cnpjs.append(item)
                elif isinstance(item, dict):
                    cnpjs.append(str(item.get("cnpj") or item.get("cnpj14") or ""))
        elif isinstance(data, dict) and "cnpjs" in data:
            cnpjs.extend(str(x) for x in data["cnpjs"])
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # jsonl line or plain CNPJ
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    cnpjs.append(str(obj.get("cnpj") or obj.get("cnpj14") or ""))
                    continue
                except json.JSONDecodeError:
                    pass
            cnpjs.append(line.split(",")[0].strip())
    return [c for c in cnpjs if _digits(c)]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.confenge_contact_resolution",
        description=(
            "Resolve public business contacts for CONFENGE outreach "
            "(candidates + provenance; no outreach send)."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--output-dir",
            "-o",
            type=Path,
            required=True,
            help="Directory for confenge-contact-candidates-v1.jsonl + run_manifest.json",
        )
        sp.add_argument(
            "--service-context",
            choices=[s.value for s in ServiceContext],
            default=ServiceContext.GENERIC.value,
            help="Service context for role ranking",
        )
        sp.add_argument(
            "--fixtures-dir",
            type=Path,
            default=None,
            help="Optional directory with synthetic/injected source fixtures",
        )
        sp.add_argument(
            "--cache-dir",
            type=Path,
            default=None,
            help="Filesystem cache with TTL (default: <output-dir>/.cache)",
        )
        sp.add_argument("--cache-ttl", type=int, default=86400, help="Cache TTL seconds")
        sp.add_argument("--no-cache", action="store_true", help="Disable resolution cache")
        sp.add_argument(
            "--allow-network",
            action="store_true",
            help="Allow optional network adapters (BrasilAPI / web search if enabled)",
        )
        sp.add_argument(
            "--enable-web-search",
            action="store_true",
            help="Enable optional web-search adapter (still NoOp without provider config)",
        )
        sp.add_argument(
            "--check-mx",
            action="store_true",
            help="Run MX layer when dnspython available (never sends mail)",
        )
        sp.add_argument("--max-workers", type=int, default=4, help="Batch concurrency limit")
        sp.add_argument("--run-id", default=None, help="Optional stable run id")

    single = sub.add_parser("resolve", help="Resolve contacts for one CNPJ")
    single.add_argument("--cnpj", required=True, help="CNPJ (digits or formatted)")
    add_common(single)

    batch = sub.add_parser("batch", help="Resolve contacts for a list of CNPJs")
    batch.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="File with CNPJs (txt, csv first column, json list, or jsonl)",
    )
    add_common(batch)

    return p


def _make_resolver(args: argparse.Namespace) -> ContactResolver:
    cache = None
    if not args.no_cache:
        cdir = args.cache_dir or (args.output_dir / ".cache")
        cache = ResolutionCache(cdir, ttl_seconds=args.cache_ttl)
    adapters = default_adapters(
        web_search_enabled=bool(args.enable_web_search),
        registry_prefer_network=bool(args.allow_network),
    )
    cfg = ResolverConfig(
        service_context=args.service_context,
        adapters=adapters,
        cache=cache,
        check_mx=bool(args.check_mx),
        allow_network=bool(args.allow_network),
        fixtures_dir=args.fixtures_dir,
        max_workers=max(1, int(args.max_workers)),
    )
    return ContactResolver(cfg)


def cmd_resolve(args: argparse.Namespace) -> int:
    resolver = _make_resolver(args)
    result = resolver.resolve_one(args.cnpj)
    summary = write_resolution_artifacts(
        [result],
        args.output_dir,
        mode="single",
        service_context=args.service_context,
        run_id=args.run_id,
    )
    print(json.dumps({**summary, "cnpj14": result.cnpj14, "absence_reason": result.absence_reason}, ensure_ascii=False, indent=2))
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    cnpjs = _load_cnpj_list(args.input)
    if not cnpjs:
        print(json.dumps({"ok": False, "error": "empty_input"}, ensure_ascii=False))
        return 2
    resolver = _make_resolver(args)
    results = resolver.resolve_batch(cnpjs, max_workers=args.max_workers)
    summary = write_resolution_artifacts(
        results,
        args.output_dir,
        mode="batch",
        service_context=args.service_context,
        run_id=args.run_id,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "resolve":
        return cmd_resolve(args)
    if args.command == "batch":
        return cmd_batch(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
