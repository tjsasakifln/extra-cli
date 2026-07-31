"""Bounded, event-invalidatable search catalog — no per-request full rglob."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Extensions eligible for artifact catalog entries
_ARTIFACT_EXTS = frozenset({".json", ".jsonl", ".md", ".csv", ".xlsx", ".pdf", ".txt", ".log"})
_DEFAULT_ROOTS = ("output", "artifacts", "docs")
_MAX_ENTRIES = 5_000
_DEFAULT_TTL_SEC = 30.0


@dataclass
class CatalogEntry:
    path: str
    name: str
    root: str
    mtime: float

    def as_result(self) -> dict[str, Any]:
        return {
            "type": "artifact",
            "id": self.path,
            "label": self.name,
            "detail": self.path,
            "href": f"/results?path={self.path}",
        }


class ArtifactSearchIndex:
    """In-memory catalog rebuilt on TTL or explicit invalidate — never hot-path rglob unbounded."""

    def __init__(
        self,
        repo_root: Path,
        roots: tuple[str, ...] = _DEFAULT_ROOTS,
        *,
        ttl_sec: float = _DEFAULT_TTL_SEC,
        max_entries: int = _MAX_ENTRIES,
    ) -> None:
        self.repo_root = repo_root
        self.roots = roots
        self.ttl_sec = ttl_sec
        self.max_entries = max_entries
        self._lock = threading.RLock()
        self._entries: list[CatalogEntry] = []
        self._built_at = 0.0
        self._generation = 0

    def invalidate(self) -> None:
        with self._lock:
            self._built_at = 0.0
            self._generation += 1

    def ensure_fresh(self, *, force: bool = False) -> list[CatalogEntry]:
        with self._lock:
            now = time.monotonic()
            if not force and self._entries and (now - self._built_at) < self.ttl_sec:
                return list(self._entries)
            self._entries = self._build()
            self._built_at = now
            return list(self._entries)

    def _build(self) -> list[CatalogEntry]:
        entries: list[CatalogEntry] = []
        for root_name in self.roots:
            root = (self.repo_root / root_name).resolve()
            if not root.exists() or not root.is_dir():
                continue
            try:
                # Controlled walk with hard caps — not a free rglob on request path semantics
                for dirpath, dirnames, filenames in os.walk(root):
                    # Skip heavy / irrelevant trees
                    dirnames[:] = [
                        d
                        for d in dirnames
                        if d not in {".git", "node_modules", "__pycache__", ".venv", "dist"}
                    ]
                    for name in filenames:
                        if Path(name).suffix.lower() not in _ARTIFACT_EXTS:
                            continue
                        p = Path(dirpath) / name
                        try:
                            if not p.is_file():
                                continue
                            # Path jail: must remain under root
                            resolved = p.resolve()
                            if not str(resolved).startswith(str(root)):
                                continue
                            st = resolved.stat()
                            entries.append(
                                CatalogEntry(
                                    path=str(resolved),
                                    name=resolved.name,
                                    root=root_name,
                                    mtime=st.st_mtime,
                                )
                            )
                        except OSError:
                            continue
                        if len(entries) >= self.max_entries:
                            break
                    if len(entries) >= self.max_entries:
                        break
            except OSError:
                continue
            if len(entries) >= self.max_entries:
                break
        # Deterministic order: newer first, then path
        entries.sort(key=lambda e: (-e.mtime, e.path))
        return entries[: self.max_entries]

    def search(self, query: str, *, limit: int = 40) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        if len(q) < 2:
            return []
        entries = self.ensure_fresh()
        out: list[dict[str, Any]] = []
        for e in entries:
            blob = f"{e.name} {e.path}".lower()
            if q in blob:
                out.append(e.as_result())
                if len(out) >= limit:
                    break
        return out


_INDEX: ArtifactSearchIndex | None = None
_INDEX_LOCK = threading.Lock()


def get_search_index(repo_root: Path | None = None) -> ArtifactSearchIndex:
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is None:
            root = repo_root or Path(__file__).resolve().parents[2]
            _INDEX = ArtifactSearchIndex(root)
        return _INDEX
