"""Append-only ledger for manual overrides (DoD §29).

Every override must carry: reason (motivo), timestamp (data), author (autor).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_OVERRIDE_FIELDS: tuple[str, ...] = ("motivo", "data", "autor", "target", "action")


@dataclass(frozen=True)
class ManualOverride:
    target: str
    action: str
    motivo: str
    autor: str
    data: str
    before: Any = None
    after: Any = None
    run_id: str | None = None

    def validate(self) -> None:
        if not self.motivo or not str(self.motivo).strip():
            raise ValueError("override requires motivo")
        if not self.autor or not str(self.autor).strip():
            raise ValueError("override requires autor")
        if not self.data or not str(self.data).strip():
            raise ValueError("override requires data")
        if not self.target or not self.action:
            raise ValueError("override requires target and action")


def new_override(
    *,
    target: str,
    action: str,
    motivo: str,
    autor: str,
    before: Any = None,
    after: Any = None,
    run_id: str | None = None,
    data: str | None = None,
) -> ManualOverride:
    ov = ManualOverride(
        target=target,
        action=action,
        motivo=motivo,
        autor=autor,
        data=data or datetime.now(UTC).isoformat(),
        before=before,
        after=after,
        run_id=run_id,
    )
    ov.validate()
    return ov


def append_override(path: str | Path, override: ManualOverride) -> Path:
    """Append one validated override as JSONL."""
    override.validate()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(override), ensure_ascii=False, default=str) + "\n")
    return p


def load_overrides(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def validate_override_row(row: dict[str, Any]) -> dict[str, Any]:
    issues = [f"missing:{k}" for k in REQUIRED_OVERRIDE_FIELDS if not row.get(k)]
    return {"ok": len(issues) == 0, "issues": issues}
