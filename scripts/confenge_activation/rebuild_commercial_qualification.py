"""Rebuild the COMMERCIAL_AUTHORITY/2.0 corpus from stored contracting evidence.

The rolling three-year membership is reconstructible from facts the datalake
already holds. This module never calls PNCP: a cutover must not depend on a
fresh crawl, and a stale crawler must not shrink a population that was already
proven.

Emits JSONL, one ``RootQualification`` per qualified CNPJ root, consumed by
``confenge commercial-qualification --corpus``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, TextIO

from scripts.confenge_activation.commercial_authority_v2 import (
    EVIDENCE_SOURCE,
    PARTY_ROLE_SUPPLIER,
    QUALIFICATION_WINDOW_YEARS,
    RootQualification,
    corpus_hash,
    evidence_hash,
    qualified_until,
    window_floor,
)

TARGET_CONFIRMED = "TARGET_CONFIRMED"

# One deterministic pass over the canonical contracts view, restricted to
# TARGET_CONFIRMED engineering companies acting as supplier. The qualifying
# contract is the most recent contracting act inside the window; the count is
# every qualifying contract, so a company stays active while any one holds.
QUALIFICATION_SQL = """
WITH confirmed AS (
    SELECT DISTINCT s.cnpj_raiz AS root8
    FROM confenge_company_sector_current s
    JOIN confenge_target_fit_shadow t USING (company_key)
    WHERE t.shadow_class = %(target_confirmed)s
), qualifying AS (
    SELECT
        left(regexp_replace(c.supplier_cnpj, '[^0-9]', '', 'g'), 8) AS root8,
        c.contrato_id,
        COALESCE(c.data_assinatura, c.data_inicio, c.data_publicacao, c.data_publicacao_fonte)::date AS qdate,
        CASE
            WHEN c.data_assinatura IS NOT NULL THEN 'data_assinatura'
            WHEN c.data_inicio IS NOT NULL THEN 'data_inicio'
            WHEN c.data_publicacao IS NOT NULL THEN 'data_publicacao'
            ELSE 'data_publicacao_fonte'
        END AS qfield
    FROM public.v_contracts_canonical_v2 c
    WHERE c.supplier_cnpj IS NOT NULL
      AND length(regexp_replace(c.supplier_cnpj, '[^0-9]', '', 'g')) = 14
      AND c.contrato_id IS NOT NULL
      -- The lead must be the supplier, never the contracting body.
      AND left(regexp_replace(c.supplier_cnpj, '[^0-9]', '', 'g'), 8)
          IS DISTINCT FROM left(regexp_replace(COALESCE(c.buyer_cnpj, ''), '[^0-9]', '', 'g'), 8)
), in_window AS (
    SELECT q.*
    FROM qualifying q
    JOIN confirmed cf ON cf.root8 = q.root8
    WHERE q.qdate IS NOT NULL
      AND q.qdate >= %(window_floor)s
      AND q.qdate <= %(today)s
)
SELECT
    root8,
    count(*)::int AS qualifying_contract_count,
    (array_agg(contrato_id ORDER BY qdate DESC, contrato_id DESC))[1] AS qualifying_contract_id,
    max(qdate) AS qualifying_contract_date,
    (array_agg(qfield ORDER BY qdate DESC, contrato_id DESC))[1] AS qualifying_date_field
FROM in_window
GROUP BY root8
ORDER BY root8
"""


def iter_qualifications(conn: Any, *, now: datetime) -> Iterator[RootQualification]:
    """Yield one qualification per root, deterministically ordered by root."""
    now = now.astimezone(UTC)
    with conn.cursor() as cur:
        cur.execute(
            QUALIFICATION_SQL,
            {
                "target_confirmed": TARGET_CONFIRMED,
                "window_floor": window_floor(now),
                "today": now.date(),
            },
        )
        for row in cur:
            yield build_qualification(row)


def build_qualification(row: Any) -> RootQualification:
    """Build a signed qualification from one aggregate row."""
    data = dict(row)
    contract_id = str(data["qualifying_contract_id"]).strip()
    contract_date = data["qualifying_contract_date"]
    q = RootQualification(
        cnpj_root8=str(data["root8"]).strip(),
        target_fit_class=TARGET_CONFIRMED,
        party_role=PARTY_ROLE_SUPPLIER,
        qualifying_contract_id=contract_id,
        qualifying_contract_date=contract_date.isoformat(),
        qualifying_date_field=str(data["qualifying_date_field"]).strip(),
        qualifying_contract_count=int(data["qualifying_contract_count"]),
        qualified_until=qualified_until(contract_date).isoformat(),
        qualification_evidence_reference=f"{EVIDENCE_SOURCE}:{contract_id}",
        provenance=EVIDENCE_SOURCE,
    )
    return RootQualification(**{**q.__dict__, "qualification_evidence_hash": evidence_hash(q)})


def write_corpus(conn: Any, out: TextIO, *, now: datetime) -> dict[str, Any]:
    """Write the JSONL corpus and return its auditable summary."""
    roots: list[RootQualification] = []
    for qualification in iter_qualifications(conn, now=now):
        out.write(json.dumps(qualification.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        roots.append(qualification)
    return {
        "policy_version": "COMMERCIAL_AUTHORITY_POLICY/2.0",
        "qualification_window_years": QUALIFICATION_WINDOW_YEARS,
        "window_floor": window_floor(now).isoformat(),
        "generated_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "qualified_root_count": len(roots),
        "qualification_evidence_hash": corpus_hash(roots),
        "provenance": EVIDENCE_SOURCE,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--out", required=True, help="JSONL corpus output path")
    parser.add_argument("--summary", default="", help="optional JSON summary output path")
    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error("--dsn or DATABASE_URL is required")

    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(args.dsn, cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    try:
        now = datetime.now(UTC)
        with open(args.out, "w", encoding="utf-8") as handle:
            summary = write_corpus(conn, handle, now=now)
    finally:
        conn.close()
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
