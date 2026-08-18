"""Versioned constants for historical-contract-authority-dossier/1.0."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

SCHEMA = "historical-contract-authority-dossier/1.0"
SCHEMA_V11 = "historical-contract-authority-dossier/1.1"
METHOD_VERSION = "historical-contract-authority-method/1.0"
EXTRACTOR_VERSION = "historical-contract-authority-extract/1.0"
SCORE_VERSION = "dossier-authority-score/1.0"
CONTRACT_VERSION = "v1.0.0"
CONSUMER_SCHEMA = "public-read-contract-analysis/1.0"
CONSUMER_ID = "web-cfg#83"
HANDOFF_SCHEMA = "authority-handoff-contract-analysis/1.0"
HANDOFF_SCHEMA_V11 = "official-live-authority-handoff/1.1"

DossierState = Literal["REJECT", "HOLD_FOR_DATA", "HANDOFF_READY"]
ClaimClass = Literal["FACT", "CALCULATION", "INFERENCE", "UNKNOWN"]
DataState = Literal["DATA_READY", "DATA_HOLD", "DATA_REJECT"]
ComparabilityState = Literal["COMPARABLE", "HOLD_FOR_DATA", "NOT_COMPARABLE", "NOT_APPLICABLE"]

DOSSIER_STATES: tuple[str, ...] = ("REJECT", "HOLD_FOR_DATA", "HANDOFF_READY")
CLAIM_CLASSES: tuple[str, ...] = ("FACT", "CALCULATION", "INFERENCE", "UNKNOWN")
DATA_STATES: tuple[str, ...] = ("DATA_READY", "DATA_HOLD", "DATA_REJECT")
COMPARABILITY_STATES: tuple[str, ...] = ("COMPARABLE", "HOLD_FOR_DATA", "NOT_COMPARABLE", "NOT_APPLICABLE")
ANALYSIS_MODES: tuple[str, ...] = ("DOCUMENT_CHAIN", "TIMELINE", "COMPARATIVE")

FORBIDDEN_PUBLIC_STATES = frozenset(
    {"INDEX", "PUBLISHABLE_INDEX", "PUBLISHABLE_NOINDEX", "PUBLISHABLE", "REVIEW_CANDIDATE"}
)
FORBIDDEN_PUBLIC_TOKENS = ("PUBLISHABLE", "INDEX")
FORBIDDEN_CONCLUSION = frozenset(
    {
        "irregular",
        "fraude",
        "sobrepreco",
        "sobrepreço",
        "culpa",
        "desequilibrio",
        "desequilíbrio",
        "deveria_reajustar",
        "has_right",
        "imbalance",
        "loss",
        "should_adjust",
    }
)
FORBIDDEN_BRAND = ("CONFENGE", "confenge", "SmartLic", "smartlic", "extra-cli")

SCORE_WEIGHTS: dict[str, int] = {
    "documentary_depth": 25,
    "epistemic_integrity": 20,
    "analytical_singularity": 15,
    "calc_chronology_rigor": 15,
    "decision_utility": 15,
    "citability": 5,
    "maintenance": 5,
}
SCORE_TOTAL = 100
HANDOFF_MIN_SCORE = 88
HANDOFF_MIN_DIMENSION = 75
MIN_MATERIAL_CLAIMS = 5
MIN_EVIDENCE_FAMILIES = 3
MAX_HANDOFF_READY = 5
MAX_OFFICIAL_LIVE_READY = 3
MAX_OFFICIAL_LIVE_CANDIDATES = 12

USER_AGENT = (
    "Extra-CLI-historical-contract-authority/1.0 "
    "(+https://github.com/tjsasakifln/extra-cli; read-only official documents)"
)
MAX_CONTRACTS = 8
MAX_DOCS_PER_CONTRACT = 4
MAX_BYTES_PER_DOC = 8 * 1024 * 1024
MAX_REQUESTS = 24
FETCH_TIMEOUT_S = 15.0
FETCH_RETRIES = 2
RATE_LIMIT_S = 1.0

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_DIR = REPO_ROOT / "exports" / "authority-handoff" / "contract-analysis" / "1.0"

STATE_TO_DATA = {
    "HANDOFF_READY": "DATA_READY",
    "HOLD_FOR_DATA": "DATA_HOLD",
    "REJECT": "DATA_REJECT",
}


def canonical_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GENERIC_FICHA_QUESTIONS = frozenset(
    {
        "what is the contract value?",
        "qual o valor do contrato?",
        "qual o valor do contrato",
    }
)


def is_sha256(value: str | None) -> bool:
    return bool(value and _SHA256_RE.fullmatch(value))


def hash_without_content_hash(document: dict[str, Any]) -> str:
    return content_hash({key: value for key, value in document.items() if key != "content_hash"})


def dossier_id(*, contract_id: str, snapshot_hash: str) -> str:
    return content_hash(
        {
            "schema": SCHEMA,
            "method": METHOD_VERSION,
            "contract_id": contract_id,
            "snapshot_hash": snapshot_hash,
        }
    )[:32]


def producer_sha() -> str:
    hasher = hashlib.sha256()
    git_dir = REPO_ROOT / ".git"
    if git_dir.is_file():
        text = git_dir.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            git_dir = Path(text.split(":", 1)[1].strip())
    if git_dir.is_dir():
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
