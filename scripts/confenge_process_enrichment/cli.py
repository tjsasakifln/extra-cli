"""CLI for process-first commercial enrichment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.confenge_process_enrichment.pipeline import ProcessFirstConfig, ProcessFirstEnricher
from scripts.confenge_process_enrichment.states import funnel_snapshot


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def cmd_enrich(args: argparse.Namespace) -> int:
    contracts = None
    if args.contracts_json:
        contracts = json.loads(Path(args.contracts_json).read_text(encoding="utf-8"))
        if isinstance(contracts, dict):
            contracts = contracts.get("contracts") or contracts.get("data") or [contracts]
    docs = None
    if args.docs_json:
        docs = json.loads(Path(args.docs_json).read_text(encoding="utf-8"))
        if isinstance(docs, dict):
            docs = docs.get("documents") or docs.get("document_texts") or [docs]

    enricher = ProcessFirstEnricher(
        config=ProcessFirstConfig(
            allow_network=bool(args.allow_network),
            max_contracts=args.max_contracts,
            dsn=args.dsn,
            registry_path=args.registry_path,
            allow_ocr=bool(args.allow_ocr),
        )
    )
    result = enricher.enrich(
        account_cnpj=args.cnpj,
        razao_social=args.razao,
        contracts=contracts,
        document_texts=docs,
        existing_enrollable=bool(args.existing_enrollable),
    )
    payload = result.to_dict()
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    accounts = _load_jsonl(Path(args.input_jsonl))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # limit=None or 0 → full population (never treat 50 as capacity)
    limit = args.limit
    if limit is not None and int(limit) == 0:
        limit = None
    if limit is not None and int(limit) == 50:
        raise SystemExit(
            "Refuse --limit 50: that is PILOT_ACCEPTANCE_SAMPLE only, not harvest capacity. "
            "Use --limit 0 for full population or omit a pilot-sized bound."
        )
    enricher = ProcessFirstEnricher(
        config=ProcessFirstConfig(
            allow_network=bool(args.allow_network),
            max_contracts=args.max_contracts,
            dsn=args.dsn,
            registry_path=str(out_dir / "process_source_registry.json"),
        )
    )
    results: list[dict[str, Any]] = []
    rows_iter = accounts if limit is None else accounts[: int(limit)]
    for row in rows_iter:
        cnpj = row.get("cnpj14") or row.get("cnpj") or row.get("account_cnpj")
        if not cnpj:
            continue
        r = enricher.enrich(
            account_cnpj=str(cnpj),
            razao_social=row.get("razao_social") or row.get("legal_name"),
            contracts=row.get("contracts"),
            document_texts=row.get("document_texts"),
        )
        d = r.to_dict()
        results.append(
            {
                "account_cnpj": r.account_cnpj,
                "terminal_state": r.terminal_state.value,
                "investigation_state": r.investigation_state.value,
                **{k: bool(r.funnel_flags.get(k)) for k in r.funnel_flags},
            }
        )
        (out_dir / f"{r.account_cnpj}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    funnel = funnel_snapshot(
        [
            {
                "contracts_resolved": x.get("contracts_resolved"),
                "process_number_resolved": x.get("process_number_resolved"),
                "process_portal_resolved": x.get("process_portal_resolved"),
                "documents_fetched": x.get("documents_fetched"),
                "company_authored_docs_found": x.get("company_authored_docs_found"),
                "any_email": x.get("any_email"),
                "verified_email": x.get("verified_email"),
                "enrollable_email": x.get("enrollable_email"),
                "named_contact": x.get("named_contact"),
                "relevant_role": x.get("relevant_role"),
                "referral_route": x.get("referral_route"),
                "terminal_state": x.get("terminal_state"),
            }
            for x in results
        ]
    )
    summary = {
        "schema": "confenge.process_first_batch.v1",
        "accounts": len(results),
        "funnel": funnel,
        "terminals": {},
    }
    for x in results:
        t = x["terminal_state"]
        summary["terminals"][t] = summary["terminals"].get(t, 0) + 1
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def cmd_sei_human(args: argparse.Namespace) -> int:
    """Operator path: SEI public search with human captcha/session."""
    from scripts.confenge_process_enrichment.adapters.sei_human_session import (
        HumanSessionSpec,
        SeiHumanSessionAdapter,
        operator_session_template,
    )

    if args.template:
        out = Path(args.template)
        out.write_text(
            json.dumps(
                operator_session_template(args.base_url or "https://colaboragov.sei.gov.br"),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"wrote operator template {out}")
        return 0
    if not args.session or not args.protocol:
        print("error: --session and --protocol required (or --template)", file=sys.stderr)
        return 2
    spec = HumanSessionSpec.from_json_file(Path(args.session))
    if args.base_url:
        spec.base_url = args.base_url.rstrip("/")
    adapter = SeiHumanSessionAdapter(spec)
    result = adapter.resolve_and_list_docs(args.protocol)
    payload = result.to_dict()
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.matched_protocol or not result.blocked else 1


def cmd_municipal_resolve(args: argparse.Namespace) -> int:
    from scripts.confenge_process_enrichment.adapters.municipal_portal import MunicipalPortalAdapter

    adapter = MunicipalPortalAdapter()
    result = adapter.resolve(
        process_number=args.process,
        municipality=args.municipality,
        uf=args.uf,
        orgao_cnpj=args.orgao_cnpj,
        entity_name=args.entity_name,
        supplier_cnpj=args.supplier_cnpj,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.resolved else 1


def cmd_national_confirmed(args: argparse.Namespace) -> int:
    import os

    from scripts.confenge_process_enrichment.national_confirmed import (
        NationalHarvestConfig,
        run_national_process_harvest,
    )

    dsn = args.dsn or os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_DATALAKE_DSN")
    if not dsn:
        print("FAIL: set --dsn or DATABASE_URL", file=sys.stderr)
        return 2
    cfg = NationalHarvestConfig(
        output_dir=Path(args.out_dir),
        max_companies=args.max_companies,
        allow_network=bool(args.allow_network),
        max_contracts=int(args.max_contracts),
        resume=not bool(args.no_resume),
        dsn=dsn,
        politeness_seconds=float(args.politeness_seconds),
        root_prefix=getattr(args, "root_prefix", None),
    )
    report = run_national_process_harvest(dsn, cfg=cfg)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    cov = report.get("contact_terminal_coverage") or {}
    # Non-zero only if closed sum broken
    return 0 if cov.get("closed_sum", True) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.confenge_process_enrichment")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enrich", help="Enrich one account")
    e.add_argument("--cnpj", required=True)
    e.add_argument("--razao")
    e.add_argument("--contracts-json")
    e.add_argument("--docs-json")
    e.add_argument("--dsn")
    e.add_argument("--out")
    e.add_argument("--registry-path")
    e.add_argument("--max-contracts", type=int, default=15)
    e.add_argument("--allow-network", action="store_true")
    e.add_argument("--allow-ocr", action="store_true")
    e.add_argument("--existing-enrollable", action="store_true")
    e.set_defaults(func=cmd_enrich)

    b = sub.add_parser("batch", help="Batch enrich from JSONL")
    b.add_argument("--input-jsonl", required=True)
    b.add_argument("--out-dir", required=True)
    b.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Smoke bound only; 0 or omit = full file. Never use 50 as capacity.",
    )
    b.add_argument("--dsn")
    b.add_argument("--max-contracts", type=int, default=10)
    b.add_argument("--allow-network", action="store_true")
    b.set_defaults(func=cmd_batch)

    n = sub.add_parser(
        "national-confirmed",
        help=(
            "Process-first harvest over live TARGET_CONFIRMED (no Top-N capacity; "
            "omit --max-companies for full national population)"
        ),
    )
    n.add_argument("--dsn", default=None, help="Postgres DSN (or DATABASE_URL / LOCAL_DATALAKE_DSN)")
    n.add_argument(
        "--out-dir",
        default="artifacts/confenge/process-first-national-confirmed",
    )
    n.add_argument(
        "--max-companies",
        type=int,
        default=None,
        help="Smoke bound only — never 50 (PILOT_ACCEPTANCE_SAMPLE)",
    )
    n.add_argument("--allow-network", action="store_true")
    n.add_argument("--max-contracts", type=int, default=4)
    n.add_argument("--no-resume", action="store_true")
    n.add_argument("--politeness-seconds", type=float, default=0.05)
    n.add_argument(
        "--root-prefix",
        default=None,
        help="Optional CNPJ-root prefix shard for parallel workers (e.g. 0, 1, 00)",
    )
    n.set_defaults(func=cmd_national_confirmed)

    sh = sub.add_parser("sei-human", help="SEI public search with human captcha/session")
    sh.add_argument("--session", help="JSON session file (captcha_answer/cookies)")
    sh.add_argument("--protocol", help="SEI/NUP protocol number")
    sh.add_argument("--base-url", help="Override SEI base URL")
    sh.add_argument("--template", help="Write operator session JSON template to this path")
    sh.add_argument("--out")
    sh.set_defaults(func=cmd_sei_human)

    mr = sub.add_parser("municipal-resolve", help="Resolve short process via municipal portals")
    mr.add_argument("--process", required=True)
    mr.add_argument("--municipality", required=True)
    mr.add_argument("--uf", required=True)
    mr.add_argument("--orgao-cnpj")
    mr.add_argument("--entity-name")
    mr.add_argument("--supplier-cnpj")
    mr.set_defaults(func=cmd_municipal_resolve)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
