#!/usr/bin/env python3
"""Run PNCP contracts 90-day pilot with structured JSON evidence (K3.2 / NEXT-30D)."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault(
    "DATABASE_URL", "postgresql://test:test@127.0.0.1:5433/pncp_datalake"
)
os.environ.setdefault("LOCAL_DATALAKE_DSN", os.environ["DATABASE_URL"])
os.environ.setdefault("CONTRACTS_FULL_DAYS", "90")


def main() -> int:
    out = _PROJECT_ROOT / "output" / "contracts" / "pilot-90d-next30d.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    report: dict = {
        "run_id": f"contracts-90d-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
        "started_at": datetime.now(UTC).isoformat(),
        "mode": "full",
        "days": int(os.environ.get("CONTRACTS_FULL_DAYS", "90")),
    }
    try:
        from scripts.crawl import contracts_crawler as cc

        if hasattr(cc, "crawl_with_evidence"):
            result = cc.crawl_with_evidence(mode="full")
            report["path"] = "crawl_with_evidence"
            report["total_records"] = getattr(result, "total_records", None)
            report["total_windows_ok"] = getattr(result, "total_windows_ok", None)
            report["total_windows_failed"] = getattr(result, "total_windows_failed", None)
            wins = getattr(result, "windows", None) or []
            report["windows"] = [
                {
                    "start": getattr(w, "window_start", None),
                    "end": getattr(w, "window_end", None),
                    "status": str(getattr(w, "status", None)),
                    "records": getattr(w, "records_fetched", None),
                    "error": getattr(w, "error_message", None),
                }
                for w in wins[:80]
            ]
        else:
            records = cc.crawl(mode="full")
            report["path"] = "crawl"
            report["total_records"] = len(records or [])
        report["status"] = "success"
    except Exception as e:
        report["status"] = "failed"
        report["error"] = f"{type(e).__name__}: {e}"
        report["traceback"] = traceback.format_exc()[-2500:]

    report["duration_s"] = round(time.monotonic() - start, 2)
    report["completed_at"] = datetime.now(UTC).isoformat()

    try:
        import psycopg2

        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM pncp_supplier_contracts")
        report["pncp_supplier_contracts_count"] = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        report["db_count_error"] = str(e)

    # checkpoint presence
    cp_dir = _PROJECT_ROOT / "data" / "contracts_checkpoints"
    if cp_dir.exists():
        report["checkpoint_files"] = [p.name for p in cp_dir.glob("*.json")]

    out.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False)[:4000])
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
