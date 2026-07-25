#!/usr/bin/env python3
"""CLIENT-READY-RECURRING-CONSULTING-CYCLE-01 — integrated consulting cycle.

Canonical operator entry:
  make client-ready-consulting-cycle
  python -m scripts.ops.client_ready_consulting_cycle run --dsn ... --out ...

Sequences (isolated PostgreSQL only):
  isolation → migrations → profile → snapshot validate → opportunities
  → linkage → dossiers → A–E pack → weekly → monthly+delta → reconcile → evidence

Global terminal status is exactly one of: PASS | BLOCKED | FAIL.
Human RC acceptance is required for PASS; otherwise BLOCKED when technical path is green.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

CAMPAIGN_ID = "CLIENT-READY-RECURRING-CONSULTING-CYCLE-01"
DEFAULT_DSN = os.getenv(
    "CLIENT_READY_DSN",
    os.getenv(
        "CAMPAIGN_TEST_DSN",
        "postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc",
    ),
)
DEFAULT_OUT = _PROJECT_ROOT / "artifacts" / "campaigns" / CAMPAIGN_ID

# Identity files that must exist on both sides of acceptance binding (fail-closed).
REQUIRED_IDENTITY_FILES: tuple[str, ...] = (
    "pack-manifest.json",
    "executive-summary.md",
    "consulting-pack.xlsx",
    "executive-report.pdf",
)

# Frozen release candidate for human product review (PR #131).
# v1 (CHANGES_REQUESTED): commercial irrelevance — kept historical only.
# v2: sector-filtered engineering pack — PENDING_HUMAN (never auto-ACCEPTED).
FROZEN_RC_V1_RUN_ID = "live-pack-20260724-220350-da3bee0b"
FROZEN_RC_V1_PRODUCT_SHA = "be96c8bc8eb2b017e491bfafe8cf99f81e321267"
FROZEN_RC_V1_ARTIFACT_NAME = "client-ready-frozen-rc"
FROZEN_RC_V1_STATUS = "CHANGES_REQUESTED"

# Active freeze identity — commercial RC v2 (sector-filtered engineering pack).
FROZEN_RC_RUN_ID = "live-pack-20260725-030451-7af94c4f"
FROZEN_RC_PRODUCT_SHA = "f7acffb8f37a14329ecc14246676ced0fcbe27aa"
FROZEN_RC_SNAPSHOT_COMMIT = "HEAD"
FROZEN_RC_ARTIFACT_NAME = "client-ready-frozen-rc-v2"
BLOCKED_MISSING_FROZEN_RC = "BLOCKED_MISSING_FROZEN_RC_OUTPUTS"

# Dump package may live outside the worktree (large ADR-020 artifact). Search order:
_DUMP_CANDIDATES = (
    _PROJECT_ROOT / "artifacts/migration/backfill-vps/pkg-20260723T195047Z",
    Path("/mnt/d/extra consultoria/artifacts/migration/backfill-vps/pkg-20260723T195047Z"),
    Path.home() / "extra-consultoria/artifacts/migration/backfill-vps/pkg-20260723T195047Z",
)


def _resolve_dump_package() -> Path | None:
    for p in _DUMP_CANDIDATES:
        if (p / "db/pncp_supplier_contracts.dump").exists() or (p / "meta/SHA256SUMS").exists():
            return p
    return None


DUMP_PACKAGE = _resolve_dump_package() or _DUMP_CANDIDATES[0]
E_EVIDENCE_DEFAULT = (
    _PROJECT_ROOT
    / "artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01"
    / "weekly-offline-rc/deliverable_e.json"
)

FORBIDDEN_HOST_MARKERS = (
    "ec-prod",
    "extra_prod",
    "/opt/extra-consultoria",
    "netcup",
    "prod.extra",
)
ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1")
ALLOWED_PORTS = (5433, 5435, 5436, 5437, 5438, 5439)  # local campaign ports only
# 5432 is reserved for shared/prod-like stacks (e.g. n8n/recuperador) — reject.
FORBIDDEN_PORTS = (5432,)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha(root: Path | None = None) -> str:
    r = root or _PROJECT_ROOT
    try:
        out = subprocess.check_output(  # noqa: S603
            ["/usr/bin/git", "rev-parse", "HEAD"],
            cwd=str(r),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


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


def isolation_guard(dsn: str, out_dir: Path | None = None) -> dict[str, Any]:
    """Fail-closed isolation. Null/unknown production_touched is not success."""
    host, port, db = parse_dsn(dsn)
    hits: list[str] = []
    hay = f"{dsn} {host or ''} {db or ''} {out_dir or ''}".lower()
    for m in FORBIDDEN_HOST_MARKERS:
        if m.lower() in hay:
            hits.append(f"forbidden:{m}")
    if host and host not in ALLOWED_HOSTS:
        hits.append(f"host_not_local:{host}")
    if port in FORBIDDEN_PORTS:
        hits.append(f"forbidden_port:{port}")
    if port is not None and port not in ALLOWED_PORTS:
        hits.append(f"port_not_campaign_isolated:{port}")
    if not dsn:
        hits.append("missing_dsn")
    if not host:
        hits.append("host_unconfirmed")
    if not db:
        hits.append("database_identity_unconfirmed")

    production_touched = any(
        h.startswith("forbidden:") or h.startswith("host_not_local:") for h in hits
    )
    # Explicit false only when confirmed isolated; never null.
    ok = len(hits) == 0 and not production_touched
    result = {
        "ok": ok,
        "production_touched": False if ok else production_touched,
        "soak_touched": False if ok else None,  # unknown if isolation failed
        "dsn_masked": mask_dsn(dsn),
        "host": host,
        "port": port,
        "database": db,
        "hits": hits,
        "checked_at": utc_now(),
        "campaign_id": CAMPAIGN_ID,
    }
    if not ok:
        # fail-closed: unknown soak is treated as blocker
        result["soak_touched"] = result["soak_touched"] is True  # force bool false only if known
        if result["soak_touched"] is None:
            result["soak_touched"] = False  # not claimed; isolation already failed
        raise SystemExit(
            json.dumps(
                {
                    "status": "FAIL",
                    "error": "ISOLATION_GUARD_BLOCK",
                    "isolation": result,
                },
                ensure_ascii=False,
            )
        )
    # Confirmed isolated path
    result["production_touched"] = False
    result["soak_touched"] = False
    return result


def connect(dsn: str) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_migrations(dsn: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    r1 = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", dsn],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    r2 = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", dsn],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "first_exit": r1.returncode,
        "second_exit": r2.returncode,
        "idempotent": r1.returncode == 0 and r2.returncode == 0,
        "duration_s": round(time.perf_counter() - t0, 3),
        "stderr_tail": (r1.stderr or r2.stderr or "")[-500:],
    }


def validate_profile() -> dict[str, Any]:
    from scripts.ops.diagnostic_profile import profile_stamp

    stamp = profile_stamp()
    path = _PROJECT_ROOT / "config/client_profiles/extra.yaml"
    body = path.read_bytes() if path.exists() else b""
    return {
        **stamp,
        "profile_path": str(path.relative_to(_PROJECT_ROOT)) if path.exists() else None,
        "profile_sha256": hashlib.sha256(body).hexdigest() if body else None,
        "exists": path.exists(),
    }


def validate_snapshot(conn: Any, dsn: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pncp_supplier_contracts")
        n = int(cur.fetchone()["n"])
        # Prefer SC filter if column uf exists
        try:
            cur.execute(
                """
                SELECT count(*) AS n FROM pncp_supplier_contracts
                WHERE COALESCE(is_active, TRUE) IS TRUE AND uf = 'SC'
                """
            )
            n_sc = int(cur.fetchone()["n"])
        except Exception:  # noqa: BLE001
            conn.rollback()
            n_sc = None
        cur.execute(
            "SELECT version FROM _migrations ORDER BY version DESC LIMIT 5"
        )
        migrations = [r["version"] for r in cur.fetchall()]
        cur.execute("SELECT current_database() AS db, inet_server_addr() AS addr")
        ident = dict(cur.fetchone() or {})

    dump_pkg = _resolve_dump_package()
    dump_path = (dump_pkg / "db/pncp_supplier_contracts.dump") if dump_pkg else None
    meta_path = (dump_pkg / "meta/export-result.json") if dump_pkg else None
    expected = None
    dump_sha = None
    dump_sha_source = None
    if meta_path and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        expected = meta.get("contracts_count")
    sums = (dump_pkg / "meta/SHA256SUMS") if dump_pkg else None
    listed_sha = None
    if sums and sums.exists():
        for line in sums.read_text(encoding="utf-8").splitlines():
            if "pncp_supplier_contracts.dump" in line:
                listed_sha = line.split()[0]
                break
    if dump_path and dump_path.exists():
        # Prefer listed authenticated checksum (ADR-020) to avoid multi-minute rehash
        if listed_sha and len(listed_sha) == 64:
            dump_sha = listed_sha
            dump_sha_source = "SHA256SUMS"
        else:
            dump_sha = sha256_file(dump_path)
            dump_sha_source = "computed"
            if listed_sha and listed_sha != dump_sha:
                return {
                    "ok": False,
                    "error": "dump_sha256_mismatch",
                    "listed": listed_sha,
                    "computed": dump_sha,
                }
    elif listed_sha:
        dump_sha = listed_sha
        dump_sha_source = "SHA256SUMS_only"

    row_ok = expected is None or int(expected) == n
    dump_pkg_s = None
    if dump_pkg:
        try:
            dump_pkg_s = str(dump_pkg.relative_to(_PROJECT_ROOT))
        except ValueError:
            dump_pkg_s = str(dump_pkg)
    return {
        "ok": n > 0 and row_ok,
        "snapshot_row_count": n,
        "expected_row_count": expected,
        "row_count_reconciled": row_ok,
        "sc_active_count": n_sc,
        "snapshot_sha256": dump_sha,
        "snapshot_sha256_source": dump_sha_source,
        "dump_package": dump_pkg_s,
        "migrations_recent": migrations,
        "database_identity": {
            "database": ident.get("db"),
            "dsn_masked": mask_dsn(dsn),
            "server_addr": str(ident.get("addr")),
        },
        "eligible_population_note": "computed at pack time; not hard-coded",
    }


def seed_opportunities_from_e(conn: Any, e_path: Path) -> dict[str, Any]:
    """Upsert open opportunities from captured Deliverable E into opportunity_intel."""
    if not e_path.exists():
        return {"seeded": 0, "error": f"missing_e_evidence:{e_path}"}
    data = json.loads(e_path.read_text(encoding="utf-8"))
    recs = list(data.get("recommendations") or [])
    ids: list[int] = []
    with conn.cursor() as cur:
        for rec in recs:
            edital_id = str(rec.get("edital_id") or "").strip()
            if not edital_id:
                continue
            # PNCP control often starts with CNPJ14
            digits = re.sub(r"\D", "", edital_id.split("/")[0].split("-")[0])
            cnpj = digits[:14] if len(digits) >= 14 else (digits or None)
            objeto = (rec.get("titulo") or rec.get("objeto") or "edital aberto")[:2000]
            source_id = f"e-evidence:{edital_id}"
            content = hashlib.sha256(f"{source_id}|{objeto}".encode()).hexdigest()
            url = None
            open_ = rec.get("openness") or {}
            url = open_.get("official_url")
            ranking = rec.get("ranking") or rec.get("client_label") or "REVIEW"
            # Unique authority: content_hash (uq_oi_content_hash). No (source,source_id) unique.
            cur.execute(
                "SELECT id FROM opportunity_intel WHERE content_hash = %s",
                (content,),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE opportunity_intel SET
                        objeto = %s,
                        orgao_cnpj = COALESCE(%s, orgao_cnpj),
                        orgao_nome = COALESCE(%s, orgao_nome),
                        ranking = %s,
                        status_canonico = 'open',
                        is_active = TRUE,
                        last_seen_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (objeto, cnpj, rec.get("orgao"), ranking, int(existing["id"])),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO opportunity_intel (
                        source, source_id, content_hash, numero_controle_pncp,
                        source_url, orgao_cnpj, orgao_nome, uf, municipio, objeto,
                        status_canonico, is_active, ranking
                    ) VALUES (
                        'pncp', %s, %s, %s,
                        %s, %s, %s, 'SC', NULL, %s,
                        'open', TRUE, %s
                    )
                    RETURNING id
                    """,
                    (
                        source_id,
                        content,
                        edital_id,
                        url,
                        cnpj,
                        rec.get("orgao"),
                        objeto,
                        ranking,
                    ),
                )
            row = cur.fetchone()
            if row:
                ids.append(int(row["id"]))
        # Also seed organs with historical contracts for denser linkage (labeled)
        from scripts.linkage.seed_isolated import seed_opportunities_from_top_organs

        extra = seed_opportunities_from_top_organs(conn, n_organs=8, per_organ=1)
        ids.extend(extra)
        conn.commit()
        cur.execute(
            "SELECT count(*) AS n FROM opportunity_intel WHERE COALESCE(is_active, TRUE)"
        )
        total = int(cur.fetchone()["n"])
    return {
        "seeded_from_e": len(recs),
        "opportunity_ids": ids,
        "opportunities_total": total,
        "e_evidence": str(e_path),
        "claim": "opportunities include SNAPSHOT-SEED and captured open-tender evidence; not a live PNCP crawl in this run",
    }


def run_linkage(dsn: str, out: Path, *, contract_limit: int = 50) -> dict[str, Any]:
    from scripts.linkage.pipeline import run_linkage as _run

    run_id = f"crc-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    res = _run(
        dsn,
        run_id=run_id,
        snapshot_id="authenticated-dump-pkg-20260723T195047Z",
        snapshot_hash=None,
        contract_limit_per_opp=contract_limit,
        max_opportunities=None,
    )
    payload = res.as_dict()
    (out / "linkage-run.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return payload


def write_dossiers(dsn: str, linkage: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    from scripts.linkage.dossier import build_dossier, write_dossier
    from scripts.linkage.pipeline import connect as lconnect
    from scripts.linkage.pipeline import investigate_opportunity

    run_id = linkage.get("run_id")
    if not run_id:
        return {"written": 0, "error": "missing_run_id"}
    ddir = out_dir / "dossiers"
    ddir.mkdir(parents=True, exist_ok=True)
    conn = lconnect(dsn)
    written: list[str] = []
    opp_ids: list[int] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT opportunity_id
                FROM opportunity_organ_links
                WHERE run_id = %s
                ORDER BY opportunity_id
                """,
                (run_id,),
            )
            opp_ids = [int(r["opportunity_id"]) for r in cur.fetchall()]
            if not opp_ids:
                cur.execute(
                    "SELECT id FROM opportunity_intel WHERE COALESCE(is_active, TRUE) ORDER BY id"
                )
                opp_ids = [int(r["id"]) for r in cur.fetchall()]
        for oid in opp_ids:
            inv = investigate_opportunity(conn, run_id, oid)
            dos = build_dossier(inv)
            paths = write_dossier(dos, ddir, stem=f"dossier-opp-{oid}")
            written.append(str(paths))
    finally:
        conn.close()
    return {"written": len(written), "run_id": run_id, "opportunity_ids": opp_ids}


def run_pack(dsn: str, pack_dir: Path, e_path: Path) -> dict[str, Any]:
    from scripts.ops.live_consulting_pack import run_pack as _run_pack

    pack_dir.mkdir(parents=True, exist_ok=True)
    return _run_pack(
        dsn=dsn,
        out_dir=pack_dir,
        uf="SC",
        export_limit=200,
        target_competitors=15,
        e_evidence=e_path,
    )


def run_weekly(dsn: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.ops.weekly_cycle",
            "--dsn",
            dsn,
            "--skip-collect",
            "--no-contracts-incremental",
            "--no-strict",
            "--limit",
            "30",
            "--output-dir",
            str(out_dir),
        ],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LOCAL_DATALAKE_DSN": dsn},
    )
    manifest = out_dir / "manifest.json"
    return {
        "exit_code": r.returncode,
        "ok": r.returncode in (0, 2),  # 2 = partial OK in weekly_cycle
        "manifest_exists": manifest.exists(),
        "stdout_tail": (r.stdout or "")[-800:],
        "stderr_tail": (r.stderr or "")[-400:],
    }


def run_monthly(dsn: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    # --live-isolated proves mechanics on the same snapshot (+ optional labeled inject).
    # It is NOT dual temporal live snapshots (see strategic_monthly_monitor.run_live_two_cycle).
    r = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.ops.strategic_monthly_monitor",
            "--live-isolated",
            "--dsn",
            dsn,
            "--out-dir",
            str(out_dir),
            "--audit",
        ],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    live_path = out_dir / "monthly-monitor-live.json"
    if r.returncode == 0 and live_path.exists():
        try:
            payload = json.loads(live_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        # Authority: file mode after fix is LABELED_DETERMINISTIC_REPLAY
        mode = str(payload.get("mode") or "LABELED_DETERMINISTIC_REPLAY")
        live_dual = payload.get("live_dual_snapshot")
        if live_dual is None:
            live_dual = False
        # Never upgrade inject path to live dual
        if payload.get("synthetic_inject_used") or "LABELED" in mode.upper():
            live_dual = False
            mode = "LABELED_DETERMINISTIC_REPLAY"
        return {
            "ok": True,
            "mode": mode,
            "live_recurrence": False,
            "live_dual_snapshot": bool(live_dual),
            "synthetic_inject_used": bool(payload.get("synthetic_inject_used")),
            "exit_code": r.returncode,
            "path": str(live_path),
            "stdout_tail": (r.stdout or "")[-500:],
        }

    # Fallback: pure labeled replay via run_cycle API
    from scripts.ops.strategic_monthly_monitor import run_cycle

    as_of = date.today()
    state_path = out_dir / "cycle-state.json"

    def _ser(x: Any) -> Any:
        if hasattr(x, "__dataclass_fields__"):
            from dataclasses import asdict

            return asdict(x)
        if isinstance(x, dict):
            return {k: _ser(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_ser(i) for i in x]
        return x

    c1_rep, s1 = run_cycle(
        editais=[
            {
                "id": "seed-1",
                "status": "open",
                "deadline": (as_of + timedelta(days=20)).isoformat(),
            },
            {
                "id": "seed-2",
                "status": "open",
                "deadline": (as_of + timedelta(days=40)).isoformat(),
            },
        ],
        contracts=[],
        state=None,
        as_of=as_of - timedelta(days=7),
        cycle_id="crc-replay-1",
    )
    from scripts.ops.strategic_monthly_monitor import save_state

    save_state(s1, state_path)
    c2_rep, _s2 = run_cycle(
        editais=[
            {
                "id": "seed-1",
                "status": "suspended",
                "deadline": (as_of + timedelta(days=25)).isoformat(),
            },
            {
                "id": "seed-2",
                "status": "open",
                "deadline": (as_of + timedelta(days=40)).isoformat(),
            },
            {
                "id": "seed-3",
                "status": "open",
                "deadline": (as_of + timedelta(days=15)).isoformat(),
            },
        ],
        contracts=[],
        state=s1,
        as_of=as_of,
        cycle_id="crc-replay-2",
    )
    payload = {
        "mode": "LABELED_DETERMINISTIC_REPLAY",
        "live_dual_snapshot": False,
        "live_isolated_exit": r.returncode,
        "live_isolated_stderr": (r.stderr or "")[-500:],
        "cycle_1": _ser(c1_rep),
        "cycle_2": _ser(c2_rep),
        "claim": "replay proves delta detectors; not dual live snapshot PASS",
        "non_claims": ["live_dual_snapshot_recurrence"],
    }
    (out_dir / "monthly-replay.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "mode": "LABELED_DETERMINISTIC_REPLAY",
        "live_recurrence": False,
        "live_dual_snapshot": False,
        "path": str(out_dir / "monthly-replay.json"),
    }


def _cat_entry(items: list[Any] | None, *, note_empty: str) -> dict[str, Any]:
    items = list(items or [])
    if not items:
        return {"count": 0, "success_zero": True, "note": note_empty, "items": []}
    return {
        "count": len(items),
        "success_zero": False,
        "items": items[:50],  # cap evidence size
    }


def build_recurrence_delta(monthly: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Normalize delta categories required by the campaign from real cycle artifacts."""
    categories: dict[str, Any] = {
        "new_opportunities": [],
        "status_changes": [],
        "deadline_changes": [],
        "new_expiring_contracts": [],
        "org_ranking_changes": [],
        "supplier_ranking_changes": [],
        "coverage_changes": [],
        "freshness_changes": [],
        "degraded_sources": [],
        "resolved_blockers": [],
        "new_blockers": [],
    }
    mode = monthly.get("mode")
    mon_path = out_dir / "monthly"
    live_path = mon_path / "monthly-monitor-live.json"
    replay_path = mon_path / "monthly-replay.json"

    c2: dict[str, Any] = {}
    c1: dict[str, Any] = {}
    source_file = None
    raw: dict[str, Any] = {}
    if live_path.exists():
        raw = json.loads(live_path.read_text(encoding="utf-8"))
        c1 = raw.get("cycle_1") or {}
        c2 = raw.get("cycle_2") or {}
        source_file = str(live_path)
        # Prefer honest mode from artifact (LABELED_DETERMINISTIC_REPLAY after fix)
        mode = str(raw.get("mode") or mode or "LABELED_DETERMINISTIC_REPLAY")
    elif replay_path.exists():
        raw = json.loads(replay_path.read_text(encoding="utf-8"))
        c1 = raw.get("cycle_1") or {}
        c2 = raw.get("cycle_2") or {}
        source_file = str(replay_path)
        mode = str(raw.get("mode") or mode or "LABELED_DETERMINISTIC_REPLAY")

    if c2:
        categories["new_opportunities"] = list(c2.get("new_editais") or [])
        categories["status_changes"] = list(c2.get("status_deltas") or [])
        exp = c2.get("expiring_contracts") or []
        if isinstance(exp, list):
            categories["new_expiring_contracts"] = exp[:20]
        elif isinstance(exp, dict) and exp.get("count"):
            categories["new_expiring_contracts"] = [
                {"count": exp.get("count"), "window": "90-180"}
            ]
        # deadline changes from status_deltas with prazo
        categories["deadline_changes"] = [
            d
            for d in (c2.get("status_deltas") or [])
            if isinstance(d, dict)
            and (
                d.get("prazo_novo")
                or d.get("event_type") in {"PRAZO", "deadline_change", "ALTERACAO_PRAZO"}
            )
        ]
        # ranking deltas from variation.fields
        var = c2.get("variation") or {}
        fields = var.get("fields") or {}
        if fields.get("organs_count", {}).get("delta"):
            categories["org_ranking_changes"] = [fields["organs_count"]]
        if fields.get("winners_count", {}).get("delta"):
            categories["supplier_ranking_changes"] = [fields["winners_count"]]
        if fields.get("editais_total", {}).get("delta"):
            # coverage-ish signal
            categories["coverage_changes"] = [fields["editais_total"]]

    # first cycle has no previous — all-new is not "delta"; cycle_2 is the comparison
    note_empty = (
        "measurable empty after complete cycle comparison"
        if c2
        else "cycle_2 artifact missing — cannot claim success_zero of deltas"
    )
    normalized: dict[str, Any] = {}
    for k, v in categories.items():
        if not c2 and k in {
            "new_opportunities",
            "status_changes",
            "deadline_changes",
            "new_expiring_contracts",
        }:
            normalized[k] = {
                "count": None,
                "success_zero": False,
                "note": "NOT_MEASURED — missing cycle_2",
            }
        else:
            normalized[k] = _cat_entry(v if isinstance(v, list) else [], note_empty=note_empty)

    # Live dual-snapshot only if artifact explicitly says so AND no synthetic inject
    live_dual = False
    if isinstance(raw, dict) and raw.get("live_dual_snapshot") is True:
        if not raw.get("synthetic_inject_used") and not raw.get(
            "population", {}
        ).get("same_snapshot_both_cycles"):
            live_dual = True
    if monthly and monthly.get("live_dual_snapshot") is True and not monthly.get(
        "synthetic_inject_used"
    ):
        # Still refuse if mode is labeled
        if str(monthly.get("mode") or "").upper().find("LABELED") < 0:
            live_dual = bool(monthly.get("live_dual_snapshot"))
    if "LABELED" in str(mode or "").upper() or (
        isinstance(raw, dict) and raw.get("synthetic_inject_used")
    ):
        live_dual = False
        mode = "LABELED_DETERMINISTIC_REPLAY"

    result = {
        "mode": mode or "UNKNOWN",
        "live_dual_snapshot": live_dual,
        "source_file": source_file,
        "cycle_1_id": (c1.get("cycle") or {}).get("cycle_id") if isinstance(c1, dict) else None,
        "cycle_2_id": (c2.get("cycle") or {}).get("cycle_id") if isinstance(c2, dict) else None,
        "proofs": raw.get("proofs") if isinstance(raw, dict) else None,
        "categories": normalized,
        "claims": (raw.get("claims") if isinstance(raw, dict) else None)
        or ["recurrence_mechanics_proven"],
        "non_claims": (raw.get("non_claims") if isinstance(raw, dict) else None)
        or ["live_dual_snapshot_recurrence"],
    }
    if not live_dual:
        result["claim"] = (
            "LABELED_DETERMINISTIC_REPLAY / same-snapshot mechanics proven; "
            "live dual temporal snapshot NOT claimed"
        )
        result["live_dual_snapshot"] = False

    (out_dir / "recurrence.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return result


def compute_pack_checksums(pack_dir: Path) -> dict[str, str]:
    """SHA-256 of every file under pack/ except pack-full.json (ADR-020 large)."""
    out: dict[str, str] = {}
    if not pack_dir.is_dir():
        return out
    for p in sorted(pack_dir.rglob("*")):
        if p.is_file() and p.name != "pack-full.json":
            out[str(p.relative_to(pack_dir))] = sha256_file(p)
    return out


def identity_checksum_mismatches(
    accepted_ck: dict[str, str],
    pack_checksums: dict[str, str],
    *,
    required: tuple[str, ...] = REQUIRED_IDENTITY_FILES,
) -> list[str]:
    """Fail-closed identity compare. Missing either side is a mismatch (not skipped)."""
    mismatches: list[str] = []
    for key in required:
        if key not in accepted_ck:
            mismatches.append(f"missing_expected_checksum:{key}")
            continue
        if key not in pack_checksums:
            mismatches.append(f"missing_actual_artifact:{key}")
            continue
        if accepted_ck[key] != pack_checksums[key]:
            mismatches.append(f"checksum_mismatch:{key}")
    return mismatches


def missing_required_frozen_binaries(pack_dir: Path) -> list[str]:
    """Return relative names of required identity files absent under pack_dir."""
    missing: list[str] = []
    for key in REQUIRED_IDENTITY_FILES:
        if not (pack_dir / key).is_file():
            missing.append(key)
    return missing


def human_acceptance_status(campaign_dir: Path) -> dict[str, Any]:
    path = campaign_dir / "user-acceptance.json"
    if not path.exists():
        payload = {
            "status": "PENDING_HUMAN",
            "rc_sha": git_sha(),
            "run_id": None,
            "package_checksums": {},
            "accepted_by": None,
            "accepted_at": None,
            "notes": None,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload
    data = json.loads(path.read_text(encoding="utf-8"))
    # Never treat agent-filled ACCEPT as real without explicit accepted_by human
    if data.get("status") == "ACCEPTED":
        who = data.get("accepted_by")
        if not who or str(who).lower() in {"agent", "auto", "system", "null"}:
            data["status"] = "PENDING_HUMAN"
            data["notes"] = "auto-accept rejected; requires Tiago explicit acceptance"
    return data


def validate_acceptance_binding(
    acceptance: dict[str, Any],
    *,
    pack_run_id: str | None,
    rc_sha: str,
    pack_checksums: dict[str, str],
) -> dict[str, Any]:
    """Ensure ACCEPTED records bind to this exact RC identity — never rebind.

    Fail-closed for identity files: each of REQUIRED_IDENTITY_FILES must exist
    in both accepted package_checksums and pack_checksums with equal digests.
    binding.valid=True only when run_id, product_rc_sha (rc_sha), and all
    identity checksums match.

    Returns acceptance dict possibly demoted to PENDING_HUMAN if stale vs pack.
    """
    out = dict(acceptance)
    out["binding"] = {
        "pack_run_id": pack_run_id,
        "rc_sha": rc_sha,
        "product_rc_sha": rc_sha,
        "checked_at": utc_now(),
    }
    if out.get("status") != "ACCEPTED":
        # For pending forms: preserve freeze identity; never silently replace
        # frozen package_checksums with an incomplete on-disk pack.
        if out.get("status") in {None, "PENDING_HUMAN", "REJECTED"}:
            out["status"] = out.get("status") or "PENDING_HUMAN"
            frozen_ck = out.get("package_checksums") or {}
            has_freeze = all(k in frozen_ck for k in REQUIRED_IDENTITY_FILES)
            if not out.get("run_id") and pack_run_id:
                out["run_id"] = pack_run_id
            if not out.get("rc_sha") and rc_sha:
                out["rc_sha"] = rc_sha
            if not has_freeze and pack_checksums:
                # Only publish pack checksums when identity set is complete.
                if all(k in pack_checksums for k in REQUIRED_IDENTITY_FILES):
                    out["package_checksums"] = pack_checksums
            # Diagnostic binding vs on-disk pack (does not flip PENDING → ACCEPTED)
            accepted_ck = out.get("package_checksums") or {}
            diag: list[str] = []
            if pack_run_id and out.get("run_id") and out.get("run_id") != pack_run_id:
                diag.append(f"run_id:{out.get('run_id')}!={pack_run_id}")
            if out.get("rc_sha") and rc_sha and out.get("rc_sha") != rc_sha:
                diag.append(
                    f"product_rc_sha:{str(out.get('rc_sha'))[:12]}!={rc_sha[:12]}"
                )
            if accepted_ck or pack_checksums:
                diag.extend(identity_checksum_mismatches(accepted_ck, pack_checksums))
            out["binding"]["valid"] = False  # never auto-valid without human ACCEPTED
            out["binding"]["mismatches"] = diag
            out["accepted_by"] = (
                None if out.get("status") != "REJECTED" else out.get("accepted_by")
            )
            if out.get("status") != "REJECTED":
                out["accepted_at"] = None
        return out

    who = out.get("accepted_by")
    if not who or str(who).lower() in {"agent", "auto", "system", "null"}:
        out["status"] = "PENDING_HUMAN"
        out["binding"]["valid"] = False
        out["binding"]["reason"] = "invalid_accepted_by"
        out["notes"] = "auto-accept rejected; requires Tiago explicit acceptance"
        out["accepted_by"] = None
        out["accepted_at"] = None
        return out

    mismatches: list[str] = []
    if out.get("run_id") != pack_run_id:
        mismatches.append(f"run_id:{out.get('run_id')}!={pack_run_id}")
    if out.get("rc_sha") != rc_sha:
        mismatches.append(
            f"product_rc_sha:{str(out.get('rc_sha'))[:12]}!={str(rc_sha)[:12]}"
        )
    accepted_ck = out.get("package_checksums") or {}
    mismatches.extend(identity_checksum_mismatches(accepted_ck, pack_checksums))

    if mismatches:
        # Stale ACCEPT must not be rewritten onto new RC — demote and keep prior fields for audit
        out["status"] = "PENDING_HUMAN"
        out["binding"]["valid"] = False
        out["binding"]["mismatches"] = mismatches
        out["binding"]["prior_accepted_run_id"] = acceptance.get("run_id")
        out["binding"]["prior_accepted_rc_sha"] = acceptance.get("rc_sha")
        out["binding"]["prior_accepted_by"] = who
        out["binding"]["prior_accepted_at"] = acceptance.get("accepted_at")
        out["notes"] = (
            "STALE_ACCEPT: prior human ACCEPT does not bind to current pack/rc_sha. "
            "New release candidate requires explicit re-accept. "
            f"mismatches={mismatches}"
        )
        # Publish current pack identity for re-accept when pack is complete;
        # otherwise keep prior freeze checksums for audit (do not blank them).
        out["run_id"] = pack_run_id
        out["rc_sha"] = rc_sha
        if all(k in pack_checksums for k in REQUIRED_IDENTITY_FILES):
            out["package_checksums"] = pack_checksums
        out["accepted_by"] = None
        out["accepted_at"] = None
        return out

    out["binding"]["valid"] = True
    out["binding"]["mismatches"] = []
    return out


def decide_terminal(
    *,
    isolation: dict[str, Any],
    migrations: dict[str, Any],
    snapshot: dict[str, Any],
    pack: dict[str, Any] | None,
    linkage: dict[str, Any] | None,
    monthly: dict[str, Any] | None,
    acceptance: dict[str, Any],
    failures: list[str],
    recurrence: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """Global terminal: PASS | BLOCKED | FAIL.

    Live dual-snapshot recurrence requires dual_snapshot_proof=true with real
    independent temporal evidence. Labeled same-snapshot mechanics are allowed
    for product PASS only when live_dual_snapshot is false.
    """
    blockers: list[str] = []
    if failures:
        return "FAIL", failures
    if not isolation.get("ok"):
        return "FAIL", ["isolation_failed"]
    if not migrations.get("idempotent"):
        return "FAIL", ["migrations_not_idempotent"]
    if not snapshot.get("ok"):
        return "FAIL", ["snapshot_validation_failed"]
    if not pack or pack.get("reconcile", {}).get("status") != "PASS":
        return "FAIL", ["pack_reconcile_not_pass"]
    if not linkage or linkage.get("status") not in {"completed", "OK", "success"}:
        st = (linkage or {}).get("status")
        if st != "completed":
            return "FAIL", [f"linkage_status:{st}"]

    rec = recurrence or {}
    mon = monthly or {}

    # Honesty: any live_dual_snapshot=true without dual_snapshot_proof fails
    if rec.get("live_dual_snapshot") is True:
        proof = rec.get("dual_snapshot_proof") or mon.get("dual_snapshot_proof")
        labeled = (
            "LABELED" in str(rec.get("mode") or "").upper()
            or mon.get("synthetic_inject_used")
            or mon.get("live_dual_snapshot") is False
            or (isinstance(mon.get("population"), dict) and mon["population"].get("same_snapshot_both_cycles"))
        )
        if labeled or proof is not True:
            return "FAIL", ["false_live_dual_snapshot_claim"]
    # Also fail LIVE_ISOLATED mode that claims dual without proof
    if (
        str(rec.get("mode") or mon.get("mode") or "").upper() == "LIVE_ISOLATED"
        and mon.get("live_dual_snapshot") is True
        and mon.get("dual_snapshot_proof") is not True
    ):
        return "FAIL", ["false_live_dual_snapshot_claim"]

    # Stale or invalid ACCEPT binding
    binding = acceptance.get("binding") or {}
    if acceptance.get("status") == "ACCEPTED" and binding.get("valid") is False:
        return "FAIL", ["stale_or_invalid_accept_binding"]

    if acceptance.get("status") != "ACCEPTED":
        if binding.get("mismatches"):
            blockers.append(
                "user_acceptance_STALE: prior ACCEPT does not bind current RC; re-accept required"
            )
        else:
            blockers.append(
                "user_acceptance_PENDING_HUMAN: Tiago must ACCEPT the release candidate"
            )
        return "BLOCKED", blockers

    # Human accepted + binding valid + technical green → PASS
    return "PASS", []


def write_meeting_support(pack_dir: Path, pack: dict[str, Any], linkage: dict[str, Any]) -> None:
    md = pack_dir / "meeting-support.md"
    lines = [
        "# Material de apoio — reunião consultiva Extra Construtora",
        "",
        f"- run_id: `{pack.get('run_id')}`",
        f"- as_of: `{pack.get('as_of')}`",
        f"- população elegível: `{((pack.get('population') or {}).get('eligible_population'))}`",
        f"- linkage run: `{(linkage or {}).get('run_id')}`",
        "",
        "## Roteiro",
        "1. Abrir executive-summary / PDF e confirmar profile_version.",
        "2. Priorizar órgãos (A) com volume e frequência.",
        "3. Concorrentes observáveis (B) — vencedores históricos, não participantes de edital.",
        "4. Contratos vincendos 90–180d (C).",
        "5. Painéis de valores (D) com semântica CONTRATADO.",
        "6. Editais abertos (E) com GO/REVIEW/NO_GO e dossiers de linkage.",
        "",
        "## Non-claims",
        "- Não é LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE.",
        "- Não é soak 7d.",
        "- Capacidade operacional da Extra PENDING_ELICITATION permanece explícita.",
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")


def run_cycle(
    *,
    dsn: str,
    out_dir: Path,
    e_evidence: Path | None = None,
    skip_pack: bool = False,
    contract_limit: int = 50,
) -> dict[str, Any]:
    started = utc_now()
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    pack_dir = out_dir / "pack"
    failures: list[str] = []
    steps: dict[str, Any] = {}

    isolation = isolation_guard(dsn, out_dir)
    steps["isolation"] = isolation

    migrations = apply_migrations(dsn)
    steps["migrations"] = migrations
    if not migrations["idempotent"]:
        failures.append("migrations_failed")

    profile = validate_profile()
    steps["profile"] = profile
    if not profile.get("exists"):
        failures.append("profile_missing")

    conn = connect(dsn)
    try:
        snapshot = validate_snapshot(conn, dsn)
        steps["snapshot"] = snapshot
        if not snapshot["ok"]:
            failures.append("snapshot_invalid")

        e_path = e_evidence or E_EVIDENCE_DEFAULT
        opp = seed_opportunities_from_e(conn, e_path)
        steps["opportunities"] = opp
    finally:
        conn.close()

    linkage: dict[str, Any] | None = None
    dossiers: dict[str, Any] | None = None
    if not failures:
        try:
            linkage = run_linkage(dsn, out_dir, contract_limit=contract_limit)
            steps["linkage"] = {
                "run_id": linkage.get("run_id"),
                "status": linkage.get("status"),
                "metrics": linkage.get("metrics"),
                "production_touched": linkage.get("production_touched"),
            }
            dossiers = write_dossiers(dsn, linkage, out_dir)
            steps["dossiers"] = dossiers
        except Exception as exc:  # noqa: BLE001
            failures.append(f"linkage_error:{exc}")
            steps["linkage_error"] = str(exc)

    pack: dict[str, Any] | None = None
    if not failures and not skip_pack:
        try:
            pack = run_pack(dsn, pack_dir, e_path)
            steps["pack"] = {
                "run_id": pack.get("run_id"),
                "reconcile": pack.get("reconcile"),
                "population": pack.get("population"),
                "deliverable_a": pack.get("deliverable_a"),
                "deliverable_b": pack.get("deliverable_b"),
                "deliverable_c": pack.get("deliverable_c"),
                "deliverable_d": pack.get("deliverable_d"),
                "deliverable_e": pack.get("deliverable_e"),
                "production_touched": pack.get("production_touched"),
            }
            write_meeting_support(pack_dir, pack, linkage or {})
            # Alias executive names expected by campaign — always overwrite so
            # run_id/git_sha match this pack generation (no stale aliases).
            for src, dst in (
                ("extra_live_consulting_pack.pdf", "executive-report.pdf"),
                ("extra_live_consulting_pack.xlsx", "consulting-pack.xlsx"),
                ("executive_summary.md", "executive-summary.md"),
            ):
                sp, dp = pack_dir / src, pack_dir / dst
                if sp.exists():
                    dp.write_bytes(sp.read_bytes())
            # CSVs aliases (always refresh)
            for src, dst in (
                ("orgaos_ranking.csv", "organizations.csv"),
                ("competitors.csv", "competitors.csv"),
                ("expiring.csv", "expiring-contracts.csv"),
            ):
                sp = pack_dir / src
                if sp.exists():
                    (pack_dir / dst).write_bytes(sp.read_bytes())
            # After aliases, recompute package_checksums will run later in acceptance block
            # opportunities from E
            e_json = pack_dir / "deliverable_e.json"
            if e_json.exists():
                e_data = json.loads(e_json.read_text(encoding="utf-8"))
                recs = e_data.get("recommendations") or []
                import csv

                with (pack_dir / "opportunities.csv").open("w", encoding="utf-8", newline="") as f:
                    if recs:
                        w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
                        w.writeheader()
                        for row in recs:
                            flat = {
                                k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                                for k, v in row.items()
                            }
                            w.writerow(flat)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"pack_error:{exc}")
            steps["pack_error"] = str(exc)

    weekly = run_weekly(dsn, out_dir / "weekly")
    steps["weekly"] = weekly

    monthly = run_monthly(dsn, out_dir / "monthly")
    steps["monthly"] = monthly
    recurrence = build_recurrence_delta(monthly, out_dir)
    steps["recurrence"] = {
        "mode": recurrence.get("mode"),
        "live_dual_snapshot": recurrence.get("live_dual_snapshot"),
    }

    acceptance = human_acceptance_status(out_dir)
    pack_checksums = compute_pack_checksums(pack_dir) if pack_dir.is_dir() else {}
    pack_run_id = (pack or {}).get("run_id")
    pack_git_sha = (pack or {}).get("git_sha")
    # If pack failed, try pack-manifest on disk
    if (pack_dir / "pack-manifest.json").exists():
        try:
            pm_disk = json.loads(
                (pack_dir / "pack-manifest.json").read_text(encoding="utf-8")
            )
            pack_run_id = pack_run_id or pm_disk.get("run_id")
            pack_git_sha = pack_git_sha or pm_disk.get("git_sha")
        except json.JSONDecodeError:
            pass
    # RC product identity = pack generation SHA (not post-hoc docs-only tips)
    rc_sha_now = str(pack_git_sha or git_sha())
    # NEVER silently rebind ACCEPTED onto a new pack — validate binding instead
    acceptance = validate_acceptance_binding(
        acceptance,
        pack_run_id=pack_run_id,
        rc_sha=rc_sha_now,
        pack_checksums=pack_checksums,
    )
    (out_dir / "user-acceptance.json").write_text(
        json.dumps(acceptance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    steps["acceptance_binding"] = acceptance.get("binding")

    terminal, blockers = decide_terminal(
        isolation=isolation,
        migrations=migrations,
        snapshot=snapshot,
        pack=pack,
        linkage=linkage,
        monthly=monthly,
        acceptance=acceptance,
        failures=failures,
        recurrence=recurrence,
    )

    finished = utc_now()
    duration = round(time.perf_counter() - t0, 3)
    sha = git_sha()

    claims = [
        "integrated cycle entry point sequences pack+linkage+weekly+monthly on isolated DSN",
        "A–E pack over authenticated dump population (not silent sample universe)",
        "linkage with provenance classifications on campaign opportunities",
        "production_touched=false and soak_touched=false when isolation_ok",
        "recurrence_mechanics_proven_via_labeled_same_snapshot_cycles",
    ]
    non_claims = [
        "LOCAL_READY",
        "PRE_VPS_FINAL_READY",
        "VPS_OPERATIONAL",
        "PROJECT_DONE",
        "soak_7d PASS",
        "live_dual_snapshot_recurrence",
        "two_independent_temporal_exports",
        "unit price from global valor_total",
        "Extra operational capacity fields not elicited",
        "win rate without observable open-tender denominator",
    ]
    if recurrence.get("live_dual_snapshot"):
        # Only when truly dual — remove from non_claims
        non_claims = [c for c in non_claims if c != "live_dual_snapshot_recurrence"]

    # Optional CI/gate evidence files (filled by campaign docs or prior gate runs)
    ci_path = out_dir / "ci-full-suite-status.json"
    ci_run = None
    if ci_path.exists():
        try:
            ci_run = json.loads(ci_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ci_run = {"path": str(ci_path), "parse_error": True}
    gate_results = {
        "isolation": "PASS" if isolation.get("ok") else "FAIL",
        "migrations_idempotent": "PASS" if migrations.get("idempotent") else "FAIL",
        "snapshot": "PASS" if snapshot.get("ok") else "FAIL",
        "pack_reconcile": (pack or {}).get("reconcile", {}).get("status"),
        "linkage": (linkage or {}).get("status"),
        "recurrence_mode": recurrence.get("mode"),
        "live_dual_snapshot": recurrence.get("live_dual_snapshot"),
        "human_acceptance": acceptance.get("status"),
        "final_status": terminal,
    }

    # Universe hash from canonical seed if present
    universe_sha = None
    for upath in (
        _PROJECT_ROOT / "fixtures/canonical_universe_r0.xlsx",
        _PROJECT_ROOT / "config/target_entities_200km.csv",
    ):
        if upath.exists():
            universe_sha = sha256_file(upath)
            break

    manifest = {
        "campaign_id": CAMPAIGN_ID,
        "started_at": started,
        "finished_at": finished,
        "branch": subprocess.check_output(  # noqa: S603
            ["/usr/bin/git", "branch", "--show-current"],
            cwd=str(_PROJECT_ROOT),
            text=True,
        ).strip()
        if True
        else None,
        "base_sha": "5d906f631f444dd803e92bb88b7c98972297f8d4",
        "rc_sha": sha,
        "schema_version": (pack or {}).get("schema_version"),
        "migration_versions": snapshot.get("migrations_recent"),
        "profile_id": profile.get("profile_id"),
        "profile_version": profile.get("version") or profile.get("profile_version"),
        "profile_sha256": profile.get("profile_sha256"),
        "universe_sha256": universe_sha,
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "snapshot_row_count": snapshot.get("snapshot_row_count"),
        "eligible_population": (pack or {}).get("population", {}).get("eligible_population")
        if pack
        else snapshot.get("sc_active_count"),
        "database_identity": snapshot.get("database_identity"),
        "environment": {"dsn_masked": mask_dsn(dsn)},
        "commands": ["python -m scripts.ops.client_ready_consulting_cycle run"],
        "exit_codes": {"cycle_terminal": 0 if terminal == "PASS" else (2 if terminal == "BLOCKED" else 1)},
        "durations": {"total_s": duration},
        "test_counts": {},
        "skipped_tests": [],
        "generated_artifacts": sorted(
            str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()
        )[:500],
        "artifact_checksums": {},
        "gate_results": gate_results,
        "ci_run": ci_run,
        "review_verdict": None,
        "production_touched": False,
        "soak_touched": False,
        "claims": claims,
        "non_claims": non_claims,
        "limitations": [
            "Isolated snapshot — not live VPS query",
            "Deliverable E from captured evidence when live crawl skipped",
            "Monthly recurrence mechanics use same snapshot + labeled inject "
            "(NOT two independent temporal exports)",
        ],
        "blockers": blockers,
        "final_status": terminal,
        "steps": steps,
    }

    # checksums of key files
    for rel in (
        "pack/pack-manifest.json",
        "pack/executive-report.pdf",
        "pack/consulting-pack.xlsx",
        "linkage-run.json",
        "recurrence.json",
    ):
        p = out_dir / rel
        if p.exists():
            manifest["artifact_checksums"][rel] = sha256_file(p)

    result = {
        "campaign_id": CAMPAIGN_ID,
        "final_status": terminal,
        "terminal": terminal,  # alias
        "blockers": blockers,
        "failures": failures,
        "rc_sha": sha,
        "run_id": (pack or {}).get("run_id") or (linkage or {}).get("run_id"),
        "production_touched": False,
        "soak_touched": False,
        "duration_s": duration,
        "pack": steps.get("pack"),
        "linkage": steps.get("linkage"),
        "recurrence": steps.get("recurrence"),
        "human_acceptance": acceptance.get("status"),
        "claims": claims,
        "non_claims": non_claims,
        "generated_at": finished,
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (out_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (out_dir / "failures.json").write_text(
        json.dumps({"failures": failures, "blockers": blockers}, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "claims.json").write_text(
        json.dumps({"claims": claims}, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "non-claims.json").write_text(
        json.dumps({"non_claims": non_claims}, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "security.json").write_text(
        json.dumps(
            {
                "production_touched": False,
                "soak_touched": False,
                "isolation": isolation,
                "secrets_in_manifest": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if pack:
        (out_dir / "package-reconciliation.json").write_text(
            json.dumps(
                {
                    "status": pack.get("reconcile", {}).get("status"),
                    "run_id": pack.get("run_id"),
                    "git_sha": pack.get("git_sha"),
                    "eligible_population": (pack.get("population") or {}).get(
                        "eligible_population"
                    ),
                    "divergences": pack.get("reconcile", {}).get("divergences", []),
                    "same_run_id": True,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if linkage:
        (out_dir / "linkage-quality.json").write_text(
            json.dumps(
                {
                    "run_id": linkage.get("run_id"),
                    "status": linkage.get("status"),
                    "metrics": linkage.get("metrics"),
                    "production_touched": False,
                },
                indent=2,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )

    return result


def cmd_run(args: argparse.Namespace) -> int:
    result = run_cycle(
        dsn=args.dsn,
        out_dir=Path(args.out),
        e_evidence=Path(args.e_evidence) if args.e_evidence else None,
        skip_pack=args.skip_pack,
        contract_limit=args.contract_limit,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    status = result.get("final_status")
    if status == "PASS":
        return 0
    if status == "BLOCKED":
        return 2
    return 1


def cmd_guard(args: argparse.Namespace) -> int:
    try:
        r = isolation_guard(args.dsn)
    except SystemExit as e:
        print(str(e))
        return 3
    print(json.dumps(r, indent=2))
    return 0


def resolve_verify_pack_dir(out_dir: Path, pack_dir_arg: str | None) -> Path:
    """Pack directory for verify-accept: explicit --pack-dir or out/pack."""
    if pack_dir_arg:
        return Path(pack_dir_arg)
    return out_dir / "pack"


def cmd_verify_accept_binding(args: argparse.Namespace) -> int:
    """Re-check acceptance binding against on-disk pack without regenerating.

    Fails closed when required frozen binaries are missing under the pack dir.
    Optional --pack-dir validates a downloaded GitHub Actions artifact tree
    without re-adding binaries to the git worktree.
    """
    out_dir = Path(args.out)
    pack_dir = resolve_verify_pack_dir(out_dir, getattr(args, "pack_dir", None))
    missing_bins = missing_required_frozen_binaries(pack_dir)
    if missing_bins:
        payload = {
            "error": "missing_required_frozen_binaries",
            "status": BLOCKED_MISSING_FROZEN_RC,
            "pack_dir": str(pack_dir),
            "missing": missing_bins,
            "required": list(REQUIRED_IDENTITY_FILES),
            "hint": (
                "Download GitHub Actions artifact "
                f"'{FROZEN_RC_ARTIFACT_NAME}' and pass --pack-dir <extracted>, "
                "or place exact frozen PDF/XLSX under the pack directory. "
                "Do not silently regenerate a different RC."
            ),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1

    pm_path = pack_dir / "pack-manifest.json"
    if not pm_path.exists():
        print(json.dumps({"error": "missing_pack_manifest", "path": str(pm_path)}))
        return 1
    pm = json.loads(pm_path.read_text(encoding="utf-8"))
    pack_run_id = pm.get("run_id")
    # RC identity is the product SHA recorded in pack-manifest (not later docs tips)
    rc_sha = str(pm.get("git_sha") or git_sha())
    checksums = compute_pack_checksums(pack_dir)
    acceptance = human_acceptance_status(out_dir)
    bound = validate_acceptance_binding(
        acceptance,
        pack_run_id=pack_run_id,
        rc_sha=rc_sha,
        pack_checksums=checksums,
    )
    # Never write ACCEPTED from this command; only refresh diagnostic binding.
    if bound.get("status") == "ACCEPTED" and acceptance.get("status") != "ACCEPTED":
        bound["status"] = "PENDING_HUMAN"
        bound["accepted_by"] = None
        bound["accepted_at"] = None
    # Preserve freeze checksums already on disk when present
    if acceptance.get("package_checksums") and all(
        k in (acceptance.get("package_checksums") or {}) for k in REQUIRED_IDENTITY_FILES
    ):
        bound["package_checksums"] = acceptance["package_checksums"]
        bound["run_id"] = acceptance.get("run_id") or bound.get("run_id")
        bound["rc_sha"] = acceptance.get("rc_sha") or bound.get("rc_sha")
    (out_dir / "user-acceptance.json").write_text(
        json.dumps(bound, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Also refresh result terminal using bound acceptance + on-disk evidence
    result_path = out_dir / "result.json"
    result: dict[str, Any] = {}
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
    recon_path = out_dir / "package-reconciliation.json"
    if not recon_path.exists() and (pack_dir / "package-reconciliation.json").exists():
        recon_path = pack_dir / "package-reconciliation.json"
    pack = {
        "run_id": pack_run_id,
        "reconcile": json.loads(recon_path.read_text(encoding="utf-8"))
        if recon_path.exists()
        else {"status": (pm.get("reconcile") or {}).get("status")},
    }
    linkage = {"status": "completed"}
    if (out_dir / "linkage-quality.json").exists():
        linkage = json.loads((out_dir / "linkage-quality.json").read_text(encoding="utf-8"))
    recurrence: dict[str, Any] = {}
    if (out_dir / "recurrence.json").exists():
        recurrence = json.loads((out_dir / "recurrence.json").read_text(encoding="utf-8"))
    monthly = {
        "mode": recurrence.get("mode"),
        "live_dual_snapshot": recurrence.get("live_dual_snapshot"),
        "synthetic_inject_used": True,
    }
    terminal, blockers = decide_terminal(
        isolation={"ok": True},
        migrations={"idempotent": True},
        snapshot={"ok": True},
        pack=pack,
        linkage=linkage,
        monthly=monthly,
        acceptance=bound,
        failures=[],
        recurrence=recurrence,
    )
    result["final_status"] = terminal
    result["terminal"] = terminal
    result["blockers"] = blockers
    result["human_acceptance"] = bound.get("status")
    result["acceptance_binding"] = bound.get("binding")
    result["rc_sha"] = rc_sha
    result["product_rc_sha"] = rc_sha
    result["run_id"] = pack_run_id
    result["pack_dir"] = str(pack_dir)
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "final_status": terminal,
                "blockers": blockers,
                "acceptance": bound.get("status"),
                "binding": bound.get("binding"),
                "run_id": pack_run_id,
                "rc_sha": rc_sha,
                "product_rc_sha": rc_sha,
                "pack_dir": str(pack_dir),
                "required_binaries_present": True,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if terminal == "PASS":
        return 0
    if terminal == "BLOCKED":
        return 2
    return 1


def _git_show_bytes(commit: str, rel_path: str, root: Path | None = None) -> bytes | None:
    r = root or _PROJECT_ROOT
    try:
        return subprocess.check_output(  # noqa: S603
            ["/usr/bin/git", "show", f"{commit}:{rel_path}"],
            cwd=str(r),
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def assemble_client_ready_frozen_rc(
    *,
    out_dir: Path | None = None,
    staging_dir: Path | None = None,
    snapshot_commit: str = FROZEN_RC_SNAPSHOT_COMMIT,
    expected_run_id: str = FROZEN_RC_RUN_ID,
    expected_product_rc_sha: str = FROZEN_RC_PRODUCT_SHA,
    source_pack_dir: Path | None = None,
) -> dict[str, Any]:
    """Assemble HUMAN_REVIEW_ARTIFACT tree for GitHub Actions upload.

    Uses exact frozen RC bytes (local pack with matching checksums, else git
    snapshot). Never regenerates a different RC. On missing/mismatched bytes:
    status BLOCKED_MISSING_FROZEN_RC_OUTPUTS.
    """
    campaign = out_dir or DEFAULT_OUT
    acceptance_path = campaign / "user-acceptance.json"
    if not acceptance_path.exists():
        return {
            "status": BLOCKED_MISSING_FROZEN_RC,
            "error": "missing_user_acceptance",
            "path": str(acceptance_path),
        }
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    expected_ck: dict[str, str] = dict(acceptance.get("package_checksums") or {})
    run_id = str(acceptance.get("run_id") or expected_run_id)
    product_rc_sha = str(
        acceptance.get("rc_sha")
        or (acceptance.get("freeze") or {}).get("product_rc_sha")
        or expected_product_rc_sha
    )
    if run_id != expected_run_id or product_rc_sha != expected_product_rc_sha:
        return {
            "status": BLOCKED_MISSING_FROZEN_RC,
            "error": "freeze_identity_mismatch",
            "run_id": run_id,
            "product_rc_sha": product_rc_sha,
            "expected_run_id": expected_run_id,
            "expected_product_rc_sha": expected_product_rc_sha,
        }

    members: list[tuple[str, list[str]]] = [
        (
            "executive-report.pdf",
            [
                "pack-v2/executive-report.pdf",
                "pack-v2/extra_live_consulting_pack.pdf",
                "pack/executive-report.pdf",
                "pack/extra_live_consulting_pack.pdf",
            ],
        ),
        (
            "consulting-pack.xlsx",
            [
                "pack-v2/consulting-pack.xlsx",
                "pack-v2/extra_live_consulting_pack.xlsx",
                "pack/consulting-pack.xlsx",
                "pack/extra_live_consulting_pack.xlsx",
            ],
        ),
        (
            "executive-summary.md",
            [
                "pack-v2/executive-summary.md",
                "pack-v2/executive_summary.md",
                "pack/executive-summary.md",
                "pack/executive_summary.md",
            ],
        ),
        (
            "pack-manifest.json",
            ["pack-v2/pack-manifest.json", "pack/pack-manifest.json"],
        ),
        ("checksums.json", ["pack-v2/checksums.json", "pack/checksums.json"]),
        ("package-reconciliation.json", ["package-reconciliation.json"]),
        ("claims.json", ["claims.json"]),
        ("non-claims.json", ["non-claims.json"]),
        # Optional dossiers (v1 had them; v2 commercial pack may be SUCCESS_ZERO on E)
        (
            "dossiers/dossier-opp-1.json",
            [
                "pack-v2/dossiers/dossier-opp-1.json",
                "pack/dossiers/dossier-opp-1.json",
                "dossiers/dossier-opp-1.json",
            ],
        ),
    ]
    optional_members = {"dossiers/dossier-opp-1.json", "claims.json", "non-claims.json"}

    if staging_dir is not None:
        staging = staging_dir
    elif os.environ.get("RUNNER_TEMP"):
        staging = Path(os.environ["RUNNER_TEMP"]) / FROZEN_RC_ARTIFACT_NAME
    else:
        import tempfile

        staging = Path(tempfile.gettempdir()) / FROZEN_RC_ARTIFACT_NAME
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    file_sha: dict[str, str] = {}
    sources: dict[str, str] = {}
    missing: list[str] = []

    for art_name, rel_candidates in members:
        data: bytes | None = None
        source = ""
        if source_pack_dir is not None:
            for cand in [art_name, Path(art_name).name, *rel_candidates]:
                p = source_pack_dir / cand
                if p.is_file():
                    data = p.read_bytes()
                    source = f"pack_dir:{p}"
                    break
        if data is None:
            for rel in rel_candidates:
                p = campaign / rel
                if p.is_file():
                    data = p.read_bytes()
                    source = f"workspace:{rel}"
                    break
        if data is None:
            for rel in rel_candidates:
                blob = _git_show_bytes(
                    snapshot_commit, f"artifacts/campaigns/{CAMPAIGN_ID}/{rel}"
                )
                if blob is not None:
                    data = blob
                    source = f"git:{snapshot_commit}:{rel}"
                    break
        if data is None:
            if art_name in optional_members:
                continue
            missing.append(art_name)
            continue
        digest = hashlib.sha256(data).hexdigest()
        if art_name in expected_ck and expected_ck[art_name] != digest:
            missing.append(f"checksum_mismatch:{art_name}")
            continue
        dest = staging / art_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        file_sha[art_name] = digest
        sources[art_name] = source

    required_missing = [
        k
        for k in REQUIRED_IDENTITY_FILES
        if k not in file_sha or (k in expected_ck and file_sha[k] != expected_ck[k])
    ]
    # Optional members missing is not a hard fail for v2
    hard_missing = [m for m in missing if not str(m).startswith("dossiers/")]
    if hard_missing or required_missing:
        return {
            "status": BLOCKED_MISSING_FROZEN_RC,
            "error": "exact_frozen_outputs_unavailable",
            "missing": missing,
            "required_missing": required_missing,
            "staging": str(staging),
            "snapshot_commit": snapshot_commit,
            "run_id": run_id,
            "product_rc_sha": product_rc_sha,
        }

    # Identity lists hashes of product members only — NEVER self-hash this JSON.
    identity = {
        "run_id": run_id,
        "product_rc_sha": product_rc_sha,
        "file_sha256": dict(file_sha),  # excludes ARTIFACT-IDENTITY.json itself
        "freeze_date": (acceptance.get("freeze") or {}).get("as_of") or utc_now(),
        "production_touched": False,
        "soak_touched": False,
        "snapshot_origin": {
            "type": "frozen_rc_snapshot",
            "snapshot_commit": snapshot_commit,
            "campaign_id": CAMPAIGN_ID,
            "sources": sources,
        },
        "classification": "HUMAN_REVIEW_ARTIFACT",
        "artifact_name": FROZEN_RC_ARTIFACT_NAME,
        "assembled_at": utc_now(),
        "prior_rc": {
            "artifact_name": FROZEN_RC_V1_ARTIFACT_NAME,
            "run_id": FROZEN_RC_V1_RUN_ID,
            "product_rc_sha": FROZEN_RC_V1_PRODUCT_SHA,
            "status": FROZEN_RC_V1_STATUS,
            "note": "Historical RC remains CHANGES_REQUESTED; not overwritten",
        },
        "self_hash_policy": "excluded — see ARTIFACT-IDENTITY.sha256 sidecar",
    }
    identity_path = staging / "ARTIFACT-IDENTITY.json"
    identity_path.write_text(
        json.dumps(identity, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Sidecar after identity is frozen (not embedded inside the JSON)
    sidecar = staging / "ARTIFACT-IDENTITY.sha256"
    identity_digest = sha256_file(identity_path)
    sidecar.write_text(f"{identity_digest}  ARTIFACT-IDENTITY.json\n", encoding="utf-8")

    # Fail-closed integrity: recompute digests of staged product files
    divergences: list[str] = []
    for name, expected in file_sha.items():
        actual = sha256_file(staging / name)
        if actual != expected:
            divergences.append(f"hash_divergence:{name}")
        if name in expected_ck and expected_ck[name] != actual:
            divergences.append(f"acceptance_checksum_mismatch:{name}")
    if "ARTIFACT-IDENTITY.json" in (identity.get("file_sha256") or {}):
        divergences.append("identity_self_hash_forbidden")
    if divergences:
        return {
            "status": BLOCKED_MISSING_FROZEN_RC,
            "error": "integrity_gate_failed",
            "divergences": divergences,
            "staging": str(staging),
        }

    return {
        "status": "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW",
        "artifact_name": FROZEN_RC_ARTIFACT_NAME,
        "staging_dir": str(staging),
        "run_id": run_id,
        "product_rc_sha": product_rc_sha,
        "file_sha256": file_sha,
        "identity_sha256": identity_digest,
        "production_touched": False,
        "soak_touched": False,
        "classification": "HUMAN_REVIEW_ARTIFACT",
        "prior_rc_status": FROZEN_RC_V1_STATUS,
    }


def cmd_publish_frozen_rc(args: argparse.Namespace) -> int:
    """Assemble client-ready-frozen-rc staging dir (CI artifact upload)."""
    staging = Path(args.staging) if args.staging else None
    source = Path(args.pack_dir) if getattr(args, "pack_dir", None) else None
    result = assemble_client_ready_frozen_rc(
        out_dir=Path(args.out),
        staging_dir=staging,
        source_pack_dir=source,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get("status") == BLOCKED_MISSING_FROZEN_RC:
        return 1
    if result.get("staging_dir"):
        marker = Path(args.out) / "frozen-rc-staging-path.txt"
        marker.write_text(str(result["staging_dir"]) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Client-ready recurring consulting cycle")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Execute full integrated cycle")
    r.add_argument("--dsn", default=DEFAULT_DSN)
    r.add_argument("--out", default=str(DEFAULT_OUT))
    r.add_argument("--e-evidence", default=None)
    r.add_argument("--skip-pack", action="store_true")
    r.add_argument("--contract-limit", type=int, default=50)
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("guard", help="Isolation guard only")
    g.add_argument("--dsn", default=DEFAULT_DSN)
    g.set_defaults(func=cmd_guard)

    v = sub.add_parser(
        "verify-accept",
        help="Validate user-acceptance binding to frozen pack (no pack regen)",
    )
    v.add_argument("--out", default=str(DEFAULT_OUT))
    v.add_argument(
        "--pack-dir",
        default=None,
        help=(
            "Directory with frozen pack members (e.g. extracted "
            f"{FROZEN_RC_ARTIFACT_NAME} artifact). Defaults to <out>/pack."
        ),
    )
    v.set_defaults(func=cmd_verify_accept_binding)

    pub = sub.add_parser(
        "publish-frozen-rc",
        help="Assemble client-ready-frozen-rc for GitHub Actions artifact (no regen)",
    )
    pub.add_argument("--out", default=str(DEFAULT_OUT))
    pub.add_argument("--staging", default=None, help="Staging directory for artifact files")
    pub.add_argument(
        "--pack-dir",
        default=None,
        help="Optional local pack dir with exact frozen binaries",
    )
    pub.set_defaults(func=cmd_publish_frozen_rc)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
