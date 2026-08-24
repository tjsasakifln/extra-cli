"""CLI for the CONFENGE dossier engine.

python3 -m scripts.dossier build --cnpj 00000000000000 --out artifacts/dossier/acme
python3 -m scripts.dossier build --cnpj 00000000000000 --fixture tests/dossier/fixtures/x.json
python3 -m scripts.dossier verify --dir artifacts/dossier/acme
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.dossier.constants import (
    CATALOG_FIXTURE,
    CATALOG_OFFICIAL_LIVE,
    COMPETITOR_LIMIT,
    CONSUMER_WEB_CFG,
    DATA_READY,
    DATA_REJECT,
    EXPIRING_WINDOW_DAYS,
    REASON_DSN_UNAVAILABLE,
    REFERENCE_SCOPE_BOTH,
    REFERENCE_SCOPES,
)
from scripts.dossier.envelope import (
    build_dossier,
    canonical_json,
    content_hash,
    producer_sha,
    public_projection,
    scan_forbidden,
    scan_markdown,
)
from scripts.dossier.handoff import DECISION_READY, rendezvous_dir, verify_handoff, write_handoff
from scripts.dossier.models import DossierRequest
from scripts.dossier.render import render_markdown
from scripts.dossier.sources import DatalakeSource, FixtureSource

DOSSIER_JSON = "dossier.json"
PUBLIC_JSON = "public-read.json"
DOSSIER_MD = "dossier.md"
MANIFEST_JSON = "manifest.json"


def _resolve_dsn(explicit: str | None) -> str | None:
    return explicit or os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_DATALAKE_DSN")


def _write(path: Path, text: str) -> str:
    """Write a file and return the sha256 of the bytes actually on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return file_digest(path)


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _cmd_build(args: argparse.Namespace) -> int:
    as_of = args.as_of or date.today().isoformat()

    if args.fixture:
        source: Any = FixtureSource(args.fixture)
        catalog_mode = CATALOG_OFFICIAL_LIVE if args.claim_live else CATALOG_FIXTURE
    else:
        dsn = _resolve_dsn(args.dsn)
        if not dsn:
            sys.stderr.write(
                f"{REASON_DSN_UNAVAILABLE}: set --dsn, DATABASE_URL or LOCAL_DATALAKE_DSN, or pass --fixture\n"
            )
            return 2
        source = DatalakeSource(dsn, observed_at=args.observed_at, competitor_limit=args.competitor_limit)
        catalog_mode = CATALOG_OFFICIAL_LIVE

    request = DossierRequest(
        cnpj=args.cnpj,
        as_of=as_of,
        catalog_mode=catalog_mode,
        consumer_id=args.consumer,
        producer_sha=producer_sha(),
        competitor_limit=args.competitor_limit,
        expiring_window_days=args.window_days,
        reference_scope=args.reference_scope,
    )
    result, document = build_dossier(source, request)

    public = public_projection(document)
    markdown = render_markdown(document)

    # The markdown is the delivered document, so it is scanned like the JSON.
    forbidden = scan_forbidden(document) + scan_forbidden(public) + scan_markdown(markdown, document)
    if forbidden:
        sys.stderr.write("forbidden claim content in dossier: " + ", ".join(forbidden) + "\n")
        return 3

    if args.out:
        out = Path(args.out)
        digests = {
            DOSSIER_JSON: _write(out / DOSSIER_JSON, canonical_json(document)),
            PUBLIC_JSON: _write(out / PUBLIC_JSON, canonical_json(public)),
            DOSSIER_MD: _write(out / DOSSIER_MD, markdown),
        }
        manifest = {
            "dossier_id": document["dossier_id"],
            "schema": document["schema"],
            "catalog_mode": document["catalog_mode"],
            "data_state": document["data_state"],
            "as_of": document["as_of"],
            "content_hash": document["content_hash"],
            "public_content_hash": public["content_hash"],
            "producer_sha": document["producer_sha"],
            # Digests of the bytes on disk, so tampering with a delivered file
            # is detectable. The document content_hash above is a different
            # thing: it identifies the facts, not the file.
            "files": digests,
            "reason_codes": document["reason_codes"],
        }
        _write(out / MANIFEST_JSON, canonical_json(manifest))
        sys.stderr.write(f"wrote {out}/ ({document['data_state']})\n")

    if args.markdown:
        sys.stdout.write(markdown)
    else:
        sys.stdout.write(canonical_json(document))

    if args.strict and result.data_state != DATA_READY:
        return 4
    if result.data_state == DATA_REJECT:
        return 5
    return 0


def _sensitive_values(document: dict[str, Any]) -> list[tuple[str, str]]:
    """Private values from the paid dossier that must never reach the public one."""
    values: list[tuple[str, str]] = []
    identity = (document.get("sections", {}).get("identity") or {}).get("payload", {})
    for field in ("cnpj14", "razao_social", "nome_fantasia", "municipio"):
        value = identity.get(field)
        if value and value != "UNKNOWN":
            values.append((f"identity.{field}", str(value)))
    competitors = (document.get("sections", {}).get("competitors") or {}).get("payload", {})
    for competitor in competitors.get("competitors", []):
        for field in ("supplier_cnpj", "supplier_nome"):
            value = competitor.get(field)
            if value and value != "UNKNOWN":
                values.append((f"competitors.{field}", str(value)))
    return values


def _cmd_verify(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    document = json.loads((directory / DOSSIER_JSON).read_text(encoding="utf-8"))
    public = json.loads((directory / PUBLIC_JSON).read_text(encoding="utf-8"))
    manifest = json.loads((directory / MANIFEST_JSON).read_text(encoding="utf-8"))

    problems: list[str] = []
    for name, expected in (manifest.get("files") or {}).items():
        path = directory / name
        if not path.exists():
            problems.append(f"missing file: {name}")
        elif file_digest(path) != expected:
            problems.append(f"file digest mismatch: {name}")
    for name in (DOSSIER_JSON, PUBLIC_JSON, DOSSIER_MD):
        if name not in (manifest.get("files") or {}):
            problems.append(f"file not covered by the manifest: {name}")
    recomputed = content_hash(document)
    if recomputed != document.get("content_hash"):
        problems.append(f"dossier content_hash mismatch: stored={document.get('content_hash')} recomputed={recomputed}")
    recomputed_public = content_hash(public)
    if recomputed_public != public.get("content_hash"):
        problems.append("public content_hash mismatch")
    if public.get("source_dossier_hash") != document.get("content_hash"):
        problems.append("public projection is not bound to this dossier")

    markdown_path = directory / DOSSIER_MD
    markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    forbidden = scan_forbidden(document) + scan_forbidden(public) + scan_markdown(markdown, document)
    if forbidden:
        problems.append("forbidden claim content: " + ", ".join(forbidden))

    # A redacted key kept with an UNKNOWN value is not a leak; a private *value*
    # surfacing anywhere in the public body is.
    body = canonical_json(public)
    for label, value in _sensitive_values(document):
        if value and value in body:
            problems.append(f"public projection leaks {label}: {value!r}")

    if document.get("catalog_mode") == CATALOG_FIXTURE and public.get("publication_readiness") == DATA_READY:
        problems.append("fixture dossier claims publication readiness")

    report = {
        "dir": str(directory),
        "dossier_id": document.get("dossier_id"),
        "data_state": document.get("data_state"),
        "catalog_mode": document.get("catalog_mode"),
        "verdict": "PASS" if not problems else "FAIL",
        "problems": problems,
    }
    sys.stdout.write(canonical_json(report))
    return 0 if not problems else 1


def _cmd_handoff(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    public = json.loads((directory / PUBLIC_JSON).read_text(encoding="utf-8"))
    manifest = json.loads((directory / MANIFEST_JSON).read_text(encoding="utf-8"))

    # The private dossier must never reach the rendezvous.
    leaks = [label for label, value in _sensitive_values_from_dir(directory) if value in canonical_json(public)]
    if leaks:
        sys.stderr.write("refusing handoff, public projection leaks: " + ", ".join(leaks) + "\n")
        return 6

    forbidden = scan_forbidden(public)
    if forbidden:
        sys.stderr.write("refusing handoff, forbidden claim content: " + ", ".join(forbidden) + "\n")
        return 3

    root = Path(args.to) if args.to else rendezvous_dir()
    result = write_handoff(public, manifest, root)
    errors = verify_handoff(root)
    result["verify_errors"] = errors
    sys.stdout.write(canonical_json(result))
    if errors:
        return 7
    return 0 if result["decision"] == DECISION_READY else 1


def _sensitive_values_from_dir(directory: Path) -> list[tuple[str, str]]:
    document = json.loads((directory / DOSSIER_JSON).read_text(encoding="utf-8"))
    return _sensitive_values(document)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.dossier",
        description="Compose the CONFENGE B2G dossier (confenge-dossier/1.0) from canonical DataLake reads.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a dossier for one CNPJ")
    build.add_argument("--cnpj", required=True, help="14-digit supplier CNPJ")
    build.add_argument("--as-of", default=None, help="Reference date (YYYY-MM-DD). Defaults to today.")
    build.add_argument("--out", default=None, help="Output directory for the artifact set")
    build.add_argument("--dsn", default=None, help="DataLake DSN. Falls back to DATABASE_URL / LOCAL_DATALAKE_DSN.")
    build.add_argument("--fixture", default=None, help="Fixture JSON path instead of the DataLake")
    build.add_argument(
        "--claim-live",
        action="store_true",
        help="Deliberately label a fixture run as official_live. Always rejected; used by tests.",
    )
    build.add_argument("--consumer", default=CONSUMER_WEB_CFG)
    build.add_argument("--competitor-limit", type=int, default=COMPETITOR_LIMIT)
    build.add_argument("--window-days", type=int, default=EXPIRING_WINDOW_DAYS)
    build.add_argument("--observed-at", default=None, help="Override the observation timestamp (RFC3339)")
    build.add_argument(
        "--reference-scope",
        choices=REFERENCE_SCOPES,
        default=REFERENCE_SCOPE_BOTH,
        help="Reference geography. BOTH is fail-closed when the national reference is unavailable.",
    )
    build.add_argument("--markdown", action="store_true", help="Print markdown instead of JSON")
    build.add_argument("--strict", action="store_true", help="Exit non-zero unless data_state is DATA_READY")
    build.set_defaults(func=_cmd_build)

    verify = sub.add_parser("verify", help="Re-verify a written artifact set")
    verify.add_argument("--dir", required=True)
    verify.set_defaults(func=_cmd_verify)

    handoff = sub.add_parser(
        "handoff",
        help="Publish the de-identified projection to the web-cfg rendezvous (READY xor BLOCKED)",
    )
    handoff.add_argument("--dir", required=True, help="Artifact set produced by build --out")
    handoff.add_argument("--to", default=None, help="Rendezvous dir. Defaults to CONFENGE_HANDOFF_DIR layout.")
    handoff.set_defaults(func=_cmd_handoff)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
