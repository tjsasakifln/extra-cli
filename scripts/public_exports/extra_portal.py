"""Versioned, bounded, read-only projection for the Extra client portal.

The review register contains evidence about execution and physical works.
Raw administrative geography and keywords only discover candidates.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = "confenge.extra-intelligence/v1"
SCOPE = "extra-sc-sao-jose-200/v1"
CENTRE_ZONE = ZoneInfo("America/Sao_Paulo")
MAX_BYTES = 2 * 1024 * 1024
MAX_REVIEWED = 1000
MAX_DISCOVERY = 8000
PNCP = re.compile(r"^(\d{14})-([12])-(\d{1,6})/(20\d{2})$")
FAMILIES = {"edificacoes", "viaria", "saneamento", "especiais", "outras_obras"}

_QUERIES = {
    "notice": """SELECT numero_controle_pncp AS key, objeto AS title, orgao_nome AS buyer,
        orgao_cnpj AS buyer_key, uf AS buyer_uf, municipio AS buyer_city,
        data_abertura AS opens_at, data_encerramento AS closes_at,
        last_status_verified_at AS status_verified_at, status_canonico AS state,
        is_active, source_active, content_hash
        FROM public.opportunity_intel WHERE source = 'pncp'""",
    "contract": """SELECT contrato_id AS key, objeto_contrato AS title, orgao_nome AS buyer,
        orgao_cnpj AS buyer_key, uf AS buyer_uf, municipio AS buyer_city,
        CASE WHEN supplier_id_type = 'CNPJ' THEN fornecedor_nome ELSE NULL END AS contractor,
        data_publicacao AS captured_day, data_publicacao_fonte AS published_on,
        data_fim AS ends_on, source_updated_at AS status_verified_at, source_updated_at,
        status_normalized AS state, is_active, quality_state
        FROM public.pncp_supplier_contracts WHERE source = 'pncp'""",
}
_WINDOW = {
    "notice": " AND ((data_encerramento >= %(start)s AND data_encerramento < %(end)s + interval '1 day')"
              " OR (data_encerramento IS NULL AND data_publicacao >= %(start)s))",
    "contract": " AND data_publicacao >= %(start)s AND data_publicacao < %(end)s + interval '1 day'",
}
_ORDER = {
    "notice": " ORDER BY data_encerramento ASC NULLS LAST, id ASC LIMIT %(limit)s",
    "contract": " ORDER BY data_publicacao DESC LIMIT %(limit)s",
}
_EXACT = {
    "notice": " AND numero_controle_pncp = ANY(%s) LIMIT 1001",
    "contract": " AND contrato_id = ANY(%s) LIMIT 1001",
}
GEO_HINT = r"(\/SC|[-–] *SC|[[:space:]]em[[:space:]]+SC)([[:space:],.;)]|$)"


def default(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("naive timestamps are not evidence")
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def encoded(value):
    return json.dumps(value, default=default, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def clean(value, size):
    if not isinstance(value, str):
        return None
    value = re.sub(r"[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]", " ", value)
    return " ".join(value.split())[:size] or None


def record_fingerprint(row, kind):
    # Geographic and scope review is bound to the persisted record, not to a
    # daily recheck timestamp. Material source updates explicitly invalidate it.
    fields = (
        ("key", "title", "buyer_key", "content_hash", "opens_at", "closes_at") if kind == "notice"
        else ("key", "title", "buyer_key", "contractor", "published_on", "ends_on", "source_updated_at")
    )
    return sha256(encoded({k: row.get(k) for k in fields})).hexdigest()


def official_url(key, kind):
    match = PNCP.fullmatch(key or "")
    if not match or match[2] != ("1" if kind == "notice" else "2"):
        return None
    return f"https://pncp.gov.br/app/{'editais' if kind == 'notice' else 'contratos'}/{match[1]}/{match[4]}/{int(match[3])}"


def parse_register(raw):
    if not isinstance(raw, dict) or raw.get("schema") != "extra-portal-review/v1" or not isinstance(raw.get("reviews"), list):
        raise ValueError("invalid register")
    if len(raw["reviews"]) > MAX_REVIEWED:
        raise ValueError("too many reviewed records")
    reviews = {"notice": {}, "contract": {}}
    for row in raw["reviews"]:
        if not isinstance(row, dict):
            raise ValueError("invalid review row")
        kind, key = row.get("kind"), row.get("key")
        if kind not in reviews or not isinstance(key, str) or not official_url(key, kind) or key in reviews[kind]:
            raise ValueError("invalid or duplicate reviewed identity")
        if not re.fullmatch(r"[a-f0-9]{64}", row.get("fingerprint", "")):
            raise ValueError("invalid review fingerprint")
        if row.get("decision") not in ("verified", "exclude") or not clean(row.get("reviewer"), 100):
            raise ValueError("missing review decision or record")
        if row["decision"] == "exclude" and (not row.get("scopeEvidence") or row.get("reason") not in (
            "not_physical_work", "outside_territory", "not_distinct_record",
        )):
            raise ValueError("unresolved records cannot be excluded")
        reviews[kind][key] = row
    return reviews


def bounded_find(cur, kind, start, end, limit):
    query = _QUERIES[kind] + _WINDOW[kind]
    params = {"start": start, "end": end, "limit": limit + 1, "geo": GEO_HINT}
    cur.execute(query + " AND uf = 'SC'" + _ORDER[kind], params)
    same_state = cur.fetchall()
    # A separate bounded national scan preserves candidates published by entities
    # elsewhere. Administrative state and free text never qualify the location.
    # Only constants selected by an internal kind are composed. All runtime values are bindings.
    cur.execute("SELECT * FROM (" + query + " AND uf IS DISTINCT FROM 'SC'"  # noqa: S608
                + _ORDER[kind] + ") AS hints"
                " WHERE title ILIKE '%%Santa Catarina%%' OR title ~* %(geo)s", params)
    other_regions = cur.fetchall()
    if kind == "contract":
        # Outside-state hints are only sampled in the bounded national slice.
        other_slice_partial = True
    else:
        cur.execute("SELECT count(*) AS total FROM (" + query + " AND uf IS DISTINCT FROM 'SC'"  # noqa: S608
                    + _ORDER[kind] + ") AS scanned", params)
        other_slice_partial = cur.fetchone()["total"] > limit
    return same_state[:limit] + other_regions[:limit], len(same_state) > limit or other_slice_partial


def exact_rows(cur, kind, ids):
    if not ids:
        return []
    cur.execute(_QUERIES[kind] + _EXACT[kind], (list(ids),))
    return cur.fetchall()


def hint(row):
    title = (row.get("title") or "").casefold()
    return bool(re.search(r"\b(obra\w*|constru\w*|reforma\w*|paviment\w*|recape\w*|drenag\w*|amplia\w*|restaur\w*)", title))


def review_projection(row, review, kind):
    url = official_url(row["key"], kind)
    buyer = clean(row.get("buyer"), 230)
    title = clean(row.get("title"), 500)
    buyer_key = row.get("buyer_key")
    if not url or not title or not buyer or not re.fullmatch(r"\d{14}", buyer_key or ""):
        return None
    if review.get("decision") != "verified" or review.get("family") not in FAMILIES or review.get("physicalWork") is not True:
        return None
    if kind == "contract" and (row.get("quality_state") != "VALID" or row.get("published_on") is None):
        return None
    # The consumer validates the structured evidence and all sites, and exposes
    # only its public-document URL and locator. The reviewer never reaches it.
    result = {
        "kind": kind, "key": kind + ":" + row["key"].replace("/", ":"), "officialUrl": url,
        "buyer": buyer, "buyerKey": buyer_key, "title": title, "family": review["family"],
        "physicalWork": True, "scopeEvidence": review.get("scopeEvidence"),
        "execution": review.get("execution"),
    }
    if kind == "notice":
        result["notice"] = {
            "state": "open" if row.get("is_active") and row.get("source_active") and row.get("state") == "open" else "unconfirmed",
            "opensAt": row.get("opens_at"), "closesAt": row.get("closes_at"),
            "statusVerifiedAt": row.get("status_verified_at"), "evidence": review.get("statusEvidence"),
            "amount": review.get("amount"), "firstCheck": clean(review.get("firstCheck"), 240),
        }
    else:
        result["contract"] = {
            "publishedOn": row["published_on"], "contractor": clean(row.get("contractor"), 230),
            "state": "active_proven" if row.get("is_active") and row.get("state") == "ACTIVE_PROVEN" else "history",
            "endsOn": row.get("ends_on"), "statusVerifiedAt": row.get("status_verified_at"),
            "endConflict": review.get("endConflict"), "endEvidence": review.get("endEvidence"),
            "amount": review.get("amount"), "comparison": clean(review.get("comparison"), 240),
        }
    return result


def assess_scan(rows, reviews, kind, exact):
    by_key: dict[str, list] = {}
    for row in exact:
        by_key.setdefault(row["key"], []).append(row)
    status = {}
    records = []
    for key, review in reviews.items():
        rowset = by_key.get(key, [])
        if len(rowset) != 1:
            status[key] = "identity_unresolved"
            continue
        row = rowset[0]
        current = record_fingerprint(row, kind)
        if review["fingerprint"] != current:
            status[key] = "source_changed"
            continue
        if review["decision"] == "exclude":
            status[key] = "excluded_with_review"
            continue
        ready = review_projection(row, review, kind)
        status[key] = "reviewed" if ready else "missing_source_fields"
        if ready:
            records.append(ready)
    controls = {"reviewed", "excluded_with_review"}
    pending = []
    for row in rows:
        marker = status.get(row["key"], "needs_review")
        if marker not in controls:
            pending.append({
                "kind": kind, "key": row["key"], "reason": marker,
                "fingerprint": record_fingerprint(row, kind),
                "officialUrl": official_url(row["key"], kind),
                "title": clean(row.get("title"), 500),
                "buyerAreaHint": clean(row.get("buyer_city"), 120),
                "workHint": hint(row),
            })
    unreviewed = len(pending)
    pending.sort(key=lambda row: not row["workHint"])
    return records, unreviewed, pending


def collect(conn, reviews, *, window_days=365, contract_offset=0, limit=MAX_DISCOVERY):
    from psycopg2.extras import RealDictCursor

    conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SET LOCAL statement_timeout = '25s'")
        cur.execute("SET LOCAL lock_timeout = '500ms'")
        cur.execute("SET LOCAL TIME ZONE 'America/Sao_Paulo'")
        cur.execute("SELECT transaction_timestamp() AS cut")
        cut = cur.fetchone()["cut"]
        today = cut.astimezone(CENTRE_ZONE).date()
        windows = {
            "notice": (today - timedelta(days=14), today + timedelta(days=90)),
            "contract": (today - timedelta(days=window_days + contract_offset), today - timedelta(days=contract_offset)),
        }
        coverage = {}
        records = []
        pending = {}
        for kind in ("notice", "contract"):
            start, end = windows[kind]
            rows, truncated = bounded_find(cur, kind, start, end, limit)
            exact = exact_rows(cur, kind, reviews[kind])
            ready, unreviewed, unchecked = assess_scan(rows, reviews[kind], kind, exact)
            coverage[kind + "s"] = {
                "scanned": len(rows), "unreviewed": unreviewed, "truncated": truncated,
                "windowStart": start, "windowEnd": end,
            }
            records.extend(ready)
            pending[kind] = unchecked
    payload = {
        "schema": SCHEMA, "scope": SCOPE, "producer": "extra-cli", "mode": "OFFICIAL_LIVE",
        "sourceCut": cut, "generatedAt": datetime.now(UTC), "coverage": coverage, "records": records,
    }
    return payload, pending


def load_register(path):
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("review register too large")
    return parse_register(json.loads(raw))


def write_snapshot(path, payload):
    content = encoded(payload)
    if len(content) > MAX_BYTES:
        raise ValueError("projection exceeded byte budget")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".extra-portal-", delete=False) as fp:
        staging = Path(fp.name)
        try:
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())
            os.fchmod(fp.fileno(), 0o440)
            staging.replace(path)
        finally:
            staging.unlink(missing_ok=True)


def main(argv=None):
    from psycopg2 import Error, connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--output", type=Path)
    target.add_argument("--review-queue", choices=["notice", "contract"])
    target.add_argument("--inspect-id")
    parser.add_argument("--contract-window-days", type=int, default=365)
    parser.add_argument("--contract-offset-days", type=int, default=0)
    parser.add_argument("--queue-offset", type=int, default=0)
    parser.add_argument("--queue-size", type=int, default=40)
    args = parser.parse_args(argv)
    if not 0 <= args.queue_offset <= MAX_DISCOVERY or not 1 <= args.queue_size <= 100:
        parser.error("invalid review range")
    if not 1 <= args.contract_window_days <= 730 or not 0 <= args.contract_offset_days <= 1825:
        parser.error("invalid historical window")
    if args.output and (args.contract_window_days != 365 or args.contract_offset_days):
        parser.error("the production window is fixed")
    try:
        reviews = load_register(args.register)
        # Existing libpq peer authentication. No authenticated web client or DSN
        # credential is given to the website or written to the projection.
        with closing(connect(dbname="pncp_datalake", host="/var/run/postgresql", connect_timeout=4)) as conn:
            if args.inspect_id:
                identity = PNCP.fullmatch(args.inspect_id)
                if not identity:
                    raise ValueError("invalid inspection identity")
                kind = "notice" if identity[2] == "1" else "contract"
                from psycopg2.extras import RealDictCursor

                conn.set_session(readonly=True)
                with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                    exact = exact_rows(cur, kind, [args.inspect_id])
                if len(exact) != 1:
                    raise ValueError("identity not unique in the persisted source")
                sys.stdout.buffer.write(encoded({
                    "kind": kind, "key": args.inspect_id,
                    "fingerprint": record_fingerprint(exact[0], kind),
                    "officialUrl": official_url(args.inspect_id, kind),
                    "title": clean(exact[0]["title"], 500),
                }) + b"\n")
                return 0
            payload, pending = collect(conn, reviews, window_days=args.contract_window_days,
                                       contract_offset=args.contract_offset_days)
        if args.output:
            write_snapshot(args.output, payload)
            print(json.dumps({"records": len(payload["records"]), "coverage": payload["coverage"]}, default=default))
        else:
            sys.stdout.buffer.write(encoded(pending[args.review_queue][args.queue_offset:args.queue_offset + args.queue_size]) + b"\n")
        return 0
    except (Error, OSError, TypeError, ValueError) as exc:
        # Do not emit SQL values, source text or credentials in systemd logs.
        print(f"extra_portal_projection_failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
