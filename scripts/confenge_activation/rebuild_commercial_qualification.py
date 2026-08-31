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
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any, TextIO

from scripts.commercial_leads.contract_relevance import (
    RULE_VERSION as CONTRACT_RELEVANCE_VERSION,
)
from scripts.commercial_leads.contract_relevance import classify_contract_relevance
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

# One deterministic pass over the canonical contracts view. Commercial
# membership is derived here; no target-fit/current/shadow table participates.
QUALIFICATION_SQL = """
WITH qualifying AS (
    SELECT
        left(regexp_replace(c.supplier_cnpj, '[^0-9]', '', 'g'), 8) AS root8,
        regexp_replace(c.supplier_cnpj, '[^0-9]', '', 'g') AS supplier_cnpj14,
        regexp_replace(COALESCE(c.buyer_cnpj, ''), '[^0-9]', '', 'g') AS buyer_cnpj14,
        c.contrato_id,
        c.objeto,
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
      AND COALESCE(c.is_active, TRUE)
      -- The lead must be the supplier, never the contracting body.
      AND left(regexp_replace(c.supplier_cnpj, '[^0-9]', '', 'g'), 8)
          IS DISTINCT FROM left(regexp_replace(COALESCE(c.buyer_cnpj, ''), '[^0-9]', '', 'g'), 8)
)
SELECT *
FROM qualifying q
WHERE q.qdate IS NOT NULL
      AND q.qdate >= %(window_floor)s
      AND q.qdate <= %(today)s
ORDER BY root8, qdate DESC, contrato_id DESC, supplier_cnpj14
"""


def iter_qualifications(conn: Any, *, now: datetime) -> Iterator[RootQualification]:
    """Yield one qualification per root, deterministically ordered by root."""
    now = now.astimezone(UTC)
    grouped: dict[str, list[dict[str, Any]]] = {}
    with conn.cursor() as cur:
        cur.execute(
            QUALIFICATION_SQL,
            {
                "window_floor": window_floor(now),
                "today": now.date(),
            },
        )
        for row in cur:
            data = dict(row)
            if classify_contract_relevance(data.get("objeto")).status != "PASS":
                continue
            if qualified_until(data["qdate"]) <= now.date():
                continue
            grouped.setdefault(str(data["root8"]), []).append(data)
    for root8 in sorted(grouped):
        yield build_qualification(grouped[root8])


def build_qualification(rows: Any) -> RootQualification:
    """Build a signed qualification from one aggregate row."""
    if isinstance(rows, (list, tuple)):
        candidates = [dict(row) for row in rows]
    else:
        candidates = [dict(rows)]
    if not candidates:
        raise ValueError("commercial qualification cannot be built from an empty contract set")
    candidates.sort(
        key=lambda row: (
            row.get("qdate") or row.get("qualifying_contract_date"),
            str(row.get("contrato_id") or row.get("qualifying_contract_id")),
        ),
        reverse=True,
    )
    data = candidates[0]
    contract_id = str(data.get("contrato_id") or data.get("qualifying_contract_id")).strip()
    contract_date = data.get("qdate") or data.get("qualifying_contract_date")
    q = RootQualification(
        cnpj_root8=str(data["root8"]).strip(),
        target_fit_class=TARGET_CONFIRMED,
        party_role=PARTY_ROLE_SUPPLIER,
        qualifying_contract_id=contract_id,
        qualifying_contract_date=contract_date.isoformat(),
        qualifying_date_field=str(data.get("qfield") or data.get("qualifying_date_field")).strip(),
        qualifying_contract_count=len(candidates),
        qualified_until=qualified_until(contract_date).isoformat(),
        qualification_evidence_reference=f"{EVIDENCE_SOURCE}:{contract_id}",
        provenance=EVIDENCE_SOURCE,
        supplier_cnpj14=str(data.get("supplier_cnpj14") or "").strip(),
        buyer_cnpj14=str(data.get("buyer_cnpj14") or "").strip(),
    )
    return RootQualification(**{**q.__dict__, "qualification_evidence_hash": evidence_hash(q)})


def write_corpus(
    conn: Any,
    out: TextIO,
    *,
    now: datetime,
    qualifications: Sequence[RootQualification] | None = None,
) -> dict[str, Any]:
    """Write the JSONL corpus and return its auditable summary."""
    roots = list(qualifications) if qualifications is not None else list(iter_qualifications(conn, now=now))
    for qualification in roots:
        out.write(json.dumps(qualification.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "policy_version": "COMMERCIAL_AUTHORITY_POLICY/2.0",
        "qualification_window_years": QUALIFICATION_WINDOW_YEARS,
        "window_floor": window_floor(now).isoformat(),
        "generated_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "qualified_root_count": len(roots),
        "qualification_evidence_hash": corpus_hash(roots),
        "provenance": EVIDENCE_SOURCE,
        "contract_relevance_version": CONTRACT_RELEVANCE_VERSION,
        "authority_source": "public.v_contracts_canonical_v2",
        "pncp_freshness_is_transport_gate": False,
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
