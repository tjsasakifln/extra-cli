"""Load and join universe / DUI / Warmbly rows into AccountFact tuples.

I/O and join only. Stage classification stays in icp_denominator.classify_stage.
Does not invent TAM, contacts, or Warmbly outcomes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.company_registry.normalization import normalize_cnpj14
from scripts.market_penetration.icp_denominator import (
    STAGES,
    AccountFact,
    PenetrationError,
    sha256_payload,
)
from scripts.warmbly_bridge.io_jsonl import InputError, read_jsonl, require_readable_file

BASELINE_SCHEMA = "penetration-baseline/1.0"
UNKNOWN = "UNKNOWN"
DEFAULT_WARMBLY_MAX_AGE_DAYS = 90

# Warmbly wire types → #388 exclusive stages. Unmapped events leave warmbly_stage empty.
WARMBLY_EVENT_TO_STAGE: dict[str, str] = {
    "CONTACTED": "CONTACTED",
    "SENT": "CONTACTED",
    "BOUNCED": "CONTACTED",
    "BOUNCE": "CONTACTED",
    "REPLIED": "QUALIFIED_CONVERSATION",
    "QUALIFIED_CONVERSATION": "QUALIFIED_CONVERSATION",
    "MEETING": "MEETING",
    "PROPOSAL": "PROPOSAL",
    "WON": "CLIENT",
    "ACTIVE_CLIENT": "CLIENT",
    "CLIENT": "CLIENT",
    "EXPANDED_CLIENT": "EXPANDED_CLIENT",
}

ACTIONABLE_ROUTE_CLASSES = frozenset(
    {
        "R1_DIRECT",
        "R2_HIGH_CONFIDENCE_DIRECT",
        "R3_ROUTED_TO_NAMED_PERSON",
        "R4_ROLE_ROUTE",
        "R5_CORPORATE_ONLY",
        "ACTIONABLE_ROUTE",
    }
)

_CODE_LIKE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
PII_DIMENSION_KEYS = frozenset(
    {
        "email",
        "phone",
        "telefone",
        "name",
        "nome",
        "razao_social",
        "nome_fantasia",
        "message",
        "body",
        "contact",
        "person",
        "person_name",
    }
)


@dataclass(frozen=True)
class DimensionTags:
    region: str
    size_portfolio: str
    trigger: str
    wedge: str
    route_class: str

    def as_dict(self) -> dict[str, str]:
        return {
            "region": self.region,
            "size_portfolio": self.size_portfolio,
            "trigger": self.trigger,
            "wedge": self.wedge,
            "route_class": self.route_class,
        }


@dataclass(frozen=True)
class JoinedAccount:
    account_id: str
    fact: AccountFact
    dimensions: DimensionTags


@dataclass(frozen=True)
class JoinIssue:
    kind: str
    source: str
    detail: str
    account_id: str | None = None


@dataclass(frozen=True)
class WarmblyFreshness:
    status: str
    latest_at: str | None
    stale: bool
    reason: str


@dataclass(frozen=True)
class JoinResult:
    accounts: tuple[JoinedAccount, ...]
    issues: tuple[JoinIssue, ...]
    universe_row_count: int
    dui_row_count: int
    warmbly_event_count: int
    warmbly_status: str
    warmbly_freshness: WarmblyFreshness
    universe_version: str
    input_hashes: dict[str, str]


def canonical_account_id(row: dict[str, Any]) -> str | None:
    """CNPJ14 preferred; otherwise a non-empty explicit account_id."""
    company = row.get("company") if isinstance(row.get("company"), dict) else {}
    raw = row.get("cnpj14") or row.get("cnpj") or row.get("account_id") or company.get("cnpj14")
    if raw is None:
        return None
    normalized = normalize_cnpj14(raw)
    if normalized:
        return normalized
    text = str(raw).strip()
    return text or None


def _is_code_token(value: str) -> bool:
    if not value or len(value) > 48:
        return False
    if value != value.upper():
        return False
    if value[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        return False
    return all(ch in _CODE_LIKE for ch in value)


def _code_or_unknown(raw: Any) -> str:
    if raw is None:
        return UNKNOWN
    if isinstance(raw, dict):
        return _code_or_unknown(raw.get("code") or raw.get("service_code"))
    text = str(raw).strip()
    if not text:
        return UNKNOWN
    token = text.replace("-", "_").replace(" ", "_").upper()
    if _is_code_token(token):
        return token
    return "UNSTRUCTURED"


def portfolio_size_bucket(contract_count: int | None) -> str:
    if contract_count is None:
        return UNKNOWN
    if contract_count <= 0:
        return "ZERO"
    if contract_count <= 4:
        return "1_4"
    if contract_count <= 19:
        return "5_19"
    if contract_count <= 99:
        return "20_99"
    return "100_plus"


def _int_or_none(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _universe_portfolio_count(row: dict[str, Any]) -> int | None:
    portfolio = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    for key in ("contract_count_total", "contract_count", "active_contract_count"):
        value = _int_or_none(portfolio.get(key))
        if value is not None:
            return value
    value = _int_or_none(row.get("contract_count"))
    if value is not None:
        return value
    evidence = row.get("construction_evidence") if isinstance(row.get("construction_evidence"), dict) else {}
    return _int_or_none(evidence.get("relevant_contract_count") or evidence.get("total_contract_count"))


def has_public_portfolio(row: dict[str, Any]) -> bool:
    if row.get("has_public_portfolio") is True:
        return True
    if row.get("has_public_portfolio") is False:
        return False
    count = _universe_portfolio_count(row)
    if count is not None:
        return count > 0
    portfolio = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    if portfolio.get("last_contract_date") or portfolio.get("first_contract_date"):
        return True
    return str(row.get("schema_version") or "") == "confenge-universe-v1"


def _dui_decision_unit_known(row: dict[str, Any]) -> bool:
    if row.get("decision_unit_known") is True:
        return True
    if row.get("primary_decision_unit_target"):
        return True
    terminal = str(row.get("terminal") or "")
    if terminal in {
        "ACTIONABLE_ROUTE",
        "DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED",
    }:
        return True
    candidates = row.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and (candidate.get("person_name") or candidate.get("canonical_name")):
                return True
    return False


def _dui_route_class(row: dict[str, Any]) -> str:
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    raw = (
        row.get("route_class")
        or extra.get("account_reachability_class")
        or row.get("account_reachability_class")
        or (row.get("terminal") if row.get("terminal") == "ACTIONABLE_ROUTE" else None)
    )
    code = _code_or_unknown(raw)
    return code if code != "UNSTRUCTURED" else UNKNOWN


def _dui_actionable_route(row: dict[str, Any]) -> bool:
    if row.get("actionable_route") is True:
        return True
    if str(row.get("terminal") or "") == "ACTIONABLE_ROUTE":
        return True
    return _dui_route_class(row) in ACTIONABLE_ROUTE_CLASSES


def _dui_trigger(row: dict[str, Any]) -> str:
    if "why_now" in row:
        return _code_or_unknown(row.get("why_now"))
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    return _code_or_unknown(extra.get("why_now") or extra.get("trigger"))


def _dui_wedge(row: dict[str, Any]) -> str:
    offer = row.get("offer") if isinstance(row.get("offer"), dict) else {}
    raw = offer.get("service_code") or row.get("service_context") or row.get("oferta_recomendada") or row.get("wedge")
    code = _code_or_unknown(raw)
    return code if code != "UNSTRUCTURED" else UNKNOWN


def map_warmbly_event(event_type: str | None) -> str | None:
    if not event_type:
        return None
    mapped = WARMBLY_EVENT_TO_STAGE.get(str(event_type).strip().upper())
    if mapped is None:
        return None
    if mapped not in STAGES:
        raise PenetrationError(f"warmbly_map_not_in_stages:{mapped}")
    return mapped


def _stage_rank(stage: str | None) -> int:
    if not stage or stage not in STAGES:
        return -1
    return STAGES.index(stage)


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if len(text) == 10:
        try:
            return datetime.fromisoformat(text).replace(tzinfo=UTC)
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def assess_warmbly_freshness(
    events: tuple[dict[str, Any], ...],
    *,
    as_of: str,
    max_age_days: int = DEFAULT_WARMBLY_MAX_AGE_DAYS,
    absent: bool = False,
) -> WarmblyFreshness:
    if absent:
        return WarmblyFreshness(status="absent", latest_at=None, stale=False, reason="warmbly_explicitly_absent")
    if not events:
        return WarmblyFreshness(status="empty", latest_at=None, stale=False, reason="no_warmbly_events")
    stamps = [
        _parse_iso_datetime(event.get("occurred_at") or event.get("as_of") or event.get("imported_at"))
        for event in events
    ]
    present = [stamp for stamp in stamps if stamp is not None]
    if not present:
        return WarmblyFreshness(
            status="stale",
            latest_at=None,
            stale=True,
            reason="warmbly_events_missing_occurred_at",
        )
    latest = max(present)
    as_of_dt = _parse_iso_datetime(as_of)
    if as_of_dt is None:
        raise PenetrationError("as_of_unparseable_for_freshness")
    age = (as_of_dt.date() - latest.date()).days
    if age > max_age_days:
        return WarmblyFreshness(
            status="stale",
            latest_at=latest.date().isoformat(),
            stale=True,
            reason=f"warmbly_latest_{latest.date().isoformat()}_older_than_{max_age_days}d",
        )
    return WarmblyFreshness(
        status="consumed",
        latest_at=latest.date().isoformat(),
        stale=False,
        reason="within_max_age",
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dir_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(item.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _load_json_document(path: Path, *, label: str) -> Any:
    require_readable_file(path, label=label)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON in {label} path={path}: {exc}") from exc


def _rows_from_payload(payload: Any, *, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for key in keys:
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        if rows is None:
            rows = [payload]
    else:
        raise InputError("payload must be object or array")
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise InputError(f"row {index} is not an object")
        out.append(row)
    return out


def load_json_or_jsonl(path: Path, *, label: str, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path, label=label)
    return _rows_from_payload(_load_json_document(path, label=label), keys=keys)


def load_universe_rows(path: Path) -> list[dict[str, Any]]:
    return load_json_or_jsonl(path, label="universe", keys=("accounts", "records", "universe"))


def load_dui_rows(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        accounts_dir = path / "accounts"
        cards = path / "cards.json"
        operator_cards = path / "operator" / "cards.json"
        if accounts_dir.is_dir():
            rows = [json.loads(item.read_text(encoding="utf-8")) for item in sorted(accounts_dir.glob("*.json"))]
            return [row for row in rows if isinstance(row, dict)]
        if cards.is_file():
            return load_json_or_jsonl(cards, label="dui-cards", keys=("cards", "accounts"))
        if operator_cards.is_file():
            return load_json_or_jsonl(operator_cards, label="dui-operator-cards", keys=("cards", "accounts"))
        collected: list[dict[str, Any]] = []
        for item in sorted(path.glob("*.json")) + sorted(path.glob("*.jsonl")):
            collected.extend(load_json_or_jsonl(item, label=f"dui:{item.name}", keys=("cards", "accounts")))
        return collected
    return load_json_or_jsonl(path, label="dui", keys=("cards", "accounts"))


def load_warmbly_events(path: Path) -> list[dict[str, Any]]:
    return load_json_or_jsonl(path, label="warmbly", keys=("events", "outcomes", "records"))


def load_universe_version(manifest_path: Path | None, universe_hash: str) -> str:
    if manifest_path is None:
        return f"input:{universe_hash}" if universe_hash else "UNKNOWN"
    payload = _load_json_document(manifest_path, label="universe-manifest")
    if not isinstance(payload, dict):
        raise InputError("universe manifest must be an object")
    rule = str(payload.get("rule_version") or payload.get("universe_schema_version") or "UNKNOWN")
    as_of = str(payload.get("as_of") or (payload.get("source") or {}).get("as_of") or "UNKNOWN")
    jsonl_sha = ""
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    jsonl_meta = outputs.get("jsonl") if isinstance(outputs.get("jsonl"), dict) else {}
    jsonl_sha = str(jsonl_meta.get("sha256") or "")
    if not jsonl_sha:
        jsonl_sha = universe_hash or "UNKNOWN"
    return f"{rule}:{as_of}:{jsonl_sha}"


def _index_by_account(
    rows: list[dict[str, Any]],
    *,
    source: str,
    issues: list[JoinIssue],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for offset, row in enumerate(rows):
        account_id = canonical_account_id(row)
        if not account_id:
            issues.append(
                JoinIssue(
                    kind="missing_canonical_id",
                    source=source,
                    detail=f"row_{offset}_missing_cnpj14",
                    account_id=None,
                )
            )
            continue
        if account_id in indexed:
            issues.append(
                JoinIssue(
                    kind="duplicate_join",
                    source=source,
                    detail=f"duplicate_{source}:{account_id}",
                    account_id=account_id,
                )
            )
            continue
        indexed[account_id] = row
    return indexed


def join_account_facts(
    universe_rows: tuple[dict[str, Any], ...],
    dui_rows: tuple[dict[str, Any], ...],
    warmbly_events: tuple[dict[str, Any], ...],
    *,
    as_of: str,
    universe_version: str,
    input_hashes: dict[str, str],
    warmbly_absent: bool = False,
    max_warmbly_age_days: int = DEFAULT_WARMBLY_MAX_AGE_DAYS,
) -> JoinResult:
    """Reconcile one joined row per canonical account ID."""
    if not as_of:
        raise PenetrationError("as_of is required")
    issues: list[JoinIssue] = []
    universe_index = _index_by_account(list(universe_rows), source="universe", issues=issues)
    dui_index = _index_by_account(list(dui_rows), source="dui", issues=issues)

    warmbly_by_account: dict[str, list[dict[str, Any]]] = {}
    if not warmbly_absent:
        for offset, event in enumerate(warmbly_events):
            account_id = canonical_account_id(event)
            if not account_id:
                issues.append(
                    JoinIssue(
                        kind="missing_canonical_id",
                        source="warmbly",
                        detail=f"event_{offset}_missing_cnpj14",
                        account_id=None,
                    )
                )
                continue
            warmbly_by_account.setdefault(account_id, []).append(event)

    freshness = assess_warmbly_freshness(
        warmbly_events if not warmbly_absent else (),
        as_of=as_of,
        max_age_days=max_warmbly_age_days,
        absent=warmbly_absent,
    )
    if warmbly_absent:
        warmbly_status = "absent"
    elif not warmbly_events:
        warmbly_status = "empty"
    else:
        warmbly_status = "consumed"

    account_ids = sorted({*universe_index, *dui_index, *warmbly_by_account})
    joined: list[JoinedAccount] = []
    for account_id in account_ids:
        universe = universe_index.get(account_id)
        dui = dui_index.get(account_id)
        events = tuple(warmbly_by_account.get(account_id) or ())
        evidence: list[str] = []
        if universe is not None:
            evidence.append("universe")
        if dui is not None:
            evidence.append("dui")

        uf = None
        public_portfolio = False
        region = UNKNOWN
        size = UNKNOWN
        if universe is not None:
            uf_raw = universe.get("uf")
            uf = str(uf_raw).strip().upper() if uf_raw else None
            region = uf or UNKNOWN
            public_portfolio = has_public_portfolio(universe)
            size = portfolio_size_bucket(_universe_portfolio_count(universe))

        decision_unit_known = _dui_decision_unit_known(dui) if dui is not None else False
        actionable_route = _dui_actionable_route(dui) if dui is not None else False
        trigger = _dui_trigger(dui) if dui is not None else UNKNOWN
        wedge = _dui_wedge(dui) if dui is not None else UNKNOWN
        route_class = _dui_route_class(dui) if dui is not None else UNKNOWN

        warmbly_stage = None
        if not warmbly_absent:
            for event in events:
                mapped = map_warmbly_event(str(event.get("event_type") or event.get("warmbly_stage") or ""))
                if _stage_rank(mapped) > _stage_rank(warmbly_stage):
                    warmbly_stage = mapped
            if events:
                evidence.append("warmbly")

        if not evidence:
            issues.append(
                JoinIssue(
                    kind="missing_canonical_id",
                    source="join",
                    detail="account_without_source_facts",
                    account_id=account_id,
                )
            )
            continue

        fact = AccountFact(
            account_id=account_id,
            uf=uf,
            has_public_portfolio=public_portfolio,
            decision_unit_known=decision_unit_known,
            actionable_route=actionable_route,
            warmbly_stage=warmbly_stage,
            evidence=tuple(evidence),
        )
        joined.append(
            JoinedAccount(
                account_id=account_id,
                fact=fact,
                dimensions=DimensionTags(
                    region=region,
                    size_portfolio=size,
                    trigger=trigger,
                    wedge=wedge,
                    route_class=route_class,
                ),
            )
        )

    return JoinResult(
        accounts=tuple(joined),
        issues=tuple(issues),
        universe_row_count=len(universe_rows),
        dui_row_count=len(dui_rows),
        warmbly_event_count=0 if warmbly_absent else len(warmbly_events),
        warmbly_status=warmbly_status,
        warmbly_freshness=freshness,
        universe_version=universe_version,
        input_hashes=dict(input_hashes),
    )


def join_from_paths(
    *,
    as_of: str,
    universe_path: Path,
    dui_path: Path | None = None,
    warmbly_path: Path | None = None,
    warmbly_absent: bool = False,
    universe_manifest_path: Path | None = None,
    max_warmbly_age_days: int = DEFAULT_WARMBLY_MAX_AGE_DAYS,
) -> JoinResult:
    universe_file = require_readable_file(universe_path, label="universe")
    universe_rows = tuple(load_universe_rows(universe_file))
    universe_hash = _file_sha256(universe_file)
    dui_rows: tuple[dict[str, Any], ...] = ()
    dui_hash = sha256_payload({"dui": "absent"})
    if dui_path is not None:
        dui_target = Path(dui_path)
        if dui_target.is_dir():
            dui_rows = tuple(load_dui_rows(dui_target))
            dui_hash = _dir_sha256(dui_target)
        else:
            dui_file = require_readable_file(dui_target, label="dui")
            dui_rows = tuple(load_dui_rows(dui_file))
            dui_hash = _file_sha256(dui_file)
    if warmbly_absent and warmbly_path is not None:
        raise PenetrationError("warmbly_path_and_absent_are_mutually_exclusive")
    if not warmbly_absent and warmbly_path is None:
        raise PenetrationError("warmbly_path_required_or_pass_warmbly_absent")
    warmbly_events: tuple[dict[str, Any], ...] = ()
    warmbly_hash = sha256_payload({"warmbly": "absent"})
    if not warmbly_absent and warmbly_path is not None:
        warmbly_file = require_readable_file(warmbly_path, label="warmbly")
        warmbly_events = tuple(load_warmbly_events(warmbly_file))
        warmbly_hash = _file_sha256(warmbly_file)
    version = load_universe_version(universe_manifest_path, universe_hash)
    return join_account_facts(
        universe_rows,
        dui_rows,
        warmbly_events,
        as_of=as_of,
        universe_version=version,
        input_hashes={
            "universe": universe_hash,
            "dui": dui_hash,
            "warmbly": warmbly_hash,
        },
        warmbly_absent=warmbly_absent,
        max_warmbly_age_days=max_warmbly_age_days,
    )


def facts_from_join(join: JoinResult) -> tuple[AccountFact, ...]:
    return tuple(account.fact for account in join.accounts)
