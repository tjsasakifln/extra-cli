"""Fail-closed isolation for CONFENGE commercial campaign."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.commercial_leads import CAMPAIGN_ID

FORBIDDEN_HOST_MARKERS = (
    "ec-prod",
    "netcup",
    "vps",
    "production",
    "prod.extra",
    "extra-prod",
    "extra_prod",
    "/opt/extra-consultoria",
)

FORBIDDEN_PATH_MARKERS = (
    "/opt/extra-consultoria",
    "soak",
    "nfs",
    "HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01",
    "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01",
    "STRATIFIED-RECALL-SOURCE-RESILIENCE-01",
)

ALLOWED_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
# Exclusive campaign port preferred; other local campaign ports accepted for tests.
ALLOWED_PORTS = (5441, 5433, 5435, 5436, 5437, 5438, 5439)
FORBIDDEN_PORTS = (5432,)


@dataclass
class IsolationResult:
    ok: bool
    production_touched: bool
    soak_touched: bool
    dsn_masked: str
    host: str | None
    port: int | None
    database: str | None
    reasons: list[str] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "production_touched": self.production_touched,
            "soak_touched": self.soak_touched,
            "dsn_masked": self.dsn_masked,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "reasons": self.reasons,
            "forbidden_hits": self.forbidden_hits,
            "campaign_id": CAMPAIGN_ID,
        }


def mask_dsn(dsn: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", dsn or "")


def parse_dsn(dsn: str) -> tuple[str | None, int | None, str | None]:
    raw = (dsn or "").strip()
    if not raw:
        return None, None, None
    if "://" not in raw:
        raw = "postgresql://" + raw
    u = urlparse(raw)
    return u.hostname, u.port, (u.path or "").lstrip("/") or None


def assert_isolation(
    dsn: str,
    *,
    out_dir: Path | str | None = None,
    require_allowed_port: bool = True,
) -> IsolationResult:
    host, port, db = parse_dsn(dsn)
    reasons: list[str] = []
    hits: list[str] = []
    masked = mask_dsn(dsn)
    production = False
    soak = False

    if not dsn:
        return IsolationResult(
            ok=False,
            production_touched=False,
            soak_touched=False,
            dsn_masked="",
            host=None,
            port=None,
            database=None,
            reasons=["missing_dsn"],
        )

    hay = f"{dsn} {host or ''} {db or ''}".lower()
    for m in FORBIDDEN_HOST_MARKERS:
        if m.lower() in hay:
            hits.append(f"host_marker:{m}")
            production = True
    if port in FORBIDDEN_PORTS:
        hits.append(f"forbidden_port:{port}")
        production = True
    if host and host not in ALLOWED_LOCAL_HOSTS:
        hits.append(f"non_local_host:{host}")
        production = True
    if require_allowed_port and port is not None and port not in ALLOWED_PORTS:
        hits.append(f"port_not_in_allowlist:{port}")
        reasons.append("port_not_allowed_for_campaign")

    if out_dir is not None:
        p = str(Path(out_dir).resolve()).lower()
        for m in FORBIDDEN_PATH_MARKERS:
            if m.lower() in p:
                hits.append(f"path_marker:{m}")
                if "soak" in m.lower() or "historical-contracts" in m.lower() or "open-tenders" in m.lower():
                    soak = True
                else:
                    production = True

    # Env guard
    for key, val in os.environ.items():
        if not val:
            continue
        low = f"{key}={val}".lower()
        if "ec-prod" in low or "extra_prod" in low:
            # only flag if used as DSN-like
            if "postgres" in low or "dsn" in key.lower() or "@" in val:
                hits.append(f"env:{key}")
                production = True

    ok = not hits and not reasons
    if hits:
        reasons.append("isolation_violation")
    return IsolationResult(
        ok=ok,
        production_touched=production,
        soak_touched=soak,
        dsn_masked=masked,
        host=host,
        port=port,
        database=db,
        reasons=reasons,
        forbidden_hits=hits,
    )
