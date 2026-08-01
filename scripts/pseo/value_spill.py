"""On-disk value spill for exact percentiles without O(N) Python lists.

Methodology (versioned):
- **method_id**: `sqlite_order_offset_v1`
- Values for each (namespace, bucket) are appended to a SQLite table.
- Exact percentile uses ORDER BY valor + LIMIT 1 OFFSET k, matching
  ``scripts.pseo.aggregate._pct`` index rule:
  ``k = min(n-1, max(0, int(round((p/100)*(n-1)))))``.
- Peak Python RAM is O(batch) for inserts + O(1) per percentile query —
  not O(N) value vectors.

Not an approximate sketch (no T-Digest / HDR). Do not claim approximation
error; this path is **exact** relative to the same discrete index rule as `_pct`.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

METHOD_ID = "sqlite_order_offset_v1"
METHOD_VERSION = "1.0.0"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spill_vals (
    ns TEXT NOT NULL,
    bucket TEXT NOT NULL,
    valor REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spill_ns_bucket_valor
    ON spill_vals(ns, bucket, valor);
"""


class ValueSpillStore:
    """SQLite spill of scalar values for exact on-disk percentiles."""

    def __init__(self, path: Path | None = None, *, create: bool = True) -> None:
        if path is None:
            fd, name = tempfile.mkstemp(prefix="pseo-value-spill-", suffix=".sqlite")
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
        self._pending: list[tuple[str, str, float]] = []
        self._batch_limit = 2_000

    def add(self, ns: str, bucket: str, valor: float) -> None:
        self._pending.append((ns, bucket, float(valor)))
        if len(self._pending) >= self._batch_limit:
            self.flush()

    def add_many(self, ns: str, bucket: str, valores: Iterable[float]) -> None:
        for v in valores:
            self.add(ns, bucket, float(v))

    def flush(self) -> None:
        if not self._pending:
            return
        self.conn.executemany(
            "INSERT INTO spill_vals(ns, bucket, valor) VALUES (?, ?, ?)",
            self._pending,
        )
        self._pending.clear()

    def commit(self) -> None:
        self.flush()
        self.conn.commit()

    def count(self, ns: str, bucket: str) -> int:
        self.flush()
        row = self.conn.execute(
            "SELECT COUNT(*) FROM spill_vals WHERE ns = ? AND bucket = ?",
            (ns, bucket),
        ).fetchone()
        return int(row[0]) if row else 0

    def sum(self, ns: str, bucket: str) -> float:
        self.flush()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(valor), 0) FROM spill_vals WHERE ns = ? AND bucket = ?",
            (ns, bucket),
        ).fetchone()
        return float(row[0]) if row else 0.0

    def min_max(self, ns: str, bucket: str) -> tuple[float | None, float | None]:
        self.flush()
        row = self.conn.execute(
            "SELECT MIN(valor), MAX(valor) FROM spill_vals WHERE ns = ? AND bucket = ?",
            (ns, bucket),
        ).fetchone()
        if not row or row[0] is None:
            return None, None
        return float(row[0]), float(row[1])

    def percentile(self, ns: str, bucket: str, p: float) -> float | None:
        """Exact discrete percentile (same index rule as aggregate._pct)."""
        n = self.count(ns, bucket)
        if n <= 0:
            return None
        off = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
        row = self.conn.execute(
            """
            SELECT valor FROM spill_vals
            WHERE ns = ? AND bucket = ?
            ORDER BY valor
            LIMIT 1 OFFSET ?
            """,
            (ns, bucket, off),
        ).fetchone()
        if row is None:
            return None
        return round(float(row[0]), 2)

    def methodology(self) -> dict[str, Any]:
        return {
            "method_id": METHOD_ID,
            "method_version": METHOD_VERSION,
            "exact": True,
            "approximate": False,
            "error_bound": None,
            "note": (
                "Exact on-disk ORDER BY + OFFSET percentiles; "
                "no Python O(N) value vectors on the streaming path."
            ),
        }

    def close(self) -> None:
        try:
            self.flush()
            self.conn.commit()
            self.conn.close()
        except sqlite3.Error:
            pass

    def secure_delete(self) -> None:
        self.close()
        if not self._owned:
            return
        if self.path.exists():
            try:
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
            for suffix in ("-wal", "-shm"):
                side = Path(str(self.path) + suffix)
                try:
                    side.unlink(missing_ok=True)
                except OSError:
                    pass
