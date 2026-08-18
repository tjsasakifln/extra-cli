"""DSN admission, production refusal, sanitization, and threshold read.

These helpers are pure (except ``read_gate_threshold``, which imports the
shipped ``GATE_THRESHOLD``). They do not reimplement coverage math.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from scripts.ops.coverage_live_proof.errors import MissingDsnError, ProductionDsnError

PRODUCTION_HOST_MARKERS: tuple[str, ...] = (
    "ec-prod",
    "prod.",
    ".prod",
    "vps.",
    "netcup",
)
PRODUCTION_PATH_MARKERS: tuple[str, ...] = (
    "/opt/extra-consultoria",
    "/opt/extra/",
)
PRODUCTION_DB_NAMES: frozenset[str] = frozenset(
    {
        "extra_prod",
        "production",
        "prod",
        "prod_datalake",
    }
)
_PASSWORD_IN_URL = re.compile(r"(://[^:/?#]+):([^@/?#]*)@", re.IGNORECASE)
_POSTGRES_SCHEMES = frozenset({"postgres", "postgresql", "postgresql+psycopg2"})


def require_explicit_dsn(dsn: str | None) -> str:
    """Return a stripped DSN or raise if missing/blank."""
    if dsn is None or not str(dsn).strip():
        raise MissingDsnError("explicit DSN required (--dsn or LOCAL_DATALAKE_DSN)")
    return str(dsn).strip()


def refuse_non_postgres_scheme(dsn: str) -> None:
    """Refuse sqlite and other non-PostgreSQL URL schemes before connect."""
    parsed = urlparse(dsn)
    scheme = (parsed.scheme or "").split("+", 1)[0].lower()
    if scheme in {"sqlite", "sqlite3", "file"}:
        from scripts.ops.coverage_live_proof.errors import NotPostgresError

        raise NotPostgresError("SQLite DSN refused as live proof")
    if scheme and scheme not in _POSTGRES_SCHEMES and "://" in dsn:
        from scripts.ops.coverage_live_proof.errors import NotPostgresError

        raise NotPostgresError(f"non-PostgreSQL DSN scheme refused: {scheme}")


def production_hits(dsn: str) -> list[str]:
    """Return production markers found in host, path, or database name."""
    lowered = dsn.lower()
    parsed = urlparse(dsn if "://" in dsn else f"postgresql://{dsn}")
    host = (parsed.hostname or "").lower()
    dbname = (parsed.path or "").lstrip("/").split("?")[0].lower()
    hits: list[str] = []
    if "ec-prod" in lowered:
        hits.append("ec-prod")
    for marker in PRODUCTION_PATH_MARKERS:
        if marker in lowered:
            hits.append(marker.rstrip("/"))
    if "/opt/extra" in lowered and "ec-prod" not in hits:
        # recall_capture_window uses this substring; keep the same refuse class.
        hits.append("/opt/extra")
    if host in {"prod", "production"} or any(m in host for m in PRODUCTION_HOST_MARKERS):
        if f"host:{host}" not in hits:
            hits.append(f"host:{host}")
    if dbname in PRODUCTION_DB_NAMES:
        hits.append(f"db:{dbname}")
    return hits


def refuse_production_dsn(dsn: str) -> None:
    """Refuse known production host/base markers used in-repo."""
    hits = production_hits(dsn)
    if hits:
        raise ProductionDsnError(
            "production DSN refused: " + ", ".join(hits)
        )


def sanitize_dsn(dsn: str) -> str:
    """Redact the password in a DSN. Never returns the raw secret."""
    parsed = urlparse(dsn)
    if parsed.password is not None:
        user = parsed.username or ""
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        auth = f"{user}:***" if user or parsed.password else ""
        netloc = f"{auth}@{host}{port}" if auth else f"{host}{port}"
        return urlunparse(parsed._replace(netloc=netloc))
    return _PASSWORD_IN_URL.sub(r"\1:***@", dsn)


def sanitize_text(text: str, dsn: str | None = None) -> str:
    """Redact passwords and raw DSN material from logs or exception text."""
    redacted = text
    if dsn:
        password = urlparse(dsn).password
        if password:
            redacted = redacted.replace(password, "***")
        raw = dsn
        safe = sanitize_dsn(dsn)
        if raw != safe:
            redacted = redacted.replace(raw, safe)
    redacted = _PASSWORD_IN_URL.sub(r"\1:***@", redacted)
    return redacted


def read_gate_threshold() -> float:
    """Read GATE_THRESHOLD from the shipped dual-coverage implementation."""
    from scripts.coverage.dual_capability_coverage import GATE_THRESHOLD

    return float(GATE_THRESHOLD)


def replace_database_name(dsn: str, dbname: str) -> str:
    """Return a DSN pointing at ``dbname`` on the same host/user."""
    parsed = urlparse(dsn)
    return urlunparse(parsed._replace(path=f"/{dbname}"))


def database_name_from_dsn(dsn: str) -> str:
    parsed = urlparse(dsn)
    return (parsed.path or "").lstrip("/").split("?")[0]
