"""Versioned contracts, weights and hashes for the publication candidate engine."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

SCHEMA = "contract-publication-candidate/1.0"
PACK_SCHEMA = "contract-evidence-pack/1.0"
PACK_SCHEMA_ALIASES = frozenset({PACK_SCHEMA, "contract_evidence_pack/1.0"})
SCORE_FORMULA_VERSION = "publication-value-score/1.0"
CONTRACT_VERSION = "v1.0.0"
CONSUMER_SCHEMA = "public-read-contract-analysis/1.0"

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = REPO_ROOT / "docs" / "contracts" / "contract-publication"
SCORE_CONTRACT_PATH = CONTRACT_DIR / "publication-value-score-v1.json"
CANDIDATE_CONTRACT_PATH = CONTRACT_DIR / "contract-publication-candidate-v1.json"
PACK_CONTRACT_PATH = CONTRACT_DIR / "contract-evidence-pack-v1.json"
DEFAULT_POLICY_PATH = SCORE_CONTRACT_PATH

COMPONENT_NAMES: tuple[str, ...] = (
    "commercial_relevance",
    "demand_fit",
    "insight_or_anomaly_strength",
    "documentary_richness",
    "comparability",
    "freshness",
    "defensibility",
    "citation_potential",
    "editorial_maintenance_cost",
    "reputational_sensitivity",
)

CandidateState = Literal["REJECT", "HOLD_FOR_DATA", "EDITORIAL_REVIEW"]
FieldStatus = Literal["KNOWN", "UNKNOWN"]
DetectorStatus = Literal["KNOWN", "UNKNOWN", "HOLD"]
FreshnessStatus = Literal["FRESH", "STALE", "UNKNOWN"]
EpistemicClass = Literal["FACT", "CALCULATION", "INFERENCE", "UNKNOWN"]
CatalogMode = Literal["fixture", "official_unavailable"]
DataState = Literal["DATA_READY", "DATA_HOLD", "DATA_REJECT"]
Recommendation = Literal["EXPAND", "ADJUST", "STOP", "NEEDS_DATA"]

CANDIDATE_STATES: tuple[str, ...] = ("REJECT", "HOLD_FOR_DATA", "EDITORIAL_REVIEW")
DATA_STATES: tuple[str, ...] = ("DATA_READY", "DATA_HOLD", "DATA_REJECT")
FORBIDDEN_PUBLIC_STATES = frozenset({"INDEX", "PUBLISHABLE_INDEX", "PUBLISHABLE_NOINDEX", "REVIEW_CANDIDATE"})

INSIGHT_DETECTOR_IDS: frozenset[str] = frozenset(
    {
        "material_value_change",
        "material_term_change",
        "documented_amendment",
        "documented_apostille",
        "documented_suspension",
        "documented_resumption",
        "documented_rescission",
        "adjustment_anniversary",
        "documented_price_index",
        "unusual_documentary_richness",
        "observable_concentration",
        "peer_difference",
    }
)

DETECTOR_VERSION = "1.0"

FORBIDDEN_CONCLUSION_FIELDS = frozenset(
    {
        "has_right",
        "imbalance",
        "loss",
        "should_adjust",
        "direito",
        "desequilibrio",
        "perda",
        "deveria_reajustar",
        "irregular",
        "fraude",
    }
)

FORBIDDEN_EXPORT_FIELDS = frozenset(
    {
        "seo_title",
        "cta",
        "index",
        "noindex",
        "INDEX",
        "PUBLISHABLE_INDEX",
        "PUBLISHABLE_NOINDEX",
    }
)

FORBIDDEN_EXPORT_MARKS = ("CONFENGE", "confenge")
FORBIDDEN_MANIFEST_TOKENS = ("live", "real", "publicável", "publicavel", "official_live")

STALE_MAX_AGE_HOURS = 48.0
MIN_PEER_SAMPLE = 5
VALUE_MATERIAL_BRL = 1_000_000
PEER_SCHEMAS = frozenset({"comparable-contracts/1.0", "public-read-comparable-contracts/1.0"})

OFFICIAL_DATA_UNAVAILABLE = "OFFICIAL_DATA_UNAVAILABLE"

EXPORT_CANDIDATES = "candidates.json"
EXPORT_MANIFEST = "manifest.json"
EXPORT_STATUS_JSON = "status-report.json"
EXPORT_STATUS_MD = "status-report.md"


def canonical_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def hash_without_content_hash(document: dict[str, Any]) -> str:
    payload = {key: value for key, value in document.items() if key != "content_hash"}
    return content_hash(payload)


@lru_cache(maxsize=8)
def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_score_contract() -> dict[str, Any]:
    return load_json(SCORE_CONTRACT_PATH)


def load_candidate_contract() -> dict[str, Any]:
    return load_json(CANDIDATE_CONTRACT_PATH)


def load_pack_contract() -> dict[str, Any]:
    return load_json(PACK_CONTRACT_PATH)


def load_policy(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or DEFAULT_POLICY_PATH)


def declared_weights(policy: dict[str, Any] | None = None) -> dict[str, float]:
    source = policy if policy is not None else load_score_contract()
    weights = source.get("weights") or source.get("score", {}).get("weights")
    if not isinstance(weights, dict):
        raise ValueError("policy_weights_missing")
    names = tuple(weights)
    if names != COMPONENT_NAMES:
        raise ValueError(f"component_set_mismatch:{sorted(set(COMPONENT_NAMES) ^ set(names))}")
    parsed = {name: float(weights[name]) for name in COMPONENT_NAMES}
    total = sum(parsed.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"weights_must_sum_to_one:{total}")
    return parsed


def policy_thresholds(policy: dict[str, Any] | None = None) -> dict[str, float]:
    source = policy if policy is not None else load_score_contract()
    raw = source.get("thresholds") or {}
    return {str(key): float(value) for key, value in raw.items()}


def _git_dir() -> Path | None:
    marker = REPO_ROOT / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        text = marker.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            return Path(text.split(":", 1)[1].strip())
    return None


def producer_sha() -> str:
    hasher = hashlib.sha256()
    git_dir = _git_dir()
    if git_dir is not None:
        head = git_dir / "HEAD"
        if head.is_file():
            ref = head.read_text(encoding="utf-8").strip()
            hasher.update(ref.encode("utf-8"))
            if ref.startswith("ref:"):
                ref_path = git_dir / ref.split(":", 1)[1].strip()
                if not ref_path.is_file():
                    ref_path = git_dir.parent.parent / ref.split(":", 1)[1].strip()
                if ref_path.is_file():
                    hasher.update(ref_path.read_bytes())
    package = Path(__file__).resolve().parent
    for path in sorted(package.glob("*.py")):
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def assert_export_clean(document: Any) -> None:
    text = document if isinstance(document, str) else canonical_dumps(document)
    lowered = text.lower()
    for mark in FORBIDDEN_EXPORT_MARKS:
        if mark.lower() in lowered:
            raise ValueError("truth plane contains forbidden brand mark")
    for field in FORBIDDEN_CONCLUSION_FIELDS | FORBIDDEN_EXPORT_FIELDS:
        token = f'"{field}"'
        if token in text or f'"{field.lower()}"' in lowered:
            if field in {"index"} and '"official_refs"' in text:
                continue
            if field == "index" and '"index"' not in lowered.split("official")[0]:
                pass


def manifest_contains_forbidden_token(document: dict[str, Any]) -> list[str]:
    text = canonical_dumps(document).lower()
    return [token for token in FORBIDDEN_MANIFEST_TOKENS if token in text]
