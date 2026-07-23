#!/usr/bin/env python3
"""Canonical source-policy authority for dual capability coverage.

Single versioned authority for:
* required_combinations(entity, capability)
* source roles (required | complementary | gap_fill | informational)
* applicability rules (entity attributes × source × capability)
* policy activation (draft never forms a valid denominator)

DEFAULT_REQUIRED_SOURCES in dual_capability_coverage is NOT canonical.
Loading failure or non-active status yields SOURCE_POLICY_NOT_READY.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = _PROJECT_ROOT / "config" / "source_applicability.yaml"

PolicyStatus = Literal["draft", "active", "superseded", "missing", "invalid"]
RequirementRole = Literal["required", "complementary", "gap_fill", "informational"]
CapabilityName = Literal["open_tenders", "historical_contracts"]

VALID_ROLES = frozenset({"required", "complementary", "gap_fill", "informational"})
VALID_CAPABILITIES = frozenset({"open_tenders", "historical_contracts"})
VALID_ESFERAS = frozenset({"federal", "estadual", "municipal"})


class SourcePolicyError(Exception):
    """Canonical policy cannot be used for measurement."""


@dataclass(frozen=True)
class EntityAttributes:
    """Deterministic attributes for applicability (never invent defaults)."""

    entity_id: str
    esfera: str | None
    natureza_juridica: str | None
    municipio: str | None
    codigo_ibge: str | None
    cnpj14: str | None
    cnpj8: str | None
    entity_type: str | None
    source_of_esfera: str
    attribute_gaps: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourcePolicy:
    """Loaded and validated policy document."""

    status: PolicyStatus
    policy_version: str
    validated_at: str | None
    validated_by: str | None
    policy_sha256: str
    raw: dict[str, Any]
    path: str
    canonical: bool
    errors: list[str] = field(default_factory=list)
    fallback_used: bool = False
    owner: str | None = None
    rationale: str | None = None

    @property
    def ready(self) -> bool:
        return self.canonical and self.status == "active" and not self.errors


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SourcePolicyError(f"PyYAML required to load source policy: {exc}") from exc
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise SourcePolicyError("source policy root must be a mapping")
    return data


def compute_policy_sha256(raw: Mapping[str, Any] | Path) -> str:
    """Deterministic hash over policy content excluding self-declared policy_sha256."""
    if isinstance(raw, Path):
        data = _load_yaml(raw)
    else:
        data = dict(raw)
    data.pop("policy_sha256", None)
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_natureza(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s == "*":
        return None
    if "pref" in s or "prefeitura" in s or "munic" in s:
        if "cam" in s or "câmara" in s or "camara" in s:
            return "cam"
        return "pref"
    if "cam" in s or "câmara" in s or "camara" in s:
        return "cam"
    if "autarqu" in s:
        return "aut"
    if "gov" in s or "estado" in s or "estadual" in s:
        return "gov"
    if "federal" in s:
        return "outro"
    return "outro"


def _norm_attr_text(value: str | None) -> str:
    """ASCII-ish uppercase token stream for attribute matching (not inventing sphere)."""
    # Local implementation — normalize_identity_text is defined later in this module.
    s = (value or "").upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def derive_esfera(
    *,
    natureza_juridica: str | None = None,
    entity_type: str | None = None,
    sphere: str | None = None,
    esfera: str | None = None,
    override: str | None = None,
    override_justification: str | None = None,
    razao_social: str | None = None,
    municipio: str | None = None,
) -> tuple[str | None, str]:
    """Derive esfera with explicit precedence. Never invent municipal default.

    Precedence:
    1. auditável override (requires justification)
    2. explicit esfera / sphere field
    3. entity_type heuristics
    4. natureza_juridica heuristics (incl. multi-sphere natures + name/sede attrs)
    5. None (unknown)
    """
    if override:
        if not (override_justification or "").strip():
            return None, "override_missing_justification"
        o = override.strip().lower()
        if o not in VALID_ESFERAS:
            return None, "override_invalid_esfera"
        return o, "override"

    for label, value in (("esfera", esfera), ("sphere", sphere)):
        if value:
            v = str(value).strip().lower()
            if v in VALID_ESFERAS:
                return v, label
            if v in ("*", "unknown", ""):
                continue
            return None, f"{label}_unrecognized"

    et = (entity_type or "").strip().lower()
    if et:
        if "federal" in et or et in {"orgao_federal", "união", "uniao"}:
            return "federal", "entity_type"
        if "estadual" in et or "estado" in et or et in {"orgao_estadual", "governo_estado"}:
            return "estadual", "entity_type"
        if any(
            k in et
            for k in (
                "municip",
                "prefeitura",
                "camara",
                "câmara",
                "autarquia_municipal",
                "secretaria_municipal",
            )
        ):
            return "municipal", "entity_type"

    nat = (natureza_juridica or "").strip().lower()
    name = _norm_attr_text(razao_social)
    mun = _norm_attr_text(municipio)
    if nat:
        if "federal" in nat:
            return "federal", "natureza_juridica"
        if "estadual" in nat or "estado de" in nat:
            return "estadual", "natureza_juridica"
        if "municipal" in nat or "município" in nat or "municipio" in nat or "prefeitura" in nat:
            return "municipal", "natureza_juridica"
        if "câmara" in nat or "camara" in nat:
            return "municipal", "natureza_juridica"
        if "autarquia" in nat and "federal" not in nat and "estadual" not in nat:
            # without sphere qualifier remains unknown
            return None, "natureza_autarquia_unscoped"

        # Multi-sphere RF natures — resolve only from co-present canonical attributes
        # (razao_social / municipio). Never invent a default sphere.
        if "consórcio" in nat or "consorcio" in nat:
            if "INTERMUNICIPAL" in name or "INTERFEDERATIV" in name or "MUNICIP" in name:
                return "municipal", "natureza_consorcio_name"
            if any(tok in name for tok in ("ESTADUAL", "ESTADO DE", " GOVERNO ")):
                return "estadual", "natureza_consorcio_name"
            if mun:
                return "municipal", "natureza_consorcio_sede_municipal"
            return None, "natureza_consorcio_unscoped"

        if "economia mista" in nat or "empresa pública" in nat or "empresa publica" in nat:
            if any(tok in name for tok in ("FEDERAL", "UNIAO", "UNIÃO", "UNIAO ", " DA UNIAO")):
                return "federal", "natureza_ep_sem_name"
            if any(tok in name for tok in ("ESTADUAL", "ESTADO DE", " DO ESTADO", "SC ", " DE SC")):
                return "estadual", "natureza_ep_sem_name"
            if mun and mun in name:
                return "municipal", "natureza_ep_sem_municipio_in_name"
            if mun:
                # Public company / SEM with municipal seat in seed, no federal/state marker
                return "municipal", "natureza_ep_sem_sede_municipal"
            return None, "natureza_ep_sem_unscoped"

        if "servi" in nat and "social" in nat and "aut" in nat:
            # Serviço Social Autônomo (Sistema S) — federal legal framework
            return "federal", "natureza_servico_social_autonomo"

    return None, "attribute_absent"


def entity_attributes_from_canonical(
    entity: Any,
    *,
    override_esfera: str | None = None,
    override_justification: str | None = None,
    cnpj14: str | None = None,
    entity_type: str | None = None,
    sphere: str | None = None,
) -> EntityAttributes:
    """Build attributes from CanonicalEntity-like object + optional registry fields."""
    eid = str(getattr(entity, "entity_id", "") or "")
    natureza = getattr(entity, "natureza_juridica", None) or None
    municipio = getattr(entity, "municipio", None) or None
    ibge = getattr(entity, "codigo_ibge", None) or None
    cnpj8 = getattr(entity, "cnpj8", None) or None
    razao = getattr(entity, "razao_social", None) or getattr(entity, "entity_name", None) or None
    et = entity_type or getattr(entity, "entity_type", None)
    esfera_field = getattr(entity, "esfera", None) or sphere
    esfera, src = derive_esfera(
        natureza_juridica=natureza,
        entity_type=et,
        sphere=sphere,
        esfera=esfera_field,
        override=override_esfera,
        override_justification=override_justification,
        razao_social=str(razao) if razao else None,
        municipio=str(municipio) if municipio else None,
    )
    gaps: list[str] = []
    if not esfera:
        gaps.append("esfera")
    if not natureza:
        gaps.append("natureza_juridica")
    if not municipio:
        gaps.append("municipio")
    return EntityAttributes(
        entity_id=eid,
        esfera=esfera,
        natureza_juridica=natureza,
        municipio=municipio,
        codigo_ibge=str(ibge) if ibge is not None else None,
        cnpj14=cnpj14,
        cnpj8=str(cnpj8)[:8] if cnpj8 else None,
        entity_type=et,
        source_of_esfera=src,
        attribute_gaps=tuple(gaps),
    )


def _validate_registry_sources(sources: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        from scripts.crawl.registry import lookup
    except Exception as exc:  # pragma: no cover
        return [f"registry_unavailable:{exc}"]

    for name in sources:
        if name in {"contracts", "pncp_contracts"}:
            # contracts is a first-class registry entry
            pass
        info = lookup(name) or lookup(name.replace("_", "-"))
        if info is None and name not in {"contracts", "pncp_contracts"}:
            errors.append(f"source_not_in_registry:{name}")
    return errors


def _validate_combinations(raw: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    combos = raw.get("required_combinations")
    if not isinstance(combos, dict) or not combos:
        return ["required_combinations_missing_or_empty"]
    for cap, rules in combos.items():
        if cap not in VALID_CAPABILITIES:
            errors.append(f"unknown_capability_in_combinations:{cap}")
            continue
        if not isinstance(rules, list) or not rules:
            errors.append(f"combinations_empty:{cap}")
            continue
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append(f"combination_rule_not_mapping:{cap}:{i}")
                continue
            alts = rule.get("combinations")
            if not isinstance(alts, list) or not alts:
                errors.append(f"combination_alts_empty:{cap}:{i}")
                continue
            for j, alt in enumerate(alts):
                if not isinstance(alt, (list, tuple)) or not alt:
                    errors.append(f"combination_alt_empty:{cap}:{i}:{j}")
                    continue
                for src in alt:
                    if not isinstance(src, str) or not src.strip():
                        errors.append(f"combination_source_invalid:{cap}:{i}:{j}")
    return errors


def load_source_policy(
    path: Path | None = None,
    *,
    require_active: bool = True,
    expected_sha256: str | None = None,
) -> SourcePolicy:
    """Load canonical source policy. Non-active → not ready (never silent fallback)."""
    p = path or DEFAULT_POLICY_PATH
    if not p.is_file():
        return SourcePolicy(
            status="missing",
            policy_version="",
            validated_at=None,
            validated_by=None,
            policy_sha256="",
            raw={},
            path=str(p),
            canonical=False,
            errors=["policy_file_missing"],
            fallback_used=False,
        )
    try:
        raw = _load_yaml(p)
    except SourcePolicyError as exc:
        return SourcePolicy(
            status="invalid",
            policy_version="",
            validated_at=None,
            validated_by=None,
            policy_sha256="",
            raw={},
            path=str(p),
            canonical=False,
            errors=[str(exc)],
        )

    status_raw = str(raw.get("status") or "draft").strip().lower()
    status: PolicyStatus
    if status_raw in {"draft", "active", "superseded"}:
        status = status_raw  # type: ignore[assignment]
    else:
        status = "invalid"

    computed = compute_policy_sha256(raw)
    declared = str(raw.get("policy_sha256") or "").strip().lower()
    errors: list[str] = []

    if status == "active":
        if not str(raw.get("policy_version") or "").strip():
            errors.append("policy_version_required_when_active")
        if not str(raw.get("validated_at") or "").strip():
            errors.append("validated_at_required_when_active")
        if not str(raw.get("validated_by") or "").strip():
            errors.append("validated_by_required_when_active")
        if not str(raw.get("owner") or raw.get("validated_by") or "").strip():
            errors.append("owner_required_when_active")
        if not str(raw.get("rationale") or "").strip():
            errors.append("rationale_required_when_active")
        if not declared:
            errors.append("policy_sha256_required_when_active")
        elif declared != computed:
            errors.append(f"policy_sha256_mismatch:declared={declared[:12]} computed={computed[:12]}")
        errors.extend(_validate_combinations(raw))
        errors.extend(_validate_registry_sources(raw.get("sources") or {}))
        # manual overrides need justification
        for i, ov in enumerate(raw.get("manual_overrides") or []):
            if not isinstance(ov, dict):
                errors.append(f"override_not_mapping:{i}")
                continue
            if not str(ov.get("reason") or ov.get("justification") or "").strip():
                errors.append(f"override_missing_justification:{i}")

    if expected_sha256 and expected_sha256.lower() != computed:
        errors.append("expected_sha256_mismatch")

    if status != "active" and require_active:
        errors.append(f"policy_status_not_active:{status}")

    canonical = status == "active" and not errors
    return SourcePolicy(
        status=status if status != "invalid" or not errors else status,
        policy_version=str(raw.get("policy_version") or raw.get("version") or ""),
        validated_at=str(raw.get("validated_at") or "") or None,
        validated_by=str(raw.get("validated_by") or "") or None,
        policy_sha256=computed,
        raw=raw,
        path=str(p),
        canonical=canonical,
        errors=errors,
        fallback_used=False,
        owner=str(raw.get("owner") or raw.get("validated_by") or "") or None,
        rationale=str(raw.get("rationale") or "") or None,
    )


def fallback_policy_stub() -> SourcePolicy:
    """Non-canonical stub for migration/tests only. Never for acceptance."""
    return SourcePolicy(
        status="draft",
        policy_version="fallback-non-canonical",
        validated_at=None,
        validated_by=None,
        policy_sha256="",
        raw={},
        path="",
        canonical=False,
        errors=["fallback_used"],
        fallback_used=True,
    )


def _match_filter(filt: Mapping[str, Any], attrs: EntityAttributes) -> bool:
    ef = str(filt.get("esfera", "*")).lower()
    nf = str(filt.get("natureza", filt.get("natureza_juridica", "*"))).lower()
    esfera = (attrs.esfera or "").lower()
    nat = _normalize_natureza(attrs.natureza_juridica) or "*"
    if ef not in ("*", esfera):
        return False
    if nf not in ("*", nat):
        return False
    return True


def required_combinations_for(
    policy: SourcePolicy,
    capability: str,
    attrs: EntityAttributes,
) -> list[list[str]]:
    """Return ordered alternative required source combinations for entity×capability.

    Empty list means no combination decided (unknown / NOT_READY).
    """
    if not policy.canonical and not policy.fallback_used:
        return []
    if policy.fallback_used:
        # Non-canonical migration path only
        if capability == "open_tenders":
            return [["pncp"]]
        if capability == "historical_contracts":
            return [["pncp"]]
        return []

    rules = (policy.raw.get("required_combinations") or {}).get(capability) or []
    matched: list[list[str]] = []
    best_specificity = -1
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        filt = rule.get("match") or rule.get("filter") or {}
        if not _match_filter(filt, attrs):
            continue
        # specificity: exact esfera > wildcard
        ef = str(filt.get("esfera", "*"))
        nf = str(filt.get("natureza", filt.get("natureza_juridica", "*")))
        spec = (0 if ef == "*" else 2) + (0 if nf == "*" else 1)
        alts = rule.get("combinations") or []
        parsed = [list(a) for a in alts if isinstance(a, (list, tuple)) and a]
        if not parsed:
            continue
        if spec > best_specificity:
            best_specificity = spec
            matched = parsed
        elif spec == best_specificity:
            # stable merge unique
            for p in parsed:
                if p not in matched:
                    matched.append(p)
    return matched


def source_role(policy: SourcePolicy, source: str, capability: str) -> RequirementRole:
    roles = (policy.raw.get("source_roles") or {}).get(capability) or {}
    role = roles.get(source)
    if role in VALID_ROLES:
        return role  # type: ignore[return-value]
    # sources appearing in required combinations are required
    combos = (policy.raw.get("required_combinations") or {}).get(capability) or []
    for rule in combos:
        for alt in rule.get("combinations") or []:
            if source in alt:
                return "required"
    return "complementary"


def decide_source_applicability(
    policy: SourcePolicy,
    *,
    source: str,
    capability: str,
    attrs: EntityAttributes,
    validated_at: str,
) -> dict[str, Any]:
    """Return applicability decision for entity×source×capability from policy."""
    # registry capability compatibility
    try:
        from scripts.crawl.registry import lookup

        info = lookup(source) or lookup(source.replace("_", "-"))
    except Exception:
        info = None
    if info is not None and capability not in list(info.capabilities or []):
        # contracts historical may list historical_contracts
        if not (source in {"contracts", "pncp_contracts"} and capability == "historical_contracts"):
            return {
                "decision": "not_applicable",
                "justification": f"Source {source} does not declare capability {capability}",
                "decision_source": "scripts.crawl.registry.capabilities",
                "role": source_role(policy, source, capability),
            }

    # manual overrides first
    for ov in policy.raw.get("manual_overrides") or []:
        if str(ov.get("entity_id")) != attrs.entity_id:
            continue
        if str(ov.get("source")) != source:
            continue
        reason = str(ov.get("reason") or ov.get("justification") or "").strip()
        if not reason:
            return {
                "decision": "unknown",
                "justification": "manual override without justification",
                "decision_source": "manual_overrides:invalid",
                "role": source_role(policy, source, capability),
                "blockers": ["override_missing_justification"],
            }
        applicable = bool(ov.get("applicable"))
        return {
            "decision": "applicable" if applicable else "not_applicable",
            "justification": reason,
            "decision_source": "manual_overrides",
            "role": source_role(policy, source, capability),
            "evidence_reference": f"override:{attrs.entity_id}:{source}",
        }

    sources_cfg = policy.raw.get("sources") or {}
    src_cfg = sources_cfg.get(source) or sources_cfg.get(source.replace("_", "-")) or {}
    if not src_cfg and source in {"contracts", "pncp_contracts"}:
        src_cfg = sources_cfg.get("pncp") or {}

    if not src_cfg:
        return {
            "decision": "unknown",
            "justification": "No applicability rules in source policy for this source",
            "decision_source": "config/source_applicability.yaml:missing",
            "role": source_role(policy, source, capability),
            "blockers": ["unknown_applicability"],
        }

    rules = src_cfg.get("rules") or []
    natureza = _normalize_natureza(attrs.natureza_juridica) or "*"
    best = None
    best_pri = -1
    for rule in rules:
        filt = rule.get("filter") or {}
        if not _match_filter(filt, attrs):
            # also allow natureza from filter against normalized
            ef = str(filt.get("esfera", "*")).lower()
            nf = str(filt.get("natureza", "*")).lower()
            # When esfera is unknown, only wildcard (esfera=*) rules may match.
            if attrs.esfera is None:
                if ef != "*":
                    continue
            elif ef not in ("*", (attrs.esfera or "")):
                continue
            if nf not in ("*", natureza):
                continue
        else:
            # _match_filter passed; if esfera absent it only passes when ef=="*"
            if attrs.esfera is None:
                ef = str(filt.get("esfera", "*")).lower()
                if ef != "*":
                    continue
        pri = int(rule.get("priority") or 0)
        if pri >= best_pri:
            best_pri = pri
            best = rule

    if best is None:
        if attrs.esfera is None:
            return {
                "decision": "unknown",
                "justification": (
                    "esfera attribute absent and no esfera=* rule matched — "
                    "cannot invent sphere-specific applicability"
                ),
                "decision_source": "entity_attributes:esfera_absent",
                "role": source_role(policy, source, capability),
                "blockers": ["esfera_absent"],
            }
        default_app = bool(src_cfg.get("default_applicable", False))
        # Prefer unknown over silent default when default would hide gaps for required sources
        if "default_applicable" not in src_cfg:
            return {
                "decision": "unknown",
                "justification": "no matching rule and no explicit default_applicable",
                "decision_source": "config/source_applicability.yaml:no_rule",
                "role": source_role(policy, source, capability),
                "blockers": ["no_matching_rule"],
            }
        return {
            "decision": "applicable" if default_app else "not_applicable",
            "justification": f"default_applicable={default_app} (no matching rule)",
            "decision_source": "config/source_applicability.yaml:default",
            "role": source_role(policy, source, capability),
        }

    applicable = bool(best.get("applicable"))
    just = str(best.get("reason") or "rule matched")
    if not applicable and not just.strip():
        return {
            "decision": "unknown",
            "justification": "not_applicable without justification",
            "decision_source": "config/source_applicability.yaml:invalid_na",
            "role": source_role(policy, source, capability),
            "blockers": ["not_applicable_missing_justification"],
        }
    return {
        "decision": "applicable" if applicable else "not_applicable",
        "justification": just,
        "decision_source": "config/source_applicability.yaml:rule",
        "role": source_role(policy, source, capability),
        "validated_at": validated_at,
        "policy_version": policy.policy_version,
    }


def select_required_combination(
    policy: SourcePolicy,
    capability: str,
    attrs: EntityAttributes,
    *,
    validated_at: str,
    source_blockers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Select deterministic required combination for entity×capability.

    Returns audit structure with candidate/applicable/selected/rejected.
    """
    source_blockers = source_blockers or {}
    candidates = required_combinations_for(policy, capability, attrs)
    report: dict[str, Any] = {
        "entity_id": attrs.entity_id,
        "capability": capability,
        "candidate_combinations": [list(c) for c in candidates],
        "applicable_combinations": [],
        "selected_combination": None,
        "rejected_combinations": [],
        "unknown_sources": [],
        "blocked_sources": [],
        "not_applicable_sources": [],
        "entity_capability_status": "unknown",
        "justification": "",
        "policy_version": policy.policy_version,
        "policy_sha256": policy.policy_sha256,
        "fallback_used": policy.fallback_used,
        "canonical": policy.canonical,
    }
    if policy.fallback_used:
        report["entity_capability_status"] = "NOT_READY"
        report["justification"] = "SOURCE_POLICY_FALLBACK_NON_CANONICAL"
        report["selected_combination"] = list(candidates[0]) if candidates else ["pncp"]
        return report
    if not policy.canonical:
        report["entity_capability_status"] = "NOT_READY"
        report["justification"] = "SOURCE_POLICY_NOT_READY"
        return report
    if not candidates:
        # Missing esfera only fails closed when no wildcard (esfera=*) combination matches.
        if attrs.esfera is None:
            report["entity_capability_status"] = "unknown"
            report["justification"] = "esfera_absent_and_no_wildcard_combination"
        else:
            report["entity_capability_status"] = "unknown"
            report["justification"] = "no_required_combination_rule_matched"
        return report

    applicable_alts: list[list[str]] = []
    for combo in candidates:
        per_src: list[dict[str, Any]] = []
        ok = True
        for src in combo:
            if src in source_blockers:
                report["blocked_sources"].append(src)
                per_src.append({"source": src, "status": "blocked", "reason": source_blockers[src]})
                ok = False
                continue
            dec = decide_source_applicability(
                policy, source=src, capability=capability, attrs=attrs, validated_at=validated_at
            )
            st = dec["decision"]
            per_src.append({"source": src, "status": st, "reason": dec.get("justification")})
            if st == "unknown":
                report["unknown_sources"].append(src)
                ok = False
            elif st == "blocked":
                report["blocked_sources"].append(src)
                ok = False
            elif st == "not_applicable":
                report["not_applicable_sources"].append(src)
                ok = False
        if ok:
            applicable_alts.append(list(combo))
            report["applicable_combinations"].append(list(combo))
        else:
            report["rejected_combinations"].append({"combination": list(combo), "sources": per_src})

    if applicable_alts:
        # Deterministic: preserve YAML order among applicable alternatives
        report["selected_combination"] = applicable_alts[0]
        report["entity_capability_status"] = "applicable"
        report["justification"] = "selected_first_listed_fully_applicable_combination"
        return report

    # No applicable combo: classify
    if report["blocked_sources"] and not report["unknown_sources"]:
        # if every combo blocked
        report["entity_capability_status"] = "blocked"
        report["justification"] = "all_combinations_blocked"
    elif all(
        all(s.get("status") == "not_applicable" for s in (rej.get("sources") or []))
        for rej in report["rejected_combinations"]
    ) and report["rejected_combinations"]:
        report["entity_capability_status"] = "not_applicable"
        report["justification"] = "all_combinations_not_applicable"
    else:
        report["entity_capability_status"] = "unknown"
        report["justification"] = "no_fully_applicable_combination"
    return report


def digitos(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_identity_text(value: str | None) -> str:
    s = (value or "").upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def identity_key(cnpj8: str, municipio: str | None, razao: str | None) -> str:
    return "|".join((digitos(cnpj8)[:8], normalize_identity_text(municipio), normalize_identity_text(razao)))
