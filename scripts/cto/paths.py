"""Repository path helpers for CTO Autopilot."""
from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return repository root (parent of scripts/)."""
    return Path(__file__).resolve().parents[2]


def cto_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".cto"


def config_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "config"


def output_cto(root: Path | None = None) -> Path:
    return (root or repo_root()) / "output" / "cto"


def current_dir(root: Path | None = None) -> Path:
    return output_cto(root) / "current"


def cycles_dir(root: Path | None = None) -> Path:
    return output_cto(root) / "cycles"


def work_registry_path(root: Path | None = None) -> Path:
    return config_dir(root) / "work_registry.yaml"


def policies_path(root: Path | None = None) -> Path:
    return cto_dir(root) / "policies.yaml"


def decision_schema_path(root: Path | None = None) -> Path:
    return cto_dir(root) / "decision.schema.json"


def review_schema_path(root: Path | None = None) -> Path:
    return cto_dir(root) / "review.schema.json"


def state_path(root: Path | None = None) -> Path:
    return current_dir(root) / "state.json"


def lock_path(root: Path | None = None) -> Path:
    return current_dir(root) / "process.lock"


def ledger_path(root: Path | None = None) -> Path:
    return current_dir(root) / "ledger.jsonl"


def observation_path(root: Path | None = None) -> Path:
    return current_dir(root) / "observation.json"


def decision_path(root: Path | None = None) -> Path:
    return current_dir(root) / "decision.json"


def budget_path(root: Path | None = None) -> Path:
    return current_dir(root) / "budget.json"


def executive_html_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "extra-consultoria-plano-executivo.html"


def dod_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "DOD.md"
