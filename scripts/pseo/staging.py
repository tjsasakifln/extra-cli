"""SQLite local staging for memory-bounded pSEO extraction.

Design goals (auditável / simple):
- Spill classified contracts and AEC bids to a temp SQLite file during DB/fixture load
- Never retain the full raw table in RAM
- Minimal indexes for streaming reads
- Secure delete (unlink) of staging file after use
- Deterministic row order (insertion order + stable id)
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.pseo.archetypes import ClassifiedContract

_SCHEMA = """
CREATE TABLE classified (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contrato_id TEXT,
    orgao_cnpj TEXT,
    orgao_nome TEXT,
    fornecedor_cnpj TEXT,
    fornecedor_nome TEXT,
    objeto TEXT NOT NULL,
    valor REAL NOT NULL,
    data_inicio TEXT,
    data_fim TEXT,
    data_publicacao TEXT,
    uf TEXT,
    municipio TEXT,
    source TEXT,
    archetypes_json TEXT NOT NULL
);
CREATE INDEX idx_classified_uf ON classified(uf);
CREATE INDEX idx_classified_data_pub ON classified(data_publicacao);

CREATE TABLE aec_bids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_json TEXT NOT NULL
);
CREATE INDEX idx_aec_bids_id ON aec_bids(id);

CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StagingStore:
    """Temp SQLite staging store for classified contracts + AEC bids."""

    def __init__(self, path: Path | None = None, *, create: bool = True) -> None:
        if path is None:
            fd, name = tempfile.mkstemp(prefix="pseo-staging-", suffix=".sqlite")
            os.close(fd)
            path = Path(name)
            self._owned = True
            create = True
        else:
            path = Path(path)
            self._owned = False
        self.path = path
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        if create:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()
        self._classified_n = 0
        self._bids_n = 0

    @classmethod
    def open_existing(cls, path: Path | str) -> StagingStore:
        """Open an already-populated staging file without recreating schema."""
        return cls(Path(path), create=False)

    def set_meta(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)),
        )

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row[0])

    def insert_classified_batch(self, rows: Iterable[ClassifiedContract]) -> int:
        payload = []
        for c in rows:
            payload.append(
                (
                    c.contrato_id,
                    c.orgao_cnpj,
                    c.orgao_nome,
                    c.fornecedor_cnpj,
                    c.fornecedor_nome,
                    c.objeto,
                    float(c.valor),
                    c.data_inicio,
                    c.data_fim,
                    c.data_publicacao,
                    c.uf,
                    c.municipio,
                    c.source,
                    json.dumps(list(c.archetypes), ensure_ascii=False),
                )
            )
        if not payload:
            return 0
        self.conn.executemany(
            """
            INSERT INTO classified (
                contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
                objeto, valor, data_inicio, data_fim, data_publicacao,
                uf, municipio, source, archetypes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        self._classified_n += len(payload)
        return len(payload)

    def insert_bids_batch(self, rows: Iterable[dict[str, Any]]) -> int:
        payload = [
            (json.dumps(dict(r), ensure_ascii=False, sort_keys=True, default=str),)
            for r in rows
        ]
        if not payload:
            return 0
        self.conn.executemany("INSERT INTO aec_bids (payload_json) VALUES (?)", payload)
        self._bids_n += len(payload)
        return len(payload)

    def commit(self) -> None:
        self.conn.commit()

    @property
    def classified_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM classified").fetchone()
        return int(row[0]) if row else 0

    @property
    def bids_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM aec_bids").fetchone()
        return int(row[0]) if row else 0

    def iter_classified(self, *, chunk_size: int = 5_000) -> Iterator[list[ClassifiedContract]]:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        cur = self.conn.execute(
            """
            SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
                   objeto, valor, data_inicio, data_fim, data_publicacao,
                   uf, municipio, source, archetypes_json
            FROM classified
            ORDER BY id
            """
        )
        while True:
            rows = cur.fetchmany(chunk_size)
            if not rows:
                break
            batch: list[ClassifiedContract] = []
            for r in rows:
                batch.append(
                    ClassifiedContract(
                        contrato_id=r[0],
                        orgao_cnpj=r[1] or "",
                        orgao_nome=r[2],
                        fornecedor_cnpj=r[3] or "",
                        fornecedor_nome=r[4],
                        objeto=r[5] or "",
                        valor=float(r[6] or 0),
                        data_inicio=r[7],
                        data_fim=r[8],
                        data_publicacao=r[9],
                        uf=r[10],
                        municipio=r[11],
                        source=r[12] or "pncp",
                        archetypes=list(json.loads(r[13] or "[]")),
                    )
                )
            yield batch

    def iter_bids(self, *, chunk_size: int = 5_000) -> Iterator[list[dict[str, Any]]]:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        cur = self.conn.execute("SELECT payload_json FROM aec_bids ORDER BY id")
        while True:
            rows = cur.fetchmany(chunk_size)
            if not rows:
                break
            yield [json.loads(r[0]) for r in rows]

    def load_all_classified(self, *, chunk_size: int = 5_000) -> list[ClassifiedContract]:
        """Forbidden on the export hot path — use iterators / stream_aggregate.

        Raises so CI/tests catch accidental full materialization.
        """
        raise RuntimeError(
            "load_all_classified is forbidden for memory-bounded export; "
            "use StagingStore.iter_classified + stream_aggregate reducers"
        )

    def load_all_bids(self, *, chunk_size: int = 5_000) -> list[dict[str, Any]]:
        """Forbidden on the export hot path — use iterators / stream_filter_bids."""
        raise RuntimeError(
            "load_all_bids is forbidden for memory-bounded export; "
            "use StagingStore.iter_bids + stream_filter_bids"
        )

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass  # best-effort close before unlink

    def secure_delete(self) -> None:
        """Close connection and unlink staging file (best-effort overwrite of path entry)."""
        self.close()
        if self.path.exists():
            try:
                # Best-effort zero truncate then unlink
                with open(self.path, "r+b") as fh:
                    size = fh.seek(0, os.SEEK_END)
                    fh.seek(0)
                    fh.write(b"\x00" * min(size, 1_048_576))
                    fh.truncate(0)
            except OSError:
                pass
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
            # WAL sidecars
            for suffix in ("-wal", "-shm"):
                side = Path(str(self.path) + suffix)
                try:
                    side.unlink(missing_ok=True)
                except OSError:
                    pass


def classified_to_row_dict(c: ClassifiedContract) -> dict[str, Any]:
    d = asdict(c)
    return d
