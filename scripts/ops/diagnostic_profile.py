"""DoD «Configuração do diagnóstico» — audit canonical Extra client profile.

Canonical path: config/client_profiles/extra.yaml

Proves (fail-closed where required):
- versioned profile exists
- region + universe monitored
- engineering work types
- value bands (hard nulls allowed; soft band recorded when set)
- modalities prioritized / allowed
- operational constraints
- priority organs field (list; may be empty pending commercial alignment)
- known competitors field (list; may be empty pending elicitation)
- profile changes are YAML-only (not scattered code rules)
- reports can stamp profile_id + version
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml"
CANONICAL_REL = "config/client_profiles/extra.yaml"


@dataclass
class CheckResult:
    item_id: str
    dod_text: str
    status: str  # PASS | PARTIAL | FAIL
    evidence: list[str] = field(default_factory=list)
    notes: str = ""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_raw_profile(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_PROFILE)
    if not p.is_file():
        raise FileNotFoundError(f"Canonical profile missing: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Profile must be a YAML mapping")
    return raw


def profile_stamp(raw: dict[str, Any] | None = None, path: Path | str | None = None) -> dict[str, Any]:
    """Metadata every report should carry."""
    data = raw if raw is not None else load_raw_profile(path)
    return {
        "profile_path": CANONICAL_REL,
        "profile_id": data.get("profile_id"),
        "display_name": data.get("display_name"),
        "version": data.get("version"),
        "version_date": data.get("version_date"),
        "stamp": f"{data.get('profile_id')}@v{data.get('version')}",
    }


def audit_diagnostic_profile(path: Path | str | None = None) -> dict[str, Any]:
    """Audit Extra profile against DoD Configuração do diagnóstico items."""
    p = Path(path or DEFAULT_PROFILE)
    checks: list[CheckResult] = []
    try:
        raw = load_raw_profile(p)
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "generated_at": utc_now(),
            "profile_path": str(p),
            "error": str(exc),
            "checks": [],
        }

    def _path_label(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            return str(path)

    # 1. Canonical versioned profile
    has_id = bool(str(raw.get("profile_id") or "").strip())
    has_ver = raw.get("version") is not None
    checks.append(
        CheckResult(
            item_id="canonical_profile",
            dod_text="Existe configuração canônica do perfil da Extra Construtora ou mecanismo equivalente versionado.",
            status="PASS" if has_id and has_ver and p.is_file() else "FAIL",
            evidence=[
                _path_label(p),
                f"profile_id={raw.get('profile_id')}",
                f"version={raw.get('version')}",
            ],
            notes="" if has_id and has_ver else "profile_id and version required",
        )
    )

    # 2. Region + universe
    region = raw.get("region") if isinstance(raw.get("region"), dict) else {}
    reg_ok = bool(region.get("uf_primary")) and (
        region.get("radius_km") is not None or region.get("universe_seed")
    )
    checks.append(
        CheckResult(
            item_id="region_universe",
            dod_text="A configuração registra região e universo monitorado.",
            status="PASS" if reg_ok else "FAIL",
            evidence=[
                f"uf_primary={region.get('uf_primary')}",
                f"radius_km={region.get('radius_km')}",
                f"universe_seed={region.get('universe_seed')}",
                f"universe_authority={region.get('universe_authority')}",
            ],
        )
    )

    # 3. Work types / engineering services
    objects = raw.get("desired_object_types") or []
    eng = raw.get("engineering_categories") or []
    types_ok = isinstance(objects, list) and len(objects) >= 1 and isinstance(eng, list) and len(eng) >= 1
    checks.append(
        CheckResult(
            item_id="work_types",
            dod_text="A configuração registra tipos de obra e serviços de engenharia relevantes.",
            status="PASS" if types_ok else "FAIL",
            evidence=[
                f"desired_object_types={len(objects) if isinstance(objects, list) else 0}",
                f"engineering_categories={eng if isinstance(eng, list) else []}",
            ],
        )
    )

    # 4. Value bands
    soft = raw.get("value_band_soft") if isinstance(raw.get("value_band_soft"), dict) else {}
    has_soft = soft.get("min_brl") is not None or soft.get("max_brl") is not None
    # Fields must exist; null hard cuts + optional soft band is valid ("when defined")
    value_ok = "minimum_value" in raw and "maximum_value" in raw
    checks.append(
        CheckResult(
            item_id="value_bands",
            dod_text="A configuração registra faixas de valor relevantes, quando definidas no alinhamento.",
            status="PASS" if value_ok else "FAIL",
            evidence=[
                f"minimum_value={raw.get('minimum_value')}",
                f"maximum_value={raw.get('maximum_value')}",
                f"value_band_soft={soft or None}",
                "null hard cuts allowed; soft band is optional guidance",
            ],
            notes="Soft band present" if has_soft else "Hard cuts null; pending commercial calibration",
        )
    )

    # 5. Modalities
    prio = raw.get("priority_modalities") or []
    allowed = raw.get("allowed_modalities")  # null = all accepted
    mod_ok = (isinstance(prio, list) and len(prio) >= 1) or allowed is None or (
        isinstance(allowed, list) and len(allowed) >= 1
    )
    checks.append(
        CheckResult(
            item_id="modalities",
            dod_text="A configuração registra modalidades aceitas ou priorizadas.",
            status="PASS" if mod_ok else "FAIL",
            evidence=[
                f"priority_modalities={prio if isinstance(prio, list) else []}",
                f"allowed_modalities={allowed}",
            ],
        )
    )

    # 6. Operational constraints
    constraints = raw.get("operational_constraints") or []
    cons_ok = isinstance(constraints, list) and len(constraints) >= 1
    checks.append(
        CheckResult(
            item_id="operational_constraints",
            dod_text="A configuração registra restrições operacionais conhecidas da empresa.",
            status="PASS" if cons_ok else "FAIL",
            evidence=[
                f"count={len(constraints) if isinstance(constraints, list) else 0}",
                *[
                    str(c.get("id") if isinstance(c, dict) else c)
                    for c in (constraints if isinstance(constraints, list) else [])[:10]
                ],
            ],
        )
    )

    # 7. Priority organs — field must exist; empty list is valid PENDING alignment
    has_organs_key = "priority_organs" in raw and isinstance(raw.get("priority_organs"), list)
    organs = raw.get("priority_organs") if has_organs_key else None
    checks.append(
        CheckResult(
            item_id="priority_organs",
            dod_text="A configuração registra órgãos prioritários definidos no alinhamento.",
            status="PASS" if has_organs_key else "FAIL",
            evidence=[
                f"priority_organs count={len(organs or [])}",
                "empty list = no organs named yet; field is registered for alignment",
            ],
            notes="PARTIAL commercial fill" if has_organs_key and not organs else "",
        )
    )

    # 8. Competitors
    has_comp_key = "known_competitors" in raw and isinstance(raw.get("known_competitors"), list)
    comps = raw.get("known_competitors") if has_comp_key else None
    checks.append(
        CheckResult(
            item_id="known_competitors",
            dod_text="A configuração registra concorrentes indicados pelo cliente.",
            status="PASS" if has_comp_key else "FAIL",
            evidence=[
                f"known_competitors count={len(comps or [])}",
                "empty list = pending elicitation; field registered in YAML",
            ],
            notes="PENDING_ELICITATION" if has_comp_key and not comps else "",
        )
    )

    # 9. Profile change without scattered code rules — honest PARTIAL if hardcodes remain
    hardcode_hits: list[str] = []
    scripts_root = PROJECT_ROOT / "scripts"
    hardcode_patterns = (
        "radius_km=200",
        "radius_km = 200",
        "RAIO_200",
        "raio_200km",
        "200 km",
        "200km",
        "priority_distance_km=200",
        "priority_distance_km = 200",
        "radius_km: 200",
    )
    if scripts_root.is_dir():
        for py in scripts_root.rglob("*.py"):
            rel = str(py)
            if "diagnostic_profile" in rel or "test_diagnostic_profile" in rel:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(pat in text for pat in hardcode_patterns):
                try:
                    hardcode_hits.append(str(py.relative_to(PROJECT_ROOT)))
                except ValueError:
                    hardcode_hits.append(str(py))
    # Always PARTIAL while residual radius hardcodes exist outside YAML
    yaml_status = "PARTIAL" if hardcode_hits else "PASS"
    checks.append(
        CheckResult(
            item_id="yaml_centralized",
            dod_text="A alteração do perfil não exige modificar regras espalhadas pelo código.",
            status=yaml_status,
            evidence=[
                CANONICAL_REL,
                "scripts/opportunity_intel/profile.py:load_client_profile",
                "scripts/ops/diagnostic_profile.py",
                f"hardcode_hits_sample={hardcode_hits[:8]}",
                f"hardcode_hits_count={len(hardcode_hits)}",
            ],
            notes=(
                "PARTIAL: residual hardcodes (e.g. 200km) remain outside YAML"
                if hardcode_hits
                else "Business parameters live in YAML; code only loads/validates"
            ),
        )
    )

    # 10. Reports identify profile version — capability via run_metadata; not every report yet
    stamp = profile_stamp(raw)
    run_meta = PROJECT_ROOT / "scripts" / "reports" / "run_metadata.py"
    has_run_meta_version = False
    if run_meta.is_file():
        rm_text = run_meta.read_text(encoding="utf-8", errors="ignore")
        has_run_meta_version = "profile_version" in rm_text and "_load_profile_version" in rm_text
    # Scan how many report modules mention profile_version
    report_hits = 0
    reports_dir = PROJECT_ROOT / "scripts" / "reports"
    if reports_dir.is_dir():
        for py in reports_dir.glob("*.py"):
            try:
                if "profile_version" in py.read_text(encoding="utf-8", errors="ignore"):
                    report_hits += 1
            except OSError:
                pass
    # PARTIAL until all generators use stamp; PASS only if widely adopted (>=5 modules)
    report_status = (
        "PASS"
        if has_run_meta_version and report_hits >= 5 and stamp.get("version") is not None
        else "PARTIAL"
        if has_run_meta_version and stamp.get("version") is not None
        else "FAIL"
    )
    checks.append(
        CheckResult(
            item_id="report_profile_version",
            dod_text="Todo relatório identifica a versão do perfil utilizada.",
            status=report_status,
            evidence=[
                f"stamp={stamp.get('stamp')}",
                "scripts/reports/run_metadata.py:_load_profile_version + profile_id/version fields",
                f"report_modules_with_profile_version={report_hits}",
                "profile_stamp() for report generators",
            ],
            notes=(
                "PARTIAL: executive/run_metadata path stamps version; not every operational report yet"
                if report_status == "PARTIAL"
                else ""
            ),
        )
    )

    fail = sum(1 for c in checks if c.status == "FAIL")
    partial = sum(1 for c in checks if c.status == "PARTIAL")
    return {
        # ok when no FAIL — PARTIAL residual is allowed (honest debt)
        "ok": fail == 0,
        "generated_at": utc_now(),
        "profile_path": _path_label(p),
        "stamp": stamp,
        "checks": [asdict(c) for c in checks],
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c.status == "PASS"),
            "partial": partial,
            "fail": fail,
            "partial_fill_notes": sum(
                1
                for c in checks
                if "PENDING" in (c.notes or "") or "PARTIAL commercial" in (c.notes or "")
            ),
        },
        "claims_allowed": [
            "Canonical Extra profile YAML is versioned and loadable",
            "Region/universe/work types/modalities/constraints registered",
            "priority_organs and known_competitors fields exist (may be empty pending alignment)",
            "Reports can stamp profile_id@version from YAML",
        ],
        "claims_forbidden": [
            "priority_organs fully populated without commercial alignment",
            "known_competitors complete without client elicitation",
            "capacity/qualifications COMPLETE when status PENDING_ELICITATION",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Audit Extra diagnostic profile (DoD)")
    p.add_argument("command", choices=["audit", "stamp"])
    p.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "stamp":
        report: dict[str, Any] = profile_stamp(path=args.profile)
    else:
        report = audit_diagnostic_profile(args.profile)

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if (args.command == "stamp" or report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
