"""Dados Abertos SC CKAN inventory + schema-drift (#253)."""

from __future__ import annotations

import hashlib
from typing import Any

from scripts.complementary.contract import RunResult, sha256_json

SOURCE = "dados_abertos_sc"
LICITATION_TOKENS = ("licit", "pregão", "pregao", "edital", "compra")
EXPECTED_RESOURCE_KEYS = ("id", "url", "format", "name")


def _looks_licitation(resource: dict[str, Any]) -> bool:
    blob = " ".join(
        str(resource.get(k) or "") for k in ("name", "description", "url", "format")
    ).lower()
    return any(token in blob for token in LICITATION_TOKENS)


def inventory_resources(package: dict[str, Any]) -> list[dict[str, Any]]:
    resources = package.get("resources") or []
    pkg_blob = {
        "name": package.get("name"),
        "description": package.get("notes") or package.get("title"),
        "url": "",
        "format": "",
    }
    pkg_is_licitation = _looks_licitation(pkg_blob)
    out: list[dict[str, Any]] = []
    for res in resources:
        if not isinstance(res, dict):
            continue
        if not pkg_is_licitation and not _looks_licitation(res) and package.get("include_all") is not True:
            continue
        rec = {
            "package_id": package.get("id") or package.get("name"),
            "resource_id": res.get("id"),
            "url": res.get("url"),
            "format": str(res.get("format") or "").upper(),
            "period": res.get("temporal_coverage") or res.get("periodo") or res.get("name"),
            "objeto": res.get("objeto") or res.get("name") or package.get("title"),
            "last_modified": res.get("last_modified") or res.get("metadata_modified"),
            "hash": res.get("hash") or hashlib.sha256(str(res.get("url") or "").encode("utf-8")).hexdigest(),
        }
        out.append(rec)
    return out


def schema_drift(resource: dict[str, Any], columns: list[str], expected: list[str]) -> list[str]:
    missing = [col for col in expected if col not in set(columns)]
    if missing:
        return missing
    for key in EXPECTED_RESOURCE_KEYS:
        if not resource.get(key) and key != "name":
            missing.append(key)
    return missing


def _norm_objeto(text: str | None) -> str:
    return " ".join(str(text or "").lower().split())


def merge_lineage_with_sc_compras(
    dados_abertos_rows: list[dict[str, Any]],
    sc_compras_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Dedup Dados Abertos SC against SC Compras without dropping lineage.

    A match keeps both source identities, official IDs and URLs. Dropping the
    SC Compras side is a contract violation.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for sc in sc_compras_rows:
        key = _norm_objeto(str(sc.get("objeto") or sc.get("descricao") or ""))
        if key:
            index.setdefault(key, []).append(sc)
    merged: list[dict[str, Any]] = []
    for row in dados_abertos_rows:
        item = dict(row)
        lineage = [
            {
                "source": SOURCE,
                "source_id": row.get("resource_id"),
                "url": row.get("url"),
                "hash": row.get("hash"),
            }
        ]
        key = _norm_objeto(str(row.get("objeto") or row.get("period") or row.get("name") or ""))
        matches = index.get(key, [])
        for sc in matches:
            sc_id = sc.get("source_id") or sc.get("id")
            sc_url = sc.get("url") or sc.get("official_url")
            if not sc_id or not sc_url:
                continue
            lineage.append(
                {
                    "source": "sc_compras",
                    "source_id": sc_id,
                    "url": sc_url,
                    "hash": sc.get("content_hash") or sc.get("hash"),
                }
            )
        item["lineage"] = lineage
        item["matched_sc_compras"] = any(link["source"] == "sc_compras" for link in lineage)
        merged.append(item)
    return merged


def run_inventory(
    packages: list[dict[str, Any]],
    *,
    processed_ids: set[str] | None = None,
    truncated: bool = False,
    drift: list[str] | None = None,
    sc_compras_rows: list[dict[str, Any]] | None = None,
) -> RunResult:
    processed = processed_ids or set()
    rows: list[dict[str, Any]] = []
    for pkg in packages:
        rows.extend(inventory_resources(pkg))
    if sc_compras_rows:
        rows = merge_lineage_with_sc_compras(rows, sc_compras_rows)
    if drift:
        return RunResult(
            SOURCE,
            "FAILED",
            fetched=len(rows),
            persisted=0,
            deduplicated=0,
            failed=len(rows),
            records=rows,
            reason=f"schema_drift:{','.join(drift)}",
        )
    if truncated:
        return RunResult(
            SOURCE,
            "partial",
            fetched=len(rows),
            persisted=len(processed),
            deduplicated=0,
            failed=0,
            records=rows,
            reason="truncated_resources",
        )
    remaining = [r for r in rows if r.get("resource_id") not in processed]
    if remaining:
        return RunResult(
            SOURCE,
            "partial",
            fetched=len(rows),
            persisted=len(processed),
            deduplicated=0,
            failed=0,
            records=rows,
            reason="resources_remaining",
        )
    terminal = "ZERO_CONFIRMED" if not rows else "success"
    return RunResult(
        SOURCE,
        terminal,
        fetched=len(rows),
        persisted=len(processed),
        deduplicated=0,
        failed=0,
        records=rows,
        job={"content_hash": sha256_json(rows)},
    )
