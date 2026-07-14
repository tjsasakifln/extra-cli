"""Measure PNCP coverage expansion after config changes.

Compares entity coverage before and after running a PNCP full crawl.
Generates a report in docs/epic-coverage/pncp-expansion-report.md.

Usage:
    python scripts/coverage/measure_pncp_expansion.py

Requires:
    - psycopg2
    - LOCAL_DATALAKE_DSN env var (default: postgresql://postgres@127.0.0.1:54399/postgres, configure password via env)
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psycopg2

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@127.0.0.1:54399/postgres")


def count_covered(source: str = "pncp") -> int:
    """Count distinct entities covered by a given source."""
    conn = psycopg2.connect(DSN, connect_timeout=10)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(DISTINCT entity_id)
        FROM entity_coverage
        WHERE is_covered = TRUE AND source = %s
        """,
        (source,),
    )
    result = cur.fetchone()[0]
    conn.close()
    return result


def measure() -> int:
    """Run crawl and measure coverage gain.

    Returns:
        Delta (after - before) of covered entities.
    """
    before = count_covered()
    print(f"[{datetime.now().isoformat()}] Entes cobertos PNCP antes: {before}")

    # Executar crawl full
    result = subprocess.run(
        [sys.executable, "scripts/crawl/monitor.py", "--source", "pncp", "--mode", "full"],
        capture_output=True,
        text=True,
        timeout=7200,
    )
    print(f"Return code: {result.returncode}")
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[:500]}")
    if result.stdout:
        # Print last 20 lines of stdout
        lines = result.stdout.strip().split("\n")
        print("\n".join(lines[-20:]))

    after = count_covered()
    delta = after - before
    print(f"[{datetime.now().isoformat()}] Entes cobertos PNCP depois: {after}")
    print(f"Ganho: +{delta} entidades")

    # Ensure docs directory exists
    report_dir = _PROJECT_ROOT / "docs" / "epic-coverage"
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_dir / "pncp-expansion-report.md"
    with open(report_path, "w") as f:
        f.write(
            f"""# PNCP v3 Coverage Expansion Report

**Data:** {datetime.now().isoformat()}
**Baseline:** {before} entes cobertos
**Resultado:** {after} entes cobertos
**Ganho:** +{delta} entidades ({"+" if delta > 0 else ""}{round(100 * delta / before, 1) if before > 0 else "N/A"}%)

## Details
- Crawl exit code: {result.returncode}
- Rate limits: `grep -c '429' logs/crawl-pncp-*.log || echo '0'`
"""
        )

    # Generate coverage report via monitor
    print("\n--- Coverage Report ---")
    report_result = subprocess.run(
        [sys.executable, "scripts/crawl/monitor.py", "--report-coverage"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if report_result.stdout:
        print(report_result.stdout[-2000:])
    if report_result.stderr:
        print(report_result.stderr[-2000:])

    return delta


if __name__ == "__main__":
    delta = measure()
    target_min = 30
    if delta >= target_min:
        print(f"\nSUCESSO: Ganho de +{delta} entidades (target: +{target_min})")
    else:
        print(f"\nATENCAO: Ganho de +{delta} entidades abaixo do target de +{target_min}")
