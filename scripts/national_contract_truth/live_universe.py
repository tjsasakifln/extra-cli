"""#302 live runner: official PNCP publishing-org denominator.

Never substitutes Extra's 1.093-entity commercial universe. nacional_completo
is true only when every catalog partition closes FOUND or ZERO_CONFIRMED with
evidence. Unconsulted partitions stay BLOCKED.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.national_contract_truth.national_universe import (
    EXTRA_COMMERCIAL_DENOMINATOR,
    NationalUniverseError,
    PartitionResult,
    PublishingOrg,
    build_universe,
    reconcile_partitions,
    sha256_payload,
)

SCHEMA = "national-universe/1.0"
PNCP_ORGAOS = "https://pncp.gov.br/api/pncp/v1/orgaos"
USER_AGENT = "extra-cli-national-universe/1.0"
DEFAULT_PAGE_SIZE = 50


class OfficialSourceError(RuntimeError):
    """Official catalog could not be fetched or parsed."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_orgaos_catalog(raw: bytes | str | list[Any] | dict[str, Any]) -> tuple[PublishingOrg, ...]:
    if isinstance(raw, (bytes, bytearray)):
        payload = json.loads(raw.decode("utf-8"))
    elif isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw
    if isinstance(payload, dict):
        items = payload.get("data") or payload.get("orgaos") or payload.get("items") or []
    else:
        items = payload
    if not isinstance(items, list):
        raise OfficialSourceError("official orgaos catalog is not a list")
    orgs: list[PublishingOrg] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        org_id = str(item.get("cnpj") or item.get("org_id") or "").strip()
        if not org_id or org_id in seen:
            continue
        seen.add(org_id)
        orgs.append(
            PublishingOrg(
                org_id=org_id,
                source="pncp",
                competence=str(item.get("competence") or ""),
                name=str(item.get("razaoSocial") or item.get("name") or org_id),
                unit_count=1,
            )
        )
    if not orgs:
        raise OfficialSourceError("official orgaos catalog produced zero publishing orgs")
    return tuple(orgs)


def fetch_orgaos_page(*, pagina: int, tamanho: int, timeout: int = 60) -> bytes:
    params = urllib.parse.urlencode({"pagina": str(pagina), "tamanhoPagina": str(tamanho)})
    url = f"{PNCP_ORGAOS}?{params}"
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — HTTPS official PNCP
            return response.read()
    except urllib.error.HTTPError as exc:
        raise OfficialSourceError(f"http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise OfficialSourceError(f"url_error:{exc.reason}") from exc


def fetch_official_catalog(*, max_orgs: int | None = None, timeout: int = 90) -> tuple[bytes, tuple[PublishingOrg, ...]]:
    raw = fetch_orgaos_page(pagina=1, tamanho=DEFAULT_PAGE_SIZE, timeout=timeout)
    orgs = parse_orgaos_catalog(raw)
    if max_orgs is not None:
        orgs = orgs[: max(0, max_orgs)]
    if not orgs:
        raise OfficialSourceError("official catalog empty after max_orgs trim")
    return raw, orgs


def close_partitions(
    orgs: tuple[PublishingOrg, ...],
    *,
    observed_org_ids: set[str],
    observed_evidence: dict[str, str] | None = None,
    consult_limit: int | None = None,
) -> tuple[PartitionResult, ...]:
    evidence_by_org = observed_evidence or {}
    results: list[PartitionResult] = []
    for index, org in enumerate(orgs):
        if consult_limit is not None and index >= consult_limit and org.org_id not in observed_org_ids:
            results.append(
                PartitionResult(
                    partition_id=org.org_id,
                    status="BLOCKED",
                    evidence="not_consulted_this_run",
                )
            )
            continue
        if org.org_id in observed_org_ids:
            results.append(
                PartitionResult(
                    partition_id=org.org_id,
                    status="FOUND",
                    evidence=evidence_by_org.get(org.org_id) or f"observed_official_contract:{org.org_id}",
                )
            )
            continue
        results.append(
            PartitionResult(
                partition_id=org.org_id,
                status="BLOCKED",
                evidence="not_consulted_this_run",
            )
        )
    return tuple(results)


def build_denominator_report(
    *,
    competence: str,
    cutoff: str,
    orgs: tuple[PublishingOrg, ...],
    partitions: tuple[PartitionResult, ...],
    raw_hash: str,
    method: str = "pncp-orgaos-publicantes-v1",
    catalog_error: str | None = None,
) -> dict[str, Any]:
    tagged = tuple(
        PublishingOrg(
            org_id=org.org_id,
            source=org.source or "pncp",
            competence=org.competence or competence,
            name=org.name,
            unit_count=org.unit_count,
        )
        for org in orgs
    )
    extra_1093 = False
    blockers: list[str] = []
    reconciliation: dict[str, Any] = {
        "schema_version": SCHEMA,
        "nacional_completo": False,
        "extra_1093_used_as_denominator": False,
        "extra_commercial_denominator": EXTRA_COMMERCIAL_DENOMINATOR,
        "blockers": blockers,
    }
    if catalog_error:
        blockers.append(catalog_error)
    try:
        universe = build_universe(
            source="pncp",
            competence=competence,
            cutoff=cutoff,
            orgs=tagged,
            method=method,
        )
        try:
            reconciliation = reconcile_partitions(universe, partitions)
        except NationalUniverseError as exc:
            blockers.append(str(exc))
            reconciliation = {
                "schema_version": SCHEMA,
                "national_universe_id": universe.national_universe_id,
                "source": universe.source,
                "competence": universe.competence,
                "cutoff": universe.cutoff,
                "catalog_hash": universe.catalog_hash,
                "org_count": universe.org_count,
                "unit_count": universe.unit_count,
                "method": universe.method,
                "expected_partitions": universe.org_count,
                "consulted_partitions": len(partitions),
                "by_status": _count_status(partitions),
                "nacional_completo": False,
                "extra_1093_used_as_denominator": False,
                "extra_commercial_denominator": EXTRA_COMMERCIAL_DENOMINATOR,
                "blockers": blockers,
            }
            reconciliation["reconciliation_hash"] = sha256_payload(reconciliation)
        else:
            if reconciliation.get("extra_1093_used_as_denominator"):
                extra_1093 = True
    except NationalUniverseError as exc:
        blockers.append(str(exc))
        reconciliation["blockers"] = blockers

    if extra_1093 or tagged and len(tagged) == EXTRA_COMMERCIAL_DENOMINATOR:
        # A catalog that happens to have 1093 orgs is still official; only the Extra commercial set is forbidden.
        pass

    by_status = reconciliation.get("by_status") or _count_status(partitions)
    report = {
        "schema_version": SCHEMA,
        "national_universe_id": reconciliation.get("national_universe_id"),
        "source": "pncp",
        "competence": competence,
        "cutoff": cutoff,
        "method": method,
        "raw_catalog_hash": raw_hash,
        "catalog_hash": reconciliation.get("catalog_hash"),
        "reconciliation_hash": reconciliation.get("reconciliation_hash"),
        "org_count": reconciliation.get("org_count", len(tagged)),
        "unit_count": reconciliation.get("unit_count", len(tagged)),
        "expected_partitions": reconciliation.get("expected_partitions", len(tagged)),
        "consulted_partitions": reconciliation.get("consulted_partitions", len(partitions)),
        "by_status": by_status,
        "nacional_completo": bool(reconciliation.get("nacional_completo")),
        "extra_1093_used_as_denominator": False,
        "extra_commercial_denominator": EXTRA_COMMERCIAL_DENOMINATOR,
        "blockers": list(reconciliation.get("blockers") or blockers),
        "orgs": [
            {
                "org_id": org.org_id,
                "source": org.source or "pncp",
                "competence": org.competence or competence,
                "name": org.name,
                "unit_count": org.unit_count,
            }
            for org in tagged
        ],
        "partitions": [
            {
                "partition_id": part.partition_id,
                "status": part.status,
                "evidence": part.evidence,
            }
            for part in partitions
        ],
        "publish_blockers": _publish_blockers(by_status, reconciliation.get("nacional_completo"), blockers),
    }
    if report["nacional_completo"] is True and (
        by_status.get("BLOCKED") or by_status.get("FAILED") or report["blockers"]
    ):
        report["nacional_completo"] = False
        report["publish_blockers"].append("nacional_completo_refused")
    return report


def _count_status(partitions: tuple[PartitionResult, ...]) -> dict[str, int]:
    counts = {"FOUND": 0, "ZERO_CONFIRMED": 0, "BLOCKED": 0, "FAILED": 0}
    for part in partitions:
        counts[str(part.status)] = counts.get(str(part.status), 0) + 1
    return counts


def _publish_blockers(by_status: dict[str, Any], nacional_completo: Any, blockers: list[str]) -> list[str]:
    codes = list(blockers)
    if by_status.get("BLOCKED"):
        codes.append("blocked_or_failed_partitions")
    if by_status.get("FAILED"):
        codes.append("blocked_or_failed_partitions")
    if not nacional_completo:
        codes.append("national_denominator_incomplete")
    # preserve order, unique
    seen: set[str] = set()
    ordered: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def run_live_universe(
    *,
    competence: str,
    cutoff: str | None = None,
    observed_org_ids: set[str] | None = None,
    observed_evidence: dict[str, str] | None = None,
    max_orgs: int | None = None,
    consult_limit: int | None = None,
    catalog_raw: bytes | None = None,
) -> dict[str, Any]:
    as_of = cutoff or utc_now()
    observed = observed_org_ids or set()
    try:
        if catalog_raw is None:
            raw, orgs = fetch_official_catalog(max_orgs=None)
        else:
            raw = catalog_raw
            orgs = parse_orgaos_catalog(raw)
        official_count = len(orgs)
        truncated = False
        if max_orgs is not None and official_count > max_orgs:
            orgs = orgs[: max(0, max_orgs)]
            truncated = True
        raw_hash = sha256_payload({"bytes": len(raw), "sha256": __import__("hashlib").sha256(raw).hexdigest()})
        partitions = close_partitions(
            orgs,
            observed_org_ids=observed,
            observed_evidence=observed_evidence,
            consult_limit=consult_limit,
        )
        report = build_denominator_report(
            competence=competence,
            cutoff=as_of,
            orgs=orgs,
            partitions=partitions,
            raw_hash=raw_hash,
        )
        report["official_catalog_org_count"] = official_count
        report["catalog_truncated"] = truncated
        if truncated:
            report["nacional_completo"] = False
            blockers = list(report.get("blockers") or [])
            blockers.append("catalog_truncated")
            report["blockers"] = blockers
            publish = list(report.get("publish_blockers") or [])
            if "catalog_truncated" not in publish:
                publish.append("catalog_truncated")
            if "national_denominator_incomplete" not in publish:
                publish.append("national_denominator_incomplete")
            report["publish_blockers"] = publish
        return report
    except OfficialSourceError as exc:
        failed = PartitionResult(partition_id="catalog", status="FAILED", evidence=str(exc))
        return build_denominator_report(
            competence=competence,
            cutoff=as_of,
            orgs=(),
            partitions=(failed,),
            raw_hash="",
            catalog_error=f"official_catalog:{exc}",
        )


def load_observed_orgs(path: str | Path) -> set[str]:
    text = Path(path).read_text(encoding="utf-8")
    if path and str(path).endswith(".json"):
        payload = json.loads(text)
        if isinstance(payload, list):
            return {str(item) for item in payload}
        return {str(item) for item in payload.get("org_ids") or payload.get("orgaos") or []}
    return {line.strip() for line in text.splitlines() if line.strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m scripts.national_contract_truth.live_universe")
    parser.add_argument("--competence", required=True)
    parser.add_argument("--cutoff", default=None)
    parser.add_argument("--observed-orgs", default=None, help="JSON list or newline CNPJ file")
    parser.add_argument("--catalog-json", default=None, help="Official catalog JSON (skip HTTP)")
    parser.add_argument("--max-orgs", type=int, default=None)
    parser.add_argument("--consult-limit", type=int, default=None)
    parser.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    observed: set[str] = set()
    if args.observed_orgs:
        observed = load_observed_orgs(args.observed_orgs)
    catalog_raw = None
    if args.catalog_json:
        catalog_raw = Path(args.catalog_json).read_bytes()
    report = run_live_universe(
        competence=args.competence,
        cutoff=args.cutoff,
        observed_org_ids=observed,
        max_orgs=args.max_orgs,
        consult_limit=args.consult_limit,
        catalog_raw=catalog_raw,
    )
    out = Path(args.out)
    if out.suffix.lower() == ".json":
        path = out
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out.mkdir(parents=True, exist_ok=True)
        path = out / "national-denominator.json"
    path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "path": str(path),
                "nacional_completo": report["nacional_completo"],
                "org_count": report["org_count"],
                "by_status": report["by_status"],
                "catalog_hash": report["catalog_hash"],
                "extra_1093_used_as_denominator": report["extra_1093_used_as_denominator"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
