"""Canonical opportunity snapshot + official reconfirm + delta (EXTRA-DECISION-LOOP-01).

HTTP outcomes remain distinct: 204, 403, 429, 5xx, timeout, partial pagination.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DIR = PROJECT_ROOT / "data" / "decision_snapshots"

# Semantic HTTP / transport outcomes (never collapse into generic "error")
HTTP_OUTCOMES = frozenset(
    {
        "ok",
        "http_204",
        "http_403",
        "http_429",
        "http_5xx",
        "http_4xx",
        "timeout",
        "error",
        "skipped_offline_fixture",
        "pagination_incomplete",
        "not_attempted",
    }
)


@dataclass
class ReconfirmResult:
    opportunity_id: Any
    source: str
    url: str | None
    timestamp: str
    status_observed: str | None
    deadline: str | None
    http_status: int | None
    outcome: str
    raw_hash: str | None
    run_id: str | None
    collection_id: str | None
    rule: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Snapshot:
    snapshot_id: str
    created_at: str
    run_id: str
    collection_id: str | None
    profile_hash: str | None
    cutoff: str
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    reconfirms: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_http_status(code: int | None, *, body_empty: bool = False) -> str:
    if code is None:
        return "error"
    if code == 204 or (code == 200 and body_empty):
        return "http_204" if code == 204 else "ok"
    if code == 200:
        return "ok"
    if code == 403:
        return "http_403"
    if code == 429:
        return "http_429"
    if 500 <= code <= 599:
        return "http_5xx"
    if 400 <= code <= 499:
        return "http_4xx"
    return "error"


def select_active_opportunities(
    rows: list[dict[str, Any]],
    *,
    universe_cnpj8: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter open/upcoming in Extra scope."""
    out: list[dict[str, Any]] = []
    for r in rows:
        status = str(r.get("status_canonico") or "").lower()
        if status not in {"open", "upcoming"}:
            continue
        if not r.get("is_active", True):
            continue
        uf = str(r.get("uf") or "").upper()
        cnpj = "".join(ch for ch in str(r.get("orgao_cnpj") or "") if ch.isdigit())
        cnpj8 = cnpj[:8] if len(cnpj) >= 8 else ""
        in_universe = True
        if universe_cnpj8 is not None:
            in_universe = cnpj8 in universe_cnpj8 or uf == "SC"
        if not in_universe:
            continue
        out.append(r)
    return out


def pick_reconfirm_targets(
    rows: list[dict[str, Any]],
    *,
    actionable: list[dict[str, Any]] | None = None,
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """All actionable + top-N by score (or all if < top_n)."""
    by_id: dict[Any, dict[str, Any]] = {}
    for r in actionable or []:
        by_id[r.get("id") or r.get("source_id")] = r
    ranked = sorted(
        rows,
        key=lambda r: (
            0 if r.get("ranking") == "GO" else 1 if r.get("ranking") == "REVIEW" else 2,
            -(float(r.get("ranking_score") or 0)),
        ),
    )
    for r in ranked[:top_n]:
        by_id[r.get("id") or r.get("source_id")] = r
    if len(rows) <= top_n:
        for r in rows:
            by_id[r.get("id") or r.get("source_id")] = r
    return list(by_id.values())


def build_pncp_url(row: dict[str, Any]) -> str | None:
    link = row.get("link_edital") or row.get("source_url")
    if link:
        return str(link)
    cnpj = "".join(ch for ch in str(row.get("orgao_cnpj") or "") if ch.isdigit())
    num = str(row.get("numero_controle_pncp") or row.get("source_id") or "")
    if cnpj and num:
        # best-effort public page
        return f"https://pncp.gov.br/app/editais/{cnpj}"
    return None


def default_http_get(
    url: str,
    *,
    timeout: float = 15.0,
) -> tuple[int | None, str, str | None]:
    """Return (status_code, body_text, error)."""
    if not str(url).startswith(("http://", "https://")):
        return None, "", "invalid_scheme"
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "extra-decision-loop/1.0 (+local research)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body, None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        return int(exc.code), body, str(exc)
    except TimeoutError as exc:
        return None, "", f"timeout:{exc}"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return None, "", f"timeout:{exc}"
        return None, "", str(exc)


def reconfirm_opportunity(
    row: dict[str, Any],
    *,
    run_id: str | None = None,
    collection_id: str | None = None,
    http_get: Callable[..., tuple[int | None, str, str | None]] | None = None,
    offline: bool = False,
) -> ReconfirmResult:
    """Reconfirm one opportunity against official source (or offline fixture mode)."""
    ts = _utc_now()
    url = build_pncp_url(row)
    source = str(row.get("source") or "pncp")
    oid = row.get("id") or row.get("source_id")

    if offline or os.getenv("DECISION_RECONFIRM_OFFLINE") == "1":
        # Deterministic offline: treat DB status as observed without claiming live HTTP ok.
        return ReconfirmResult(
            opportunity_id=oid,
            source=source,
            url=url,
            timestamp=ts,
            status_observed=str(row.get("status_canonico")),
            deadline=str(row.get("data_encerramento") or "") or None,
            http_status=None,
            outcome="skipped_offline_fixture",
            raw_hash=_sha(json.dumps({"id": oid, "status": row.get("status_canonico")}, sort_keys=True)),
            run_id=run_id,
            collection_id=collection_id,
            rule="offline_db_status_not_live_http",
            error=None,
        )

    if not url:
        return ReconfirmResult(
            opportunity_id=oid,
            source=source,
            url=None,
            timestamp=ts,
            status_observed=None,
            deadline=None,
            http_status=None,
            outcome="error",
            raw_hash=None,
            run_id=run_id,
            collection_id=collection_id,
            rule="missing_official_url",
            error="no_url",
        )

    getter = http_get or default_http_get
    code, body, err = getter(url)
    if err and err.startswith("timeout"):
        outcome = "timeout"
    else:
        outcome = classify_http_status(code, body_empty=not (body or "").strip())
        if err and outcome == "error":
            outcome = "error"

    status_observed = None
    if outcome == "ok":
        # lightweight heuristic — do not invent closed if page loads
        low = body.lower()
        if "revogad" in low or "anulad" in low:
            status_observed = "revoked"
        elif "suspens" in low:
            status_observed = "suspended"
        elif "encerrad" in low and "abert" not in low:
            status_observed = "closed"
        else:
            status_observed = str(row.get("status_canonico") or "open")

    return ReconfirmResult(
        opportunity_id=oid,
        source=source,
        url=url,
        timestamp=ts,
        status_observed=status_observed,
        deadline=str(row.get("data_encerramento") or "") or None,
        http_status=code,
        outcome=outcome,
        raw_hash=_sha(body[:8000]) if body else None,
        run_id=run_id,
        collection_id=collection_id,
        rule="pncp_or_official_url_get",
        error=err,
    )


def build_snapshot(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    collection_id: str | None = None,
    profile_hash: str | None = None,
    reconfirm_map: dict[Any, dict[str, Any]] | None = None,
    snapshot_id: str | None = None,
) -> Snapshot:
    reconfirm_map = reconfirm_map or {}
    active = select_active_opportunities(rows)
    snap_id = snapshot_id or f"snap-{run_id}"
    created = _utc_now()
    opps: list[dict[str, Any]] = []
    for r in active:
        oid = r.get("id") or r.get("source_id")
        rc = reconfirm_map.get(oid) or {}
        high_conf_open = (
            str(r.get("status_canonico")) in {"open", "upcoming"}
            and rc.get("outcome") == "ok"
        )
        opps.append(
            {
                "id": oid,
                "source": r.get("source"),
                "source_id": r.get("source_id"),
                "numero_controle_pncp": r.get("numero_controle_pncp"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "orgao_nome": r.get("orgao_nome"),
                "objeto": r.get("objeto"),
                "status_canonico": r.get("status_canonico"),
                "data_encerramento": str(r.get("data_encerramento") or "") or None,
                "valor_estimado": r.get("valor_estimado"),
                "ranking": r.get("ranking"),
                "ranking_score": r.get("ranking_score"),
                "reconfirm_outcome": rc.get("outcome") or "not_attempted",
                "high_confidence_open": high_conf_open,
                "link_edital": r.get("link_edital"),
            }
        )
    return Snapshot(
        snapshot_id=snap_id,
        created_at=created,
        run_id=run_id,
        collection_id=collection_id,
        profile_hash=profile_hash,
        cutoff=created[:10],
        opportunities=opps,
        reconfirms=list(reconfirm_map.values()),
        counts={
            "active": len(opps),
            "high_confidence_open": sum(1 for o in opps if o.get("high_confidence_open")),
            "reconfirmed_ok": sum(1 for o in opps if o.get("reconfirm_outcome") == "ok"),
        },
    )


def compute_delta(
    previous: Snapshot | dict[str, Any] | None,
    current: Snapshot | dict[str, Any],
) -> dict[str, Any]:
    """Delta categories: new, changed, deadline_changed, suspended, revoked, closed, removed, still_open_reconfirmed."""
    prev = previous.to_dict() if isinstance(previous, Snapshot) else (previous or {})
    cur = current.to_dict() if isinstance(current, Snapshot) else current
    prev_map = {o.get("id"): o for o in (prev.get("opportunities") or [])}
    cur_map = {o.get("id"): o for o in (cur.get("opportunities") or [])}

    new_ids = [i for i in cur_map if i not in prev_map]
    removed_ids = [i for i in prev_map if i not in cur_map]
    deadline_changed: list[Any] = []
    changed: list[Any] = []
    suspended: list[Any] = []
    revoked: list[Any] = []
    closed: list[Any] = []
    still_open: list[Any] = []

    for oid, o in cur_map.items():
        if oid not in prev_map:
            continue
        p = prev_map[oid]
        if p.get("data_encerramento") != o.get("data_encerramento"):
            deadline_changed.append(oid)
        if p.get("status_canonico") != o.get("status_canonico"):
            changed.append(oid)
            st = str(o.get("status_canonico") or "")
            if st == "suspended":
                suspended.append(oid)
            elif st in {"revoked", "annulled"}:
                revoked.append(oid)
            elif st == "closed":
                closed.append(oid)
        if (
            o.get("status_canonico") in {"open", "upcoming"}
            and o.get("reconfirm_outcome") == "ok"
        ):
            still_open.append(oid)

    return {
        "schema": "extra-snapshot-delta/1.0",
        "previous_snapshot_id": prev.get("snapshot_id"),
        "current_snapshot_id": cur.get("snapshot_id"),
        "new": new_ids,
        "changed": changed,
        "deadline_changed": deadline_changed,
        "suspended": suspended,
        "revoked": revoked,
        "closed": closed,
        "removed": removed_ids,
        "still_open_reconfirmed": still_open,
        "counts": {
            "new": len(new_ids),
            "changed": len(changed),
            "deadline_changed": len(deadline_changed),
            "suspended": len(suspended),
            "revoked": len(revoked),
            "closed": len(closed),
            "removed": len(removed_ids),
            "still_open_reconfirmed": len(still_open),
        },
    }


def load_latest_snapshot(directory: Path | None = None) -> dict[str, Any] | None:
    d = directory or DEFAULT_SNAPSHOT_DIR
    if not d.is_dir():
        return None
    files = sorted(d.glob("snapshot-*.json"))
    if not files:
        return None
    raw = json.loads(files[-1].read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else None


def save_snapshot(snapshot: Snapshot, directory: Path | None = None) -> Path:
    d = directory or DEFAULT_SNAPSHOT_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"snapshot-{snapshot.snapshot_id}.json"
    path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    latest = d / "latest.json"
    latest.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def reconfirm_batch(
    targets: list[dict[str, Any]],
    *,
    run_id: str,
    collection_id: str | None = None,
    http_get: Callable[..., tuple[int | None, str, str | None]] | None = None,
    offline: bool = False,
    sleep_s: float = 0.0,
) -> dict[Any, dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = {}
    for row in targets:
        rc = reconfirm_opportunity(
            row,
            run_id=run_id,
            collection_id=collection_id,
            http_get=http_get,
            offline=offline,
        )
        out[rc.opportunity_id] = rc.to_dict()
        if sleep_s > 0:
            time.sleep(sleep_s)
    return out
