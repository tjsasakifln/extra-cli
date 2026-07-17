"""Shared helpers for the workspace CLI facade.

Paths, DSN, graceful PostgreSQL access, JSON/table output, file fallbacks.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Auto-load .env
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_FILE)
    except ImportError:
        pass

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://test:test@127.0.0.1:5433/pncp_datalake",
)

PROJECT_ROOT = _PROJECT_ROOT
DATA_DIR = _PROJECT_ROOT / "data"
OUTPUT_DIR = _PROJECT_ROOT / "output"
SESSION_DIR = _PROJECT_ROOT / "docs" / "ops" / "session-2026-07-17"
SESSION_OUTPUT = _PROJECT_ROOT / "output" / "session-2026-07-17"
CLIENT_PROFILE = _PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml"
LEDGER_PATH = DATA_DIR / "extra_ledger.json"
OVERRIDES_PATH = DATA_DIR / "workspace_overrides.json"
ENTITY_SOURCE_REGISTRY = DATA_DIR / "entity_source_registry.jsonl"
EDITAL_WORKSPACE = DATA_DIR / "edital_workspace"
PROPOSAL_WORKSPACE = DATA_DIR / "proposal_workspace"


@dataclass
class SectionResult:
    """One section of the daily queue (or similar multi-section report)."""

    name: str
    status: str  # OK | EMPTY | UNAVAILABLE
    reason: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_dsn(explicit: str | None = None) -> str:
    """Resolve DSN from explicit arg or LOCAL_DATALAKE_DSN."""
    return explicit or os.getenv("LOCAL_DATALAKE_DSN") or DEFAULT_DSN


def try_pg_conn(dsn: str | None = None, timeout: int = 3) -> tuple[Any | None, str | None]:
    """Try PostgreSQL connection. Returns (conn, None) or (None, reason)."""
    target = get_dsn(dsn)
    try:
        import psycopg2

        conn = psycopg2.connect(target, connect_timeout=timeout)
        conn.autocommit = True
        return conn, None
    except Exception as exc:  # noqa: BLE001 — intentional graceful degrade
        return None, f"PostgreSQL unavailable: {type(exc).__name__}: {exc}"


def pg_query(
    conn: Any,
    sql: str,
    params: tuple[Any, ...] | list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Run SQL and return list of dicts (RealDictCursor)."""
    import psycopg2.extras

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [_serialize_row(dict(r)) for r in rows]


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (bytes, bytearray)):
            out[k] = v.decode("utf-8", errors="replace")
        else:
            # Decimal etc.
            try:
                from decimal import Decimal

                if isinstance(v, Decimal):
                    out[k] = float(v)
                    continue
            except ImportError:
                pass
            out[k] = v
    return out


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_jsonl(path: Path, limit: int = 500) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(items) >= limit:
                    break
    except OSError:
        return []
    return items


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def load_overrides() -> dict[str, Any]:
    data = load_json(OVERRIDES_PATH)
    if isinstance(data, dict):
        return data
    return {"version": 1, "overrides": [], "updated_at": None}


def save_overrides(data: dict[str, Any]) -> None:
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_json(OVERRIDES_PATH, data)


def load_ledger() -> dict[str, Any]:
    data = load_json(LEDGER_PATH)
    if isinstance(data, dict):
        return data
    return {
        "version": 1,
        "cliente": "Extra Construtora",
        "created_at": date.today().isoformat(),
        "oportunidades": [],
        "propostas": [],
        "contratos": [],
        "atestados": [],
        "capacidades": [],
        "notas": [],
    }


def save_ledger(data: dict[str, Any]) -> None:
    save_json(LEDGER_PATH, data)


def print_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    """Simple fixed-width table for terminal."""
    if not rows:
        print("  (vazio)")
        return
    cols = columns or list(rows[0].keys())
    # Cap column widths
    widths: dict[str, int] = {}
    for c in cols:
        widths[c] = min(48, max(len(c), max(len(_cell(r.get(c))) for r in rows)))
    header = " | ".join(c[: widths[c]].ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        print(" | ".join(_cell(r.get(c))[: widths[c]].ljust(widths[c]) for c in cols))


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.2f}"
    text = str(value).replace("\n", " ")
    return text


def emit(data: Any, as_json: bool = False) -> None:
    """Print structured result as JSON or human text."""
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def print_section(section: SectionResult, as_json: bool = False) -> None:
    if as_json:
        return  # caller emits full payload
    icon = {"OK": "✅", "EMPTY": "⬜", "UNAVAILABLE": "⚠️"}.get(section.status, "•")
    print(f"\n{icon} {section.name} [{section.status}]")
    if section.reason:
        print(f"   {section.reason}")
    if section.meta:
        meta_bits = [f"{k}={v}" for k, v in section.meta.items()]
        print(f"   meta: {', '.join(meta_bits)}")
    if section.items:
        # Prefer a short set of columns if present
        preferred = [
            "id",
            "orgao",
            "orgao_nome",
            "municipio",
            "objeto",
            "valor",
            "valor_estimado",
            "ranking",
            "status",
            "status_canonico",
            "data_abertura",
            "data_encerramento",
            "prazo",
            "fonte",
            "source",
            "dias_ate_fim",
            "field",
            "action",
            "bucket",
        ]
        cols = [c for c in preferred if any(c in it for it in section.items)]
        if not cols:
            cols = list(section.items[0].keys())[:6]
        print_table(section.items[:25], cols)
        if len(section.items) > 25:
            print(f"   … +{len(section.items) - 25} itens")


def slugify(text: str, max_len: int = 48) -> str:
    import re
    import unicodedata

    norm = unicodedata.normalize("NFKD", text)
    ascii_text = norm.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return (slug or "item")[:max_len]


def parse_date_safe(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
