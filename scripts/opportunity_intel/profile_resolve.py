"""Canonical Extra client profile resolver (EXTRA-DECISION-LOOP-01).

Merges versioned public profile + optional gitignored local override,
tracks field states (SET/PENDING/NOT_APPLICABLE/REDACTED), produces a
stable hash and profile_status without inventing commercial values.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml

FieldState = Literal["SET", "PENDING", "NOT_APPLICABLE", "REDACTED"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PUBLIC = PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml"
DEFAULT_LOCAL = PROJECT_ROOT / "config" / "client_profiles" / "extra.local.yaml"
DEFAULT_EXAMPLE = PROJECT_ROOT / "config" / "client_profiles" / "extra.local.example.yaml"

SCHEMA_VERSION = "extra-profile/2.0"

# Fields that must never land in git when set with real commercial values.
SENSITIVE_KEYS = frozenset(
    {
        "capital_giro",
        "capacidade_simultanea",
        "cats_atestados",
        "equipe",
        "equipamentos",
        "certidoes",
        "margem_minima",
        "risco_aceitavel",
        "contratos_atuais",
        "apetite_consorcios",
        "capacidade_garantia",
        "working_capital_brl",
        "guarantee_capacity_brl",
        "simultaneous_works",
        "minimum_margin_pct",
        "acceptable_risk",
    }
)

# Impact of absence on decision (for profile_status)
FIELD_IMPACT: dict[str, str] = {
    "capital_giro": "Sem capital de giro → REVIEW (não PARTICIPAR automático)",
    "capacidade_simultanea": "Sem capacidade simultânea → REVIEW comercial",
    "cats_atestados": "Sem CATs → REVIEW técnico (habilitação)",
    "equipe": "Sem equipe declarada → REVIEW operacional",
    "equipamentos": "Sem equipamentos → REVIEW operacional",
    "certidoes": "Sem certidões → REVIEW de habilitação",
    "margem_minima": "Sem margem mínima → REVIEW comercial",
    "risco_aceitavel": "Sem apetite de risco → REVIEW comercial",
    "contratos_atuais": "Sem contratos atuais → REVIEW de capacidade",
    "apetite_consorcios": "Sem política de consórcio → REVIEW quando consórcio for opção",
    "capacidade_garantia": "Sem capacidade de garantia → REVIEW comercial",
    "region": "Sem região → REVIEW de escopo geográfico",
    "desired_object_types": "Sem tipos de objeto → REVIEW de fit técnico",
    "value_band_soft": "Sem faixa de valor → REVIEW comercial soft",
    "operational_constraints": "Sem restrições operacionais → REVIEW de escopo",
    "engineering_categories": "Sem categorias de engenharia → REVIEW técnico",
}


@dataclass(frozen=True)
class FieldRecord:
    key: str
    state: FieldState
    origin: str  # public | local | derived
    sensitive: bool
    impact: str
    has_value: bool
    question: str | None = None


@dataclass
class ResolvedProfile:
    profile_id: str
    display_name: str
    version: int
    schema_version: str
    resolved_at: str
    profile_hash: str
    public_path: str
    local_path: str | None
    local_loaded: bool
    data: dict[str, Any]
    fields: list[FieldRecord] = field(default_factory=list)
    pending_critical: list[str] = field(default_factory=list)
    pending_all: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        """Export for manifests — redacts sensitive SET values."""
        safe = _redact_sensitive(copy.deepcopy(self.data))
        return {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "version": self.version,
            "schema_version": self.schema_version,
            "resolved_at": self.resolved_at,
            "profile_hash": self.profile_hash,
            "public_path": self.public_path,
            "local_path": self.local_path,
            "local_loaded": self.local_loaded,
            "pending_critical": list(self.pending_critical),
            "pending_all": list(self.pending_all),
            "data_redacted": safe,
            "fields": [asdict(f) for f in self.fields],
        }


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Profile not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Profile must be a YAML mapping: {path}")
    return raw


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    if isinstance(val, (list, dict)) and not val:
        return True
    return False


def _state_from_value(val: Any, explicit: str | None = None) -> FieldState:
    if explicit:
        s = explicit.strip().upper().replace("-", "_")
        if s in {"SET", "PENDING", "NOT_APPLICABLE", "N_A", "NA", "N/A"}:
            if s in {"N_A", "NA", "N/A"}:
                return "NOT_APPLICABLE"
            return s  # type: ignore[return-value]
        if s in {"PENDING_ELICITATION", "ELICIT", "TODO", "NULL"}:
            return "PENDING"
        if s == "REDACTED":
            return "REDACTED"
    if isinstance(val, dict):
        st = val.get("status") or val.get("state")
        if st:
            return _state_from_value(val.get("value"), str(st))
        if _is_empty(val):
            return "PENDING"
        return "SET"
    if _is_empty(val):
        return "PENDING"
    return "SET"


def _redact_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    def walk(obj: Any, key: str | None = None) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if str(k) in SENSITIVE_KEYS:
                    st = _state_from_value(v)
                    if st == "SET":
                        out[k] = {"status": "REDACTED", "value": None, "note": "sensitive redacted"}
                    else:
                        out[k] = walk(v, str(k))
                else:
                    out[k] = walk(v, str(k))
            return out
        if isinstance(obj, list):
            return [walk(x, key) for x in obj]
        return obj

    result = walk(data)
    return result if isinstance(result, dict) else {}


def _stable_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _collect_field_records(data: dict[str, Any], local_keys: set[str]) -> list[FieldRecord]:
    records: list[FieldRecord] = []
    # Structural / operational
    structural = (
        "region",
        "desired_object_types",
        "value_band_soft",
        "operational_constraints",
        "engineering_categories",
        "hard_blocks",
        "weights",
        "triage_thresholds",
    )
    for key in structural:
        val = data.get(key)
        state = _state_from_value(val)
        origin = "local" if key in local_keys else "public"
        records.append(
            FieldRecord(
                key=key,
                state=state,
                origin=origin,
                sensitive=False,
                impact=FIELD_IMPACT.get(key, "Pode alterar fit ou confiança"),
                has_value=not _is_empty(val),
            )
        )

    elicitation_raw = data.get("elicitation")
    elicitation: dict[str, Any] = (
        elicitation_raw if isinstance(elicitation_raw, dict) else {}
    )
    queue_qs = {
        item.get("field", "").split(".")[-1]: item.get("question")
        for item in (data.get("elicitation_queue") or [])
        if isinstance(item, dict)
    }

    capacity_keys = (
        "capital_giro",
        "capacidade_simultanea",
        "cats_atestados",
        "equipe",
        "equipamentos",
        "certidoes",
        "margem_minima",
        "risco_aceitavel",
        "contratos_atuais",
        "apetite_consorcios",
        "capacidade_garantia",
    )
    for key in capacity_keys:
        val = data.get(key)
        if val is None and key in elicitation:
            val = elicitation[key]
        # capacity.* mirror
        raw_cap = data.get("capacity")
        cap: dict[str, Any] = raw_cap if isinstance(raw_cap, dict) else {}
        mirror_map = {
            "capital_giro": "working_capital_brl",
            "capacidade_simultanea": "simultaneous_works",
            "capacidade_garantia": "guarantee_capacity_brl",
            "equipe": "team_available",
            "equipamentos": "equipment",
            "contratos_atuais": "current_contracts",
            "apetite_consorcios": "consortium_appetite",
        }
        mirror_key = mirror_map.get(key)
        if _is_empty(val) and mirror_key is not None and mirror_key in cap:
            val = cap.get(mirror_key)
        state = _state_from_value(val)
        if isinstance(val, dict) and (val.get("status") or val.get("state")):
            state = _state_from_value(val.get("value"), str(val.get("status") or val.get("state")))
        origin = "local" if key in local_keys or any(k.startswith("capacity") for k in local_keys) else "public"
        records.append(
            FieldRecord(
                key=key,
                state=state,
                origin=origin,
                sensitive=True,
                impact=FIELD_IMPACT.get(key, "Afeta decisão comercial"),
                has_value=state == "SET",
                question=queue_qs.get(key) or queue_qs.get(mirror_map.get(key, "")),
            )
        )
    return records


def resolve_extra_profile(
    public_path: str | Path | None = None,
    local_path: str | Path | None = None,
    *,
    require_public: bool = True,
) -> ResolvedProfile:
    """Resolve Extra profile: public YAML + optional local override."""
    pub = Path(public_path) if public_path else DEFAULT_PUBLIC
    loc = Path(local_path) if local_path is not None else DEFAULT_LOCAL

    if require_public and not pub.is_file():
        raise FileNotFoundError(f"Public profile missing: {pub}")

    public_data = _load_yaml(pub) if pub.is_file() else {}
    local_loaded = False
    local_keys: set[str] = set()
    local_path_str: str | None = None
    data = copy.deepcopy(public_data)

    if loc.is_file():
        local_data = _load_yaml(loc)
        local_keys = set(local_data.keys())
        data = _deep_merge(public_data, local_data)
        local_loaded = True
        local_path_str = str(loc)

    fields = _collect_field_records(data, local_keys)
    pending_all = [f.key for f in fields if f.state == "PENDING"]
    # Critical = sensitive capacity + structural essentials
    critical_set = SENSITIVE_KEYS | {
        "region",
        "desired_object_types",
        "value_band_soft",
        "operational_constraints",
        "engineering_categories",
    }
    pending_critical = [f.key for f in fields if f.state == "PENDING" and f.key in critical_set]

    # Hash includes structure + states + non-sensitive values; sensitive SET → REDACTED token
    hash_payload = {
        "schema_version": SCHEMA_VERSION,
        "profile_id": data.get("profile_id"),
        "version": data.get("version"),
        "data": _redact_sensitive(data),
        "field_states": {f.key: f.state for f in fields},
        "local_loaded": local_loaded,
    }
    profile_hash = _stable_hash(hash_payload)

    return ResolvedProfile(
        profile_id=str(data.get("profile_id") or "extra_construtora"),
        display_name=str(data.get("display_name") or "Extra"),
        version=int(data.get("version") or 1),
        schema_version=SCHEMA_VERSION,
        resolved_at=_utc_now(),
        profile_hash=profile_hash,
        public_path=str(pub),
        local_path=local_path_str,
        local_loaded=local_loaded,
        data=data,
        fields=fields,
        pending_critical=pending_critical,
        pending_all=pending_all,
    )


def write_profile_status(
    resolved: ResolvedProfile,
    out_dir: Path,
) -> tuple[Path, Path]:
    """Write profile_status.json and profile_status.md."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "extra-profile-status/1.0",
        "profile_id": resolved.profile_id,
        "version": resolved.version,
        "schema_version": resolved.schema_version,
        "resolved_at": resolved.resolved_at,
        "profile_hash": resolved.profile_hash,
        "local_loaded": resolved.local_loaded,
        "local_path": resolved.local_path,
        "filled": [asdict(f) for f in resolved.fields if f.state == "SET"],
        "pending": [asdict(f) for f in resolved.fields if f.state == "PENDING"],
        "not_applicable": [asdict(f) for f in resolved.fields if f.state == "NOT_APPLICABLE"],
        "redacted": [asdict(f) for f in resolved.fields if f.state == "REDACTED"],
        "pending_critical": resolved.pending_critical,
        "pending_all": resolved.pending_all,
        "minimal_questions": [
            f.question or f"Preencher campo `{f.key}` ({f.impact})"
            for f in resolved.fields
            if f.state == "PENDING"
        ],
        "decision_impact_summary": (
            "Campos críticos pendentes produzem REVIEW, nunca PARTICIPAR automático."
            if resolved.pending_critical
            else "Nenhum campo crítico pendente no resolvedor (verificação humana ainda requerida)."
        ),
    }
    json_path = out_dir / "profile_status.json"
    md_path = out_dir / "profile_status.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# Profile status — {resolved.profile_id}",
        "",
        f"- **Hash:** `{resolved.profile_hash[:16]}…`",
        f"- **Versão:** {resolved.version}",
        f"- **Resolvido em:** {resolved.resolved_at}",
        f"- **Override local:** {'sim' if resolved.local_loaded else 'não'}",
        f"- **Pendentes críticos:** {len(resolved.pending_critical)}",
        "",
        "## Pendentes críticos",
        "",
    ]
    if resolved.pending_critical:
        for k in resolved.pending_critical:
            impact = FIELD_IMPACT.get(k, "")
            lines.append(f"- `{k}` — {impact}")
    else:
        lines.append("- (nenhum)")
    lines += ["", "## Perguntas mínimas", ""]
    questions = payload.get("minimal_questions")
    if isinstance(questions, list):
        for q in questions[:20]:
            lines.append(f"- {q}")
    lines += [
        "",
        "## Política",
        "",
        "- Ausência material → **REVIEW**, não auto-NÃO_PARTICIPAR.",
        "- Dados sensíveis reais ficam só em `extra.local.yaml` (gitignored).",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def assert_local_not_tracked(repo_root: Path | None = None) -> dict[str, Any]:
    """Safety check: sensitive local override must not be tracked by git."""
    root = repo_root or PROJECT_ROOT
    local = root / "config" / "client_profiles" / "extra.local.yaml"
    gitignore = root / ".gitignore"
    gitignore_text = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    patterns_ok = any(
        p in gitignore_text
        for p in (
            "extra.local.yaml",
            "config/client_profiles/extra.local.yaml",
            "*.local.yaml",
        )
    )
    return {
        "local_path": str(local),
        "local_exists": local.is_file(),
        "gitignore_covers": patterns_ok,
        "safe": patterns_ok,
    }
