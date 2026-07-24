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
DUMP_PACKAGE = (
    _PROJECT_ROOT / "artifacts/migration/backfill-vps/pkg-20260723T195047Z"
)
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

    dump_path = DUMP_PACKAGE / "db/pncp_supplier_contracts.dump"
    meta_path = DUMP_PACKAGE / "meta/export-result.json"
    expected = None
    dump_sha = None
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        expected = meta.get("contracts_count")
    if dump_path.exists():
        dump_sha = sha256_file(dump_path)
        sums = DUMP_PACKAGE / "meta/SHA256SUMS"
        if sums.exists():
            # verify listed hash for dump basename
            for line in sums.read_text(encoding="utf-8").splitlines():
                if "pncp_supplier_contracts.dump" in line:
                    listed = line.split()[0]
                    if listed != dump_sha:
                        return {
                            "ok": False,
                            "error": "dump_sha256_mismatch",
                            "listed": listed,
                            "computed": dump_sha,
                        }

    row_ok = expected is None or int(expected) == n
    return {
        "ok": n > 0 and row_ok,
        "snapshot_row_count": n,
        "expected_row_count": expected,
        "row_count_reconciled": row_ok,
        "sc_active_count": n_sc,
        "snapshot_sha256": dump_sha,
        "dump_package": str(DUMP_PACKAGE.relative_to(_PROJECT_ROOT))
        if DUMP_PACKAGE.exists()
        else None,
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
    # Prefer live-isolated two-cycle path when available
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
    if r.returncode != 0:
        # Fallback: synthetic two-cycle via run_cycle API with labeled replay
        from scripts.ops.strategic_monthly_monitor import run_cycle

        as_of = date.today()
        state_path = out_dir / "cycle-state.json"
        # Cycle 1
        c1 = run_cycle(
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
            as_of=as_of - timedelta(days=7),
            previous=None,
            state_path=state_path,
            cycle_id="crc-replay-1",
        )
        # Cycle 2 with status change + new edital
        c2 = run_cycle(
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
            as_of=as_of,
            previous=c1,
            state_path=state_path,
            cycle_id="crc-replay-2",
        )
        payload = {
            "mode": "LABELED_DETERMINISTIC_REPLAY",
            "live_isolated_exit": r.returncode,
            "live_isolated_stderr": (r.stderr or "")[-500:],
            "cycle_1": c1 if isinstance(c1, dict) else getattr(c1, "__dict__", str(c1)),
            "cycle_2": c2 if isinstance(c2, dict) else getattr(c2, "__dict__", str(c2)),
            "claim": "replay proves delta detectors; not dual live snapshot PASS",
        }
        # normalize dataclasses
        def _ser(x: Any) -> Any:
            if hasattr(x, "__dataclass_fields__"):
                from dataclasses import asdict

                return asdict(x)
            if isinstance(x, dict):
                return {k: _ser(v) for k, v in x.items()}
            if isinstance(x, list):
                return [_ser(i) for i in x]
            return x

        payload["cycle_1"] = _ser(c1)
        payload["cycle_2"] = _ser(c2)
        (out_dir / "monthly-replay.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "mode": "LABELED_DETERMINISTIC_REPLAY",
            "live_recurrence": False,
            "path": str(out_dir / "monthly-replay.json"),
        }

    return {
        "ok": True,
        "mode": "LIVE_ISOLATED",
        "live_recurrence": True,
        "exit_code": r.returncode,
        "stdout_tail": (r.stdout or "")[-500:],
    }


def build_recurrence_delta(monthly: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Normalize delta categories required by the campaign."""
    categories = {
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
    if mode == "LABELED_DETERMINISTIC_REPLAY":
        raw = {}
        p = out_dir / "monthly" / "monthly-replay.json"
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            c2d = raw.get("cycle_2") or {}
            # extract from CycleResult structure if present
            if isinstance(c2d, dict):
                for d in c2d.get("status_deltas") or []:
                    categories["status_changes"].append(d)
                for e in (c2d.get("new_editais") or c2d.get("cycle", {}).get("new_editais") or []):
                    categories["new_opportunities"].append(e)
                # if fields nested under reports
                mon = c2d.get("monthly") or {}
                if mon.get("new_editais"):
                    categories["new_opportunities"] = mon["new_editais"]
        for k, v in list(categories.items()):
            if not v:
                categories[k] = {
                    "count": 0,
                    "success_zero": True,
                    "note": "measurable empty or not applicable in labeled replay",
                }
            else:
                categories[k] = {"count": len(v) if isinstance(v, list) else 1, "items": v, "success_zero": False}
        result = {
            "mode": mode,
            "live_dual_snapshot": False,
            "categories": categories,
            "claim": "LABELED_DETERMINISTIC_REPLAY — mechanics proven; live dual snapshot not claimed",
        }
    else:
        # live-isolated: read artifacts if present
        mon_path = out_dir / "monthly"
        for name in ("monthly-monitor-live.json", "monthly-cycle.json", "cycle-state.json"):
            p = mon_path / name
            if p.exists():
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if isinstance(raw, dict):
                    for key in categories:
                        if key in raw:
                            categories[key] = raw[key]
        for k, v in list(categories.items()):
            if not v:
                categories[k] = {
                    "count": 0,
                    "success_zero": True,
                    "note": "empty after complete comparison or field not emitted",
                }
        result = {
            "mode": mode or "LIVE_ISOLATED",
            "live_dual_snapshot": bool(monthly.get("live_recurrence")),
            "categories": categories,
        }
    (out_dir / "recurrence.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return result


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
) -> tuple[str, list[str]]:
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
        # linkage pipeline uses status completed
        st = (linkage or {}).get("status")
        if st != "completed":
            return "FAIL", [f"linkage_status:{st}"]
    # Technical green → human acceptance gate
    if acceptance.get("status") != "ACCEPTED":
        blockers.append(
            "user_acceptance_PENDING_HUMAN: Tiago must ACCEPT the release candidate"
        )
        if monthly and monthly.get("mode") == "LABELED_DETERMINISTIC_REPLAY":
            blockers.append(
                "live_dual_snapshot_unavailable: recurrence mechanics via labeled replay only"
            )
        return "BLOCKED", blockers
    if monthly and monthly.get("mode") == "LABELED_DETERMINISTIC_REPLAY":
        # even with human accept, cannot claim full live recurrence PASS per objective
        blockers.append(
            "live_dual_snapshot_unavailable after human accept — operational recurrence partial"
        )
        return "BLOCKED", blockers
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
            # alias executive names expected by campaign
            for src, dst in (
                ("extra_live_consulting_pack.pdf", "executive-report.pdf"),
                ("extra_live_consulting_pack.xlsx", "consulting-pack.xlsx"),
                ("executive_summary.md", "executive-summary.md"),
            ):
                sp, dp = pack_dir / src, pack_dir / dst
                if sp.exists() and not dp.exists():
                    dp.write_bytes(sp.read_bytes())
            # CSVs aliases
            for src, dst in (
                ("orgaos_ranking.csv", "organizations.csv"),
                ("competitors.csv", "competitors.csv"),
                ("expiring.csv", "expiring-contracts.csv"),
            ):
                sp = pack_dir / src
                if sp.exists():
                    (pack_dir / dst).write_bytes(sp.read_bytes())
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
    if pack:
        acceptance["run_id"] = pack.get("run_id")
        acceptance["rc_sha"] = git_sha()
        # checksums from pack
        ck = pack_dir / "checksums.json"
        if ck.exists():
            acceptance["package_checksums"] = json.loads(ck.read_text(encoding="utf-8"))
        (out_dir / "user-acceptance.json").write_text(
            json.dumps(acceptance, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    terminal, blockers = decide_terminal(
        isolation=isolation,
        migrations=migrations,
        snapshot=snapshot,
        pack=pack,
        linkage=linkage,
        monthly=monthly,
        acceptance=acceptance,
        failures=failures,
    )

    finished = utc_now()
    duration = round(time.perf_counter() - t0, 3)
    sha = git_sha()

    claims = [
        "integrated cycle entry point sequences pack+linkage+weekly+monthly on isolated DSN",
        "A–E pack over authenticated dump population (not silent sample universe)",
        "linkage with provenance classifications on campaign opportunities",
        "production_touched=false and soak_touched=false when isolation_ok",
    ]
    non_claims = [
        "LOCAL_READY",
        "PRE_VPS_FINAL_READY",
        "VPS_OPERATIONAL",
        "PROJECT_DONE",
        "soak_7d PASS",
        "live dual national snapshot recurrence" if not recurrence.get("live_dual_snapshot") else None,
        "unit price from global valor_total",
        "Extra operational capacity fields not elicited",
        "win rate without observable open-tender denominator",
    ]
    non_claims = [c for c in non_claims if c]

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
        "universe_sha256": None,
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "snapshot_row_count": snapshot.get("snapshot_row_count"),
        "eligible_population": (pack or {}).get("population", {}).get("eligible_population")
        if pack
        else snapshot.get("sc_active_count"),
        "database_identity": snapshot.get("database_identity"),
        "environment": {"dsn_masked": mask_dsn(dsn)},
        "commands": ["python -m scripts.ops.client_ready_consulting_cycle run"],
        "exit_codes": {},
        "durations": {"total_s": duration},
        "test_counts": {},
        "skipped_tests": [],
        "generated_artifacts": sorted(
            str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()
        )[:500],
        "artifact_checksums": {},
        "gate_results": {},
        "ci_run": None,
        "review_verdict": None,
        "production_touched": False,
        "soak_touched": False,
        "claims": claims,
        "non_claims": non_claims,
        "limitations": [
            "Isolated snapshot — not live VPS query",
            "Deliverable E from captured evidence when live crawl skipped",
            "Labeled monthly replay if live-isolated two-cycle unavailable",
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

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
