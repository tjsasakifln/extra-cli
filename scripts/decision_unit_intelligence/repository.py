"""JSON-first persistence. SQL is additive and optional."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.models import dumps_stable


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Machine JSON stays ASCII-safe so Windows readers using the locale default do not corrupt evidence.
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def account_hash(account_dict: dict[str, Any]) -> str:
    import hashlib

    slim = {
        "cnpj": account_dict.get("cnpj"),
        "candidates": account_dict.get("candidates"),
        "routes": account_dict.get("routes"),
        "terminal": account_dict.get("terminal"),
        "recommendation": account_dict.get("recommendation"),
        "policy_version": account_dict.get("policy_version"),
    }
    return hashlib.sha256(dumps_stable(slim).encode("utf-8")).hexdigest()


class JsonRunRepository:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_account(self, account: dict[str, Any]) -> Path:
        path = self.root / "accounts" / f"{account['cnpj']}.json"
        write_json(path, account)
        return path

    def save_manifest(self, manifest: dict[str, Any]) -> Path:
        path = self.root / "manifest.json"
        write_json(path, manifest)
        return path

    def save_funnel(self, funnel: dict[str, Any]) -> Path:
        path = self.root / "funnel.json"
        write_json(path, funnel)
        return path

    def load_accounts(self) -> list[dict[str, Any]]:
        folder = self.root / "accounts"
        if not folder.exists():
            return []
        return [read_json(p) for p in sorted(folder.glob("*.json"))]
