"""Nominal gap report for entities not operationally covered."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.source_registry.builder import load_registry
from scripts.source_registry.models import OPERATIONAL_STATUSES, EntitySourceRecord

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "coverage"


def _is_gap(record: EntitySourceRecord) -> bool:
    """Entity is a gap when not operationally covered."""
    return record.access_status not in OPERATIONAL_STATUSES


def gap_rows(records: list[EntitySourceRecord]) -> list[dict[str, Any]]:
    """Build gap row dicts for non-operational entities."""
    rows: list[dict[str, Any]] = []
    for r in records:
        if not _is_gap(r):
            continue
        rows.append(
            {
                "canonical_id": r.canonical_id,
                "entity_id": r.canonical_id,
                "cnpj": r.cnpj,
                "name": r.razao_social,
                "municipio": r.municipio,
                "uf": r.uf,
                "ibge_code": r.ibge_code,
                "entity_type": r.natureza_juridica,
                "access_status": r.access_status,
                "blocker_class": r.current_blocker or "none",
                "next_action": r.next_action,
                "priority": r.priority,
                "strategy": r.collection_strategy,
                "plataformas": r.plataformas,
                "mapping_confidence": r.mapping_confidence,
            }
        )
    # Highest priority first, then name
    rows.sort(key=lambda x: (x["priority"], x["name"] or ""))
    return rows


def generate_gap_report(
    records: list[EntitySourceRecord] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate JSONL + Markdown gap report for uncovered entities.

    Outputs:
        - ``entity-source-gaps.jsonl``
        - ``entity-source-gaps.md``

    Returns:
        Summary dict with counts by blocker class.
    """
    if records is None:
        records = load_registry()

    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = gap_rows(records)
    by_blocker = Counter(r["blocker_class"] for r in rows)
    by_status = Counter(r["access_status"] for r in rows)
    by_strategy = Counter(r["strategy"] for r in rows)
    by_priority = Counter(r["priority"] for r in rows)

    generated_at = datetime.now(UTC).isoformat()
    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "total_entities": len(records),
        "operational": sum(1 for r in records if r.access_status in OPERATIONAL_STATUSES),
        "gaps": len(rows),
        "gap_pct": round(100.0 * len(rows) / len(records), 2) if records else 0.0,
        "by_blocker_class": dict(by_blocker.most_common()),
        "by_access_status": dict(by_status.most_common()),
        "by_strategy": dict(by_strategy.most_common()),
        "by_priority": {str(k): v for k, v in sorted(by_priority.items())},
    }

    jsonl_path = out_dir / "entity-source-gaps.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    md_path = out_dir / "entity-source-gaps.md"
    md_path.write_text(_render_markdown(summary, rows), encoding="utf-8")

    summary["jsonl_path"] = str(jsonl_path)
    summary["md_path"] = str(md_path)
    logger.info(
        "Gap report: %s gaps / %s entities → %s",
        summary["gaps"],
        summary["total_entities"],
        jsonl_path,
    )
    return summary


def _render_markdown(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "# Entity Source Gaps",
        "",
        f"**Generated:** {summary['generated_at']}",
        f"**Total entities:** {summary['total_entities']}",
        f"**Operational:** {summary['operational']}",
        f"**Gaps:** {summary['gaps']} ({summary['gap_pct']}%)",
        "",
        "## By blocker class",
        "",
        "| Blocker | Count |",
        "|---------|------:|",
    ]
    for blocker, count in (summary.get("by_blocker_class") or {}).items():
        lines.append(f"| `{blocker}` | {count} |")

    lines.extend(
        [
            "",
            "## By access status",
            "",
            "| Status | Count |",
            "|--------|------:|",
        ]
    )
    for status, count in (summary.get("by_access_status") or {}).items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(
        [
            "",
            "## By strategy",
            "",
            "| Strategy | Count |",
            "|----------|------:|",
        ]
    )
    for strategy, count in (summary.get("by_strategy") or {}).items():
        lines.append(f"| `{strategy}` | {count} |")

    # Top priority gaps (priority 1-2)
    top = [r for r in rows if r["priority"] <= 2][:50]
    lines.extend(
        [
            "",
            "## Priority 1–2 sample (up to 50)",
            "",
            "| Priority | Name | Município | Blocker | Next action | Strategy |",
            "|---------:|------|-----------|---------|-------------|----------|",
        ]
    )
    for r in top:
        name = (r["name"] or "")[:50].replace("|", "/")
        mun = (r["municipio"] or "")[:25].replace("|", "/")
        lines.append(
            f"| {r['priority']} | {name} | {mun} | `{r['blocker_class']}` | {r['next_action']} | `{r['strategy']}` |"
        )

    lines.append("")
    return "\n".join(lines)
