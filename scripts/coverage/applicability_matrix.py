#!/usr/bin/env python3
"""Entity × source × capability applicability matrix (DoD §7.2).

Uses config/source_applicability.yaml + crawl registry capabilities.
Produces decisions with justification, validation date, decision source.
Never silently substitutes complementary for mandatory sources.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.registry import export_registry, lookup  # noqa: E402

Capability = Literal["open_tenders", "historical_contracts"]
Decision = Literal["applicable", "not_applicable", "unknown"]

DEFAULT_APPLICABILITY = _PROJECT_ROOT / "config" / "source_applicability.yaml"
DEFAULT_UNIVERSE_CSV = _PROJECT_ROOT / "config" / "target_entities_200km.csv"

# Explicit minimum combination for Extra (DoD §7.2)
MIN_SOURCE_COMBINATION: dict[str, list[str]] = {
    "open_tenders": ["pncp", "ciga_ckan"],  # primary pair; sc_compras complementary for SC state
    "historical_contracts": ["pncp", "contracts"],
}
MANDATORY_SOURCES: dict[str, list[str]] = {
    "open_tenders": ["pncp"],
    "historical_contracts": ["pncp"],
}


@dataclass
class ApplicabilityDecision:
    entity_id: str
    source: str
    capability: Capability
    decision: Decision
    justification: str
    validated_at: str
    decision_source: str
    role: str = "complementary"
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None  # type: ignore
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    # minimal fallback: empty
    return {}


def load_applicability_config(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_APPLICABILITY
    if not p.is_file():
        return {"version": "missing", "sources": {}}
    return _load_yaml(p)


def load_universe_entities(csv_path: Path | None = None, limit: int | None = None) -> list[dict[str, str]]:
    import csv

    p = csv_path or DEFAULT_UNIVERSE_CSV
    if not p.is_file():
        return []
    rows: list[dict[str, str]] = []
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            if limit is not None and i >= limit:
                break
            rows.append({k: (v or "").strip() for k, v in row.items()})
    return rows


def _entity_id(row: dict[str, str], idx: int) -> str:
    return (
        row.get("canonical_id")
        or row.get("entity_id")
        or row.get("cnpj")
        or row.get("cnpj_8")
        or row.get("id")
        or f"entity-{idx}"
    )


def _match_rule(rules: list[dict[str, Any]], esfera: str, natureza: str) -> dict[str, Any] | None:
    best = None
    best_pri = -1
    for rule in rules:
        filt = rule.get("filter") or {}
        ef = str(filt.get("esfera", "*"))
        nf = str(filt.get("natureza", "*"))
        if ef not in ("*", esfera) and ef != esfera:
            continue
        if nf not in ("*", natureza) and nf != natureza:
            continue
        pri = int(rule.get("priority") or 0)
        if pri >= best_pri:
            best_pri = pri
            best = rule
    return best


def decide_for_entity_source(
    *,
    entity: dict[str, str],
    entity_id: str,
    source_name: str,
    capability: Capability,
    cfg: dict[str, Any],
    registry_role: str,
    validated_at: str,
) -> ApplicabilityDecision:
    sources_cfg = (cfg.get("sources") or {})
    src_cfg = sources_cfg.get(source_name) or sources_cfg.get(source_name.replace("_", "-")) or {}
    # contracts capability rides on PNCP federal applicability when no dedicated rules
    if not src_cfg and source_name in {"contracts", "pncp_contracts"}:
        src_cfg = sources_cfg.get("pncp") or {}
    reg = lookup(source_name)
    caps = list(reg.capabilities) if reg else []
    if capability not in caps and reg is not None:
        return ApplicabilityDecision(
            entity_id=entity_id,
            source=source_name,
            capability=capability,
            decision="not_applicable",
            justification=f"Source {source_name} does not declare capability {capability}",
            validated_at=validated_at,
            decision_source="scripts.crawl.registry.capabilities",
            role=registry_role,
        )

    esfera = (entity.get("esfera") or entity.get("sphere") or "municipal").lower()
    natureza = (entity.get("natureza") or entity.get("natureza_juridica") or entity.get("entity_type") or "*").lower()
    # normalize natureza shortcuts
    if "pref" in natureza:
        natureza = "pref"
    elif "cam" in natureza:
        natureza = "cam"

    rules = src_cfg.get("rules") or []
    if not rules and not src_cfg:
        # no config — unknown for this source
        return ApplicabilityDecision(
            entity_id=entity_id,
            source=source_name,
            capability=capability,
            decision="unknown",
            justification="No applicability rules in source_applicability.yaml for this source",
            validated_at=validated_at,
            decision_source="config/source_applicability.yaml:missing",
            role=registry_role,
            blockers=["unknown_applicability"],
        )

    default_app = bool(src_cfg.get("default_applicable", True))
    rule = _match_rule(rules, esfera, natureza) if rules else None
    if rule is None:
        decision: Decision = "applicable" if default_app else "not_applicable"
        just = f"default_applicable={default_app} (no matching rule)"
        dsrc = "config/source_applicability.yaml:default"
    else:
        decision = "applicable" if rule.get("applicable") else "not_applicable"
        just = str(rule.get("reason") or "rule matched")
        dsrc = "config/source_applicability.yaml:rule"

    return ApplicabilityDecision(
        entity_id=entity_id,
        source=source_name,
        capability=capability,
        decision=decision,
        justification=just,
        validated_at=validated_at,
        decision_source=dsrc,
        role=registry_role,
    )


def build_matrix(
    *,
    entities: list[dict[str, str]] | None = None,
    cfg: dict[str, Any] | None = None,
    sources: list[str] | None = None,
    capabilities: list[Capability] | None = None,
    limit_entities: int | None = 50,
    validated_at: str | None = None,
) -> dict[str, Any]:
    validated_at = validated_at or date.today().isoformat()
    cfg = cfg if cfg is not None else load_applicability_config()
    entities = entities if entities is not None else load_universe_entities(limit=limit_entities)
    reg = {r["id"]: r for r in export_registry()}
    source_names = sources or list(reg.keys())
    caps: list[Capability] = capabilities or ["open_tenders", "historical_contracts"]

    decisions: list[ApplicabilityDecision] = []
    for i, ent in enumerate(entities):
        eid = _entity_id(ent, i)
        for src in source_names:
            role = (reg.get(src) or {}).get("role") or "complementary"
            for cap in caps:
                decisions.append(
                    decide_for_entity_source(
                        entity=ent,
                        entity_id=eid,
                        source_name=src,
                        capability=cap,
                        cfg=cfg,
                        registry_role=role,
                        validated_at=validated_at,
                    )
                )

    unknowns = [d for d in decisions if d.decision == "unknown"]
    blockers_by_entity: dict[str, list[str]] = {}
    blockers_by_source: dict[str, list[str]] = {}
    blockers_by_capability: dict[str, list[str]] = {}
    for d in decisions:
        for b in d.blockers:
            blockers_by_entity.setdefault(d.entity_id, []).append(f"{d.source}:{d.capability}:{b}")
            blockers_by_source.setdefault(d.source, []).append(f"{d.entity_id}:{d.capability}:{b}")
            blockers_by_capability.setdefault(d.capability, []).append(f"{d.entity_id}:{d.source}:{b}")

    # complementary must not replace mandatory
    substitution_guard = {
        "rule": "complementary_sources_do_not_replace_mandatory",
        "mandatory": MANDATORY_SOURCES,
        "min_combination": MIN_SOURCE_COMBINATION,
        "enforced": True,
    }

    # gate: zero unknown on necessary pairs (mandatory sources × entities)
    necessary_unknowns = [
        d
        for d in unknowns
        if d.source in MANDATORY_SOURCES.get(d.capability, [])
    ]
    gate = {
        "zero_necessary_unknowns": len(necessary_unknowns) == 0,
        "n_necessary_unknowns": len(necessary_unknowns),
        "n_unknown_total": len(unknowns),
    }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "config_version": cfg.get("version"),
        "n_entities": len(entities),
        "n_sources": len(source_names),
        "n_decisions": len(decisions),
        "min_source_combination": MIN_SOURCE_COMBINATION,
        "mandatory_sources": MANDATORY_SOURCES,
        "substitution_guard": substitution_guard,
        "gate": gate,
        "blockers": {
            "by_entity_sample": {k: v[:5] for k, v in list(blockers_by_entity.items())[:20]},
            "by_source": {k: len(v) for k, v in blockers_by_source.items()},
            "by_capability": {k: len(v) for k, v in blockers_by_capability.items()},
        },
        "unknown_gaps": [d.to_dict() for d in unknowns[:200]],
        "decisions_sample": [d.to_dict() for d in decisions[:100]],
        "decisions": [d.to_dict() for d in decisions],
        "claims": {
            "allowed": [
                "Applicability matrix generated with justification and decision_source",
                "Minimum source combination is explicit",
            ],
            "forbidden": ["LOCAL_READY", "operational coverage 95%", "zero unknown universe-wide without full run"],
        },
    }


def write_matrix(out_dir: Path, matrix: dict[str, Any]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # full decisions can be large — write summary + gaps + sample
    summary = {k: v for k, v in matrix.items() if k != "decisions"}
    path = out_dir / "applicability-matrix.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    # CSV of sample decisions
    import csv

    sample = matrix.get("decisions") or matrix.get("decisions_sample") or []
    csv_path = out_dir / "applicability-decisions-sample.csv"
    if sample:
        keys = list(sample[0].keys())
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for row in sample[:5000]:
                w.writerow(row)
    gaps_path = out_dir / "unknown-gaps.json"
    gaps_path.write_text(
        json.dumps(matrix.get("unknown_gaps") or [], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §7.2 applicability matrix")
    p.add_argument("--out", type=Path, default=Path("output/applicability-matrix"))
    p.add_argument("--limit-entities", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.add_argument("--full-universe", action="store_true", help="Use all CSV entities (slow)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build matrix in memory; do not write output files",
    )
    args = p.parse_args(argv)
    limit = None if args.full_universe else args.limit_entities
    matrix = build_matrix(limit_entities=limit)
    if args.dry_run:
        slim = {k: matrix[k] for k in matrix if k not in ("decisions",)}
        slim["dry_run"] = True
        slim["would_write"] = str(args.out)
        print(json.dumps(slim, indent=2, ensure_ascii=False, default=str)[:8000])
        return 0 if matrix["gate"]["zero_necessary_unknowns"] else 1
    path = write_matrix(args.out, matrix)
    slim = {k: matrix[k] for k in matrix if k not in ("decisions",)}
    if args.json:
        print(json.dumps(slim, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"entities={matrix['n_entities']} decisions={matrix['n_decisions']} gate={matrix['gate']}")
        print(f"wrote {path}")
    return 0 if matrix["gate"]["zero_necessary_unknowns"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
