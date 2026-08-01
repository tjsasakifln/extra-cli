"""Extra client profile calibration — list missing critical fields, import, version.

Never invent PENDING values. Blocks personalized P4/P5 while critical fields missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CRITICAL_FIELDS = (
    "margem_minima",
    "capital_giro",
    "capacidade_garantia",
    "capacidade_simultanea",
    "equipe",
    "contratos_correntes",
    "risco_aceitavel",
)

# nested operational_capacity paths in extra.yaml
CRITICAL_NESTED = {
    "margem_minima": ("operational_capacity", "margem_minima"),
    "capital_giro": ("operational_capacity", "capital_giro"),
    "capacidade_garantia": ("operational_capacity", "capacidade_garantia"),
    "capacidade_simultanea": ("operational_capacity", "capacidade_simultanea"),
    "equipe": ("operational_capacity", "equipe"),
    "contratos_correntes": ("operational_capacity", "contratos_correntes"),
    "risco_aceitavel": ("operational_capacity", "risco_aceitavel"),
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def profile_path(client: str = "extra_construtora") -> Path:
    # file is extra.yaml for extra_construtora
    name = "extra.yaml" if "extra" in client else f"{client}.yaml"
    return _project_root() / "config" / "client_profiles" / name


def load_profile(client: str = "extra_construtora") -> dict[str, Any]:
    path = profile_path(client)
    if not path.exists():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _status_pending(node: Any) -> bool:
    if node is None:
        return True
    if isinstance(node, dict):
        st = str(node.get("status") or "").upper()
        if st in {"PENDING", "PENDING_ELICITATION"}:
            return True
        if node.get("value") is None and node.get("amount") is None and "status" in node:
            return st != "SET"
        return False
    return False


def list_missing_critical(profile: dict[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    op = profile.get("operational_capacity") or profile.get("capacity") or {}
    top_level_pending = set(profile.get("pending_fields") or [])

    for field in CRITICAL_FIELDS:
        node = op.get(field) if isinstance(op, dict) else None
        top = profile.get(field)
        pending = False
        reason = ""
        if field in top_level_pending:
            pending = True
            reason = "listed in pending_fields"
        elif _status_pending(node):
            pending = True
            reason = f"operational_capacity.{field} status PENDING or empty"
        elif top is None and node is None:
            pending = True
            reason = "field absent"
        elif top is None and isinstance(node, dict) and node.get("value") is None:
            # check SET with null value
            if str(node.get("status", "")).upper() != "SET":
                pending = True
                reason = "null value without SET"
        if pending:
            missing.append(
                {
                    "field": field,
                    "reason": reason,
                    "required_for": ["EXTRA_WIN_PROBABILITY_AVAILABLE", "OPTIMAL_BID_RECOMMENDATION_AVAILABLE"],
                }
            )
    return missing


def personalization_blockers(client: str = "extra_construtora") -> dict[str, Any]:
    profile = load_profile(client)
    missing = list_missing_critical(profile)
    return {
        "client": client,
        "profile_id": profile.get("profile_id"),
        "profile_version": profile.get("version"),
        "missing_critical": missing,
        "personalization_allowed": len(missing) == 0,
        "p4_claim": "DATA_BLOCKED" if missing else "IMPLEMENTED",
        "p5_claim": "DATA_BLOCKED" if missing else "IMPLEMENTED",
        "notes": [
            "Do not invent PENDING values",
            "Population market win likelihood must use CALIBRATED_MARKET_WIN_LIKELIHOOD naming",
            "EXTRA_WIN_PROBABILITY_AVAILABLE requires Extra outcome sample or hierarchical pooling + full profile",
        ],
    }


def generate_form(client: str = "extra_construtora") -> dict[str, Any]:
    profile = load_profile(client)
    missing = list_missing_critical(profile)
    form = {
        "client": client,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instructions": "Preencha apenas campos com evidência real. Não invente.",
        "fields": [
            {
                "field": m["field"],
                "value": None,
                "unit": "BRL" if "capital" in m["field"] or "margem" in m["field"] else "text",
                "reason_missing": m["reason"],
            }
            for m in missing
        ],
    }
    return form


def import_responses(
    responses: dict[str, Any],
    *,
    client: str = "extra_construtora",
    author: str = "unknown",
    source: str = "elicitation",
) -> dict[str, Any]:
    """Version responses under artifacts/predictive/profiles/ — does not invent."""
    out_dir = _project_root() / "artifacts" / "predictive" / "profiles" / client
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("v*.json"))
    version = len(existing) + 1
    # validate types lightly
    fields = responses.get("fields") or responses
    cleaned: dict[str, Any] = {}
    errors: list[str] = []
    iterable = fields if isinstance(fields, dict) else {
        f["field"]: f.get("value") for f in fields
    }
    for k, v in iterable.items():
        if v is None or v == "":
            errors.append(f"{k}: empty")
            continue
        cleaned[k] = v
    payload = {
        "client": client,
        "version": version,
        "author": author,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "values": cleaned,
        "errors": errors,
        "complete": not errors and set(CRITICAL_FIELDS).issubset(cleaned.keys()),
    }
    path = out_dir / f"v{version:03d}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(path), **payload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extra profile calibration for predictive P4/P5")
    parser.add_argument("--client", default="extra_construtora")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-missing", help="List critical PENDING fields")
    sub.add_parser("form", help="Generate editable form JSON")
    p_imp = sub.add_parser("import", help="Import filled form JSON")
    p_imp.add_argument("--file", required=True)
    p_imp.add_argument("--author", default="operator")
    sub.add_parser("blockers", help="JSON blockers for P4/P5")

    # also allow: python -m scripts.predictive.profile_calibration --client X  (defaults to blockers)
    args = parser.parse_args(argv)

    if args.cmd == "list-missing":
        profile = load_profile(args.client)
        print(json.dumps(list_missing_critical(profile), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "form":
        print(json.dumps(generate_form(args.client), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "import":
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        result = import_responses(data, client=args.client, author=args.author)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("complete") else 2
    if args.cmd == "blockers":
        print(json.dumps(personalization_blockers(args.client), indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    # Support: python -m scripts.predictive.profile_calibration --client extra_construtora
    # without subcommand → blockers
    raw = sys.argv[1:]
    if raw and raw[0].startswith("--") and "list-missing" not in raw and "form" not in raw and "import" not in raw and "blockers" not in raw:
        # inject blockers
        sys.exit(main(raw + ["blockers"]))
    if not raw:
        sys.exit(main(["blockers"]))
    sys.exit(main(raw))
