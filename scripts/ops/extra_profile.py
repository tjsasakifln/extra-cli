#!/usr/bin/env python3
"""Canonical Extra Construtora operational profile CLI.

Commands (CLI-first, no web UI):

  python3 -m scripts.ops.extra_profile init
  python3 -m scripts.ops.extra_profile validate
  python3 -m scripts.ops.extra_profile show
  python3 -m scripts.ops.extra_profile diff --other PATH
  python3 -m scripts.ops.extra_profile intake
  python3 -m scripts.ops.extra_profile stamp

Does not invent capacity/CAT/guarantee values. Absence stays UNKNOWN /
NOT_PROVIDED / PENDING — never treated as capacity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml"
CANONICAL_REL = "config/client_profiles/extra.yaml"
SCHEMA = "extra-operational-profile/1.1"

# Sentinel tokens that MUST NOT be read as positive capacity
ABSENCE_TOKENS = frozenset(
    {
        "UNKNOWN",
        "NOT_PROVIDED",
        "NOT_APPLICABLE",
        "PENDING",
        "N/A",
        "NA",
        "NONE",
        "NULL",
        "",
    }
)

# Fields that block GO / ACTIONABLE when missing (honest capacity)
CRITICAL_CAPACITY_KEYS = (
    "capital_giro",
    "capacidade_garantia",
    "capacidade_simultanea",
    "cats_atestados",
    "margem_minima",
)

REQUIRED_TOP_LEVEL = (
    "profile_id",
    "display_name",
    "version",
    "identity",
    "region",
    "desired_object_types",
    "hard_blocks",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_raw(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_PROFILE)
    if not p.is_file():
        raise FileNotFoundError(f"Profile not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Profile must be a YAML mapping")
    return raw


def is_absent(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().upper() in ABSENCE_TOKENS:
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    if isinstance(value, dict):
        status = str(value.get("status") or "").upper()
        if status in {"PENDING", "UNKNOWN", "NOT_PROVIDED"}:
            return True
    return False


def field_provenance(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """Origin/date metadata when present; else explicit NOT_PROVIDED."""
    elic = raw.get("elicitation") if isinstance(raw.get("elicitation"), dict) else {}
    meta = elic.get(key) if isinstance(elic.get(key), dict) else None
    val = raw.get(key)
    if meta is None and isinstance(raw.get("capacity"), dict):
        # nested capacity map may hold status
        cap = raw["capacity"]
        if key in ("capital_giro", "capacidade_garantia", "capacidade_simultanea"):
            meta = {"status": cap.get("status"), "source": "capacity_block"}
    if is_absent(val) and not meta:
        return {
            "value_state": "NOT_PROVIDED" if key in (raw.get("elicitation_queue") or []) else "UNKNOWN",
            "source": None,
            "as_of": None,
        }
    if meta:
        return {
            "value_state": str(meta.get("status") or ("CONFIRMED" if not is_absent(val) else "PENDING")),
            "source": meta.get("source") or meta.get("origin"),
            "as_of": meta.get("as_of") or meta.get("date") or meta.get("updated_at"),
        }
    return {
        "value_state": "CONFIRMED" if not is_absent(val) else "UNKNOWN",
        "source": "profile_yaml",
        "as_of": raw.get("version_date"),
    }


def profile_hash(path: Path | str | None = None, raw: dict[str, Any] | None = None) -> str:
    """Stable hash of canonical YAML bytes (preferred) or serialized raw."""
    if path is not None or raw is None:
        p = Path(path or DEFAULT_PROFILE)
        return sha256_file(p)
    # deterministic JSON of raw (sorted)
    payload = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return sha256_bytes(payload)


def stamp(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_PROFILE)
    raw = load_raw(p)
    h = profile_hash(p)
    return {
        "schema": SCHEMA,
        "profile_path": CANONICAL_REL if p.resolve() == DEFAULT_PROFILE.resolve() else str(p),
        "profile_id": raw.get("profile_id"),
        "display_name": raw.get("display_name"),
        "version": raw.get("version"),
        "version_date": raw.get("version_date"),
        "profile_hash": h,
        "stamp": f"{raw.get('profile_id')}@v{raw.get('version')}:{h[:12]}",
        "stamped_at": utc_now(),
    }


def critical_pending(raw: dict[str, Any]) -> list[str]:
    pending: list[str] = []
    for key in CRITICAL_CAPACITY_KEYS:
        val = raw.get(key)
        # nested capacity
        if is_absent(val):
            cap = raw.get("capacity") if isinstance(raw.get("capacity"), dict) else {}
            if key == "capital_giro" and not is_absent(cap.get("working_capital_brl")):
                continue
            if key == "capacidade_garantia" and not is_absent(cap.get("guarantee_capacity_brl")):
                continue
            if key == "capacidade_simultanea" and not is_absent(cap.get("simultaneous_works")):
                continue
            if key == "cats_atestados":
                quals = raw.get("qualifications") if isinstance(raw.get("qualifications"), dict) else {}
                if not is_absent(quals.get("cats_atestados")):
                    continue
            pending.append(key)
    return pending


def validate_profile(path: Path | str | None = None) -> dict[str, Any]:
    """Structural + honesty validation. Never treats absence as capacity."""
    p = Path(path or DEFAULT_PROFILE)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        raw = load_raw(p)
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "path": str(p),
            "errors": [str(exc)],
            "warnings": [],
            "stamp": None,
            "critical_pending": [],
        }

    for key in REQUIRED_TOP_LEVEL:
        if key not in raw:
            errors.append(f"missing_required:{key}")

    if raw.get("profile_id") in (None, ""):
        errors.append("profile_id_empty")
    try:
        int(raw.get("version"))
    except (TypeError, ValueError):
        errors.append("version_not_int")

    identity = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
    cnpj = str(identity.get("cnpj") or "").replace(".", "").replace("/", "").replace("-", "")
    if cnpj and (len(cnpj) != 14 or not cnpj.isdigit()):
        errors.append("identity_cnpj_invalid")
    if not cnpj:
        warnings.append("identity_cnpj_missing")

    region = raw.get("region") if isinstance(raw.get("region"), dict) else {}
    if not region.get("uf_primary"):
        errors.append("region_uf_primary_missing")

    objects = raw.get("desired_object_types")
    if not isinstance(objects, list) or not objects:
        errors.append("desired_object_types_empty")

    # Honesty: null capacity must not be coerced
    for key in CRITICAL_CAPACITY_KEYS:
        val = raw.get(key)
        if val is not None and isinstance(val, (int, float)) and val < 0:
            errors.append(f"negative_capacity:{key}")

    # Do not allow optimistic defaults sneaking into hard max without provenance
    if raw.get("maximum_value") is not None and is_absent(raw.get("maximum_value")):
        errors.append("maximum_value_absent_token_misused")

    pending = critical_pending(raw)
    if pending:
        warnings.append("critical_capacity_pending:" + ",".join(pending))

    hard = raw.get("hard_blocks") if isinstance(raw.get("hard_blocks"), dict) else {}
    if hard.get("require_future_deadline") is False:
        warnings.append("hard_block_require_future_deadline_disabled")

    st = stamp(p)
    ok = not errors
    return {
        "ok": ok,
        "path": str(p.relative_to(PROJECT_ROOT) if p.is_relative_to(PROJECT_ROOT) else p),
        "errors": errors,
        "warnings": warnings,
        "stamp": st,
        "critical_pending": pending,
        "go_blocked": bool(pending),
        "validated_at": utc_now(),
    }


def show_profile(path: Path | str | None = None, *, json_out: bool = False) -> dict[str, Any]:
    p = Path(path or DEFAULT_PROFILE)
    raw = load_raw(p)
    st = stamp(p)
    pending = critical_pending(raw)
    provenance = {k: field_provenance(raw, k) for k in CRITICAL_CAPACITY_KEYS}
    payload = {
        "stamp": st,
        "identity": raw.get("identity"),
        "region": raw.get("region"),
        "geographic_footprint": raw.get("geographic_footprint"),
        "priority_organs": raw.get("priority_organs") or [],
        "allowed_modalities": raw.get("allowed_modalities"),
        "priority_modalities": raw.get("priority_modalities"),
        "desired_object_types": [
            {"id": o.get("id"), "label": o.get("label")}
            for o in (raw.get("desired_object_types") or [])
            if isinstance(o, dict)
        ],
        "value_band_soft": raw.get("value_band_soft"),
        "minimum_value": raw.get("minimum_value"),
        "maximum_value": raw.get("maximum_value"),
        "hard_blocks": raw.get("hard_blocks"),
        "critical_pending": pending,
        "provenance_critical": provenance,
        "version_notes": raw.get("version_notes"),
    }
    return payload


def diff_profiles(path_a: Path, path_b: Path) -> dict[str, Any]:
    a = load_raw(path_a)
    b = load_raw(path_b)
    keys = sorted(set(a) | set(b))
    changed: list[dict[str, Any]] = []
    only_a: list[str] = []
    only_b: list[str] = []
    for k in keys:
        if k not in a:
            only_b.append(k)
            continue
        if k not in b:
            only_a.append(k)
            continue
        if a[k] != b[k]:
            changed.append({"key": k, "before": a[k], "after": b[k]})
    return {
        "path_a": str(path_a),
        "path_b": str(path_b),
        "hash_a": profile_hash(path_a),
        "hash_b": profile_hash(path_b),
        "version_a": a.get("version"),
        "version_b": b.get("version"),
        "changed_keys": [c["key"] for c in changed],
        "changed": changed,
        "only_in_a": only_a,
        "only_in_b": only_b,
        "identical": not changed and not only_a and not only_b,
    }


def build_intake(path: Path | str | None = None) -> dict[str, Any]:
    """Questions for human intake — does not invent answers."""
    raw = load_raw(path)
    pending = critical_pending(raw)
    questions = []
    catalog = {
        "capital_giro": "Qual o capital de giro disponível (BRL) para propostas e garantias?",
        "capacidade_garantia": "Qual a capacidade de emissão de garantias (proposta/contrato)?",
        "capacidade_simultanea": "Quantas obras/contratos simultâneos a Extra sustenta com segurança?",
        "cats_atestados": "Quais CATs/atestados vigentes (objeto, valor, órgão, validade)?",
        "equipe": "Qual a equipe técnica disponível?",
        "equipamentos": "Quais equipamentos próprios relevantes?",
        "certidoes": "Status consolidado das certidões?",
        "margem_minima": "Margem mínima aceitável por tipo de objeto?",
        "risco_aceitavel": "Apetite de risco (prazos curtos, órgãos, garantias)?",
        "apetite_consorcios": "Tolerância a consórcios?",
        "priority_organs": "Quais órgãos priorizar?",
        "maximum_value": "Valor máximo por contrato (BRL)?",
    }
    queue = list(raw.get("elicitation_queue") or [])
    for key in queue + [k for k in catalog if k not in queue]:
        if key not in catalog:
            continue
        questions.append(
            {
                "key": key,
                "question": catalog[key],
                "current_state": field_provenance(raw, key),
                "required_for_actionable_go": key in CRITICAL_CAPACITY_KEYS,
            }
        )
    return {
        "schema": "extra-profile-intake/1.0",
        "generated_at": utc_now(),
        "stamp": stamp(path),
        "critical_pending": pending,
        "questions": questions,
        "instruction": (
            "Preencher apenas com dados fornecidos pela Extra. "
            "Use NOT_PROVIDED se solicitado e não informado. "
            "Nunca inventar capital, garantias, CATs ou capacidades."
        ),
    }


def init_scaffold(dest: Path) -> dict[str, Any]:
    """Create a non-secret scaffold if dest missing (does not overwrite canonical)."""
    if dest.exists():
        raise FileExistsError(f"Refusing to overwrite existing profile: {dest}")
    scaffold = {
        "profile_id": "extra_construtora",
        "display_name": "Extra Empreiteira e Construtora",
        "version": 1,
        "version_date": utc_now()[:10],
        "version_notes": "Scaffold — preencher com dados reais; capacidades PENDING",
        "identity": {
            "cnpj": None,
            "legal_name": None,
            "trade_name": None,
            "headquarters_municipio": None,
            "headquarters_uf": "SC",
        },
        "region": {
            "uf_primary": "SC",
            "radius_km": 200,
            "universe_seed": "Extra - alvos de licitação. R-0.xlsx",
            "universe_authority": "spreadsheet_canonical",
        },
        "desired_object_types": [],
        "positive_terms": [],
        "negative_terms": [],
        "priority_organs": [],
        "allowed_modalities": None,
        "minimum_value": None,
        "maximum_value": None,
        "capital_giro": None,
        "capacidade_garantia": None,
        "capacidade_simultanea": None,
        "cats_atestados": [],
        "hard_blocks": {
            "require_within_radius": True,
            "require_future_deadline": True,
            "exclude_terminal_or_suspended": True,
            "require_official_url": True,
        },
        "elicitation_queue": list(CRITICAL_CAPACITY_KEYS),
        "weights": {"data_confidence": {}, "client_fit": {}},
        "triage_thresholds": {},
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        yaml.safe_dump(scaffold, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {"created": str(dest), "stamp": stamp(dest), "note": "Scaffold only — not production Extra profile"}


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extra operational profile CLI")
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE),
        help=f"Profile path (default {CANONICAL_REL})",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create scaffold profile (never overwrites)")
    p_init.add_argument("--dest", required=True, help="Destination YAML path")

    sub.add_parser("validate", help="Validate profile honesty + structure")
    sub.add_parser("show", help="Show profile summary + provenance")
    sub.add_parser("intake", help="Emit intake questionnaire for pending fields")
    sub.add_parser("stamp", help="Emit version+hash stamp for reports")

    p_diff = sub.add_parser("diff", help="Diff two profile versions")
    p_diff.add_argument("--other", required=True, help="Other profile path")

    args = parser.parse_args(argv)
    path = Path(args.profile)

    try:
        if args.cmd == "init":
            _print_json(init_scaffold(Path(args.dest)))
            return 0
        if args.cmd == "validate":
            result = validate_profile(path)
            _print_json(result)
            return 0 if result["ok"] else 2
        if args.cmd == "show":
            _print_json(show_profile(path))
            return 0
        if args.cmd == "intake":
            _print_json(build_intake(path))
            return 0
        if args.cmd == "stamp":
            _print_json(stamp(path))
            return 0
        if args.cmd == "diff":
            _print_json(diff_profiles(path, Path(args.other)))
            return 0
    except (OSError, ValueError, FileExistsError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
