"""Isolation guard — refuse production / soak / VPS targets.

Campaign CANONICAL-ENTITY-LINKAGE-01 must never touch soak or production.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


# Forbidden host markers (literal substrings, case-insensitive)
FORBIDDEN_HOST_MARKERS = (
    "ec-prod",
    "netcup",
    "vps",
    "production",
    "prod.extra",
    "extra-prod",
)

FORBIDDEN_PATH_MARKERS = (
    "/opt/extra-consultoria",
    "soak",
    "nfs",
    "/var/lib/extra-soak",
    "historical-contracts-operational-closure-01/soak",
)

# Allowed local isolated hosts/ports for this campaign
ALLOWED_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
PREFERRED_PORTS = (5438,)


@dataclass
class IsolationCheck:
    ok: bool
    production_touched: bool
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
            "dsn_masked": self.dsn_masked,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "reasons": self.reasons,
            "forbidden_hits": self.forbidden_hits,
            "campaign_id": "CANONICAL-ENTITY-LINKAGE-01",
        }


def mask_dsn(dsn: str) -> str:
    return re.sub(r":([^:@/]+)@", ":***@", dsn or "")


def parse_dsn(dsn: str) -> tuple[str | None, int | None, str | None]:
    raw = (dsn or "").strip()
    if not raw:
        return None, None, None
    if "://" not in raw:
        raw = "postgresql://" + raw
    u = urlparse(raw)
    host = u.hostname
    port = u.port
    db = (u.path or "").lstrip("/") or None
    return host, port, db


def check_dsn(dsn: str | None, *, require_isolated_port: bool = True) -> IsolationCheck:
    dsn = dsn or os.environ.get("LINKAGE_TEST_DSN") or os.environ.get("LOCAL_DATALAKE_DSN") or ""
    host, port, db = parse_dsn(dsn)
    reasons: list[str] = []
    hits: list[str] = []
    masked = mask_dsn(dsn)

    if not dsn:
        return IsolationCheck(
            ok=False,
            production_touched=False,
            dsn_masked="",
            host=None,
            port=None,
            database=None,
            reasons=["missing_dsn"],
        )

    hay = f"{dsn} {host or ''} {db or ''}".lower()
    for m in FORBIDDEN_HOST_MARKERS:
        if m in hay:
            hits.append(f"host_marker:{m}")
    for m in FORBIDDEN_PATH_MARKERS:
        if m in hay:
            hits.append(f"path_marker:{m}")

    if host and host not in ALLOWED_LOCAL_HOSTS:
        hits.append(f"non_local_host:{host}")

    if require_isolated_port and port is not None and port not in PREFERRED_PORTS:
        # Campaign isolation: only preferred local RC ports are accepted.
        hits.append(f"port_not_isolated:{port}")
        reasons.append(f"port_{port}_not_preferred_5438")

    production_touched = bool(hits) and any(
        h.startswith("host_marker:") or h.startswith("path_marker:") or h.startswith("non_local_host:")
        for h in hits
    )
    # Port/path policy failures block ok without claiming production was touched.
    policy_fail = any(h.startswith("port_not_isolated:") for h in hits)
    ok = (
        not production_touched
        and not policy_fail
        and bool(host)
        and host in ALLOWED_LOCAL_HOSTS
        and (not require_isolated_port or port in PREFERRED_PORTS or port is None)
    )

    if ok:
        reasons.append("local_isolated_dsn")
    else:
        reasons.append("isolation_failed")

    return IsolationCheck(
        ok=ok,
        production_touched=production_touched,
        dsn_masked=masked,
        host=host,
        port=port,
        database=db,
        reasons=reasons,
        forbidden_hits=hits,
    )


def assert_isolated(dsn: str | None) -> IsolationCheck:
    chk = check_dsn(dsn)
    if not chk.ok or chk.production_touched:
        raise RuntimeError(
            "ISOLATION_GUARD_BLOCK: refused non-isolated or production/soak DSN "
            f"hits={chk.forbidden_hits} dsn={chk.dsn_masked}"
        )
    return chk


def scan_command_line(argv: list[str] | str) -> list[str]:
    """Return forbidden markers found in a command line (for gate scripts)."""
    text = " ".join(argv) if isinstance(argv, list) else str(argv)
    low = text.lower()
    hits: list[str] = []
    for m in FORBIDDEN_HOST_MARKERS + FORBIDDEN_PATH_MARKERS:
        if m.lower() in low:
            hits.append(m)
    if "ssh " in low and "ec-prod" in low:
        hits.append("ssh_ec-prod")
    if "systemctl" in low and "extra-" in low:
        hits.append("systemctl_extra")
    return hits
