"""Filesystem cache keyed by cnpj_root + source_hash + as_of."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.confenge_account_intelligence.models import cache_key as make_cache_key


class AccountIntelCache:
    """Simple JSON file cache. Offline-safe; no network."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else Path(".cache/confenge_account_intelligence")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_").replace(":", "__")
        return self.root / f"{safe}.json"

    def get(self, *, cnpj_root: str, source_hash: str, as_of: str) -> dict[str, Any] | None:
        key = make_cache_key(cnpj_root_value=cnpj_root, source_hash=source_hash, as_of=as_of)
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    def put(
        self,
        dossier: dict[str, Any],
        *,
        cnpj_root: str,
        source_hash: str,
        as_of: str,
    ) -> Path:
        key = make_cache_key(cnpj_root_value=cnpj_root, source_hash=source_hash, as_of=as_of)
        path = self._path(key)
        path.write_text(
            json.dumps(dossier, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return path

    def key(self, *, cnpj_root: str, source_hash: str, as_of: str) -> str:
        return make_cache_key(cnpj_root_value=cnpj_root, source_hash=source_hash, as_of=as_of)
